"""
FastAPI backend for Stock Monitor (DipSense).
Data is served from SQLite (stock_data.db).
A background APScheduler refreshes stocks one-by-one every 15 minutes.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import threading

import scheduler
from data import store

app = FastAPI(title="DipSense API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKS_FILE = os.path.join(BASE_DIR, "stocks.json")


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    store.init_db()          # create table if needed
    scheduler.start(run_now=True)   # start APScheduler + immediate first pass


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.stop()


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_stocks() -> list:
    with open(STOCKS_FILE) as f:
        return json.load(f)


def save_stocks(stocks: list):
    with open(STOCKS_FILE, "w") as f:
        json.dump(stocks, f, indent=2)


# ── Models ────────────────────────────────────────────────────────────────────

class StockAdd(BaseModel):
    symbol: str
    name: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/stocks")
def list_stocks():
    """Return raw watchlist from stocks.json."""
    return load_stocks()


@app.post("/api/stocks", status_code=201)
def add_stock(stock: StockAdd):
    stocks = load_stocks()
    symbol = stock.symbol.upper().strip()
    name = stock.name.strip()

    if any(s["symbol"].upper() == symbol for s in stocks):
        raise HTTPException(status_code=409, detail=f"{symbol} already in watchlist")

    entry = {"symbol": symbol, "name": name, "sector": "Other"}
    stocks.append(entry)
    save_stocks(stocks)

    # Immediately kick off a background refresh for the new stock
    threading.Thread(
        target=scheduler.refresh_one,
        args=(symbol, name, "Other"),
        kwargs={"skip_if_fresh": False},
        daemon=True,
    ).start()

    return {"message": f"{symbol} added", "stocks": stocks}


@app.delete("/api/stocks/{symbol}")
def remove_stock(symbol: str):
    stocks = load_stocks()
    symbol = symbol.upper()
    updated = [s for s in stocks if s["symbol"].upper() != symbol]
    if len(updated) == len(stocks):
        raise HTTPException(status_code=404, detail=f"{symbol} not found")
    save_stocks(updated)
    store.delete(symbol)          # remove from SQLite cache too
    return {"message": f"{symbol} removed", "stocks": updated}


@app.get("/api/dashboard")
def dashboard():
    """
    Return all stock analysis results from SQLite — instant, no yfinance call.
    Falls back to a loading placeholder if a stock hasn't been cached yet.
    """
    stocks = load_stocks()
    cached = {r["symbol"]: r for r in store.get_all()}

    result = []
    for s in stocks:
        sym = s["symbol"].upper()
        if sym in cached:
            result.append(cached[sym])
        else:
            # Stock is in watchlist but hasn't been fetched yet
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
    Returns 202 Accepted if data isn't cached yet (refresh in progress).
    """
    result = store.get(symbol.upper())
    if result is None:
        raise HTTPException(
            status_code=202,
            detail=f"{symbol.upper()} not yet cached — refresh in progress"
        )
    return result


@app.get("/api/scheduler/status")
def scheduler_status():
    """Return scheduler state: next run time, what's being fetched now, per-stock freshness."""
    return scheduler.status()


@app.post("/api/scheduler/refresh/{symbol}")
def force_refresh(symbol: str):
    """Manually trigger a refresh for one specific stock."""
    stocks = load_stocks()
    meta = next((s for s in stocks if s["symbol"].upper() == symbol.upper()), None)
    if not meta:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")

    threading.Thread(
        target=scheduler.refresh_one,
        args=(meta["symbol"], meta.get("name", meta["symbol"]), meta.get("sector", "Other")),
        kwargs={"skip_if_fresh": False},
        daemon=True,
    ).start()
    return {"message": f"Refresh triggered for {symbol.upper()}"}


@app.get("/health")
def health():
    return {"status": "ok", "scheduler": scheduler.status()["running"]}
