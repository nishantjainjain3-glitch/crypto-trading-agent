"""Unit tests for the Jesse-inspired Monte Carlo simulation engine."""

from src.analysis.monte_carlo import run_monte_carlo_simulation

def test_monte_carlo_runs_successfully():
    pnls = [1.5, -0.9, 2.1, -1.6, 0.8, -0.4, 3.2, -1.1, 0.5]
    res = run_monte_carlo_simulation(pnls, initial_equity=18.0, num_simulations=500, random_seed=42)
    assert res["num_trades"] == 9
    assert res["num_simulations"] == 500
    assert "median_ending_equity" in res
    assert "p95_worst_drawdown_pct" in res
    assert "risk_of_ruin_pct" in res
    assert res["risk_of_ruin_pct"] >= 0.0

def test_monte_carlo_handles_too_few_trades():
    res = run_monte_carlo_simulation([1.0, -1.0])
    assert "error" in res
