"""Unit tests for Yang-Zhang Volatility, TCA Execution Analysis, and CPPI Drawdown Cushion."""

import pytest
import numpy as np
import pandas as pd
import tempfile
import os

from src.analysis.yang_zhang_volatility import compute_yang_zhang_volatility
from src.engine.tca_analyzer import TransactionCostAnalyzer
from src.engine.cppi_risk_cushion import CPPIRiskCushion
from src.engine.dynamic_risk_allocator import DynamicRiskAllocator


def create_synthetic_ohlcv(n_bars: int = 50, base_price: float = 100.0, vol: float = 0.02) -> pd.DataFrame:
    np.random.seed(42)
    rows = []
    price = base_price
    for _ in range(n_bars):
        open_p = price + np.random.normal(0, vol * price * 0.5)
        high_p = open_p + abs(np.random.normal(0, vol * price))
        low_p = open_p - abs(np.random.normal(0, vol * price))
        close_p = open_p + np.random.normal(0, vol * price * 0.5)
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)
        volume = float(np.random.randint(1000, 10000))
        rows.append({
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": volume,
        })
        price = close_p
    return pd.DataFrame(rows)


def test_yang_zhang_volatility_calculation():
    df = create_synthetic_ohlcv(n_bars=30, base_price=50.0, vol=0.03)
    res = compute_yang_zhang_volatility(df, window=14)

    assert "yang_zhang" in res
    assert "garman_klass" in res
    assert "parkinson" in res
    assert "close_to_close" in res
    assert "volatility_regime" in res
    assert res["yang_zhang"] > 0.0
    assert res["annualized_yz"] > 0.0
    assert res["volatility_regime"] in ["LOW_VOLATILITY", "NORMAL_VOLATILITY", "HIGH_VOLATILITY", "EXTREME_VOLATILITY"]
    assert res["recommended_stop_buffer_multiplier"] in [1.2, 1.5, 2.0]


def test_yang_zhang_insufficient_data():
    df_small = create_synthetic_ohlcv(n_bars=3)
    res = compute_yang_zhang_volatility(df_small, window=14)
    assert res["yang_zhang"] == 0.0
    assert res["volatility_regime"] == "NORMAL_VOLATILITY"


def test_tca_analyzer_recording_and_slippage():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_path = tf.name

    try:
        tca = TransactionCostAnalyzer(storage_path=temp_path)
        # Record a BUY where fill price was 100.20 and decision was 100.00 (20 bps slippage)
        rec = tca.record_execution(
            symbol="SOL/USDT",
            side="BUY",
            decision_price=100.0,
            fill_price=100.20,
            quantity=2.0,
            bid_price=99.98,
            ask_price=100.02,
            order_type="LIMIT",
        )

        assert rec["slippage_bps"] == pytest.approx(20.0, rel=1e-2)
        assert rec["total_shortfall_usd"] == pytest.approx(0.40, rel=1e-2)
        assert rec["market_impact_bps"] >= 0.0

        summary = tca.get_tca_summary()
        assert summary["total_executions"] == 1
        assert summary["avg_slippage_bps"] == pytest.approx(20.0, rel=1e-2)

        # Penalty check: 20 bps should trigger a modest penalty (> 0)
        penalty = tca.get_symbol_slippage_penalty("SOL/USDT")
        assert penalty > 0.0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_cppi_risk_cushion_healthy():
    cppi = CPPIRiskCushion(max_drawdown_pct=5.0, multiplier=3.0, min_notional_usd=5.0)
    # Peak 20.0, Current 20.0 -> 0% drawdown, floor is 19.0, cushion is 1.0
    res = cppi.evaluate_cushion(current_equity=20.0, peak_equity=20.0)
    assert res["trading_allowed"] is True
    assert res["cushion_usd"] == 1.0
    assert res["current_drawdown_pct"] == 0.0
    assert res["status"] == "HEALTHY"


def test_cppi_risk_cushion_breach_veto():
    cppi = CPPIRiskCushion(max_drawdown_pct=5.0, multiplier=3.0, min_notional_usd=5.0)
    # Peak 20.0, Current 18.8 -> 6% drawdown, below floor (19.0)
    res = cppi.evaluate_cushion(current_equity=18.8, peak_equity=20.0)
    assert res["trading_allowed"] is False
    assert res["status"] == "DRAWDOWN_FLOOR_BREACH"

    alloc = cppi.constrain_allocation(proposed_usd=10.0, current_equity=18.8, peak_equity=20.0)
    assert alloc["allowed"] is False
    assert alloc["allocated_usd"] == 0.0
    assert "CPPI_FLOOR_PROTECTION" in alloc["reason"]


def test_dynamic_risk_allocator_cppi_integration():
    allocator = DynamicRiskAllocator(
        min_notional_usd=5.0,
        max_portfolio_risk_pct=2.5,
        max_drawdown_limit_pct=5.0,
    )

    # When equity is at floor, allocate_position should veto
    res = allocator.allocate_position(
        symbol="BTC/USDT",
        entry_price=60000.0,
        stop_loss_price=59000.0,
        free_cash_usdt=10.0,
        total_equity_usdt=18.8,
        peak_equity_usdt=20.0,  # 6% drawdown > 5% limit
    )
    assert res["is_approved"] is False
    assert "CPPI" in res["reason"]
