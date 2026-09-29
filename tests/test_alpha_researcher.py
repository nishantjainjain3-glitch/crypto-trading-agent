import pytest
import pandas as pd
import numpy as np
from src.engine.alpha_researcher import QuantitativeAlphaResearcher


def generate_ohlcv_sample(num_bars: int = 120) -> pd.DataFrame:
    np.random.seed(42)
    closes = 100.0 + np.cumsum(np.random.normal(0.1, 1.0, num_bars))
    highs = closes + np.abs(np.random.normal(0.5, 0.2, num_bars))
    lows = closes - np.abs(np.random.normal(0.5, 0.2, num_bars))
    opens = closes - np.random.normal(0, 0.2, num_bars)
    volumes = np.random.uniform(500, 2000, num_bars)

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def test_compute_performance_metrics():
    researcher = QuantitativeAlphaResearcher()
    pnls = [2.5, 3.1, -1.2, 4.0, -1.5, 2.0, -0.8, 3.5]
    metrics = researcher.compute_performance_metrics(pnls)

    assert metrics["total_trades"] == 8
    assert metrics["win_rate_pct"] > 50.0
    assert metrics["profit_factor"] > 1.0
    assert "institutional_score" in metrics
    assert metrics["qualification"] in ("INSTITUTIONAL_READY", "CANDIDATE", "UNQUALIFIED")


def test_strategy_momentum_impulse_execution():
    researcher = QuantitativeAlphaResearcher()
    df = generate_ohlcv_sample(100)
    pnls = researcher.strategy_momentum_impulse(df)

    # Returns a list of trade percentage returns
    assert isinstance(pnls, list)


def test_strategy_donchian_breakout():
    researcher = QuantitativeAlphaResearcher()
    df = generate_ohlcv_sample(100)
    pnls = researcher.strategy_donchian_breakout(df, window=15)

    assert isinstance(pnls, list)


def test_evaluate_strategy_on_ohlcv():
    researcher = QuantitativeAlphaResearcher()
    df = generate_ohlcv_sample(100)
    res = researcher.evaluate_strategy_on_ohlcv("MOMENTUM_IMPULSE", df)

    assert "strategy_name" in res
    assert res["strategy_name"] == "MOMENTUM_IMPULSE"
    assert "institutional_score" in res
