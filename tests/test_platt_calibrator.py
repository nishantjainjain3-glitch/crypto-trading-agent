import pytest
import os
from src.analysis.platt_calibrator import PlattCalibrator


def test_calibrate_probability_bounds():
    calibrator = PlattCalibrator(data_path="data/test_platt.json")

    # High score should give higher probability than low score
    prob_high = calibrator.calibrate_probability(95.0)
    prob_mid = calibrator.calibrate_probability(50.0)
    prob_low = calibrator.calibrate_probability(20.0)

    assert 0.10 <= prob_low <= 0.90
    assert 0.10 <= prob_mid <= 0.90
    assert 0.10 <= prob_high <= 0.90
    assert prob_high > prob_low


def test_compute_brier_metrics():
    calibrator = PlattCalibrator(data_path="data/test_platt.json")

    # Perfectly calibrated predictions
    probs = [0.9, 0.8, 0.1, 0.2]
    outcomes = [1, 1, 0, 0]
    res = calibrator.compute_brier_metrics(probs, outcomes)

    assert "brier_score" in res
    assert res["brier_score"] < 0.10  # Low error
    assert res["brier_skill_score"] > 0.0  # Positive skill vs 50/50


def test_fit_from_trade_history():
    test_path = "data/test_platt_fit.json"
    if os.path.exists(test_path):
        os.remove(test_path)

    calibrator = PlattCalibrator(data_path=test_path)
    mock_history = [
        {"entry_score": 90, "net_pnl_usd": 1.5},
        {"entry_score": 85, "net_pnl_usd": 1.2},
        {"entry_score": 80, "net_pnl_usd": -0.8},
        {"entry_score": 75, "net_pnl_usd": 0.5},
        {"entry_score": 60, "net_pnl_usd": -1.0},
        {"entry_score": 95, "net_pnl_usd": 2.0},
    ]

    fit_res = calibrator.fit_from_trade_history(mock_history)
    assert fit_res["status"] == "FITTED"
    assert fit_res["sample_count"] == 6
    assert "brier_score" in fit_res

    if os.path.exists(test_path):
        os.remove(test_path)
