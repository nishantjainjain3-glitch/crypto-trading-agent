"""Multi-Horizon Trend & Volume Alignment Consensus Engine.

Analyzes micro (15m), intermediate (1h), and macro (4h) timeframes
to produce a unified directional conviction score before entering trades.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Compute exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))


class MultiHorizonConsensusEngine:
    """Evaluates multi-timeframe directional agreement across 15m, 1h, and 4h data."""

    def __init__(
        self,
        min_consensus_threshold: float = 0.35,
        strong_consensus_threshold: float = 0.65,
    ):
        self.min_consensus_threshold = min_consensus_threshold
        self.strong_consensus_threshold = strong_consensus_threshold

    def evaluate_timeframe_structure(self, df: pd.DataFrame, timeframe_label: str) -> Dict[str, Any]:
        """Analyze trend, momentum, and volume characteristics of a single timeframe."""
        if df is None or len(df) < 25:
            return {
                "timeframe": timeframe_label,
                "score": 0.0,
                "direction": "NEUTRAL",
                "reason": "Insufficient bar count",
            }

        close = df["close"]
        vol = df["volume"]

        ema_fast = compute_ema(close, 9 if timeframe_label == "15m" else 20)
        ema_slow = compute_ema(close, 21 if timeframe_label == "15m" else 50)
        rsi = compute_rsi(close, 14)

        current_close = close.iloc[-1]
        fast_val = ema_fast.iloc[-1]
        slow_val = ema_slow.iloc[-1]
        rsi_val = rsi.iloc[-1] if not rsi.empty else 50.0

        # Moving average alignment score (-1.0 to +1.0)
        ma_diff_pct = (fast_val - slow_val) / slow_val
        ma_score = 0.0
        if fast_val > slow_val and current_close > fast_val:
            ma_score = 1.0
        elif fast_val > slow_val:
            ma_score = 0.5
        elif fast_val < slow_val and current_close < fast_val:
            ma_score = -1.0
        elif fast_val < slow_val:
            ma_score = -0.5

        # RSI momentum score (-1.0 to +1.0)
        rsi_score = 0.0
        if 50.0 <= rsi_val <= 68.0:
            rsi_score = 1.0  # Healthy bullish expansion
        elif rsi_val > 68.0:
            rsi_score = 0.4  # Bullish but approaching overbought
        elif 32.0 <= rsi_val < 50.0:
            rsi_score = -0.6  # Bearish drift
        elif rsi_val < 32.0:
            rsi_score = -0.3  # Oversold bounce potential

        # Volume expansion score (0.0 to 1.0)
        avg_vol = vol.rolling(20).mean().iloc[-1]
        curr_vol = vol.iloc[-1]
        rvol = (curr_vol / avg_vol) if avg_vol > 0 else 1.0

        vol_multiplier = 1.2 if rvol >= 1.5 else (1.0 if rvol >= 1.0 else 0.8)

        # Composite timeframe score
        composite = (ma_score * 0.65 + rsi_score * 0.35) * vol_multiplier
        clamped_score = float(np.clip(composite, -1.0, 1.0))

        direction = "BULLISH" if clamped_score >= 0.25 else ("BEARISH" if clamped_score <= -0.25 else "NEUTRAL")

        return {
            "timeframe": timeframe_label,
            "score": round(clamped_score, 3),
            "direction": direction,
            "rsi": round(float(rsi_val), 1),
            "rvol": round(float(rvol), 2),
            "fast_above_slow": bool(fast_val > slow_val),
            "close_above_fast": bool(current_close > fast_val),
        }

    def compute_consensus(
        self,
        tf_15m_df: Optional[pd.DataFrame] = None,
        tf_1h_df: Optional[pd.DataFrame] = None,
        tf_4h_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """Compute unified multi-horizon consensus score across available timeframes."""
        weights = {"15m": 0.20, "1h": 0.50, "4h": 0.30}
        sub_scores = {}
        weighted_sum = 0.0
        total_weight = 0.0

        if tf_15m_df is not None and not tf_15m_df.empty:
            res_15m = self.evaluate_timeframe_structure(tf_15m_df, "15m")
            sub_scores["15m"] = res_15m
            weighted_sum += res_15m["score"] * weights["15m"]
            total_weight += weights["15m"]

        if tf_1h_df is not None and not tf_1h_df.empty:
            res_1h = self.evaluate_timeframe_structure(tf_1h_df, "1h")
            sub_scores["1h"] = res_1h
            weighted_sum += res_1h["score"] * weights["1h"]
            total_weight += weights["1h"]

        if tf_4h_df is not None and not tf_4h_df.empty:
            res_4h = self.evaluate_timeframe_structure(tf_4h_df, "4h")
            sub_scores["4h"] = res_4h
            weighted_sum += res_4h["score"] * weights["4h"]
            total_weight += weights["4h"]

        consensus_score = (weighted_sum / total_weight) if total_weight > 0 else 0.0
        consensus_score = round(float(np.clip(consensus_score, -1.0, 1.0)), 3)

        # Check directional alignment
        directions = [s["direction"] for s in sub_scores.values() if s.get("direction") != "NEUTRAL"]
        is_aligned = len(directions) >= 2 and all(d == directions[0] for d in directions)

        if consensus_score >= self.strong_consensus_threshold:
            verdict = "STRONG_BUY"
        elif consensus_score >= self.min_consensus_threshold:
            verdict = "LEAN_BUY"
        elif consensus_score <= -self.strong_consensus_threshold:
            verdict = "STRONG_SELL"
        elif consensus_score <= -self.min_consensus_threshold:
            verdict = "LEAN_SELL"
        else:
            verdict = "NEUTRAL"

        is_eligible_for_buy = consensus_score >= self.min_consensus_threshold and (
            sub_scores.get("1h", {}).get("direction") in ("BULLISH", "NEUTRAL")
        )

        return {
            "consensus_score": consensus_score,
            "verdict": verdict,
            "is_aligned": is_aligned,
            "is_eligible_for_buy": is_eligible_for_buy,
            "sub_timeframes": sub_scores,
        }
