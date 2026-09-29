import pytest
from src.engine.dynamic_risk_allocator import DynamicRiskAllocator


def test_drawdown_dampener_scaling():
    allocator = DynamicRiskAllocator()

    # 0% drawdown -> 1.0 multiplier
    assert allocator.compute_drawdown_dampener(100.0, 100.0) == 1.0

    # 10% drawdown (90/100) -> 1.0 - 2.0 * 0.10 = 0.8
    assert allocator.compute_drawdown_dampener(90.0, 100.0) == 0.8

    # 35% drawdown -> clamped at minimum 0.40
    assert allocator.compute_drawdown_dampener(65.0, 100.0) == 0.40


def test_kelly_fraction_calculation():
    allocator = DynamicRiskAllocator()

    # Winning series with 60% win rate and 2.0 payoff ratio
    trades = [
        {"pnl_usd": 2.0},
        {"pnl_usd": 2.0},
        {"pnl_usd": 2.0},
        {"pnl_usd": -1.0},
        {"pnl_usd": -1.0},
    ]
    frac = allocator.calculate_kelly_fraction(trades)
    # Full Kelly: (0.6 * 2.0 - 0.4) / 2.0 = 0.8 / 2.0 = 0.40 -> Quarter Kelly = 0.10
    assert 0.05 <= frac <= 0.30


def test_allocate_position_small_account():
    allocator = DynamicRiskAllocator(min_notional_usd=5.0)

    # Small account ($17.30 USDT)
    res = allocator.allocate_position(
        symbol="LINK/USDT",
        entry_price=15.0,
        stop_loss=14.5,
        free_cash_usdt=16.0,
        total_equity_usdt=17.3,
        peak_equity_usdt=17.3,
        open_positions_count=0,
        max_open_positions=1,
    )

    assert res["is_approved"] is True
    assert res["allocated_usd"] >= 5.0
    assert res["quantity"] > 0.0


def test_allocate_position_insufficient_cash():
    allocator = DynamicRiskAllocator(min_notional_usd=5.0)

    # Cash below $5.00 minNotional
    res = allocator.allocate_position(
        symbol="LINK/USDT",
        entry_price=15.0,
        stop_loss=14.5,
        free_cash_usdt=2.50,
        total_equity_usdt=17.3,
        peak_equity_usdt=17.3,
        open_positions_count=0,
    )

    assert res["is_approved"] is False
    assert "below exchange minNotional" in res["reason"]


def test_allocate_position_max_positions_reached():
    allocator = DynamicRiskAllocator()

    res = allocator.allocate_position(
        symbol="ETH/USDT",
        entry_price=2600.0,
        stop_loss=2550.0,
        free_cash_usdt=20.0,
        total_equity_usdt=35.0,
        peak_equity_usdt=35.0,
        open_positions_count=1,
        max_open_positions=1,
    )

    assert res["is_approved"] is False
    assert "Maximum open positions" in res["reason"]
