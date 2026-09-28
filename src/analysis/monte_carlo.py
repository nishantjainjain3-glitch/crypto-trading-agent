"""Jesse-inspired Monte Carlo simulation engine for stress-testing strategy trade sequences."""

import numpy as np
from typing import List, Dict, Any, Optional

def run_monte_carlo_simulation(
    trade_pnls_pct: List[float],
    initial_equity: float = 18.0,
    num_simulations: int = 1000,
    ruin_drawdown_pct: float = 20.0,
    random_seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Stress-tests a trading strategy using Monte Carlo trade-order shuffling.
    
    Principles adapted from Jesse's Monte Carlo module:
    - Shuffles the sequence of actual trade outcomes 1,000+ times to evaluate
      whether strategy performance was due to lucky sequencing or robust edge.
    - Calculates Risk of Ruin (probability of suffering drawdown > ruin_drawdown_pct).
    - Calculates the 95th and 99th percentile worst-case maximum drawdown.
    """
    if not trade_pnls_pct or len(trade_pnls_pct) < 3:
        return {
            "num_trades": len(trade_pnls_pct),
            "num_simulations": 0,
            "error": "At least 3 completed trades required for Monte Carlo simulation.",
        }

    if random_seed is not None:
        np.random.seed(random_seed)

    trades = np.array(trade_pnls_pct, dtype=float)
    n_trades = len(trades)
    
    ending_equities = []
    max_drawdowns = []
    ruin_count = 0
    profitable_runs = 0

    for _ in range(num_simulations):
        # Shuffled / resampled trades with replacement (bootstrapping)
        sampled_pnls = np.random.choice(trades, size=n_trades, replace=True)
        
        # Build equity path
        equity_factors = 1.0 + (sampled_pnls / 100.0)
        # Prevent negative capital
        equity_factors = np.maximum(equity_factors, 0.0)
        curve = initial_equity * np.cumprod(equity_factors)
        
        # Calculate maximum peak-to-trough drawdown for this path
        peaks = np.maximum.accumulate(curve)
        drawdowns = (peaks - curve) / (peaks + 1e-9) * 100.0
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        
        ending_equity = float(curve[-1])
        ending_equities.append(ending_equity)
        max_drawdowns.append(max_dd)

        if max_dd >= ruin_drawdown_pct:
            ruin_count += 1
        if ending_equity > initial_equity:
            profitable_runs += 1

    ending_equities = np.array(ending_equities)
    max_drawdowns = np.array(max_drawdowns)

    risk_of_ruin_pct = round((ruin_count / num_simulations) * 100.0, 2)
    win_probability_pct = round((profitable_runs / num_simulations) * 100.0, 2)
    median_equity = round(float(np.median(ending_equities)), 2)
    p95_max_drawdown = round(float(np.percentile(max_drawdowns, 95)), 2)
    p99_max_drawdown = round(float(np.percentile(max_drawdowns, 99)), 2)
    median_max_drawdown = round(float(np.median(max_drawdowns)), 2)

    return {
        "num_trades": n_trades,
        "num_simulations": num_simulations,
        "initial_equity": round(initial_equity, 2),
        "median_ending_equity": median_equity,
        "median_max_drawdown_pct": median_max_drawdown,
        "p95_worst_drawdown_pct": p95_max_drawdown,
        "p99_worst_drawdown_pct": p99_max_drawdown,
        "risk_of_ruin_pct": risk_of_ruin_pct,
        "win_probability_pct": win_probability_pct,
        "ruin_threshold_pct": ruin_drawdown_pct,
        "verdict": (
            "ROBUST" if risk_of_ruin_pct < 5.0 and win_probability_pct > 60.0
            else ("ACCEPTABLE" if risk_of_ruin_pct < 15.0 else "HIGH_RISK_OF_OVERFITTING")
        ),
    }
