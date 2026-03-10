"""
SQLite persistence layer for stock analysis results.
Uses stdlib sqlite3 — no extra dependencies.

Table: stock_cache
  symbol      TEXT PRIMARY KEY
  name        TEXT
  sector      TEXT
  result_json TEXT   -- full JSON blob from full_analysis()
  updated_at  REAL   -- Unix timestamp of last successful refresh
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
    """Create table if it doesn't exist. Safe to call multiple times."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_cache (
                symbol      TEXT PRIMARY KEY,
                name        TEXT NOT NULL DEFAULT '',
                sector      TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)
        conn.commit()
    print(f"[store] DB ready at {DB_PATH}")


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
    """Return all stored results, ordered by sector then symbol."""
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
    """Remove a stock from the cache."""
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
