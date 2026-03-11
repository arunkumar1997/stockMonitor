"""
News fetcher using Yahoo Finance RSS feeds.
No API key required. Performs keyword-based negative sentiment scoring.
Keywords and thresholds are loaded from the app_config DB table at call time.
"""
import feedparser
import time
from typing import List, Dict

_news_cache: dict = {}


def _get_cfg():
    """Lazily load config from DB at call time (always fresh)."""
    from data import store
    return {
        "negative_keywords": store.config_get("negative_keywords") or [],
        "positive_keywords": store.config_get("positive_keywords") or [],
        "avoid_threshold":   store.config_get("avoid_news_threshold") or 0.55,
        "neg_headline_thr":  store.config_get("negative_headline_threshold") or 0.45,
        "cache_ttl":         store.config_get("news_cache_ttl") or 600,
    }


def _score_sentiment(text: str, neg_kws: List[str], pos_kws: List[str]) -> float:
    """Returns a negativity score 0.0–1.0 based on keyword matching."""
    text_lower = text.lower()
    neg = sum(1 for kw in neg_kws if kw in text_lower)
    pos = sum(1 for kw in pos_kws if kw in text_lower)
    total = neg + pos
    if total == 0:
        return 0.1  # neutral-slightly-negative baseline
    return round(neg / total, 2)


def get_news(symbol: str, company_name: str = "") -> Dict:
    """Fetch news for a stock symbol via Yahoo Finance RSS."""
    cfg = _get_cfg()
    cache_key = symbol
    now = time.time()
    if cache_key in _news_cache:
        entry = _news_cache[cache_key]
        if now - entry["ts"] < cfg["cache_ttl"]:
            return entry["data"]

    headlines = []
    negative_score = 0.1

    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
        feed = feedparser.parse(url)

        if feed.entries:
            for entry in feed.entries[:8]:
                title = entry.get("title", "")
                link  = entry.get("link", "#")
                published = entry.get("published", "")
                score = _score_sentiment(title, cfg["negative_keywords"], cfg["positive_keywords"])
                headlines.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "negative_score": score,
                    "is_negative": score > cfg["neg_headline_thr"],
                })

            scores = [h["negative_score"] for h in headlines[:5]]
            negative_score = round(sum(scores) / len(scores), 2) if scores else 0.1
        else:
            headlines = [{"title": "No recent news found.", "link": "#", "published": "",
                          "negative_score": 0, "is_negative": False}]

    except Exception as e:
        print(f"[news] Error fetching news for {symbol}: {e}")
        headlines = [{"title": "Unable to fetch news.", "link": "#", "published": "",
                      "negative_score": 0, "is_negative": False}]

    result = {
        "symbol": symbol,
        "negative_score": negative_score,
        "sentiment": "Negative" if negative_score > 0.5 else ("Neutral" if negative_score > 0.25 else "Positive"),
        "headlines": headlines,
    }
    _news_cache[cache_key] = {"data": result, "ts": now}
    return result
