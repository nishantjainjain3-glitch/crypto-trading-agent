"""Institutional liquidity sweep (SSL/BSL) detection engine for crypto."""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

def detect_liquidity_sweep(
    df: pd.DataFrame,
    lookback_candles: int = 20,
    min_wick_ratio: float = 0.35,
    min_volume_ratio: float = 1.25,
) -> Optional[Dict[str, Any]]:
    """
    Detect whether the latest candles formed a false breakdown (Sell-Side Liquidity Sweep)
    or false breakout (Buy-Side Liquidity Sweep).
    
    A Bullish Liquidity Sweep (SSL Sweep):
    1. Swing low established in the lookback window.
    2. Current or previous candle drops below the swing low.
    3. Reclaims the swing low before close, leaving a long lower shadow (rejection wick).
    4. Confirmed by volume surge (RVOL >= min_volume_ratio).
    """
    if df.empty or len(df) < lookback_candles + 2:
        return None

    recent_df = df.iloc[-lookback_candles - 2 : -2]
    swing_low = float(recent_df["low"].min())
    swing_high = float(recent_df["high"].max())

    trigger_candle = df.iloc[-2]
    current_candle = df.iloc[-1]
    
    vol_sma = float(df["volume"].rolling(20).mean().iloc[-1])
    rvol = float(trigger_candle["volume"]) / (vol_sma + 1e-9)

    # Bullish SSL Sweep (Long Setup)
    # Check if trigger candle pierced below swing low but closed above it
    cand_low = float(trigger_candle["low"])
    cand_close = float(trigger_candle["close"])
    cand_high = float(trigger_candle["high"])
    cand_open = float(trigger_candle["open"])
    
    candle_range = cand_high - cand_low
    lower_wick = min(cand_open, cand_close) - cand_low
    wick_ratio = lower_wick / (candle_range + 1e-9)

    if cand_low < swing_low and cand_close > swing_low and wick_ratio >= min_wick_ratio:
        if rvol >= min_volume_ratio:
            entry_price = float(current_candle["close"])
            stop_loss = round(cand_low * 0.998, 4)  # Small buffer under wick
            risk_per_unit = entry_price - stop_loss
            if risk_per_unit > 0:
                target_price = round(entry_price + (risk_per_unit * 2.0), 4)
                return {
                    "setup": "BULLISH_SSL_SWEEP",
                    "direction": "BUY",
                    "swept_level": swing_low,
                    "wick_low": cand_low,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "target_price": target_price,
                    "risk_to_reward": round((target_price - entry_price) / risk_per_unit, 2),
                    "rvol": round(rvol, 2),
                    "wick_ratio": round(wick_ratio, 2),
                    "confidence": "HIGH" if rvol >= 1.5 else "MEDIUM",
                    "rationale": f"Swept liquidity below swing low ${swing_low:.2f} with {rvol:.1f}x volume rejection.",
                }

    # Bearish BSL Sweep (Short Setup / Exit Longs)
    upper_wick = cand_high - max(cand_open, cand_close)
    upper_wick_ratio = upper_wick / (candle_range + 1e-9)
    if cand_high > swing_high and cand_close < swing_high and upper_wick_ratio >= min_wick_ratio:
        if rvol >= min_volume_ratio:
            entry_price = float(current_candle["close"])
            stop_loss = round(cand_high * 1.002, 4)
            risk_per_unit = stop_loss - entry_price
            if risk_per_unit > 0:
                target_price = round(entry_price - (risk_per_unit * 2.0), 4)
                return {
                    "setup": "BEARISH_BSL_SWEEP",
                    "direction": "SELL",
                    "swept_level": swing_high,
                    "wick_high": cand_high,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "target_price": target_price,
                    "risk_to_reward": round((entry_price - target_price) / risk_per_unit, 2),
                    "rvol": round(rvol, 2),
                    "wick_ratio": round(upper_wick_ratio, 2),
                    "confidence": "HIGH" if rvol >= 1.5 else "MEDIUM",
                    "rationale": f"Swept liquidity above swing high ${swing_high:.2f} with {rvol:.1f}x volume rejection.",
                }

    return None
