"""
FastAPI backend for Stock Monitor (DipSense).
Data is served from SQLite (stock_data.db).
Watchlist is now fully DB-driven — stocks.json is no longer used.
A background APScheduler refreshes stocks one-by-one every 15 minutes.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading

import scheduler
from data import store

app = FastAPI(title="DipSense API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    store.init_db()
    scheduler.start(run_now=False)  # no auto-refresh on start — use manual refresh


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.stop()


# ── Models ────────────────────────────────────────────────────────────────────

class StockAdd(BaseModel):
    symbol: str
    name: str
    sector: str = "Other"


# ── Watchlist Routes ──────────────────────────────────────────────────────────

@app.get("/api/stocks")
def list_stocks():
    """Return all active (non-deleted) watchlist entries."""
    return store.watchlist_get_all()


@app.post("/api/stocks", status_code=201)
def add_stock(stock: StockAdd):
    symbol = stock.symbol.upper().strip()
    name = stock.name.strip()
    sector = stock.sector.strip() or "Other"

    # Check if already active
    active = [s for s in store.watchlist_get_all() if s["symbol"] == symbol]
    if active:
        raise HTTPException(status_code=409, detail=f"{symbol} already in watchlist")

    store.watchlist_add(symbol, name, sector)

    # Immediately kick off a background refresh for the new stock
    threading.Thread(
        target=scheduler.refresh_one,
        args=(symbol, name, sector),
        kwargs={"skip_if_fresh": False},
        daemon=True,
    ).start()

    return {"message": f"{symbol} added", "stocks": store.watchlist_get_all()}


@app.delete("/api/stocks/{symbol}")
def remove_stock(symbol: str):
    """Soft-delete a stock — keeps it in the DB, removes from active dashboard."""
    sym = symbol.upper()
    active = [s for s in store.watchlist_get_all() if s["symbol"] == sym]
    if not active:
        raise HTTPException(status_code=404, detail=f"{sym} not found in active watchlist")

    store.watchlist_soft_delete(sym)
    return {"message": f"{sym} moved to trash", "stocks": store.watchlist_get_all()}


@app.get("/api/stocks/deleted")
def list_deleted_stocks():
    """Return all soft-deleted watchlist entries."""
    return store.watchlist_get_deleted()


@app.post("/api/stocks/{symbol}/restore")
def restore_stock(symbol: str):
    """Restore a soft-deleted stock back to the active watchlist."""
    sym = symbol.upper()
    deleted = [s for s in store.watchlist_get_deleted() if s["symbol"] == sym]
    if not deleted:
        raise HTTPException(status_code=404, detail=f"{sym} not found in trash")

    store.watchlist_restore(sym)

    # Re-queue a refresh so data is fresh on restore
    meta = deleted[0]
    threading.Thread(
        target=scheduler.refresh_one,
        args=(sym, meta.get("name", sym), meta.get("sector", "Other")),
        kwargs={"skip_if_fresh": False},
        daemon=True,
    ).start()

    return {"message": f"{sym} restored", "stocks": store.watchlist_get_all()}


@app.delete("/api/stocks/{symbol}/purge")
def purge_stock(symbol: str):
    """Permanently hard-delete a stock from watchlist and cache."""
    sym = symbol.upper()
    if not store.watchlist_exists(sym):
        raise HTTPException(status_code=404, detail=f"{sym} not found")

    store.watchlist_purge(sym)
    return {"message": f"{sym} permanently deleted"}


# ── Dashboard & Analysis ──────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard():
    """
    Return all stock analysis results from SQLite — instant, no yfinance call.
    Only returns active (non-deleted) watchlist stocks.
    Falls back to a loading placeholder if a stock hasn't been cached yet.
    """
    stocks = store.watchlist_get_all()
    cached = {r["symbol"]: r for r in store.get_all()}

    result = []
    for s in stocks:
        sym = s["symbol"]
        if sym in cached:
            result.append(cached[sym])
        else:
            result.append({
                "symbol": sym,
                "name": s.get("name", sym),
                "sector": s.get("sector", "Other"),
                "current_price": 0,
                "price_change_pct": 0,
                "price_change": 0,
                "sparkline": [],
                "dip": {"is_dip": False, "dip_pct": 0, "severity": "none", "recent_high": 0},
                "resistance_levels": [],
                "support_levels": [],
                "rsi": None,
                "moving_averages": {},
                "signal": {"signal": "WAIT", "confidence": 0, "reasons": ["Data loading…"]},
                "news": {"headlines": [], "negative_score": 0, "sentiment": "Neutral"},
                "_updated_at": None,
            })
    return result


@app.get("/api/analyze/{symbol}")
def analyze_stock(symbol: str):
    """
    Return cached analysis for a single stock.
    Returns 202 Accepted if data isn't cached yet.
    """
    result = store.get(symbol.upper())
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=f"{symbol.upper()} not yet cached — refresh in progress"
        )
    return result


# ── Scheduler ─────────────────────────────────────────────────────────────────

@app.get("/api/scheduler/status")
def scheduler_status():
    """Return scheduler state: next run time, what's being fetched now, per-stock freshness."""
    return scheduler.status()


@app.post("/api/scheduler/refresh/{symbol}")
def force_refresh(symbol: str):
    """Manually trigger a refresh for one specific stock."""
    sym = symbol.upper()
    active = {s["symbol"]: s for s in store.watchlist_get_all()}
    if sym not in active:
        raise HTTPException(status_code=404, detail=f"{sym} not in active watchlist")

    meta = active[sym]
    threading.Thread(
        target=scheduler.refresh_one,
        args=(sym, meta.get("name", sym), meta.get("sector", "Other")),
        kwargs={"skip_if_fresh": False},
        daemon=True,
    ).start()
    return {"message": f"Refresh triggered for {sym}"}


@app.get("/health")
def health():
    return {"status": "ok", "scheduler": scheduler.status()["running"]}


@app.get("/api/logs")
def get_logs(limit: int = 200):
    """Return the last N scheduler log entries (newest first)."""
    return scheduler.get_logs(limit=min(limit, 500))


# ── Config / Settings ──────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    value: object  # str | int | float | list


@app.get("/api/config")
def get_config():
    """Return all config entries grouped by category."""
    entries = store.config_get_all()
    grouped: dict = {}
    for e in entries:
        cat = e["category"]
        grouped.setdefault(cat, []).append(e)
    return grouped


@app.put("/api/config/{key}")
def update_config(key: str, body: ConfigUpdate):
    """Update a single config value by key."""
    ok = store.config_set(key, body.value)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")
    return {"key": key, "value": body.value, "message": "Updated"}
