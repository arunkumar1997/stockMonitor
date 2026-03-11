"""
Stock data fetcher using yfinance.
Fetches ONE symbol at a time — called by the background scheduler,
never called directly from API request handlers.
"""
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
        prev    = float(df["Close"].iloc[-2])
        high52  = float(df["High"].max())
        low52   = float(df["Low"].min())
        return {
            "symbol": symbol,
            "longName": symbol,      # overridden by watchlist name in scheduler
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


def _safe_float(val) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    try:
        if val is None:
            return None
        f = float(val)
        return round(f, 4) if f == f else None   # NaN check
    except (TypeError, ValueError):
        return None


def get_fundamentals(symbol: str) -> Dict:
    """
    Fetch fundamental data for a symbol via yf.Ticker().info.
    Returns a dict — all values may be None if unavailable (common for Indian stocks).
    """
    empty = {
        "trailing_pe": None, "forward_pe": None, "peg_ratio": None,
        "price_to_book": None, "ev_to_ebitda": None,
        "trailing_eps": None, "forward_eps": None,
        "free_cashflow": None, "operating_cashflow": None,
        "debt_to_equity": None,
        "profit_margin": None, "revenue_growth": None, "earnings_growth": None,
        "dividend_yield": None, "return_on_equity": None,
        "market_cap": None,
    }
    try:
        info = yf.Ticker(symbol).info
        if not info:
            return empty

        result = {
            "trailing_pe":        _safe_float(info.get("trailingPE")),
            "forward_pe":         _safe_float(info.get("forwardPE")),
            "peg_ratio":          _safe_float(info.get("pegRatio")),
            "price_to_book":      _safe_float(info.get("priceToBook")),
            "ev_to_ebitda":       _safe_float(info.get("enterpriseToEbitda")),
            "trailing_eps":       _safe_float(info.get("trailingEps")),
            "forward_eps":        _safe_float(info.get("forwardEps")),
            "free_cashflow":      _safe_float(info.get("freeCashflow")),
            "operating_cashflow": _safe_float(info.get("operatingCashflow")),
            "debt_to_equity":     _safe_float(info.get("debtToEquity")),
            "profit_margin":      _safe_float(info.get("profitMargins")),
            "revenue_growth":     _safe_float(info.get("revenueGrowth")),
            "earnings_growth":    _safe_float(info.get("earningsGrowth")),
            "dividend_yield":     _safe_float(info.get("dividendYield")),
            "return_on_equity":   _safe_float(info.get("returnOnEquity")),
            "market_cap":         _safe_float(info.get("marketCap")),
        }
        print(f"[fetcher] Fundamentals fetched for {symbol} (PE={result['trailing_pe']})")
        return result

    except Exception as e:
        print(f"[fetcher] Fundamentals error for {symbol}: {e}")
        return empty
