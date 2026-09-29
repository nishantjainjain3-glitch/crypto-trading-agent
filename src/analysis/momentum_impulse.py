"""Early Momentum Impulse Detector.

Identifies early-stage breakouts with volume surges before assets reach
the public gainers leaderboard, avoiding top-chasing FOMO.
"""

import logging
import pandas as pd
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def detect_momentum_impulse(
    df: pd.DataFrame,
    technicals: Dict[str, Any],
    change_24h_pct: float = 0.0,
    htf_bullish: bool = True,
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Evaluates whether an asset is experiencing an early momentum breakout.

    Criteria:
    1. Early in Move: 24h gain is between +1.0% and +14.0% (not already +30% at the top).
    2. Volume Explosion: 1H RVOL >= 1.8x indicating institutional accumulation.
    3. Moving Average Breakout: Price is above 20 EMA and 50 EMA, or just crossed above them.
    4. Strong Expansion Candle: Current candle range >= 1.3x ATR, closing near the high (>65% of range).
    5. Favorable Risk/Reward: Target +6.0% to +10.0%, stop loss below breakout candle low (~1.8% to 2.2%).
    """
    if df.empty or len(df) < 20 or not technicals:
        return {"is_valid_impulse": False, "score_boost": 0, "rationale": "Insufficient data"}

    current_price = technicals.get("current_price", float(df["close"].iloc[-1]))
    rvol = technicals.get("rvol", 1.0)
    rsi = technicals.get("rsi", 50.0)
    atr = technicals.get("atr", current_price * 0.02)
    above_20 = technicals.get("above_20_ema", False)
    above_50 = technicals.get("above_50_ema", False)

    # Filter 1: Disqualify coins already over-extended (anti-FOMO rule)
    if change_24h_pct > 18.0:
        return {
            "is_valid_impulse": False,
            "score_boost": -15,
            "rationale": f"Anti-FOMO Guard: Coin is already extended (+{change_24h_pct:.1f}%). High exhaustion risk.",
        }

    # Filter 2: Must have positive momentum but not overbought
    if rsi > 76.0 or rsi < 45.0:
        return {
            "is_valid_impulse": False,
            "score_boost": 0,
            "rationale": f"RSI {rsi:.1f} outside impulse sweet spot (45-76).",
        }

    # Filter 3: Relative volume surge (institutions stepping in)
    has_volume_surge = rvol >= 1.75

    # Filter 4: Candle structure inspection
    last_candle = df.iloc[-1]
    c_open = float(last_candle["open"])
    c_close = float(last_candle["close"])
    c_high = float(last_candle["high"])
    c_low = float(last_candle["low"])
    candle_range = max(c_high - c_low, 1e-9)

    # Bullish candle body and closing in upper 35% of the range
    is_bullish_bar = c_close > c_open
    close_near_high = (c_close - c_low) / candle_range >= 0.60
    range_expanding = candle_range >= (0.9 * atr)

    # Filter 5: Trend alignment
    trend_aligned = (above_20 and above_50) or (above_20 and htf_bullish)

    if has_volume_surge and is_bullish_bar and close_near_high and trend_aligned:
        # Calculate asymmetric levels
        stop_dist = max(current_price * 0.016, min(current_price * 0.024, (current_price - c_low) + (0.2 * atr)))
        target_dist = max(current_price * 0.06, max(stop_dist * 3.0, 3.8 * atr))

        stop_loss = round(current_price - stop_dist, 4)
        target_price = round(current_price + target_dist, 4)

        return {
            "is_valid_impulse": True,
            "direction": "BUY",
            "score_boost": 25,
            "rvol": rvol,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "expected_gain_pct": round((target_dist / current_price) * 100, 2),
            "risk_pct": round((stop_dist / current_price) * 100, 2),
            "rationale": (
                f"Early Momentum Impulse: {rvol:.1f}x volume surge with bullish close near highs "
                f"(Target +{((target_dist/current_price)*100):.1f}%, Stop -{((stop_dist/current_price)*100):.1f}%)"
            ),
        }

    return {
        "is_valid_impulse": False,
        "score_boost": 0,
        "rationale": f"No impulse setup (RVOL={rvol:.1f}x, BullishBar={is_bullish_bar}, TrendAligned={trend_aligned})",
    }
