"""Crypto Order Flow & Smart Money concepts: FVG, Wyckoff VSA, and Cumulative Volume Delta."""

import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def detect_fair_value_gaps(df: pd.DataFrame, min_gap_pct: float = 0.05) -> Dict[str, Any]:
    """
    Identifies bullish and bearish Fair Value Gaps (FVG) / Liquidity Imbalances.
    - Bullish FVG: Bar[i-2].High < Bar[i].Low (unfilled void in Bar[i-1])
    - Bearish FVG: Bar[i-2].Low > Bar[i].High (unfilled void in Bar[i-1])
    """
    if len(df) < 3 or not all(col in df.columns for col in ["High", "Low", "Close"]):
        return {"bullish_fvgs": [], "bearish_fvgs": [], "active_bullish_count": 0, "active_bearish_count": 0, "bias": "NEUTRAL"}

    bullish_fvgs = []
    bearish_fvgs = []
    n = len(df)

    for i in range(2, n):
        c_prev2_high = float(df["High"].iloc[i - 2])
        c_prev2_low = float(df["Low"].iloc[i - 2])
        c_curr_high = float(df["High"].iloc[i])
        c_curr_low = float(df["Low"].iloc[i])
        c_mid_close = float(df["Close"].iloc[i - 1])

        if c_curr_low > c_prev2_high:
            gap_size = c_curr_low - c_prev2_high
            gap_pct = (gap_size / c_mid_close) * 100.0 if c_mid_close > 0 else 0.0
            if gap_pct >= min_gap_pct:
                mitigated = any(float(df["Low"].iloc[j]) <= c_prev2_high for j in range(i + 1, n))
                bullish_fvgs.append({
                    "candle_index": int(i - 1),
                    "top": round(c_curr_low, 6),
                    "bottom": round(c_prev2_high, 6),
                    "size_pct": round(gap_pct, 2),
                    "mitigated": mitigated
                })

        elif c_prev2_low > c_curr_high:
            gap_size = c_prev2_low - c_curr_high
            gap_pct = (gap_size / c_mid_close) * 100.0 if c_mid_close > 0 else 0.0
            if gap_pct >= min_gap_pct:
                mitigated = any(float(df["High"].iloc[j]) >= c_prev2_low for j in range(i + 1, n))
                bearish_fvgs.append({
                    "candle_index": int(i - 1),
                    "top": round(c_prev2_low, 6),
                    "bottom": round(c_curr_high, 6),
                    "size_pct": round(gap_pct, 2),
                    "mitigated": mitigated
                })

    active_bullish = [f for f in bullish_fvgs if not f["mitigated"]]
    active_bearish = [f for f in bearish_fvgs if not f["mitigated"]]

    bias = "BULLISH" if len(active_bullish) > len(active_bearish) else ("BEARISH" if len(active_bearish) > len(active_bullish) else "NEUTRAL")

    return {
        "bullish_fvgs": bullish_fvgs[-5:],
        "bearish_fvgs": bearish_fvgs[-5:],
        "active_bullish_count": len(active_bullish),
        "active_bearish_count": len(active_bearish),
        "bias": bias
    }


def analyze_wyckoff_vsa(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Volume Spread Analysis (VSA) based on Wyckoff methodologies.
    Examines the interaction between spread (High - Low) and Volume to detect smart money activity.
    """
    if len(df) < 20 or "Volume" not in df.columns:
        return {"signals": [], "dominant_bias": "NEUTRAL", "status": "INSUFFICIENT_DATA"}

    spread = df["High"] - df["Low"]
    avg_spread = spread.rolling(window=20).mean()
    rel_spread = spread / avg_spread.replace(0, np.nan)

    vol = df["Volume"].astype(float)
    avg_vol = vol.rolling(window=20).mean()
    rel_vol = vol / avg_vol.replace(0, np.nan)

    signals = []
    n = len(df)

    for i in range(max(20, n - 8), n):
        o = float(df["Open"].iloc[i])
        c = float(df["Close"].iloc[i])
        h = float(df["High"].iloc[i])
        l = float(df["Low"].iloc[i])
        rv = float(rel_vol.iloc[i]) if not np.isnan(rel_vol.iloc[i]) else 1.0
        rs = float(rel_spread.iloc[i]) if not np.isnan(rel_spread.iloc[i]) else 1.0

        bar_spread = h - l
        close_pos = (c - l) / bar_spread if bar_spread > 0 else 0.5

        if c < o and rv > 1.5 and close_pos >= 0.4:
            signals.append({
                "bar_index": int(i),
                "name": "Stopping Volume",
                "bias": "BULLISH",
                "description": "Absorption of selling pressure with close held well off lows"
            })
        elif c > o and rv > 2.0 and rs > 1.8 and close_pos < 0.6:
            signals.append({
                "bar_index": int(i),
                "name": "Buying Climax",
                "bias": "BEARISH",
                "description": "Exhaustion into late retail buying spikes"
            })
        elif c < o and rv > 2.0 and rs > 1.8 and close_pos > 0.4:
            signals.append({
                "bar_index": int(i),
                "name": "Selling Climax",
                "bias": "BULLISH",
                "description": "Capitulation absorbed by buyers"
            })
        elif c <= o and rv < 0.75 and rs < 0.85:
            signals.append({
                "bar_index": int(i),
                "name": "No Supply Test",
                "bias": "BULLISH",
                "description": "Low volume pullback confirming floating seller supply is dried up"
            })
        elif c >= o and rv < 0.75 and rs < 0.85:
            signals.append({
                "bar_index": int(i),
                "name": "No Demand Test",
                "bias": "BEARISH",
                "description": "Advance stalling on negligible volume"
            })

    bull_count = sum(1 for s in signals if s["bias"] == "BULLISH")
    bear_count = sum(1 for s in signals if s["bias"] == "BEARISH")
    bias = "BULLISH" if bull_count > bear_count else ("BEARISH" if bear_count > bull_count else "NEUTRAL")

    return {
        "signals": signals[-5:],
        "dominant_bias": bias,
        "latest_relative_volume": round(float(rel_vol.iloc[-1]), 2) if not np.isnan(rel_vol.iloc[-1]) else 1.0,
        "latest_relative_spread": round(float(rel_spread.iloc[-1]), 2) if not np.isnan(rel_spread.iloc[-1]) else 1.0
    }


def calculate_cumulative_volume_delta(df: pd.DataFrame, lookback_bars: int = 20) -> Dict[str, Any]:
    """
    Cumulative Volume Delta (CVD) and Absorption Detector.
    Uses Close Location Value (CLV): CLV = ((Close - Low) - (High - Close)) / (High - Low)
    """
    if len(df) < 5 or not all(c in df.columns for c in ["High", "Low", "Close", "Volume"]):
        return {
            "current_cvd": 0.0,
            "recent_delta_bias": "NEUTRAL",
            "divergence": "NONE",
            "absorption_detected": False,
            "status": "INSUFFICIENT_DATA"
        }

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)

    hl_range = (high - low).replace(0, np.nan)
    clv = ((close - low) - (high - close)) / hl_range
    clv = clv.fillna(0.0).clip(-1.0, 1.0)

    bar_delta = vol * clv
    cvd = bar_delta.cumsum()

    lb = min(lookback_bars, len(df))
    recent_delta = float(bar_delta.iloc[-lb:].sum())
    
    half = max(2, lb // 2)
    p_low_prev = float(low.iloc[-lb:-half].min())
    p_low_curr = float(low.iloc[-half:].min())
    cvd_low_prev = float(cvd.iloc[-lb:-half].min())
    cvd_low_curr = float(cvd.iloc[-half:].min())

    p_high_prev = float(high.iloc[-lb:-half].max())
    p_high_curr = float(high.iloc[-half:].max())
    cvd_high_prev = float(cvd.iloc[-lb:-half].max())
    cvd_high_curr = float(cvd.iloc[-half:].max())

    bull_div = (p_low_curr <= p_low_prev and cvd_low_curr > cvd_low_prev)
    bear_div = (p_high_curr >= p_high_prev and cvd_high_curr < cvd_high_prev)

    divergence = "BULLISH_DIVERGENCE" if bull_div else ("BEARISH_DIVERGENCE" if bear_div else "NONE")
    delta_bias = "BULLISH" if recent_delta > 0 else ("BEARISH" if recent_delta < 0 else "NEUTRAL")

    return {
        "current_cvd": round(float(cvd.iloc[-1]), 2),
        "recent_delta_bias": delta_bias,
        "divergence": divergence,
        "absorption_detected": bull_div or bear_div,
        "latest_bar_delta": round(float(bar_delta.iloc[-1]), 2),
        "latest_clv": round(float(clv.iloc[-1]), 3),
        "status": "OK"
    }


def analyze_order_flow(df: pd.DataFrame) -> Dict[str, Any]:
    """Composite order flow evaluation scoring tape pressure 0-100."""
    fvg = detect_fair_value_gaps(df)
    vsa = analyze_wyckoff_vsa(df)
    cvd = calculate_cumulative_volume_delta(df)

    score = 50
    if fvg.get("bias") == "BULLISH":
        score += 15
    elif fvg.get("bias") == "BEARISH":
        score -= 15

    if vsa.get("dominant_bias") == "BULLISH":
        score += 15
    elif vsa.get("dominant_bias") == "BEARISH":
        score -= 15

    if cvd.get("recent_delta_bias") == "BULLISH":
        score += 10
    elif cvd.get("recent_delta_bias") == "BEARISH":
        score -= 10

    if cvd.get("divergence") == "BULLISH_DIVERGENCE":
        score += 10
    elif cvd.get("divergence") == "BEARISH_DIVERGENCE":
        score -= 10

    score = max(5, min(95, score))
    verdict = "STRONG_ACCUMULATION" if score >= 75 else ("ACCUMULATION" if score >= 60 else ("STRONG_DISTRIBUTION" if score <= 25 else ("DISTRIBUTION" if score <= 40 else "NEUTRAL")))

    return {
        "order_flow_score": score,
        "verdict": verdict,
        "fair_value_gaps": fvg,
        "wyckoff_vsa": vsa,
        "cumulative_volume_delta": cvd
    }
