"""Tests for ported quantitative and protection modules from indian-trading-agent."""

import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from src.engine.protections import CryptoProtectionManager
from src.analysis.order_flow import detect_fair_value_gaps, analyze_wyckoff_vsa, calculate_cumulative_volume_delta, analyze_order_flow
from src.analysis.order_book_depth import analyze_order_book_depth
from src.engine.exit_manager import evaluate_minimal_roi_exit, compute_crypto_trailing_stop
from src.engine.crypto_gatekeeper import CryptoTradeGatekeeper


def test_crypto_protection_manager_cooldowns(tmp_path):
    cd_file = str(tmp_path / "test_cooldowns.json")
    mgr = CryptoProtectionManager(storage_path=cd_file)

    # Initially no cooldown
    in_cd, reason = mgr.is_in_cooldown("SOL/USDT")
    assert not in_cd
    assert reason is None

    # Set manual cooldown for 2 hours
    mgr.set_cooldown("SOL/USDT", hours=2.0, reason="Test Lockout")
    in_cd, reason = mgr.is_in_cooldown("SOL/USDT")
    assert in_cd
    assert "Test Lockout" in reason

    # Clear cooldown
    mgr.clear_cooldown("SOL/USDT")
    in_cd, _ = mgr.is_in_cooldown("SOL/USDT")
    assert not in_cd


def test_crypto_stoploss_guard_triggers_lockout(tmp_path):
    cd_file = str(tmp_path / "test_cooldowns.json")
    mgr = CryptoProtectionManager(storage_path=cd_file)

    # First stoploss hit: should NOT trigger lockout
    locked1 = mgr.record_stoploss_hit("AVAX/USDT", exit_price=10.20, loss_pct=-1.5)
    assert not locked1
    in_cd, _ = mgr.is_in_cooldown("AVAX/USDT")
    assert not in_cd

    # Second stoploss hit: SHOULD trigger StoplossGuard lockout
    locked2 = mgr.record_stoploss_hit("AVAX/USDT", exit_price=10.05, loss_pct=-1.6)
    assert locked2
    in_cd, reason = mgr.is_in_cooldown("AVAX/USDT")
    assert in_cd
    assert "StoplossGuard" in reason


def test_protections_max_drawdown_guard(tmp_path):
    cd_file = str(tmp_path / "test_cooldowns.json")
    mgr = CryptoProtectionManager(storage_path=cd_file)

    # 2% drawdown -> PASS
    res1 = mgr.evaluate_entry_protections("BTC/USDT", current_equity=9.80, peak_equity=10.0, daily_loss_usd=0.0)
    assert res1["allowed"] is True

    # 6% drawdown -> BLOCKED (> 5.0% limit)
    res2 = mgr.evaluate_entry_protections("BTC/USDT", current_equity=9.40, peak_equity=10.0, daily_loss_usd=0.0)
    assert res2["allowed"] is False
    assert any("MAX_DRAWDOWN_GUARD" in v for v in res2["violations"])


def test_candle_health_anti_knife_and_chase(tmp_path):
    cd_file = str(tmp_path / "test_cooldowns.json")
    mgr = CryptoProtectionManager(storage_path=cd_file)

    # Falling knife: price is at 10% of 24h range (low=10, high=20, price=11)
    res_knife = mgr.evaluate_candle_health("DOGE/USDT", current_price=11.0, high_24h=20.0, low_24h=10.0, strategy="PULLBACK")
    assert res_knife["allowed"] is False
    assert any("FALLING_KNIFE" in v for v in res_knife["violations"])

    # Over extended chase: price is 4% above breakout trigger (trigger=100, price=104)
    res_chase = mgr.evaluate_candle_health("SOL/USDT", current_price=104.0, high_24h=105.0, low_24h=95.0, strategy="BREAKOUT", trigger_price=100.0)
    assert res_chase["allowed"] is False
    assert any("OVER_EXTENDED" in v for v in res_chase["violations"])


def test_order_flow_analysis():
    # Construct synthetic OHLCV dataframe with a bullish FVG and high volume
    n = 30
    prices = np.linspace(100, 110, n)
    df = pd.DataFrame({
        "Open": prices - 0.2,
        "High": prices + 1.0,
        "Low": prices - 0.5,
        "Close": prices + 0.3,
        "Volume": [1000.0] * n
    })
    # Create deliberate bullish FVG at candle 20: High of 18 < Low of 20
    df.loc[18, "High"] = 105.0
    df.loc[19, "Low"] = 105.5
    df.loc[19, "High"] = 106.5
    df.loc[20, "Low"] = 105.8  # Low of 20 (105.8) > High of 18 (105.0)

    res = analyze_order_flow(df)
    assert "order_flow_score" in res
    assert 0 <= res["order_flow_score"] <= 100
    assert "verdict" in res
    assert "cumulative_volume_delta" in res
    assert "wyckoff_vsa" in res


def test_order_book_depth_mock():
    class MockExchange:
        def fetch_order_book(self, symbol, limit=20):
            return {
                "bids": [[100.0, 50.0], [99.9, 40.0], [99.8, 30.0]],
                "asks": [[100.1, 20.0], [100.2, 25.0], [100.3, 15.0]]
            }

    class MockClient:
        def __init__(self):
            self.exchange = MockExchange()

    res = analyze_order_book_depth(MockClient(), "BTC/USDT", limit=20)
    assert res["available"] is True
    assert res["spread_bps"] > 0
    assert res["imbalance_ratio"] == 2.0  # 120 / 60
    assert res["allowed_by_depth"] is True


def test_decaying_minimal_roi_exit():
    # Hour 1: Gain +2.3% exceeds early +2.2% target -> Exit
    e1 = evaluate_minimal_roi_exit(entry_price=100.0, current_price=102.3, holding_hours=1.0)
    assert e1["should_exit"] is True

    # Hour 1: Gain +1.5% below early +2.2% target -> Hold
    e2 = evaluate_minimal_roi_exit(entry_price=100.0, current_price=101.5, holding_hours=1.0)
    assert e2["should_exit"] is False

    # Hour 4: Target decayed to +1.4%. Gain +1.5% now exceeds target -> Exit
    e3 = evaluate_minimal_roi_exit(entry_price=100.0, current_price=101.5, holding_hours=4.0)
    assert e3["should_exit"] is True


def test_gatekeeper_with_protections(tmp_path):
    cd_file = str(tmp_path / "test_cooldowns.json")
    mgr = CryptoProtectionManager(storage_path=cd_file)
    gatekeeper = CryptoTradeGatekeeper(protection_manager=mgr)

    # Lock symbol in cooldown
    mgr.set_cooldown("AVAX/USDT", hours=24.0, reason="StoplossGuard whipsaw lock")

    passed, verdict, vetoes = gatekeeper.evaluate_candidate(
        symbol="AVAX/USDT",
        direction="BUY",
        entry_price=10.0,
        stop_loss=9.5,
        target_price=11.0,
        technicals={"rvol": 1.5, "above_20_ema": True, "rsi": 50.0},
        active_positions={},
        daily_pnl_usd=0.0
    )
    assert not passed
    assert verdict == "VETOED"
    assert any("COOLDOWN_ACTIVE" in v for v in vetoes)
