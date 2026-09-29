import pytest
import pandas as pd
import numpy as np
from src.analysis.multi_horizon_consensus import MultiHorizonConsensusEngine


def generate_mock_trending_df(length: int = 50, trend: str = "bullish") -> pd.DataFrame:
    """Generate realistic OHLCV dataframe with specified trend."""
    np.random.seed(42)
    step = 0.5 if trend == "bullish" else (-0.5 if trend == "bearish" else 0.0)
    base = 100.0
    closes = [base + i * step + np.random.normal(0, 0.2) for i in range(length)]
    highs = [c + abs(np.random.normal(0.4, 0.1)) for c in closes]
    lows = [c - abs(np.random.normal(0.4, 0.1)) for c in closes]
    opens = [closes[max(0, i - 1)] for i in range(length)]
    volumes = [1000.0 + i * 10 + np.random.normal(0, 50) for i in range(length)]

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def test_timeframe_evaluation_bullish():
    engine = MultiHorizonConsensusEngine()
    df = generate_mock_trending_df(60, "bullish")
    res = engine.evaluate_timeframe_structure(df, "1h")

    assert res["timeframe"] == "1h"
    assert res["score"] > 0.0
    assert res["direction"] == "BULLISH"
    assert res["fast_above_slow"] is True


def test_timeframe_evaluation_bearish():
    engine = MultiHorizonConsensusEngine()
    df = generate_mock_trending_df(60, "bearish")
    res = engine.evaluate_timeframe_structure(df, "1h")

    assert res["timeframe"] == "1h"
    assert res["score"] < 0.0
    assert res["direction"] == "BEARISH"
    assert res["fast_above_slow"] is False


def test_consensus_aligned_bullish():
    engine = MultiHorizonConsensusEngine()
    df_15m = generate_mock_trending_df(50, "bullish")
    df_1h = generate_mock_trending_df(60, "bullish")
    df_4h = generate_mock_trending_df(70, "bullish")

    consensus = engine.compute_consensus(df_15m, df_1h, df_4h)
    assert consensus["consensus_score"] >= 0.35
    assert consensus["is_aligned"] is True
    assert consensus["is_eligible_for_buy"] is True
    assert consensus["verdict"] in ("STRONG_BUY", "LEAN_BUY")


def test_consensus_conflicted_signals():
    engine = MultiHorizonConsensusEngine()
    df_15m = generate_mock_trending_df(50, "bearish")
    df_1h = generate_mock_trending_df(60, "bullish")
    df_4h = generate_mock_trending_df(70, "bearish")

    consensus = engine.compute_consensus(df_15m, df_1h, df_4h)
    # When signals oppose each other, score is muted and not unanimously aligned
    assert consensus["is_aligned"] is False
