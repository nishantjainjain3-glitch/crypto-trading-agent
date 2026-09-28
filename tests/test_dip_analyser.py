"""Unit tests for the OctoBot-inspired Dip Analyser."""

import pandas as pd
import numpy as np
from src.analysis.dip_analyser import analyze_dip_setup

def test_dip_analyser_identifies_valid_dip():
    # Construct 30 candles of dummy data
    np.random.seed(42)
    n = 30
    closes = [100.0 - i * 0.5 for i in range(n)] # downward sloping into support
    df = pd.DataFrame({
        "open": [c + 0.1 for c in closes],
        "high": [c + 0.5 for c in closes],
        "low": [c - 0.8 for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
    })
    
    # Last candle has a bullish hammer wick
    df.iloc[-1, df.columns.get_loc("open")] = 85.0
    df.iloc[-1, df.columns.get_loc("close")] = 85.5
    df.iloc[-1, df.columns.get_loc("high")] = 86.0
    df.iloc[-1, df.columns.get_loc("low")] = 83.0 # long lower shadow
    
    technicals = {
        "current_price": 85.5,
        "rsi": 32.0, # oversold pullback
        "bb_lower": 85.0, # at lower band
        "ema50": 88.0,
        "atr": 2.0,
        "cpr": {"s1": 85.2},
    }
    
    res = analyze_dip_setup(df, technicals, htf_bullish=True, symbol="SOL/USDT")
    assert res["is_valid_dip"] is True
    assert res["direction"] == "BUY"
    assert res["target_price"] > 85.5
    assert res["stop_loss"] < 85.5
    assert res["expected_gain_pct"] >= 4.5
    assert res["risk_pct"] <= 2.2

def test_dip_analyser_rejects_macro_downtrend():
    df = pd.DataFrame({"open": [100]*25, "high": [101]*25, "low": [99]*25, "close": [100]*25})
    technicals = {"current_price": 100, "rsi": 30.0, "bb_lower": 100}
    res = analyze_dip_setup(df, technicals, htf_bullish=False, symbol="BTC/USDT")
    assert res["is_valid_dip"] is False
    assert "Macro trend" in res["rationale"]
