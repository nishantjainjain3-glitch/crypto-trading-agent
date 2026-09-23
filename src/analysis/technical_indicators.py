"""Technical indicator calculations for crypto pairs."""

import pandas as pd
import numpy as np
from typing import Dict, Any

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Dict[str, pd.Series]:
    """Calculate Bollinger Bands."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return {
        "middle": sma,
        "upper": upper,
        "lower": lower,
        "bandwidth": (upper - lower) / (sma + 1e-9),
    }

def calculate_cpr_pivots(high: float, low: float, close: float) -> Dict[str, float]:
    """Calculate Central Pivot Range (CPR) and standard floor pivots."""
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (pivot - bc) + pivot
    
    cpr_top = max(tc, bc)
    cpr_bottom = min(tc, bc)
    cpr_width_pct = ((cpr_top - cpr_bottom) / pivot) * 100 if pivot else 0.0
    
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    
    return {
        "pivot": round(pivot, 4),
        "tc": round(tc, 4),
        "bc": round(bc, 4),
        "cpr_top": round(cpr_top, 4),
        "cpr_bottom": round(cpr_bottom, 4),
        "cpr_width_pct": round(cpr_width_pct, 3),
        "r1": round(r1, 4),
        "s1": round(s1, 4),
        "r2": round(r2, 4),
        "s2": round(s2, 4),
    }

def compute_all_technicals(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute complete technical dashboard metrics on OHLCV data."""
    if df.empty or len(df) < 20:
        return {}

    close = df["close"]
    volume = df["volume"]
    current_close = float(close.iloc[-1])
    current_volume = float(volume.iloc[-1])
    
    # EMAs
    ema20 = calculate_ema(close, 20)
    ema50 = calculate_ema(close, 50) if len(close) >= 50 else pd.Series(index=close.index, dtype=float)
    ema200 = calculate_ema(close, 200) if len(close) >= 200 else pd.Series(index=close.index, dtype=float)
    
    # RSI & ATR
    rsi_series = calculate_rsi(close, 14)
    atr_series = calculate_atr(df, 14)
    current_rsi = float(rsi_series.iloc[-1]) if not rsi_series.isna().iloc[-1] else 50.0
    current_atr = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (current_close * 0.02)
    
    # RVOL (Relative Volume vs 20-period average)
    vol_sma20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else current_volume
    rvol = round(current_volume / (vol_sma20 + 1e-9), 2)
    
    # Bollinger Bands
    bb = calculate_bollinger_bands(close, 20, 2.0)
    
    # CPR from previous candle high/low/close
    prev_candle = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
    cpr = calculate_cpr_pivots(
        float(prev_candle["high"]),
        float(prev_candle["low"]),
        float(prev_candle["close"]),
    )
    
    val_ema20 = float(ema20.iloc[-1])
    val_ema50 = float(ema50.iloc[-1]) if not ema50.empty and not ema50.isna().iloc[-1] else val_ema20
    val_ema200 = float(ema200.iloc[-1]) if not ema200.empty and not ema200.isna().iloc[-1] else val_ema50
    
    trend_state = "BULLISH" if current_close > val_ema20 > val_ema50 else (
        "BEARISH" if current_close < val_ema20 < val_ema50 else "RANGE_BOUND"
    )

    return {
        "current_price": current_close,
        "ema20": round(val_ema20, 4),
        "ema50": round(val_ema50, 4),
        "ema200": round(val_ema200, 4),
        "trend_state": trend_state,
        "above_20_ema": current_close > val_ema20,
        "above_50_ema": current_close > val_ema50,
        "above_200_ema": current_close > val_ema200,
        "rsi": round(current_rsi, 2),
        "atr": round(current_atr, 4),
        "atr_pct": round((current_atr / current_close) * 100, 2),
        "rvol": rvol,
        "volume": current_volume,
        "bb_upper": round(float(bb["upper"].iloc[-1]), 4) if not bb["upper"].isna().iloc[-1] else 0.0,
        "bb_lower": round(float(bb["lower"].iloc[-1]), 4) if not bb["lower"].isna().iloc[-1] else 0.0,
        "cpr": cpr,
    }
