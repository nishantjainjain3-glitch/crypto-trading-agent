"""Dual-Regime Strategy Orchestrator.

Detects macro and pair-level market regimes (Trending vs. Ranging) and routes
execution between Momentum Breakouts and Range Mean-Reversion.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


class DualStrategyOrchestrator:
    """Classifies pair market regime and generates appropriate strategy signals."""

    def __init__(
        self,
        adx_trend_threshold: float = 23.0,
        adx_range_threshold: float = 19.0,
    ):
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_range_threshold = adx_range_threshold

    def calculate_adx_approx(self, df: pd.DataFrame, period: int = 14) -> float:
        """Approximate Average Directional Index (ADX) to gauge trend strength."""
        if len(df) < period + 5:
            return 20.0

        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()

        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        plus_di = 100.0 * (pd.Series(plus_dm).rolling(period).mean() / (atr + 1e-9))
        minus_di = 100.0 * (pd.Series(minus_dm).rolling(period).mean() / (atr + 1e-9))

        dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
        adx = dx.rolling(period).mean().iloc[-1]

        return float(adx) if not np.isnan(adx) else 20.0

    def detect_regime(self, df: pd.DataFrame, technicals: Dict[str, Any]) -> str:
        """Classify current regime as TRENDING_EXPANSION, RANGING_CONSOLIDATION, or TRANSITIONAL."""
        adx = self.calculate_adx_approx(df)

        close = df["close"]
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_width = ((std20 * 4.0) / (sma20 + 1e-9)).iloc[-1] if len(close) >= 20 else 0.05

        if adx >= self.adx_trend_threshold:
            return "TRENDING_EXPANSION"
        elif adx <= self.adx_range_threshold or bb_width < 0.035:
            return "RANGING_CONSOLIDATION"
        else:
            return "TRANSITIONAL"

    def evaluate_mean_reversion_candidate(
        self,
        symbol: str,
        df: pd.DataFrame,
        technicals: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Evaluate pair for range-bound mean-reversion setup (buy range support, target midline)."""
        if len(df) < 25:
            return None

        close = df["close"]
        low = df["low"]
        high = df["high"]

        range_low = low.rolling(20).min().iloc[-1]
        range_high = high.rolling(20).max().iloc[-1]
        midline = (range_high + range_low) / 2.0

        current_price = close.iloc[-1]
        range_span = range_high - range_low
        if range_span <= 0:
            return None

        price_position_in_range = (current_price - range_low) / range_span
        rsi = technicals.get("rsi", 50.0)

        # Candidate criteria: Price is in lower 20% of range with oversold/turning RSI (30-45)
        if price_position_in_range <= 0.22 and rsi <= 45.0:
            stop_loss = round(range_low * 0.985, 4)  # 1.5% below range low
            target_price = round(midline, 4)

            risk = current_price - stop_loss
            reward = target_price - current_price
            if risk > 0 and (reward / risk) >= 1.5:
                return {
                    "strategy": "RANGE_MEAN_REVERSION",
                    "symbol": symbol,
                    "direction": "BUY",
                    "entry_price": current_price,
                    "stop_loss": stop_loss,
                    "target_price": target_price,
                    "range_low": round(range_low, 4),
                    "range_high": round(range_high, 4),
                    "reward_to_risk": round(reward / risk, 2),
                    "rationale": f"Mean Reversion: Price at lower {price_position_in_range*100:.0f}% of range (RSI {rsi:.1f}), targeting midline ${midline:.4f}",
                }

        return None
