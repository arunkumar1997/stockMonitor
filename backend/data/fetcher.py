"""
Stock data fetcher using yfinance.
Fetches ONE symbol at a time — called by the background scheduler,
never called directly from API request handlers.
"""
import time
import yfinance as yf
import pandas as pd
from typing import Optional, Dict


def get_history(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """
    Download OHLCV history for a single symbol.
    Returns a clean DataFrame or None on failure.
    """
    try:
        df = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            print(f"[fetcher] Empty result for {symbol}")
            return None

        # Flatten MultiIndex columns if present (single-ticker download)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[keep].dropna()
        return df if not df.empty else None

    except Exception as e:
        print(f"[fetcher] Download error {symbol}: {e}")
        return None


def get_info(symbol: str, df: Optional[pd.DataFrame] = None) -> Dict:
    """
    Derive price info from the downloaded history DataFrame.
    Falls back to yf.fast_info only if df is unavailable.
    """
    if df is not None and len(df) >= 2:
        current = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        high52 = float(df["High"].max())
        low52 = float(df["Low"].min())
        return {
            "symbol": symbol,
            "longName": symbol,      # overridden by stocks.json name in scheduler
            "currentPrice": current,
            "previousClose": prev,
            "currency": "INR",
            "fiftyTwoWeekHigh": high52,
            "fiftyTwoWeekLow": low52,
            "marketCap": 0,
            "sector": "",
        }

    # Fallback: lightweight fast_info
    try:
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info
        return {
            "symbol": symbol,
            "longName": symbol,
            "currentPrice": float(getattr(fi, "last_price", 0) or 0),
            "previousClose": float(getattr(fi, "previous_close", 0) or 0),
            "currency": getattr(fi, "currency", "INR") or "INR",
            "fiftyTwoWeekHigh": float(getattr(fi, "year_high", 0) or 0),
            "fiftyTwoWeekLow": float(getattr(fi, "year_low", 0) or 0),
            "marketCap": float(getattr(fi, "market_cap", 0) or 0),
            "sector": "",
        }
    except Exception as e:
        print(f"[fetcher] fast_info fallback error {symbol}: {e}")
        return {
            "symbol": symbol, "longName": symbol,
            "currentPrice": 0, "previousClose": 0,
            "currency": "INR", "fiftyTwoWeekHigh": 0,
            "fiftyTwoWeekLow": 0, "marketCap": 0, "sector": "",
        }
