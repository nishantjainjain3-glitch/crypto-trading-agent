"""Unit tests for the Autonomous Self-Optimization Engine."""

import os
import json
import pytest
import pandas as pd
from unittest.mock import MagicMock
from src.engine.self_optimizer import SelfOptimizationEngine
from src.analysis.technical_indicators import compute_all_technicals


def test_audit_gatekeeper_efficiency(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    attr_file = data_dir / "gatekeeper_attribution.json"

    sample_attribution = {
        "STOP_LOSS_GUARD": {
            "vetoes_count": 5,
            "saved_loss_usd": 12.50,
            "missed_profit_usd": 1.20,
        },
        "INSUFFICIENT_VOLUME": {
            "vetoes_count": 8,
            "saved_loss_usd": 2.00,
            "missed_profit_usd": 6.50,
        },
    }
    with open(attr_file, "w", encoding="utf-8") as f:
        json.dump(sample_attribution, f)

    optimizer = SelfOptimizationEngine(data_dir=str(data_dir))
    audit = optimizer.audit_gatekeeper_efficiency()

    assert "STOP_LOSS_GUARD" in audit
    sl_gate = audit["STOP_LOSS_GUARD"]
    assert sl_gate["saved_loss_usd"] == 12.50
    assert sl_gate["missed_profit_usd"] == 1.20
    assert sl_gate["net_benefit_usd"] == 11.30
    assert sl_gate["efficiency_pct"] > 90.0
    assert sl_gate["health"] == "HEALTHY_PROTECTION"
    assert sl_gate["action"] == "MAINTAIN"

    vol_gate = audit["INSUFFICIENT_VOLUME"]
    assert vol_gate["net_benefit_usd"] == -4.50
    assert vol_gate["health"] == "RESTRICTIVE"
    assert vol_gate["action"] == "CALIBRATE_LOOSER"


def test_calibrate_volatility_regime(tmp_path):
    optimizer = SelfOptimizationEngine(data_dir=str(tmp_path))

    # High volatility
    high_tech = [{"atr_pct": 3.5}, {"atr_pct": 4.0}, {"atr_pct": 3.2}]
    res_high = optimizer.calibrate_volatility_regime(high_tech)
    assert res_high["regime"] == "HIGH_VOLATILITY"
    assert res_high["recommended_target_mult"] == 4.5
    assert res_high["recommended_min_target_pct"] == 5.5

    # Low volatility
    low_tech = [{"atr_pct": 1.2}, {"atr_pct": 1.5}, {"atr_pct": 1.4}]
    res_low = optimizer.calibrate_volatility_regime(low_tech)
    assert res_low["regime"] == "LOW_VOLATILITY"
    assert res_low["recommended_rvol"] == 0.95
    assert res_low["recommended_min_target_pct"] == 4.0

    # Normal volatility
    norm_tech = [{"atr_pct": 2.2}, {"atr_pct": 2.5}]
    res_norm = optimizer.calibrate_volatility_regime(norm_tech)
    assert res_norm["regime"] == "NORMAL_VOLATILITY"


def test_run_optimization_cycle_updates_gatekeeper(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    attr_file = data_dir / "gatekeeper_attribution.json"

    # Restrictive volume gate
    sample_attr = {
        "INSUFFICIENT_VOLUME": {
            "vetoes_count": 10,
            "saved_loss_usd": 1.0,
            "missed_profit_usd": 15.0,
        }
    }
    with open(attr_file, "w", encoding="utf-8") as f:
        json.dump(sample_attr, f)

    optimizer = SelfOptimizationEngine(data_dir=str(data_dir))
    mock_gatekeeper = MagicMock()
    mock_gatekeeper.min_rvol = 1.2

    low_vol_tech = [{"atr_pct": 1.5}]
    record = optimizer.run_optimization_cycle(
        gatekeeper=mock_gatekeeper,
        technicals_list=low_vol_tech,
    )

    assert record["market_regime"] == "LOW_VOLATILITY"
    assert mock_gatekeeper.min_rvol < 1.2
    assert os.path.exists(optimizer.log_path)


def test_rvol_completed_and_prorated():
    # Construct 25 rows of OHLCV data
    rows = []
    base_price = 100.0
    for i in range(25):
        rows.append({
            "timestamp": 1700000000000 + i * 3600000,
            "open": base_price + i,
            "high": base_price + i + 1,
            "low": base_price + i - 1,
            "close": base_price + i + 0.5,
            "volume": 1000.0,
        })
    df = pd.DataFrame(rows)

    # Set last closed candle (index 23) to high volume 2500 (2.5x average)
    df.loc[23, "volume"] = 2500.0
    # Set current incomplete candle (index 24) to low volume 100 (0.1x average)
    df.loc[24, "volume"] = 100.0

    techs = compute_all_technicals(df)
    assert techs["rvol"] >= 2.0  # Captures completed candle surge, not blocked by 0.1x incomplete candle
