import os
import json
import pytest
import tempfile
import shutil
from src.engine.counterfactual_tracker import CounterfactualTracker
from src.engine.crypto_paper_trader import CryptoPaperTrader

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)

def test_counterfactual_tracker_record_and_evaluate(temp_dir):
    ledger_file = os.path.join(temp_dir, "test_cf_ledger.json")
    attribution_file = os.path.join(temp_dir, "test_attribution.json")
    tracker = CounterfactualTracker(
        ledger_path=ledger_file,
        attribution_path=attribution_file,
        default_stake_usd=10.0,
        expiry_hours=1.0,
    )

    # 1. Record a declined setup
    entry = tracker.record_declined_setup(
        symbol="SOL/USDT",
        direction="BUY",
        entry_price=100.0,
        stop_loss=98.0,
        target_price=104.0,
        atr=2.0,
        veto_reasons=["HTF_HEADWIND: Price below 1H 50 EMA"],
        score=75.0,
    )

    assert entry is not None
    assert entry["symbol"] == "SOL/USDT"
    assert entry["primary_gate"] == "HTF_HEADWIND"
    assert entry["status"] == "OPEN"
    assert len(tracker.entries) == 1

    # 2. Test deduplication within cooldown
    dup = tracker.record_declined_setup(
        symbol="SOL/USDT",
        direction="BUY",
        entry_price=100.0,
        stop_loss=98.0,
        target_price=104.0,
        atr=2.0,
        veto_reasons=["HTF_HEADWIND: Price below 1H 50 EMA"],
    )
    assert dup is None
    assert len(tracker.entries) == 1

    # 3. Simulate market price hitting stop loss (Saved Loss)
    resolved = tracker.evaluate_open_counterfactuals({"SOL/USDT": 97.5})
    assert len(resolved) == 1
    assert resolved[0]["outcome"] == "SAVED_LOSS"
    assert resolved[0]["status"] == "RESOLVED"
    assert resolved[0]["saved_loss_usd"] == 0.20  # 10.0 * (2.0 / 100.0)

    # 4. Check attribution aggregation
    attr = tracker.recompute_attribution()
    assert "HTF_HEADWIND" in attr
    assert attr["HTF_HEADWIND"]["saved_trades_count"] == 1
    assert attr["HTF_HEADWIND"]["saved_losses_usd"] == 0.20
    assert attr["HTF_HEADWIND"]["net_benefit_usd"] == 0.20

    # 5. Record another setup that hits target (Missed Profit)
    entry2 = tracker.record_declined_setup(
        symbol="DOGE/USDT",
        direction="BUY",
        entry_price=0.10,
        stop_loss=0.09,
        target_price=0.12,
        atr=0.01,
        veto_reasons=["MARKET_LAGGARD: Underperforming BTC"],
    )
    assert entry2 is not None

    resolved2 = tracker.evaluate_open_counterfactuals({"DOGE/USDT": 0.125})
    assert len(resolved2) == 1
    assert resolved2[0]["outcome"] == "MISSED_PROFIT"
    assert resolved2[0]["missed_profit_usd"] > 1.90  # 10 * 20% - fee

    summary = tracker.get_summary()
    assert summary["total_vetoed_setups"] == 2
    assert summary["resolved_counterfactuals"] == 2
    assert summary["total_capital_saved_usd"] == 0.20

def test_paper_trader_mfe_and_mae_tracking(temp_dir):
    trader = CryptoPaperTrader(data_dir=temp_dir, slippage_pct=0.0, taker_fee_pct=0.0)
    trader.ledger["virtual_cash_usdt"] = 50.0

    # Open position
    trader.open_position(
        symbol="ETH/USDT",
        direction="BUY",
        entry_price=2000.0,
        quantity=0.01,
        stop_loss=1950.0,
        target_price=2100.0,
        atr=25.0,
    )

    # Simulate price reaching higher (MFE: +1.5%) - activates breakeven stop at 2001.6
    trader.update_positions({"ETH/USDT": 2030.0}) # Peak +1.5%

    # Simulate price pulling back to 1980.0 (-1.0%), hitting breakeven stop loss
    closed_list = trader.update_positions({"ETH/USDT": 1980.0})
    assert len(closed_list) == 1
    closed = closed_list[0]

    assert "mfe_pct" in closed
    assert "mae_pct" in closed
    assert "holding_seconds" in closed
    assert closed["mfe_pct"] == 1.5   # Peak reached 2030 (+1.5%)
    assert closed["mae_pct"] == -1.0  # Trough reached 1980 (-1.0%)
    assert closed["exit_reason"] == "STOP_LOSS_HIT"
