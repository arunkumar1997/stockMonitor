"""
SQLite persistence layer for Stock Monitor (DipSense).

Tables:
  watchlist
    symbol      TEXT PRIMARY KEY
    name        TEXT
    sector      TEXT
    deleted_at  REAL   -- NULL = active, non-NULL unix timestamp = soft-deleted

  stock_cache
    symbol      TEXT PRIMARY KEY
    name        TEXT
    sector      TEXT
    result_json TEXT   -- full JSON blob from full_analysis()
    updated_at  REAL   -- Unix timestamp of last successful refresh

  app_config
    key         TEXT PRIMARY KEY
    value       TEXT   -- JSON-encoded value (string, number, or list)
    type        TEXT   -- 'str' | 'int' | 'float' | 'json_list'
    label       TEXT   -- Human-readable label for the UI
    description TEXT   -- Tooltip / helper text
    category    TEXT   -- UI section grouping
"""
import sqlite3
import json
import time
import os
import threading
from typing import Optional, List, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "stock_data.db")

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    """Open a connection with WAL mode for concurrent reads."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    with _conn() as conn:
        # Watchlist — source of truth for which stocks are tracked
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol      TEXT PRIMARY KEY,
                name        TEXT NOT NULL DEFAULT '',
                sector      TEXT NOT NULL DEFAULT 'Other',
                deleted_at  REAL           -- NULL = active
            )
        """)
        # Analysis cache — results from yfinance / analysis pipeline
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_cache (
                symbol      TEXT PRIMARY KEY,
                name        TEXT NOT NULL DEFAULT '',
                sector      TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)
        # App configuration — all tunable parameters
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'str',
                label       TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                category    TEXT NOT NULL DEFAULT 'General'
            )
        """)
        conn.commit()
    config_seed_defaults()
    print(f"[store] DB ready at {DB_PATH}")


# ── App Config ────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG = [
    # key, default_value, type, label, description, category
    ("negative_keywords",
     json.dumps(["fraud","lawsuit","loss","crash","downgrade","miss","disappoint",
                 "fine","penalty","ban","halt","suspend","recall","deficit",
                 "default","bankrupt","investigation","probe","decline","drop",
                 "plunge","slump","warning","risk","concern","weak","cut",
                 "layoff","resign","exit","overvalue","bubble",
                 "inflation","recession","slowdown","bearish",
                 "debt","liabilit","breach","hack","leak","sanction"]),
     "json_list", "Negative Keywords",
     "Words that push sentiment toward negative. Case-insensitive substring match.",
     "News & Sentiment"),

    ("positive_keywords",
     json.dumps(["beat","surge","record","profit","growth","strong","upgrade",
                 "buy","bullish","outperform","raise","dividend","expand",
                 "partnership","acquire","launch","win","award","breakout"]),
     "json_list", "Positive Keywords",
     "Words that push sentiment toward positive.",
     "News & Sentiment"),

    ("avoid_news_threshold", "0.55", "float", "AVOID Signal Threshold",
     "News negativity score (0–1) above which the signal becomes AVOID.",
     "News & Sentiment"),

    ("negative_headline_threshold", "0.45", "float", "Negative Headline Threshold",
     "Per-headline score above which a headline is flagged as negative.",
     "News & Sentiment"),

    ("news_cache_ttl", "600", "int", "News Cache TTL (seconds)",
     "How long to cache news results before re-fetching.",
     "News & Sentiment"),

    ("dip_window", "20", "int", "Dip Window (days)",
     "Number of recent trading days used to find the recent high for dip calculation.",
     "Dip Detection"),

    ("dip_threshold", "5.0", "float", "Moderate Dip Threshold (%)",
     "Minimum % drop from recent high to be classified as a moderate dip.",
     "Dip Detection"),

    ("buy_dip_pct", "3.0", "float", "BUY Signal Min Dip (%)",
     "Minimum dip % required to generate a BUY signal.",
     "Dip Detection"),

    ("buy_small_dip_min", "1.0", "float", "BUY SMALL Min Dip (%)",
     "Lower bound of dip range for BUY SMALL signal.",
     "Dip Detection"),

    ("buy_small_dip_max", "3.0", "float", "BUY SMALL Max Dip (%)",
     "Upper bound of dip range for BUY SMALL signal.",
     "Dip Detection"),

    ("rsi_oversold", "35", "int", "RSI Oversold Threshold",
     "RSI below this triggers the 'oversold' buy boost.",
     "Technical Analysis"),

    ("rsi_overbought", "65", "int", "RSI Overbought Threshold",
     "RSI above this triggers the 'overbought' warning.",
     "Technical Analysis"),

    ("volume_spike_ratio", "1.5", "float", "Volume Spike Ratio",
     "Volume ratio (latest / 20-day avg) above which a volume spike is detected.",
     "Technical Analysis"),

    ("sparkline_days", "30", "int", "Sparkline Days",
     "Number of days of closing price shown in the sparkline chart.",
     "Technical Analysis"),

    ("history_period", "6mo", "str", "History Period",
     "yfinance period for OHLCV download. Options: 1mo, 3mo, 6mo, 1y, 2y.",
     "Technical Analysis"),

    # ── Fundamental analysis thresholds ──────────────────────────────────────
    ("pe_overvalued", "40", "float", "P/E Overvalued Threshold",
     "Trailing P/E ratio above which a stock is flagged as overvalued.",
     "Fundamental Analysis"),

    ("pe_undervalued", "15", "float", "P/E Undervalued Threshold",
     "Trailing P/E ratio below which a stock is flagged as potentially undervalued.",
     "Fundamental Analysis"),

    ("high_debt_equity", "1.5", "float", "High Debt/Equity Threshold",
     "Debt-to-equity ratio above which a high-leverage warning is raised.",
     "Fundamental Analysis"),

    ("ev_ebitda_stretched", "25", "float", "EV/EBITDA Stretched Threshold",
     "EV/EBITDA multiple above which the enterprise valuation is considered stretched.",
     "Fundamental Analysis"),
]


def config_seed_defaults():
    """Insert default config rows. Uses INSERT OR IGNORE so existing values are never overwritten."""
    with _lock:
        with _conn() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO app_config (key, value, type, label, description, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, _DEFAULT_CONFIG)
            conn.commit()


def config_get(key: str):
    """Return a config value, decoded to its native Python type."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT value, type FROM app_config WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    return _decode_config(row["value"], row["type"])


def _decode_config(raw: str, typ: str):
    if typ == "int":
        return int(raw)
    if typ == "float":
        return float(raw)
    if typ == "json_list":
        return json.loads(raw)
    return raw  # str


def config_set(key: str, value) -> bool:
    """Update a config value. Returns False if key doesn't exist."""
    with _lock:
        with _conn() as conn:
            row = conn.execute(
                "SELECT type FROM app_config WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return False
            typ = row["type"]
            if typ == "json_list":
                raw = json.dumps(value)
            else:
                raw = str(value)
            conn.execute(
                "UPDATE app_config SET value = ? WHERE key = ?", (raw, key)
            )
            conn.commit()
    return True


def config_get_all() -> List[Dict]:
    """Return all config rows as dicts with decoded value."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT key, value, type, label, description, category FROM app_config ORDER BY category, key"
        ).fetchall()
    result = []
    for r in rows:
        result.append({
            "key": r["key"],
            "value": _decode_config(r["value"], r["type"]),
            "type": r["type"],
            "label": r["label"],
            "description": r["description"],
            "category": r["category"],
        })
    return result



# ── Watchlist CRUD ────────────────────────────────────────────────────────────

def watchlist_add(symbol: str, name: str, sector: str = "Other"):
    """Insert a new stock into the watchlist (or un-delete if it was soft-deleted)."""
    sym = symbol.upper().strip()
    with _lock:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO watchlist (symbol, name, sector, deleted_at)
                VALUES (?, ?, ?, NULL)
                ON CONFLICT(symbol) DO UPDATE SET
                    name       = excluded.name,
                    sector     = excluded.sector,
                    deleted_at = NULL
            """, (sym, name, sector))
            conn.commit()


def watchlist_exists(symbol: str) -> bool:
    """Return True if the symbol exists in the watchlist (active OR deleted)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM watchlist WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
    return row is not None


def watchlist_get_all() -> List[Dict]:
    """Return all active (non-deleted) watchlist entries."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT symbol, name, sector FROM watchlist WHERE deleted_at IS NULL ORDER BY sector, symbol"
        ).fetchall()
    return [dict(r) for r in rows]


def watchlist_get_deleted() -> List[Dict]:
    """Return all soft-deleted watchlist entries."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT symbol, name, sector, deleted_at FROM watchlist WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def watchlist_soft_delete(symbol: str):
    """Soft-delete a stock — sets deleted_at timestamp, keeps row in DB."""
    with _lock:
        with _conn() as conn:
            conn.execute(
                "UPDATE watchlist SET deleted_at = ? WHERE symbol = ?",
                (time.time(), symbol.upper())
            )
            conn.commit()


def watchlist_restore(symbol: str):
    """Restore a soft-deleted stock — clears deleted_at."""
    with _lock:
        with _conn() as conn:
            conn.execute(
                "UPDATE watchlist SET deleted_at = NULL WHERE symbol = ?",
                (symbol.upper(),)
            )
            conn.commit()


def watchlist_purge(symbol: str):
    """Hard-delete a stock from both watchlist and cache."""
    sym = symbol.upper()
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM watchlist WHERE symbol = ?", (sym,))
            conn.execute("DELETE FROM stock_cache WHERE symbol = ?", (sym,))
            conn.commit()


# ── Stock Cache CRUD ──────────────────────────────────────────────────────────

def upsert(symbol: str, name: str, sector: str, result: dict):
    """Insert or replace a stock's full analysis result."""
    with _lock:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO stock_cache (symbol, name, sector, result_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name        = excluded.name,
                    sector      = excluded.sector,
                    result_json = excluded.result_json,
                    updated_at  = excluded.updated_at
            """, (
                symbol.upper(),
                name,
                sector,
                json.dumps(result),
                time.time(),
            ))
            conn.commit()


def get(symbol: str) -> Optional[Dict]:
    """Return the stored result for a symbol, or None if not found."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT result_json, updated_at FROM stock_cache WHERE symbol = ?",
            (symbol.upper(),)
        ).fetchone()
    if not row:
        return None
    result = json.loads(row["result_json"])
    result["_updated_at"] = row["updated_at"]
    return result


def get_all() -> List[Dict]:
    """Return all cached results for active watchlist stocks, ordered by sector then symbol."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT result_json, updated_at FROM stock_cache ORDER BY sector, symbol"
        ).fetchall()
    out = []
    for row in rows:
        result = json.loads(row["result_json"])
        result["_updated_at"] = row["updated_at"]
        out.append(result)
    return out


def delete(symbol: str):
    """Remove a stock from the cache only (used internally)."""
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM stock_cache WHERE symbol = ?", (symbol.upper(),))
            conn.commit()


def get_staleness() -> Dict[str, float]:
    """Return symbol → age_in_seconds for all cached entries."""
    now = time.time()
    with _conn() as conn:
        rows = conn.execute("SELECT symbol, updated_at FROM stock_cache").fetchall()
    return {row["symbol"]: round(now - row["updated_at"], 1) for row in rows}
