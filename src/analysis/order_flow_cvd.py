"""Order Flow Cumulative Volume Delta (CVD) and Liquidation Cluster Analyzer.

Analyzes aggressive taker buy versus sell volume across Binance trade streams
to detect absorption, divergence, and margin liquidation clusters.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


class OrderFlowCVDAnalyzer:
    """Calculates Cumulative Volume Delta and order flow divergence metrics."""

    def __init__(self, divergence_lookback: int = 14):
        self.divergence_lookback = divergence_lookback

    def compute_cvd_from_trades(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute Cumulative Volume Delta and taker buy/sell ratio from raw public trade data."""
        if not trades:
            return {
                "cvd_value": 0.0,
                "taker_buy_vol": 0.0,
                "taker_sell_vol": 0.0,
                "buy_ratio": 0.50,
                "imbalance": "BALANCED",
                "divergence": "NONE",
            }

        buy_vol = 0.0
        sell_vol = 0.0

        for t in trades:
            qty = float(t.get("amount", t.get("qty", 0.0)))
            side = t.get("side", "").lower()
            if side == "buy":
                buy_vol += qty
            elif side == "sell":
                sell_vol += qty

        total_vol = buy_vol + sell_vol
        cvd_value = round(buy_vol - sell_vol, 4)
        buy_ratio = round(buy_vol / total_vol, 3) if total_vol > 0 else 0.50

        if buy_ratio >= 0.65:
            imbalance = "HEAVY_BUY_ABSORPTION"
        elif buy_ratio <= 0.35:
            imbalance = "HEAVY_SELL_PRESSURE"
        else:
            imbalance = "BALANCED"

        return {
            "cvd_value": cvd_value,
            "taker_buy_vol": round(buy_vol, 4),
            "taker_sell_vol": round(sell_vol, 4),
            "buy_ratio": buy_ratio,
            "imbalance": imbalance,
        }

    def detect_cvd_divergence(
        self,
        prices: List[float],
        cvd_series: List[float],
    ) -> Dict[str, Any]:
        """Detect bullish or bearish divergence between price action and cumulative volume delta."""
        if len(prices) < self.divergence_lookback or len(cvd_series) < self.divergence_lookback:
            return {"divergence": "NONE", "strength": 0.0, "reason": "Insufficient data points"}

        p_window = np.array(prices[-self.divergence_lookback:])
        cvd_window = np.array(cvd_series[-self.divergence_lookback:])

        price_slope = float(p_window[-1] - p_window[0]) / p_window[0] if p_window[0] > 0 else 0.0
        cvd_slope = float(cvd_window[-1] - cvd_window[0])

        # Bullish Absorption Divergence: Price falling or flat, but aggressive CVD rising
        if price_slope <= -0.005 and cvd_slope > 0:
            strength = min(1.0, abs(price_slope) * 15.0)
            return {
                "divergence": "BULLISH_ABSORPTION",
                "strength": round(strength, 2),
                "reason": "Price made lower low while aggressive taker CVD rose (smart money limit absorption)",
            }

        # Bearish Exhaustion Divergence: Price rising, but aggressive CVD falling
        if price_slope >= 0.005 and cvd_slope < 0:
            strength = min(1.0, abs(price_slope) * 15.0)
            return {
                "divergence": "BEARISH_EXHAUSTION",
                "strength": round(strength, 2),
                "reason": "Price made higher high while aggressive taker CVD fell (buyer exhaustion)",
            }

        return {
            "divergence": "NONE",
            "strength": 0.0,
            "reason": "Price and CVD trajectory are aligned",
        }

    def estimate_liquidation_clusters(
        self,
        current_price: float,
        atr: float,
        leverage_tiers: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Estimate long and short liquidation clusters based on common leverage brackets (10x, 20x, 50x)."""
        if current_price <= 0:
            return {"long_liquidation_band": 0.0, "short_liquidation_band": 0.0}

        tiers = leverage_tiers or [10, 20, 50]
        long_clusters = []
        short_clusters = []

        for lev in tiers:
            # Liquidation threshold approximately (1 / leverage) distance
            liq_dist_pct = 1.0 / lev
            long_liq = current_price * (1.0 - liq_dist_pct)
            short_liq = current_price * (1.0 + liq_dist_pct)
            long_clusters.append(round(long_liq, 4))
            short_clusters.append(round(short_liq, 4))

        # Nearest liquidation magnets
        nearest_short_squeeze = min(short_clusters)
        nearest_long_flush = max(long_clusters)

        return {
            "nearest_short_squeeze_level": nearest_short_squeeze,
            "nearest_long_flush_level": nearest_long_flush,
            "short_liquidation_levels": short_clusters,
            "long_liquidation_levels": long_clusters,
            "squeeze_upside_pct": round(((nearest_short_squeeze - current_price) / current_price) * 100, 2),
            "flush_downside_pct": round(((nearest_long_flush - current_price) / current_price) * 100, 2),
        }
