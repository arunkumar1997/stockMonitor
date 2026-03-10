"""
Background scheduler for stock data refreshes.
Uses APScheduler BackgroundScheduler — runs in its own thread,
completely separate from the FastAPI event loop.

Jobs:
  refresh_all  — every 15 min, iterates stocks one-by-one
  refresh_one  — on-demand (called when a new stock is added)
"""
import json
import os
import random
import time
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from data.fetcher import get_history, get_info
from data.analysis import full_analysis
from data.news import get_news
from data import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKS_FILE = os.path.join(BASE_DIR, "stocks.json")

REFRESH_INTERVAL_MINUTES = 15
INTER_STOCK_DELAY = (1.5, 3.5)   # random sleep (seconds) between each stock

# Tracks the symbol currently being refreshed (for status endpoint)
_current_symbol: str = ""
_lock = threading.Lock()


def _load_stocks() -> list:
    try:
        with open(STOCKS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def refresh_one(symbol: str, name: str, sector: str, *, skip_if_fresh: bool = False):
    """
    Fetch + analyse a single stock and persist to SQLite.
    Called by the scheduler loop and also directly for new stocks.
    """
    global _current_symbol

    if skip_if_fresh:
        staleness = store.get_staleness()
        age = staleness.get(symbol.upper(), 9999)
        if age < REFRESH_INTERVAL_MINUTES * 60:
            print(f"[scheduler] {symbol} fresh ({age:.0f}s old), skipping")
            return

    with _lock:
        _current_symbol = symbol

    print(f"[scheduler] Refreshing {symbol} …")
    try:
        df = get_history(symbol)
        info = get_info(symbol, df)
        info["longName"] = name          # override with human-readable name
        news = get_news(symbol, name)
        result = full_analysis(symbol, df, info, news)
        result["sector"] = sector
        store.upsert(symbol, name, sector, result)
        print(f"[scheduler] ✓ {symbol} saved")
    except Exception as e:
        print(f"[scheduler] ✗ {symbol} error: {e}")
    finally:
        with _lock:
            _current_symbol = ""


def refresh_all():
    """Full pass — iterate every stock one-by-one with a polite delay."""
    stocks = _load_stocks()
    print(f"[scheduler] Starting full refresh of {len(stocks)} stocks")
    for s in stocks:
        symbol = s["symbol"]
        name = s.get("name", symbol)
        sector = s.get("sector", "Other")
        refresh_one(symbol, name, sector, skip_if_fresh=False)
        delay = random.uniform(*INTER_STOCK_DELAY)
        time.sleep(delay)
    print(f"[scheduler] Full refresh complete")


# ── Singleton scheduler ───────────────────────────────────────────────────────

_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def start(run_now: bool = True):
    """
    Start the background scheduler.
    If run_now=True, trigger an immediate first pass so the DB is
    populated right away without waiting 15 minutes.
    """
    _scheduler.add_job(
        refresh_all,
        trigger=IntervalTrigger(minutes=REFRESH_INTERVAL_MINUTES),
        id="refresh_all",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    _scheduler.start()
    print(f"[scheduler] Started — interval {REFRESH_INTERVAL_MINUTES} min")

    if run_now:
        # Run in a daemon thread so startup doesn't block
        t = threading.Thread(target=refresh_all, name="initial-refresh", daemon=True)
        t.start()


def stop():
    """Gracefully shut down the scheduler."""
    try:
        _scheduler.shutdown(wait=False)
        print("[scheduler] Stopped")
    except Exception:
        pass


def status() -> dict:
    """Return status info for the /api/scheduler/status endpoint."""
    job = _scheduler.get_job("refresh_all")
    with _lock:
        current = _current_symbol

    next_run = None
    if job and job.next_run_time:
        next_run = job.next_run_time.isoformat()

    staleness = store.get_staleness()
    oldest = max(staleness.values(), default=0) if staleness else 0
    freshest = min(staleness.values(), default=0) if staleness else 0

    return {
        "running": _scheduler.running,
        "current_symbol": current,
        "next_run": next_run,
        "interval_minutes": REFRESH_INTERVAL_MINUTES,
        "total_cached": len(staleness),
        "oldest_data_age_sec": oldest,
        "freshest_data_age_sec": freshest,
        "per_symbol_age_sec": staleness,
    }
