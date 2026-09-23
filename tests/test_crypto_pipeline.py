"""Unit tests for the Crypto Trading Agent pipeline."""

import os
import shutil
import pytest
import pandas as pd
import numpy as np

from src.analysis.technical_indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_cpr_pivots,
    compute_all_technicals,
)
from src.analysis.liquidity_sweep import detect_liquidity_sweep
from src.engine.position_sizer import PositionSizer
from src.engine.crypto_gatekeeper import CryptoTradeGatekeeper
from src.engine.crypto_paper_trader import CryptoPaperTrader
from src.analysis.backtest_runner import CryptoBacktester

TEST_DATA_DIR = "test_data_dir"

@pytest.fixture(autouse=True)
def clean_test_dir():
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    yield
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)

def test_position_sizer_atr_math():
    sizer = PositionSizer(total_capital=10000.0, risk_pct_per_trade=1.0, max_capital_per_trade_pct=33.33)
    # Entry: 50000, Stop: 49000 -> Distance 1000, Target risk: 100 USD -> Qty: 0.1 BTC ($5000)
    res = sizer.calculate_size(
        symbol="BTC/USDT",
        entry_price=50000.0,
        stop_loss=49000.0,
        atr=1000.0,
        current_equity=10000.0,
    )
    assert res["target_risk_usd"] == 100.0
    assert res["stop_distance"] == 1000.0
    # Because max_capital_per_trade_pct is 33.33% ($3333), 0.1 BTC ($5000) should be capped!
    assert res["was_capped"] is True
    assert res["allocated_capital_usd"] <= 3333.34

def test_gatekeeper_veto_logic():
    gate = CryptoTradeGatekeeper(min_reward_to_risk=1.5, min_rvol=1.2, max_concurrent_positions=2, daily_loss_limit_usd=500.0)
    
    # Test 1: Low Reward-to-Risk (Entry 100, Stop 95, Target 105 -> RR 1.0 < 1.5)
    passed, verdict, vetoes = gate.evaluate_candidate(
        symbol="SOL/USDT",
        direction="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target_price=105.0,
        technicals={"rvol": 1.5, "above_20_ema": True, "rsi": 55.0},
        active_positions={},
        daily_pnl_usd=0.0,
    )
    assert not passed
    assert any("INSUFFICIENT_RR" in v for v in vetoes)

    # Test 2: Low Volume (RVOL 0.8 < 1.2)
    passed, verdict, vetoes = gate.evaluate_candidate(
        symbol="SOL/USDT",
        direction="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        technicals={"rvol": 0.8, "above_20_ema": True, "rsi": 55.0},
        active_positions={},
        daily_pnl_usd=0.0,
    )
    assert not passed
    assert any("INSUFFICIENT_VOLUME" in v for v in vetoes)

    # Test 3: Approved candidate (RR 2.0, RVOL 1.5, RSI 55)
    passed, verdict, vetoes = gate.evaluate_candidate(
        symbol="SOL/USDT",
        direction="BUY",
        entry_price=100.0,
        stop_loss=95.0,
        target_price=110.0,
        technicals={"rvol": 1.5, "above_20_ema": True, "rsi": 55.0},
        active_positions={},
        daily_pnl_usd=0.0,
    )
    assert passed
    assert verdict == "APPROVED"
    assert len(vetoes) == 0

def test_liquidity_sweep_detection():
    # Construct a synthetic DataFrame where a candle pierces swing low and reclaims on high volume
    dates = pd.date_range("2026-01-01", periods=25, freq="1h")
    # Prices steady at 100
    df = pd.DataFrame({
        "open": [100.0] * 25,
        "high": [102.0] * 25,
        "low": [98.0] * 25,
        "close": [100.0] * 25,
        "volume": [1000.0] * 25,
    }, index=dates)

    # Trigger candle at index -2: swings down to 94 (below swing low 98), closes at 99 with long wick and 2.5x volume
    df.iloc[-2, df.columns.get_loc("low")] = 94.0
    df.iloc[-2, df.columns.get_loc("open")] = 99.5
    df.iloc[-2, df.columns.get_loc("close")] = 99.0
    df.iloc[-2, df.columns.get_loc("volume")] = 2500.0

    sweep = detect_liquidity_sweep(df, lookback_candles=20)
    assert sweep is not None
    assert sweep["setup"] == "BULLISH_SSL_SWEEP"
    assert sweep["direction"] == "BUY"
    assert sweep["swept_level"] == 98.0
    assert sweep["risk_to_reward"] >= 1.5

def test_paper_trader_execution_and_ledger():
    trader = CryptoPaperTrader(data_dir=TEST_DATA_DIR, initial_capital_usdt=10000.0)
    
    # Open Position
    pos = trader.open_position(
        symbol="ETH/USDT",
        direction="BUY",
        entry_price=3000.0,
        quantity=1.0,
        stop_loss=2900.0,
        target_price=3300.0,
        atr=50.0,
    )
    assert pos["symbol"] == "ETH/USDT"
    assert len(trader.positions) == 1
    assert trader.ledger["virtual_cash_usdt"] < 10000.0

    # Test dynamic breakeven (+1.0x ATR at 3050+)
    trader.update_positions({"ETH/USDT": 3060.0})
    assert trader.positions["ETH/USDT"]["breakeven_triggered"] is True
    assert trader.positions["ETH/USDT"]["stop_loss"] >= 3000.0

    # Test closing at target
    closed = trader.close_position("ETH/USDT", exit_price=3300.0, reason="TARGET_HIT")
    assert closed["net_pnl_usd"] > 0
    assert trader.ledger["winning_trades"] == 1
    assert trader.ledger["win_rate_pct"] == 100.0
    assert len(trader.positions) == 0

def test_backtester_metrics():
    backtester = CryptoBacktester(initial_capital=10000.0)
    # Generate 100 days of trending synthetic data
    dates = pd.date_range("2025-01-01", periods=100, freq="1d")
    close = np.linspace(100, 200, 100)
    df = pd.DataFrame({
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": [10000.0] * 100,
    }, index=dates)

    res = backtester.backtest_ema_crossover(df, fast_period=10, slow_period=20)
    assert "sharpe_ratio" in res
    assert "sortino_ratio" in res
    assert "max_drawdown_pct" in res
    assert res["total_return_pct"] > 0
