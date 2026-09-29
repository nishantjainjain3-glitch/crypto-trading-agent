"""Unit tests for the Early Momentum Impulse Detector."""

import pytest
import pandas as pd
from src.analysis.momentum_impulse import detect_momentum_impulse


def test_detect_momentum_impulse_identifies_breakout():
    rows = []
    base = 10.0
    for i in range(25):
        rows.append({
            "timestamp": 1700000000000 + i * 3600000,
            "open": base + i * 0.05,
            "high": base + i * 0.05 + 0.10,
            "low": base + i * 0.05 - 0.05,
            "close": base + i * 0.05 + 0.08,
            "volume": 1000.0,
        })
    # Last candle: strong breakout bar closing at highs
    rows[-1] = {
        "timestamp": 1700000000000 + 24 * 3600000,
        "open": 11.20,
        "high": 11.80,
        "low": 11.15,
        "close": 11.75,
        "volume": 3500.0,
    }
    df = pd.DataFrame(rows)

    technicals = {
        "current_price": 11.75,
        "rvol": 2.8,
        "rsi": 62.0,
        "atr": 0.35,
        "above_20_ema": True,
        "above_50_ema": True,
        "htf_bullish": True,
    }

    signal = detect_momentum_impulse(
        df=df,
        technicals=technicals,
        change_24h_pct=5.5,
        htf_bullish=True,
        symbol="TEST/USDT",
    )

    assert signal["is_valid_impulse"] is True
    assert signal["score_boost"] == 25
    assert signal["target_price"] > 11.75
    assert signal["stop_loss"] < 11.75
    assert signal["expected_gain_pct"] >= 6.0
    assert signal["risk_pct"] <= 2.5


def test_detect_momentum_impulse_rejects_extended_fomo():
    df = pd.DataFrame([{"open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000}] * 25)
    technicals = {
        "current_price": 15.0,
        "rvol": 3.0,
        "rsi": 82.0,
        "atr": 0.5,
        "above_20_ema": True,
        "above_50_ema": True,
    }

    # Already +35% (like NMR on the gainers list)
    signal = detect_momentum_impulse(
        df=df,
        technicals=technicals,
        change_24h_pct=35.0,
        htf_bullish=True,
        symbol="FOMO/USDT",
    )

    assert signal["is_valid_impulse"] is False
    assert "Anti-FOMO Guard" in signal["rationale"]


def test_detect_momentum_impulse_rejects_low_volume():
    df = pd.DataFrame([{"open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000}] * 25)
    technicals = {
        "current_price": 10.5,
        "rvol": 0.9,
        "rsi": 55.0,
        "atr": 0.2,
        "above_20_ema": True,
        "above_50_ema": True,
    }

    signal = detect_momentum_impulse(
        df=df,
        technicals=technicals,
        change_24h_pct=3.0,
        htf_bullish=True,
        symbol="LOWVOL/USDT",
    )

    assert signal["is_valid_impulse"] is False
