"""
Technical analysis engine.
- Dip detection (% below 20-day high)
- Resistance levels (swing highs)
- Support levels (swing lows)
- Buy/Sell/Hold signal generation
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def detect_dip(df: pd.DataFrame, window: int = 20, threshold: float = 5.0) -> Dict:
    """
    Detect if the stock is in a dip relative to its recent high.
    Returns dip percentage and severity label.
    """
    if df is None or len(df) < window:
        return {"is_dip": False, "dip_pct": 0.0, "severity": "none", "recent_high": 0.0}

    recent = df["Close"].tail(window)
    recent_high = float(recent.max())
    current = float(df["Close"].iloc[-1])

    dip_pct = round((recent_high - current) / recent_high * 100, 2) if recent_high > 0 else 0.0

    if dip_pct >= 15:
        severity = "extreme"
    elif dip_pct >= 10:
        severity = "high"
    elif dip_pct >= threshold:
        severity = "moderate"
    elif dip_pct >= 2:
        severity = "minor"
    else:
        severity = "none"

    return {
        "is_dip": dip_pct >= threshold,
        "dip_pct": dip_pct,
        "severity": severity,
        "recent_high": round(recent_high, 2),
    }


def find_resistance_levels(df: pd.DataFrame, window: int = 20, num_levels: int = 3) -> List[float]:
    """
    Identify resistance levels using swing highs (local maxima).
    A swing high is a candle whose high is greater than surrounding candles.
    """
    if df is None or len(df) < window:
        return []

    highs = df["High"].values
    resistance = []

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and \
           highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            resistance.append(round(float(highs[i]), 2))

    # Cluster nearby resistance levels (within 1%)
    clustered = []
    for level in sorted(set(resistance)):
        if not clustered or abs(level - clustered[-1]) / clustered[-1] > 0.01:
            clustered.append(level)

    # Return levels above current price, sorted ascending
    current = float(df["Close"].iloc[-1])
    above = [l for l in clustered if l > current]
    return above[:num_levels] if above else clustered[-num_levels:]


def find_support_levels(df: pd.DataFrame, window: int = 20, num_levels: int = 3) -> List[float]:
    """
    Identify support levels using swing lows (local minima).
    """
    if df is None or len(df) < window:
        return []

    lows = df["Low"].values
    support = []

    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and \
           lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            support.append(round(float(lows[i]), 2))

    clustered = []
    for level in sorted(set(support), reverse=True):
        if not clustered or abs(level - clustered[-1]) / clustered[-1] > 0.01:
            clustered.append(level)

    current = float(df["Close"].iloc[-1])
    below = [l for l in clustered if l < current]
    return below[:num_levels] if below else clustered[:num_levels]


def calc_moving_averages(df: pd.DataFrame) -> Dict:
    """Calculate common moving averages."""
    if df is None or len(df) < 5:
        return {}
    closes = df["Close"]
    result = {}
    for period in [10, 20, 50, 200]:
        if len(closes) >= period:
            result[f"ma{period}"] = round(float(closes.tail(period).mean()), 2)
    return result


def calc_rsi(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Calculate RSI (Relative Strength Index)."""
    if df is None or len(df) < period + 1:
        return None
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return round(val, 1) if not np.isnan(val) else None


def get_sparkline_data(df: pd.DataFrame, days: int = 30) -> List[float]:
    """Get last N days of closing prices for sparkline chart."""
    if df is None or df.empty:
        return []
    return [round(float(v), 2) for v in df["Close"].tail(days).tolist()]


def detect_volume_spike(df: pd.DataFrame, window: int = 20) -> Dict:
    """
    Detects unusual volume (spike vs 20-day average).
    High volume on a down day = distribution (bearish).
    High volume on an up day = accumulation (bullish).
    """
    if df is None or len(df) < window:
        return {"is_spike": False, "volume_ratio": 1.0, "direction": "neutral"}

    avg_vol = float(df["Volume"].tail(window).mean())
    latest_vol = float(df["Volume"].iloc[-1])
    ratio = round(latest_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_close
    up_day = last_close >= prev_close

    return {
        "is_spike": ratio > 1.5,
        "volume_ratio": ratio,
        "direction": "up" if up_day else "down",
    }


def generate_signal(
    dip: Dict,
    resistance_levels: List[float],
    support_levels: List[float],
    ma: Dict,
    rsi: Optional[float],
    current_price: float,
    news_negative_score: float,
    volume: Dict = None,
) -> Dict:
    """
    DipSense-style signal generation:
      AVOID     — negative news detected
      BUY       — price drop ≥ 3% with support holding (healthy correction)
      BUY SMALL — price drop 1-3% with support holding
      WAIT      — support not holding, high distribution volume, or unclear setup
    """
    reasons = []

    # ── Rule 1: AVOID on strong negative news ────────────────────────────────
    if news_negative_score > 0.55:
        reasons.append("Negative news detected — avoid until sentiment clears")
        return {
            "signal": "AVOID",
            "confidence": min(95, int(50 + news_negative_score * 45)),
            "buy_score": 0,
            "sell_score": 3,
            "reasons": reasons,
        }

    # ── Rule 2: Check support health ─────────────────────────────────────────
    ma20 = ma.get("ma20")
    support_holds = True
    if support_levels and current_price > 0:
        nearest_support = support_levels[0]
        if current_price < nearest_support * 0.98:
            support_holds = False
            reasons.append(f"Price broken below support at {nearest_support:.2f}")
    elif ma20 and current_price > 0:
        if current_price < ma20 * 0.95:
            support_holds = False
            reasons.append("Price significantly below MA20 — support not holding")

    # ── Rule 3: Volume analysis ───────────────────────────────────────────────
    high_distribution_volume = False
    if volume and volume["is_spike"] and volume["direction"] == "down":
        high_distribution_volume = True
        reasons.append(f"High distribution volume ({volume['volume_ratio']}x avg) on down day")

    # ── Rule 4: Apply DipSense signal rules ───────────────────────────────────
    dip_pct = dip.get("dip_pct", 0)

    if not support_holds and high_distribution_volume:
        reasons.append("Breakdown in progress — wait for stabilisation")
        return {
            "signal": "WAIT",
            "confidence": 70,
            "buy_score": 0,
            "sell_score": 2,
            "reasons": reasons,
        }

    if dip_pct >= 3 and support_holds:
        # Healthy correction with support intact
        if rsi is not None and rsi < 35:
            reasons.append(f"RSI {rsi} — oversold, strong dip opportunity")
            confidence = 90
        elif dip_pct >= 10:
            reasons.append(f"Major dip {dip_pct:.1f}% with support intact — high conviction")
            confidence = 85
        elif dip_pct >= 5:
            reasons.append(f"Moderate-high dip {dip_pct:.1f}% from recent high")
            confidence = 78
        else:
            reasons.append(f"Price dropped {dip_pct:.1f}% — dip with support holding")
            confidence = 72

        if volume and volume["is_spike"] and volume["direction"] == "up":
            reasons.append("Accumulation volume confirms buying interest")
            confidence = min(95, confidence + 5)

        if resistance_levels and current_price > 0:
            prox = (resistance_levels[0] - current_price) / current_price * 100
            if prox < 3:
                reasons.append(f"Caution: resistance close at {resistance_levels[0]:.2f}")
                confidence = max(55, confidence - 10)

        return {
            "signal": "BUY",
            "confidence": confidence,
            "buy_score": 3,
            "sell_score": 0,
            "reasons": reasons,
        }

    if 1 <= dip_pct < 3 and support_holds:
        reasons.append(f"Small dip {dip_pct:.1f}% — partial position entry")
        confidence = 62
        if rsi is not None and rsi < 45:
            reasons.append(f"RSI {rsi} — room to run lower, sizing accordingly")
        return {
            "signal": "BUY SMALL",
            "confidence": confidence,
            "buy_score": 1,
            "sell_score": 0,
            "reasons": reasons,
        }

    # Default: wait for a better setup
    if dip_pct < 1:
        reasons.append("No meaningful dip yet — wait for better entry")
    elif not support_holds:
        reasons.append("Support not confirmed — wait for stabilisation")
    else:
        reasons.append("Setup unclear — monitor for clearer signal")

    if rsi is not None and rsi > 65:
        reasons.append(f"RSI {rsi} — overbought, not a good entry")

    return {
        "signal": "WAIT",
        "confidence": 60,
        "buy_score": 0,
        "sell_score": 1,
        "reasons": reasons,
    }


def full_analysis(symbol: str, df, info: Dict, news: Dict) -> Dict:
    """Run complete analysis for a stock and return structured result."""
    current_price = info.get("currentPrice", 0)
    previous_close = info.get("previousClose", 0)

    price_change = round(current_price - previous_close, 4) if previous_close else 0
    price_change_pct = round((price_change / previous_close) * 100, 2) if previous_close else 0

    dip = detect_dip(df)
    resistance = find_resistance_levels(df)
    support = find_support_levels(df)
    ma = calc_moving_averages(df)
    rsi = calc_rsi(df)
    volume = detect_volume_spike(df)
    sparkline = get_sparkline_data(df)
    signal = generate_signal(
        dip, resistance, support, ma, rsi,
        current_price, news.get("negative_score", 0),
        volume=volume,
    )

    return {
        "symbol": symbol,
        "name": info.get("longName", symbol),
        "currency": info.get("currency", "USD"),
        "current_price": current_price,
        "previous_close": previous_close,
        "price_change": price_change,
        "price_change_pct": price_change_pct,
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
        "sector": info.get("sector", ""),
        "dip": dip,
        "resistance_levels": resistance,
        "support_levels": support,
        "moving_averages": ma,
        "rsi": rsi,
        "volume": volume,
        "sparkline": sparkline,
        "signal": signal,
        "news": news,
    }
