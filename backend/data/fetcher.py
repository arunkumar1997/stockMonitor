"""
Stock data fetcher using Playwright browser scraping (replaces yfinance API).

Uses a headless Chromium browser to scrape Yahoo Finance pages directly,
avoiding YFRateLimitError entirely. A singleton browser instance is reused
across all requests for efficiency.

Data sources:
  - History (OHLCV): Yahoo Finance /history/ page table
  - Info:            Derived from history DataFrame (no extra request)
  - Fundamentals:    Yahoo Finance /key-statistics/ page tables
"""

import time
import random
import threading
import atexit

import pandas as pd
from typing import Optional, Dict


class PlaywrightBrowserMissingError(RuntimeError):
    """Raised when Playwright's Chromium binary is not installed on this machine."""

    pass


# ── Singleton browser management ─────────────────────────────────────────────

_browser = None
_playwright = None
_pw_context = None
_lock = threading.Lock()
_browser_missing_logged = False  # log the "install chromium" hint only once


def _get_browser():
    """Lazily initialise and return a shared Playwright browser instance."""
    global _browser, _playwright, _pw_context
    with _lock:
        if _browser is None or not _browser.is_connected():
            from playwright.sync_api import sync_playwright

            _pw_context = sync_playwright().start()
            try:
                _browser = _pw_context.chromium.launch(headless=True)
            except Exception as e:
                msg = str(e)
                if (
                    "Executable doesn't exist" in msg
                    or "playwright install" in msg.lower()
                ):
                    # Clean up the partially-started context so the next call retries cleanly
                    try:
                        _pw_context.stop()
                    except Exception:
                        pass
                    _pw_context = None
                    raise PlaywrightBrowserMissingError(
                        "Playwright Chromium is not installed. "
                        "Run: python -m playwright install chromium"
                    ) from e
                raise
            print("[fetcher] Playwright browser launched")
        return _browser


def _log_browser_missing_once(err: "PlaywrightBrowserMissingError") -> None:
    """Emit the actionable install hint at most once per process."""
    global _browser_missing_logged
    if not _browser_missing_logged:
        print(f"[fetcher] {err}")
        _browser_missing_logged = True


def _shutdown_browser():
    """Clean up browser on process exit."""
    global _browser, _pw_context
    try:
        if _browser:
            _browser.close()
        if _pw_context:
            _pw_context.stop()
    except Exception:
        pass


atexit.register(_shutdown_browser)


def _new_page():
    """Create a fresh page in the shared browser."""
    browser = _get_browser()
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return ctx.new_page()


def _polite_delay():
    """Small random delay between page loads."""
    time.sleep(random.uniform(0.5, 1.2))


# ── History fetching ─────────────────────────────────────────────────────────


def get_history(symbol: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """
    Scrape OHLCV history from Yahoo Finance's /history/ page.
    Returns a clean DataFrame or None on failure.
    The page typically shows ~250 trading days (~1 year) of data.
    """
    page = None
    try:
        _polite_delay()
        page = _new_page()
        url = f"https://finance.yahoo.com/quote/{symbol}/history/"
        print(f"[fetcher] Navigating to {url}")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)  # let table render

        table = page.query_selector("table")
        if not table:
            print(f"[fetcher] No table found for {symbol}")
            return None

        tbody = table.query_selector("tbody")
        if not tbody:
            print(f"[fetcher] No tbody found for {symbol}")
            return None

        rows_data = []
        for tr in tbody.query_selector_all("tr"):
            cells = tr.query_selector_all("td")
            if len(cells) < 7:
                continue
            try:
                date_str = cells[0].inner_text().strip()
                o = float(cells[1].inner_text().strip().replace(",", ""))
                h = float(cells[2].inner_text().strip().replace(",", ""))
                l = float(cells[3].inner_text().strip().replace(",", ""))
                c = float(cells[4].inner_text().strip().replace(",", ""))
                vol_str = cells[6].inner_text().strip().replace(",", "")
                v = int(vol_str) if vol_str and vol_str != "-" else 0
                rows_data.append(
                    {
                        "Date": pd.to_datetime(date_str),
                        "Open": o,
                        "High": h,
                        "Low": l,
                        "Close": c,
                        "Volume": v,
                    }
                )
            except (ValueError, IndexError):
                continue

        if not rows_data:
            print(f"[fetcher] No valid rows parsed for {symbol}")
            return None

        df = pd.DataFrame(rows_data).set_index("Date").sort_index()

        # Trim to requested period
        period_days = _period_to_days(period)
        if len(df) > period_days:
            df = df.tail(period_days)

        print(f"[fetcher] History OK for {symbol}: {len(df)} rows")
        return df

    except PlaywrightBrowserMissingError as e:
        _log_browser_missing_once(e)
        return None
    except Exception as e:
        print(f"[fetcher] History error for {symbol}: {e}")
        return None
    finally:
        if page:
            try:
                page.context.close()
            except Exception:
                pass


def _period_to_days(period: str) -> int:
    """Convert period string to approximate trading days."""
    mapping = {
        "1mo": 22,
        "3mo": 65,
        "6mo": 130,
        "1y": 252,
        "2y": 504,
        "5y": 1260,
    }
    return mapping.get(period, 130)


# ── Info (derived from history) ──────────────────────────────────────────────


def get_info(symbol: str, df: Optional[pd.DataFrame] = None) -> Dict:
    """
    Derive price info from the downloaded history DataFrame.
    Falls back to scraping the Yahoo Finance quote page if df is unavailable.
    """
    if df is not None and len(df) >= 2:
        current = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        high52 = float(df["High"].max())
        low52 = float(df["Low"].min())
        return {
            "symbol": symbol,
            "longName": symbol,  # overridden by watchlist name in scheduler
            "currentPrice": current,
            "previousClose": prev,
            "currency": "INR",
            "fiftyTwoWeekHigh": high52,
            "fiftyTwoWeekLow": low52,
            "marketCap": 0,
            "sector": "",
        }

    # Fallback: scrape quote page via browser
    page = None
    try:
        page = _new_page()
        page.goto(f"https://finance.yahoo.com/quote/{symbol}/", timeout=30000)
        page.wait_for_timeout(2000)

        current = 0.0
        prev = 0.0
        for el in page.query_selector_all("fin-streamer"):
            field = el.get_attribute("data-field")
            val = el.get_attribute("data-value")
            if field == "regularMarketPrice" and val:
                current = float(val)
                break
        for el in page.query_selector_all("fin-streamer"):
            field = el.get_attribute("data-field")
            val = el.get_attribute("data-value")
            if field == "regularMarketPreviousClose" and val:
                prev = float(val)
                break

        return {
            "symbol": symbol,
            "longName": symbol,
            "currentPrice": current,
            "previousClose": prev,
            "currency": "INR",
            "fiftyTwoWeekHigh": 0,
            "fiftyTwoWeekLow": 0,
            "marketCap": 0,
            "sector": "",
        }
    except PlaywrightBrowserMissingError as e:
        _log_browser_missing_once(e)
        return {
            "symbol": symbol,
            "longName": symbol,
            "currentPrice": 0,
            "previousClose": 0,
            "currency": "INR",
            "fiftyTwoWeekHigh": 0,
            "fiftyTwoWeekLow": 0,
            "marketCap": 0,
            "sector": "",
        }
    except Exception as e:
        print(f"[fetcher] Quote scrape error for {symbol}: {e}")
        return {
            "symbol": symbol,
            "longName": symbol,
            "currentPrice": 0,
            "previousClose": 0,
            "currency": "INR",
            "fiftyTwoWeekHigh": 0,
            "fiftyTwoWeekLow": 0,
            "marketCap": 0,
            "sector": "",
        }
    finally:
        if page:
            try:
                page.context.close()
            except Exception:
                pass


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_float(val) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    try:
        if val is None:
            return None
        f = float(val)
        return round(f, 4) if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def _parse_stat_value(text: str) -> Optional[float]:
    """Parse a stat value like '23.95', '1.09T', '14.00%', 'N/A'."""
    if not text or text.strip() in ("N/A", "--", "∞"):
        return None
    text = text.strip().replace(",", "")

    # Handle percentage
    if text.endswith("%"):
        try:
            return round(float(text[:-1]) / 100, 6)
        except ValueError:
            return None

    # Handle suffixes: T, B, M, K
    multipliers = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    for suffix, mult in multipliers.items():
        if text.endswith(suffix):
            try:
                return round(float(text[:-1]) * mult, 4)
            except ValueError:
                return None

    # Plain number
    try:
        return round(float(text), 4)
    except ValueError:
        return None


# ── Fundamentals fetching ────────────────────────────────────────────────────

_FUNDAMENTAL_EMPTY = {
    "trailing_pe": None,
    "forward_pe": None,
    "peg_ratio": None,
    "price_to_book": None,
    "ev_to_ebitda": None,
    "trailing_eps": None,
    "forward_eps": None,
    "free_cashflow": None,
    "operating_cashflow": None,
    "debt_to_equity": None,
    "profit_margin": None,
    "revenue_growth": None,
    "earnings_growth": None,
    "dividend_yield": None,
    "return_on_equity": None,
    "market_cap": None,
}

# Map of display label → our key name
_STAT_LABEL_MAP = {
    "trailing p/e": "trailing_pe",
    "forward p/e": "forward_pe",
    "peg ratio (5yr expected)": "peg_ratio",
    "price/book (mrq)": "price_to_book",
    "enterprise value/ebitda": "ev_to_ebitda",
    "diluted eps (ttm)": "trailing_eps",
    "forward annual dividend yield": "dividend_yield",
    "trailing annual dividend yield": "dividend_yield",
    "profit margin": "profit_margin",
    "return on equity (ttm)": "return_on_equity",
    "revenue per share (ttm)": None,  # skip
    "quarterly revenue growth (yoy)": "revenue_growth",
    "quarterly earnings growth (yoy)": "earnings_growth",
    "total debt/equity (mrq)": "debt_to_equity",
    "market cap": "market_cap",
    "enterprise value": None,  # skip (we use ev/ebitda)
    "levered free cash flow (ttm)": "free_cashflow",
    "operating cash flow (ttm)": "operating_cashflow",
}


def get_fundamentals(symbol: str) -> Dict:
    """
    Scrape fundamental data from Yahoo Finance's /key-statistics/ page.
    Returns a dict with all values — None if unavailable.
    """
    page = None
    try:
        _polite_delay()
        page = _new_page()
        url = f"https://finance.yahoo.com/quote/{symbol}/key-statistics/"
        print(f"[fetcher] Navigating to {url}")
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        result = dict(_FUNDAMENTAL_EMPTY)

        # Parse all tables on the page
        tables = page.query_selector_all("table")
        for table in tables:
            for tr in table.query_selector_all("tr"):
                cells = tr.query_selector_all("td")
                if len(cells) < 2:
                    continue
                label = cells[0].inner_text().strip().lower()
                value_text = cells[1].inner_text().strip()

                # Match against our label map
                for key_label, our_key in _STAT_LABEL_MAP.items():
                    if our_key and key_label in label:
                        parsed = _parse_stat_value(value_text)
                        if parsed is not None:
                            # debt_to_equity comes as percentage on YF (e.g. 43.21%)
                            # but our analysis expects a ratio — already handled by %->decimal
                            result[our_key] = parsed
                        break

        # For forward_eps, try to derive from forward_pe and current price
        # (not directly on key-statistics page)

        pe = result.get("trailing_pe")
        print(f"[fetcher] Fundamentals OK for {symbol} (PE={pe})")
        return result

    except PlaywrightBrowserMissingError as e:
        _log_browser_missing_once(e)
        return dict(_FUNDAMENTAL_EMPTY)
    except Exception as e:
        print(f"[fetcher] Fundamentals error for {symbol}: {e}")
        return dict(_FUNDAMENTAL_EMPTY)
    finally:
        if page:
            try:
                page.context.close()
            except Exception:
                pass
