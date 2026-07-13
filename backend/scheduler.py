"""
Background scheduler for stock data refreshes.
Uses APScheduler BackgroundScheduler — runs in its own thread,
completely separate from the FastAPI event loop.

Jobs:
  refresh_all  — every 15 min, iterates stocks one-by-one
  refresh_one  — on-demand (called when a new stock is added)
"""

import random
import time
import threading
from collections import deque
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from data.fetcher import get_history, get_info, get_fundamentals
from data.analysis import full_analysis
from data.news import get_news
from data import store

REFRESH_INTERVAL_MINUTES = 15
INTER_STOCK_DELAY = (1.5, 3.5)  # random sleep (seconds) between each stock

# ── In-memory log buffer ──────────────────────────────────────────────────────
_log_buffer: deque = deque(maxlen=500)  # last 500 entries
_log_lock = threading.Lock()
_log_seq = 0  # monotonic counter


def _log(level: str, message: str, symbol: str = ""):
    """Append a structured log entry to the in-memory buffer."""
    global _log_seq
    with _log_lock:
        _log_seq += 1
        _log_buffer.append(
            {
                "id": _log_seq,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "level": level,  # INFO | SUCCESS | ERROR | WARN
                "symbol": symbol,
                "message": message,
            }
        )
    tag = {"INFO": "ℹ", "SUCCESS": "✓", "ERROR": "✗", "WARN": "⚠"}.get(level, "·")
    sym = f" [{symbol}]" if symbol else ""
    print(f"[scheduler]{sym} {tag} {message}")


def get_logs(limit: int = 200):
    """Return the most recent `limit` log entries (newest first)."""
    with _log_lock:
        entries = list(_log_buffer)
    return list(reversed(entries))[:limit]


# ── Symbol currently being refreshed ─────────────────────────────────────────
_current_symbol: str = ""
_refresh_lock = threading.Lock()

# Per-symbol last-fetch outcome (guarded by _refresh_lock).
# Shape: { "SYMBOL.NS": {"status": "ok"|"error", "message": str, "ts": ISO-8601} }
_last_fetch_status: dict[str, dict] = {}


def _record_fetch_status(symbol: str, status: str, message: str) -> None:
    """Record the outcome of the most recent refresh for `symbol`."""
    entry = {
        "status": status,
        "message": message,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    with _refresh_lock:
        _last_fetch_status[symbol.upper()] = entry


def _do_refresh_one(symbol: str, name: str, sector: str, *, skip_if_fresh: bool = False):
    """
    Fetch + analyse a single stock and persist to SQLite.
    Called by the scheduler loop and also directly for new stocks.
    """
    global _current_symbol

    if skip_if_fresh:
        staleness = store.get_staleness()
        age = staleness.get(symbol.upper(), 9999)
        if age < REFRESH_INTERVAL_MINUTES * 60:
            _log("INFO", f"Fresh ({age:.0f}s old), skipping", symbol)
            return

    with _refresh_lock:
        _current_symbol = symbol

    _log("INFO", "Starting refresh …", symbol)
    t0 = time.time()
    try:
        from data.analysis import load_config

        cfg = load_config()
        period = cfg.get("history_period", "6mo")

        _log("INFO", f"Fetching {period} OHLCV history …", symbol)
        df = get_history(symbol, period=period)
        if df is None:
            _log("WARN", "No price history returned — skipping", symbol)
            _record_fetch_status(symbol, "error", "No price history returned")
            return
        _log("INFO", f"Got {len(df)} candles", symbol)

        info = get_info(symbol, df)
        info["longName"] = name

        _log("INFO", "Fetching news …", symbol)
        news = get_news(symbol, name)
        neg = news.get("negative_score", 0)
        _log(
            "INFO",
            f"News: {news.get('headline_count', 0)} headlines, neg_score={neg:.2f}",
            symbol,
        )

        _log("INFO", "Fetching fundamentals …", symbol)
        fundamentals = get_fundamentals(symbol)
        pe = fundamentals.get("trailing_pe")
        _log("INFO", f"Fundamentals: PE={pe}", symbol)

        result = full_analysis(
            symbol, df, info, news, cfg=cfg, fundamentals=fundamentals
        )
        result["sector"] = sector

        sig = result.get("signal", {})
        val = result.get("valuation", {})
        elapsed = time.time() - t0
        _log(
            "SUCCESS",
            f"Signal={sig.get('signal','?')} ({sig.get('confidence','?')}%) "
            f"| Valuation={val.get('status','?')} "
            f"| Price={result.get('current_price','?')} "
            f"| Done in {elapsed:.1f}s",
            symbol,
        )
        store.upsert(symbol, name, sector, result)
        _record_fetch_status(
            symbol,
            "ok",
            f"Signal={sig.get('signal','?')} ({sig.get('confidence','?')}%)",
        )

    except Exception as e:
        _log("ERROR", f"{type(e).__name__}: {e}", symbol)
        _record_fetch_status(symbol, "error", f"{type(e).__name__}: {e}")
    finally:
        with _refresh_lock:
            _current_symbol = ""


def refresh_one(symbol: str, name: str, sector: str, *, skip_if_fresh: bool = False):
    """Shim preserved for API compatibility — see _do_refresh_one for the real work."""
    return _do_refresh_one(symbol, name, sector, skip_if_fresh=skip_if_fresh)


def refresh_all():
    """Full pass — iterate every active watchlist stock one-by-one with a polite delay."""
    stocks = store.watchlist_get_all()
    _log("INFO", f"⟳ Starting full refresh — {len(stocks)} stocks")
    for s in stocks:
        symbol = s["symbol"]
        name = s.get("name", symbol)
        sector = s.get("sector", "Other")
        refresh_one(symbol, name, sector, skip_if_fresh=False)
        delay = random.uniform(*INTER_STOCK_DELAY)
        time.sleep(delay)
    _log("INFO", "⟳ Full refresh complete")


# ── Singleton scheduler ───────────────────────────────────────────────────────

_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def start(run_now: bool = False):
    """
    Start the background scheduler.
    Auto-refresh is disabled — data is refreshed only on manual trigger
    or when a new stock is added via the API.
    """
    _scheduler.start()
    _log("INFO", "Scheduler started — manual-refresh-only mode")

    if run_now:
        t = threading.Thread(target=refresh_all, name="initial-refresh", daemon=True)
        t.start()


def stop():
    """Gracefully shut down the scheduler."""
    try:
        _scheduler.shutdown(wait=False)
        _log("INFO", "Scheduler stopped")
    except Exception:
        pass


def status() -> dict:
    """Return status info for the /api/scheduler/status endpoint."""
    job = _scheduler.get_job("refresh_all")
    with _refresh_lock:
        current = _current_symbol

    next_run = None
    if job and job.next_run_time:
        next_run = job.next_run_time.isoformat()

    staleness = store.get_staleness()
    oldest = max(staleness.values(), default=0) if staleness else 0
    freshest = min(staleness.values(), default=0) if staleness else 0

    with _refresh_lock:
        last_fetch_status = dict(_last_fetch_status)

    return {
        "running": _scheduler.running,
        "current_symbol": current,
        "next_run": next_run,
        "interval_minutes": REFRESH_INTERVAL_MINUTES,
        "total_cached": len(staleness),
        "oldest_data_age_sec": oldest,
        "freshest_data_age_sec": freshest,
        "per_symbol_age_sec": staleness,
        "last_fetch_status": last_fetch_status,
    }
