"""Yang-Zhang (2000) Multi-Component Unbiased Volatility Estimator.

Computes the minimum-variance unbiased estimator of asset price volatility,
accounting for both overnight gap variance and intraday continuous drift.
Superior to standard close-to-close volatility and Parkinson high-low estimators.
"""

import math
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def compute_yang_zhang_volatility(
    df: pd.DataFrame,
    window: int = 14,
    annual_factor: float = 365.0 * 24.0,  # Hourly default; 365 for daily
) -> Dict[str, Any]:
    """
    Calculate Yang-Zhang, Garman-Klass, Parkinson, and Close-to-Close volatility.

    Parameters:
    - df: DataFrame with columns 'open', 'high', 'low', 'close'
    - window: lookback window length
    - annual_factor: periods per year (e.g. 365*24 for 1h candles)
    """
    if len(df) < max(window + 1, 5):
        return {
            "yang_zhang": 0.0,
            "garman_klass": 0.0,
            "parkinson": 0.0,
            "close_to_close": 0.0,
            "volatility_regime": "NORMAL_VOLATILITY",
            "annualized_yz": 0.0,
            "sample_size": len(df),
        }

    sub_df = df.iloc[-window - 1:].copy()
    opens = sub_df["open"].values[1:]
    highs = sub_df["high"].values[1:]
    lows = sub_df["low"].values[1:]
    closes = sub_df["close"].values[1:]
    prev_closes = sub_df["close"].values[:-1]

    n = len(opens)
    if n < 3:
        return {
            "yang_zhang": 0.0,
            "garman_klass": 0.0,
            "parkinson": 0.0,
            "close_to_close": 0.0,
            "volatility_regime": "NORMAL_VOLATILITY",
            "annualized_yz": 0.0,
            "sample_size": n,
        }

    # Log prices
    u = np.log(opens / prev_closes)       # Overnight jumps
    c = np.log(closes / opens)            # Intraday open-to-close
    h = np.log(highs / opens)             # Normalized high
    l = np.log(lows / opens)              # Normalized low

    # 1. Overnight jump variance (Vo)
    u_mean = np.mean(u)
    v_o = np.sum((u - u_mean) ** 2) / (n - 1)

    # 2. Continuous open-to-close variance (Vc)
    c_mean = np.mean(c)
    v_c = np.sum((c - c_mean) ** 2) / (n - 1)

    # 3. Rogers-Satchell variance (Vrs)
    v_rs = np.mean(h * (h - c) + l * (l - c))

    # 4. Yang-Zhang weighting factor k
    k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))

    # 5. Combined Yang-Zhang variance
    v_yz = v_o + k * v_c + (1.0 - k) * v_rs
    yz_vol = math.sqrt(max(0.0, v_yz))

    # Alternative estimators for cross-validation:
    # Garman-Klass (1980)
    gk_var = np.mean(0.5 * (np.log(highs / lows) ** 2) - (2.0 * math.log(2.0) - 1.0) * (np.log(closes / opens) ** 2))
    gk_vol = math.sqrt(max(0.0, gk_var))

    # Parkinson (1980)
    park_var = np.mean((np.log(highs / lows) ** 2) / (4.0 * math.log(2.0)))
    park_vol = math.sqrt(max(0.0, park_var))

    # Standard Close-to-Close
    log_returns = np.log(closes / prev_closes)
    c2c_vol = float(np.std(log_returns, ddof=1))

    # Annualized Yang-Zhang
    annualized_yz = yz_vol * math.sqrt(annual_factor)

    # Regime categorization based on annualized volatility
    if annualized_yz < 0.25:
        regime = "LOW_VOLATILITY"
    elif annualized_yz <= 0.65:
        regime = "NORMAL_VOLATILITY"
    elif annualized_yz <= 1.20:
        regime = "HIGH_VOLATILITY"
    else:
        regime = "EXTREME_VOLATILITY"

    return {
        "yang_zhang": round(float(yz_vol), 6),
        "garman_klass": round(float(gk_vol), 6),
        "parkinson": round(float(park_vol), 6),
        "close_to_close": round(float(c2c_vol), 6),
        "annualized_yz": round(float(annualized_yz), 4),
        "volatility_regime": regime,
        "sample_size": n,
        "recommended_stop_buffer_multiplier": round(
            1.2 if regime == "LOW_VOLATILITY" else (1.5 if regime == "NORMAL_VOLATILITY" else 2.0),
            2,
        ),
    }
