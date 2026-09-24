"""Unit tests for institutional quantitative risk metrics and Binance smart money signals."""

import pytest
import pandas as pd
import numpy as np
from src.analysis.risk_metrics import PortfolioRiskEngine, _approx_norm_ppf
from src.analysis.smart_money_signals import analyze_smart_money_backing


def test_approx_norm_ppf():
    # Known quantiles for standard normal distribution
    assert abs(_approx_norm_ppf(0.5) - 0.0) < 1e-4
    assert abs(_approx_norm_ppf(0.95) - 1.64485) < 1e-3
    assert abs(_approx_norm_ppf(0.99) - 2.32634) < 1e-3
    assert abs(_approx_norm_ppf(0.05) - (-1.64485)) < 1e-3


def test_portfolio_risk_engine_metrics():
    # Synthetic return series with negative skew and fat tails
    np.random.seed(42)
    normal_rets = np.random.normal(0.001, 0.02, 100)
    # Add negative crash tails (characteristic of crypto)
    normal_rets[10] = -0.08
    normal_rets[25] = -0.06
    normal_rets[50] = 0.07

    returns = pd.Series(normal_rets)
    engine = PortfolioRiskEngine(returns)
    metrics = engine.compute_all_metrics(confidence=0.95)

    assert metrics["status"] == "OK"
    assert metrics["sample_size"] == 100
    assert metrics["var_historical_pct"] > 0
    assert metrics["var_cornish_fisher_pct"] > 0
    assert metrics["cvar_expected_shortfall_pct"] >= metrics["var_historical_pct"]
    assert "sharpe_ratio" in metrics
    assert "sortino_ratio" in metrics
    assert metrics["max_drawdown_pct"] > 0


def test_analyze_smart_money_fallback():
    # Non-existent ticker fallback
    res = analyze_smart_money_backing("NONEXISTENT_COIN/USDT")
    assert isinstance(res, dict)
    assert res["has_signal"] is False
    assert res["is_accumulating"] is False
    assert res["direction"] == "NEUTRAL"
