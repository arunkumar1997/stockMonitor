"""
seed_db.py — One-time migration from stocks.json → SQLite watchlist table.

Usage:
    cd backend
    python seed_db.py

Safe to run multiple times — uses INSERT OR IGNORE so existing rows are skipped.
Stocks with "is_deleted": true in the JSON are seeded as soft-deleted.
"""
import json
import os
import sys
import sqlite3
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCKS_JSON = os.path.join(BASE_DIR, "stocks.json")
DB_PATH = os.path.join(BASE_DIR, "stock_data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def ensure_watchlist_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            symbol      TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            sector      TEXT NOT NULL DEFAULT 'Other',
            deleted_at  REAL
        )
    """)
    conn.commit()


def seed():
    if not os.path.exists(STOCKS_JSON):
        print(f"[seed] stocks.json not found at {STOCKS_JSON} — nothing to migrate.")
        sys.exit(0)

    with open(STOCKS_JSON) as f:
        stocks = json.load(f)

    conn = get_conn()
    ensure_watchlist_table(conn)

    inserted = 0
    skipped = 0
    deleted_count = 0

    for s in stocks:
        symbol = s.get("symbol", "").upper().strip()
        name = s.get("name", symbol)
        sector = s.get("sector", "Other")
        is_deleted = s.get("is_deleted", False)
        deleted_at = time.time() if is_deleted else None

        # INSERT OR IGNORE — won't overwrite existing rows
        cur = conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, name, sector, deleted_at) VALUES (?, ?, ?, ?)",
            (symbol, name, sector, deleted_at)
        )
        if cur.rowcount == 1:
            inserted += 1
            if is_deleted:
                deleted_count += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    print(f"[seed] Done!")
    print(f"  ✅ Inserted : {inserted} stocks ({deleted_count} as soft-deleted)")
    print(f"  ⏭  Skipped  : {skipped} (already in DB)")
    print(f"  📄 Source   : {STOCKS_JSON}")
    print(f"  🗄  DB       : {DB_PATH}")

    if inserted > 0:
        print("\n  You can now safely archive / delete stocks.json.")


if __name__ == "__main__":
    seed()
