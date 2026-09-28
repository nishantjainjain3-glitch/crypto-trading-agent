"""OctoBot-inspired Dip Analyser: detects oversold pullbacks into support within macro uptrends."""

import pandas as pd
from typing import Dict, Any, Optional

def analyze_dip_setup(
    df: pd.DataFrame,
    technicals: Dict[str, Any],
    htf_bullish: bool = True,
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Evaluates whether an asset is in a valid Dip Buy configuration.
    
    Principles adapted from OctoBot's Dip Analyser:
    1. Macro Uptrend: Higher timeframe (4H) must be bullish (Price > 50 EMA).
    2. Tactical Dip: 1H RSI is pulled back (RSI <= 40 or oversold).
    3. Structural Support: Price is touching or near lower Bollinger Band or CPR S1.
    4. Asymmetric Risk/Reward: Target is reversion to upper band / EMA (+4.5% to +6.0%),
       with stop loss placed tightly below the dip low (-1.5% to -2.0%).
    """
    if df.empty or len(df) < 20 or not technicals:
        return {"is_valid_dip": False, "score_boost": 0, "rationale": "Insufficient data"}

    current_price = technicals.get("current_price", float(df["close"].iloc[-1]))
    rsi = technicals.get("rsi", 50.0)
    bb_lower = technicals.get("bb_lower", 0.0)
    ema50 = technicals.get("ema50", 0.0)
    atr = technicals.get("atr", current_price * 0.02)
    cpr = technicals.get("cpr", {})
    s1 = cpr.get("s1", 0.0)

    # Filter 1: Must have macro uptrend support
    if not htf_bullish:
        return {
            "is_valid_dip": False,
            "score_boost": -10,
            "rationale": "Macro trend is not bullish; dips are dangerous to buy.",
        }

    # Filter 2: RSI oversold or healthy pullback zone (RSI between 25 and 42)
    is_rsi_dip = 20.0 <= rsi <= 42.0

    # Filter 3: Support zone test (near or below lower Bollinger Band, or within 0.5% of CPR S1)
    is_bb_dip = (bb_lower > 0) and (current_price <= bb_lower * 1.012)
    is_s1_dip = (s1 > 0) and (abs(current_price - s1) / current_price <= 0.008)
    near_support = is_bb_dip or is_s1_dip

    # Filter 4: Reversal wick / rejection candle (current candle's lower shadow is > 30% of range)
    last_candle = df.iloc[-1]
    c_open = float(last_candle["open"])
    c_close = float(last_candle["close"])
    c_high = float(last_candle["high"])
    c_low = float(last_candle["low"])
    total_range = max(c_high - c_low, 1e-9)
    lower_shadow = min(c_open, c_close) - c_low
    has_reversal_wick = (lower_shadow / total_range) >= 0.28

    if is_rsi_dip and near_support:
        stop_dist = max(current_price * 0.015, min(current_price * 0.022, 1.5 * atr))
        target_dist = max(current_price * 0.045, 3.5 * atr)
        
        score_boost = 20 if has_reversal_wick else 15
        support_type = "Lower Bollinger Band" if is_bb_dip else "CPR S1 Support"
        
        return {
            "is_valid_dip": True,
            "direction": "BUY",
            "score_boost": score_boost,
            "stop_loss": round(current_price - stop_dist, 4),
            "target_price": round(current_price + target_dist, 4),
            "expected_gain_pct": round((target_dist / current_price) * 100, 2),
            "risk_pct": round((stop_dist / current_price) * 100, 2),
            "rationale": (
                f"OctoBot Dip Buy Signal: RSI at {rsi:.1f} bouncing off {support_type} "
                f"with 4H trend alignment (Target +{((target_dist/current_price)*100):.1f}%, Stop -{((stop_dist/current_price)*100):.1f}%)"
            ),
        }

    return {
        "is_valid_dip": False,
        "score_boost": 0,
        "rationale": f"No dip setup (RSI={rsi:.1f}, near_support={near_support})",
    }
