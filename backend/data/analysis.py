"""
Technical analysis engine.
- Dip detection (% below N-day high, configurable)
- Resistance levels (swing highs)
- Support levels (swing lows)
- Buy/Sell/Hold signal generation

All thresholds are read from the app_config DB table via the `cfg` dict
passed into full_analysis(). Call load_config() to get the dict.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def load_config() -> Dict:
    """Load all analysis-relevant config from DB. Call once per refresh cycle."""
    from data import store
    return {
        "dip_window":            store.config_get("dip_window") or 20,
        "dip_threshold":         store.config_get("dip_threshold") or 5.0,
        "buy_dip_pct":           store.config_get("buy_dip_pct") or 3.0,
        "buy_small_dip_min":     store.config_get("buy_small_dip_min") or 1.0,
        "buy_small_dip_max":     store.config_get("buy_small_dip_max") or 3.0,
        "rsi_oversold":          store.config_get("rsi_oversold") or 35,
        "rsi_overbought":        store.config_get("rsi_overbought") or 65,
        "volume_spike_ratio":    store.config_get("volume_spike_ratio") or 1.5,
        "sparkline_days":        store.config_get("sparkline_days") or 30,
        "avoid_news_threshold":  store.config_get("avoid_news_threshold") or 0.55,
        "history_period":        store.config_get("history_period") or "6mo",
        # Fundamental analysis thresholds
        "pe_overvalued":         store.config_get("pe_overvalued") or 40,
        "pe_undervalued":        store.config_get("pe_undervalued") or 15,
        "high_debt_equity":      store.config_get("high_debt_equity") or 1.5,
        "ev_ebitda_stretched":   store.config_get("ev_ebitda_stretched") or 25,
    }


def detect_dip(df: pd.DataFrame, cfg: Dict) -> Dict:
    """
    Detect if the stock is in a dip relative to its recent high.
    Returns dip percentage and severity label.
    """
    window    = cfg.get("dip_window", 20)
    threshold = cfg.get("dip_threshold", 5.0)

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
    """Identify resistance levels using swing highs (local maxima)."""
    if df is None or len(df) < window:
        return []
    highs = df["High"].values
    resistance = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance.append(round(float(highs[i]), 2))
    clustered = []
    for level in sorted(set(resistance)):
        if not clustered or abs(level - clustered[-1]) / clustered[-1] > 0.01:
            clustered.append(level)
    current = float(df["Close"].iloc[-1])
    above = [l for l in clustered if l > current]
    return above[:num_levels] if above else clustered[-num_levels:]


def find_support_levels(df: pd.DataFrame, window: int = 20, num_levels: int = 3) -> List[float]:
    """Identify support levels using swing lows (local minima)."""
    if df is None or len(df) < window:
        return []
    lows = df["Low"].values
    support = []
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
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
    gain  = delta.clip(lower=0).rolling(window=period).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))
    val   = float(rsi.iloc[-1])
    return round(val, 1) if not np.isnan(val) else None


def get_sparkline_data(df: pd.DataFrame, days: int = 30) -> List[float]:
    """Get last N days of closing prices for sparkline chart."""
    if df is None or df.empty:
        return []
    return [round(float(v), 2) for v in df["Close"].tail(days).tolist()]


def detect_volume_spike(df: pd.DataFrame, cfg: Dict) -> Dict:
    """Detects unusual volume (spike vs 20-day average)."""
    window = cfg.get("dip_window", 20)
    ratio_threshold = cfg.get("volume_spike_ratio", 1.5)

    if df is None or len(df) < window:
        return {"is_spike": False, "volume_ratio": 1.0, "direction": "neutral"}

    avg_vol    = float(df["Volume"].tail(window).mean())
    latest_vol = float(df["Volume"].iloc[-1])
    ratio      = round(latest_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    last_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) > 1 else last_close
    up_day = last_close >= prev_close

    return {
        "is_spike":     ratio > ratio_threshold,
        "volume_ratio": ratio,
        "direction":    "up" if up_day else "down",
    }


def calc_valuation(fundamentals: Dict, cfg: Dict) -> Dict:
    """
    Score and classify fundamental valuation.
    score 0=very overvalued, 100=very undervalued.
    Status: UNDERVALUED | FAIR | OVERVALUED | STRETCHED | UNKNOWN
    """
    if not fundamentals:
        return {"status": "UNKNOWN", "score": 50, "flags": [], "summary_reasons": []}

    pe_over  = cfg.get("pe_overvalued", 40)
    pe_under = cfg.get("pe_undervalued", 15)
    de_limit = cfg.get("high_debt_equity", 1.5)
    ev_limit = cfg.get("ev_ebitda_stretched", 25)

    score   = 50
    flags   = []
    reasons = []

    pe  = fundamentals.get("trailing_pe")
    fpe = fundamentals.get("forward_pe")
    peg = fundamentals.get("peg_ratio")
    ev  = fundamentals.get("ev_to_ebitda")
    de  = fundamentals.get("debt_to_equity")
    fcf = fundamentals.get("free_cashflow")
    rev = fundamentals.get("revenue_growth")
    roe = fundamentals.get("return_on_equity")

    # P/E analysis
    if pe is not None and pe > 0:
        if pe > pe_over:
            score -= 20
            flags.append("high_pe")
            reasons.append(f"High P/E {pe:.1f}x — potentially overvalued")
        elif pe < pe_under:
            score += 20
            flags.append("low_pe")
            reasons.append(f"Low P/E {pe:.1f}x — potentially undervalued")
        else:
            reasons.append(f"P/E {pe:.1f}x — within fair range")

    # Forward P/E vs trailing
    if fpe is not None and pe is not None and fpe > 0 and pe > 0:
        if fpe < pe * 0.85:
            score += 10
            reasons.append(f"Fwd P/E {fpe:.1f}x < trailing — earnings growth expected")
        elif fpe > pe * 1.15:
            score -= 8
            reasons.append(f"Fwd P/E {fpe:.1f}x > trailing — earnings may decline")

    # PEG ratio
    if peg is not None and peg > 0:
        if peg > 2:
            score -= 12
            flags.append("high_peg")
            reasons.append(f"PEG {peg:.2f} > 2 — overvalued relative to growth")
        elif peg < 1:
            score += 12
            flags.append("low_peg")
            reasons.append(f"PEG {peg:.2f} < 1 — growth at discount")

    # EV/EBITDA
    if ev is not None and ev > 0:
        if ev > ev_limit:
            score -= 15
            flags.append("stretched_ev")
            reasons.append(f"EV/EBITDA {ev:.1f}x — stretched valuation")
        elif ev < 10:
            score += 10
            reasons.append(f"EV/EBITDA {ev:.1f}x — reasonable enterprise value")

    # Debt/Equity
    if de is not None:
        if de > de_limit:
            score -= 10
            flags.append("high_debt")
            reasons.append(f"D/E {de:.2f} — high leverage, watch cashflow")
        elif de < 0.3:
            score += 5
            reasons.append(f"D/E {de:.2f} — low debt, solid balance sheet")

    # Free cashflow
    if fcf is not None:
        if fcf < 0:
            score -= 15
            flags.append("negative_fcf")
            reasons.append("Negative free cashflow — company burning cash")
        else:
            score += 8
            flags.append("positive_fcf")

    # Revenue growth
    if rev is not None:
        if rev < 0:
            score -= 10
            flags.append("declining_revenue")
            reasons.append(f"Revenue growth {rev*100:.1f}% — declining top-line")
        elif rev > 0.15:
            score += 8
            reasons.append(f"Revenue growth {rev*100:.1f}% — strong top-line")

    # ROE
    if roe is not None:
        if roe > 0.20:
            score += 5
            reasons.append(f"ROE {roe*100:.1f}% — excellent capital efficiency")
        elif roe < 0:
            score -= 8
            flags.append("negative_roe")

    score = max(0, min(100, score))
    if score >= 70:
        status = "UNDERVALUED"
    elif score >= 45:
        status = "FAIR"
    elif score >= 25:
        status = "OVERVALUED"
    else:
        status = "STRETCHED"

    return {
        "status":  status,
        "score":   score,
        "flags":   flags,
        "summary_reasons": reasons[:4],
    }


def generate_signal(
    dip: Dict,
    resistance_levels: List[float],
    support_levels: List[float],
    ma: Dict,
    rsi: Optional[float],
    current_price: float,
    news_negative_score: float,
    cfg: Dict,
    volume: Dict = None,
    valuation: Dict = None,
) -> Dict:
    """DipSense signal generation — all thresholds from cfg."""
    reasons = []
    avoid_thr   = cfg.get("avoid_news_threshold", 0.55)
    buy_dip     = cfg.get("buy_dip_pct", 3.0)
    small_min   = cfg.get("buy_small_dip_min", 1.0)
    small_max   = cfg.get("buy_small_dip_max", 3.0)
    rsi_low     = cfg.get("rsi_oversold", 35)
    rsi_high    = cfg.get("rsi_overbought", 65)

    # ── Rule 1: AVOID on strong negative news ────────────────────────────────
    if news_negative_score > avoid_thr:
        reasons.append("Negative news detected — avoid until sentiment clears")
        return {
            "signal": "AVOID",
            "confidence": min(95, int(50 + news_negative_score * 45)),
            "buy_score": 0, "sell_score": 3, "reasons": reasons,
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

    dip_pct = dip.get("dip_pct", 0)

    if not support_holds and high_distribution_volume:
        reasons.append("Breakdown in progress — wait for stabilisation")
        return {"signal": "WAIT", "confidence": 70, "buy_score": 0, "sell_score": 2, "reasons": reasons}

    if dip_pct >= buy_dip and support_holds:
        if rsi is not None and rsi < rsi_low:
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

        # ── Fundamental valuation adjustments ────────────────────────────────
        if valuation:
            val_status = valuation.get("status", "UNKNOWN")
            val_flags  = valuation.get("flags", [])
            if val_status == "STRETCHED":
                reasons.append("Warning: valuation stretched — high risk entry")
                confidence = max(40, confidence - 20)
            elif val_status == "OVERVALUED":
                reasons.append("Caution: fundamentals suggest overvaluation")
                confidence = max(50, confidence - 12)
            elif val_status == "UNDERVALUED":
                reasons.append("Fundamentals support: stock appears undervalued")
                confidence = min(95, confidence + 8)
            if "negative_fcf" in val_flags:
                reasons.append("Note: negative free cashflow — monitor closely")
                confidence = max(45, confidence - 5)
            if "high_debt" in val_flags and val_status not in ("FAIR", "UNDERVALUED"):
                reasons.append("Note: high leverage — adds risk")

        return {"signal": "BUY", "confidence": confidence, "buy_score": 3, "sell_score": 0, "reasons": reasons}

    if small_min <= dip_pct < small_max and support_holds:
        reasons.append(f"Small dip {dip_pct:.1f}% — partial position entry")
        confidence = 62
        if rsi is not None and rsi < 45:
            reasons.append(f"RSI {rsi} — room to run lower, sizing accordingly")
        if valuation:
            val_status = valuation.get("status", "UNKNOWN")
            if val_status in ("OVERVALUED", "STRETCHED"):
                confidence = max(45, confidence - 10)
                reasons.append("Overvaluation limits conviction — size small")
        return {"signal": "BUY SMALL", "confidence": confidence, "buy_score": 1, "sell_score": 0, "reasons": reasons}

    if dip_pct < 1:
        reasons.append("No meaningful dip yet — wait for better entry")
    elif not support_holds:
        reasons.append("Support not confirmed — wait for stabilisation")
    else:
        reasons.append("Setup unclear — monitor for clearer signal")

    if rsi is not None and rsi > rsi_high:
        reasons.append(f"RSI {rsi} — overbought, not a good entry")

    return {"signal": "WAIT", "confidence": 60, "buy_score": 0, "sell_score": 1, "reasons": reasons}


def full_analysis(symbol: str, df, info: Dict, news: Dict,
                  cfg: Dict = None, fundamentals: Dict = None) -> Dict:
    """Run complete analysis for a stock and return structured result."""
    if cfg is None:
        cfg = load_config()

    current_price    = info.get("currentPrice", 0)
    previous_close   = info.get("previousClose", 0)
    price_change     = round(current_price - previous_close, 4) if previous_close else 0
    price_change_pct = round((price_change / previous_close) * 100, 2) if previous_close else 0

    dip        = detect_dip(df, cfg)
    resistance = find_resistance_levels(df)
    support    = find_support_levels(df)
    ma         = calc_moving_averages(df)
    rsi        = calc_rsi(df)
    volume     = detect_volume_spike(df, cfg)
    sparkline  = get_sparkline_data(df, days=cfg.get("sparkline_days", 30))
    valuation  = calc_valuation(fundamentals or {}, cfg)
    signal     = generate_signal(
        dip, resistance, support, ma, rsi,
        current_price, news.get("negative_score", 0),
        cfg=cfg, volume=volume, valuation=valuation,
    )

    return {
        "symbol":              symbol,
        "name":                info.get("longName", symbol),
        "currency":            info.get("currency", "USD"),
        "current_price":       current_price,
        "previous_close":      previous_close,
        "price_change":        price_change,
        "price_change_pct":    price_change_pct,
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
        "fifty_two_week_low":  info.get("fiftyTwoWeekLow", 0),
        "sector":              info.get("sector", ""),
        "dip":                 dip,
        "resistance_levels":   resistance,
        "support_levels":      support,
        "moving_averages":     ma,
        "rsi":                 rsi,
        "volume":              volume,
        "sparkline":           sparkline,
        "signal":              signal,
        "news":                news,
        "fundamentals":        fundamentals or {},
        "valuation":           valuation,
    }
