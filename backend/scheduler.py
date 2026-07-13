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
import queue
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


# ── Single-worker refresh queue ──────────────────────────────────────────────
#
# All Playwright fetches funnel through ONE dedicated OS thread. The sync
# Playwright API pins its greenlet event loop to whichever thread first called
# sync_playwright().start(); any subsequent call from a different thread
# raises "cannot switch to a different thread (which happens to have exited)".
# Serializing here guarantees the browser singleton in fetcher._get_browser()
# is always accessed from the same thread. See issue #005.
#
# Queue payload: (symbol, name, sector, skip_if_fresh) tuple, or None sentinel
# to signal worker shutdown.
_refresh_queue: "queue.Queue[tuple | None]" = queue.Queue()
_refresh_worker: threading.Thread | None = None


def _refresh_worker_loop():
    """Consume jobs from `_refresh_queue` sequentially until a None sentinel arrives."""
    while True:
        item = _refresh_queue.get()
        if item is None:
            break
        symbol, name, sector, skip_if_fresh = item
        try:
            _do_refresh_one(symbol, name, sector, skip_if_fresh=skip_if_fresh)
        except Exception as e:
            # A single bad job must never kill the worker.
            _log("ERROR", f"Worker exception: {type(e).__name__}: {e}", symbol)
        # Polite delay between fetches lives here (formerly in refresh_all),
        # so both scheduled and ad-hoc refreshes are equally polite to upstream.
        time.sleep(random.uniform(*INTER_STOCK_DELAY))


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
    """
    Enqueue a refresh job for `symbol`. Returns immediately.

    All Playwright work runs on the dedicated `_refresh_worker` thread so the
    browser singleton stays pinned to one OS thread for its whole life — see
    #005 for why cross-thread calls into sync Playwright are fatal.
    """
    _refresh_queue.put((symbol, name, sector, skip_if_fresh))
    _log("INFO", f"Queued refresh for {symbol}", symbol)


def refresh_all():
    """Enqueue every active watchlist stock. The worker processes them one-by-one."""
    stocks = store.watchlist_get_all()
    for s in stocks:
        _refresh_queue.put(
            (s["symbol"], s.get("name", s["symbol"]), s.get("sector", "Other"), False)
        )
    _log("INFO", f"⟳ Queued {len(stocks)} stocks for refresh")


# ── Singleton scheduler ───────────────────────────────────────────────────────

_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def start(run_now: bool = False):
    """
    Start the background scheduler.
    Auto-refresh is disabled — data is refreshed only on manual trigger
    or when a new stock is added via the API.
    """
    global _refresh_worker

    _scheduler.start()
    _log("INFO", "Scheduler started — manual-refresh-only mode")

    if _refresh_worker is None or not _refresh_worker.is_alive():
        _refresh_worker = threading.Thread(
            target=_refresh_worker_loop, name="refresh-worker", daemon=True
        )
        _refresh_worker.start()
        _log("INFO", "Refresh worker started")

    if run_now:
        t = threading.Thread(target=refresh_all, name="initial-refresh", daemon=True)
        t.start()


def stop():
    """Gracefully shut down the worker and the scheduler."""
    global _refresh_worker

    # Signal the worker to drain and exit.
    try:
        _refresh_queue.put(None)
        if _refresh_worker is not None:
            _refresh_worker.join(timeout=2.0)
    except Exception:
        pass
    _refresh_worker = None

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
        "queued": _refresh_queue.qsize(),
        "next_run": next_run,
        "interval_minutes": REFRESH_INTERVAL_MINUTES,
        "total_cached": len(staleness),
        "oldest_data_age_sec": oldest,
        "freshest_data_age_sec": freshest,
        "per_symbol_age_sec": staleness,
        "last_fetch_status": last_fetch_status,
    }
