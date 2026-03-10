"""
News fetcher using Yahoo Finance RSS feeds.
No API key required. Performs keyword-based negative sentiment scoring.
"""
import feedparser
import requests
from typing import List, Dict
import time

_news_cache: dict = {}
CACHE_TTL = 600  # 10 minutes

NEGATIVE_KEYWORDS = [
    "fraud", "lawsuit", "loss", "crash", "downgrade", "miss", "disappoint",
    "fine", "penalty", "ban", "halt", "suspend", "recall", "deficit",
    "default", "bankrupt", "investigation", "probe", "decline", "drop",
    "plunge", "slump", "warning", "risk", "concern", "weak", "cut",
    "layoff", "resign", "exit", "sell", "short", "overvalue", "bubble",
    "inflation", "recession", "slowdown", "bearish", "negative", "loss",
    "debt", "liabilit", "breach", "hack", "leak", "sanction"
]

POSITIVE_KEYWORDS = [
    "beat", "surge", "record", "profit", "growth", "strong", "upgrade",
    "buy", "bullish", "outperform", "raise", "dividend", "expand",
    "partnership", "acquire", "launch", "win", "award", "breakout"
]


def _score_sentiment(text: str) -> float:
    """Returns a negativity score 0.0–1.0 based on keyword matching."""
    text_lower = text.lower()
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    total = neg + pos
    if total == 0:
        return 0.1  # neutral-slightly-negative baseline
    return round(neg / total, 2)


def get_news(symbol: str, company_name: str = "") -> Dict:
    """Fetch news for a stock symbol via Yahoo Finance RSS."""
    cache_key = symbol
    now = time.time()
    if cache_key in _news_cache:
        entry = _news_cache[cache_key]
        if now - entry["ts"] < CACHE_TTL:
            return entry["data"]

    # Strip market suffix for cleaner search (e.g. RELIANCE.NS -> RELIANCE)
    clean_symbol = symbol.split(".")[0]

    headlines = []
    negative_score = 0.1

    try:
        # Yahoo Finance RSS feed
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        feed = feedparser.parse(url)

        if feed.entries:
            for entry in feed.entries[:8]:
                title = entry.get("title", "")
                link = entry.get("link", "#")
                published = entry.get("published", "")
                score = _score_sentiment(title)
                headlines.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "negative_score": score,
                    "is_negative": score > 0.45,
                })

            # Overall score = average of top 5
            scores = [h["negative_score"] for h in headlines[:5]]
            negative_score = round(sum(scores) / len(scores), 2) if scores else 0.1
        else:
            headlines = [{"title": "No recent news found.", "link": "#", "published": "", "negative_score": 0, "is_negative": False}]

    except Exception as e:
        print(f"[news] Error fetching news for {symbol}: {e}")
        headlines = [{"title": "Unable to fetch news.", "link": "#", "published": "", "negative_score": 0, "is_negative": False}]

    result = {
        "symbol": symbol,
        "negative_score": negative_score,
        "sentiment": "Negative" if negative_score > 0.5 else ("Neutral" if negative_score > 0.25 else "Positive"),
        "headlines": headlines,
    }
    _news_cache[cache_key] = {"data": result, "ts": now}
    return result
