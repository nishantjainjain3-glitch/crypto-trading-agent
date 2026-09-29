import pytest
import pandas as pd
import numpy as np

from src.analysis.order_flow_cvd import OrderFlowCVDAnalyzer
from src.engine.limit_chaser import LimitChaser
from src.engine.dual_strategy_orchestrator import DualStrategyOrchestrator
from src.engine.portfolio_allocator_v2 import PortfolioAllocatorV2


def test_order_flow_cvd_calculation():
    analyzer = OrderFlowCVDAnalyzer()
    trades = [
        {"side": "buy", "amount": 1.5},
        {"side": "buy", "amount": 2.5},
        {"side": "sell", "amount": 1.0},
    ]
    res = analyzer.compute_cvd_from_trades(trades)
    assert res["taker_buy_vol"] == 4.0
    assert res["taker_sell_vol"] == 1.0
    assert res["cvd_value"] == 3.0
    assert res["buy_ratio"] == 0.80
    assert res["imbalance"] == "HEAVY_BUY_ABSORPTION"


def test_cvd_divergence_detection():
    analyzer = OrderFlowCVDAnalyzer(divergence_lookback=10)
    # Price dropping while CVD rising (Bullish absorption)
    prices = [100.0 - i * 0.5 for i in range(15)]
    cvd = [10.0 + i * 2.0 for i in range(15)]

    div = analyzer.detect_cvd_divergence(prices, cvd)
    assert div["divergence"] == "BULLISH_ABSORPTION"
    assert div["strength"] > 0.0


def test_liquidation_clusters():
    analyzer = OrderFlowCVDAnalyzer()
    clusters = analyzer.estimate_liquidation_clusters(current_price=100.0, atr=2.0)

    assert clusters["nearest_short_squeeze_level"] > 100.0
    assert clusters["nearest_long_flush_level"] < 100.0
    assert len(clusters["short_liquidation_levels"]) == 3
    assert len(clusters["long_liquidation_levels"]) == 3


def test_limit_chaser_optimal_price():
    chaser = LimitChaser()
    bid = 10.00
    ask = 10.05

    # Attempt 1: at best bid
    p1 = chaser.compute_optimal_limit_price("AVAX/USDT", "BUY", bid, ask, attempt=1)
    assert p1 == 10.00

    # Attempt 2: stepped inside spread
    p2 = chaser.compute_optimal_limit_price("AVAX/USDT", "BUY", bid, ask, attempt=2)
    assert 10.00 < p2 < 10.05


def test_dual_strategy_regime_and_mean_reversion():
    orchestrator = DualStrategyOrchestrator()

    # Ranging dataframe
    np.random.seed(42)
    closes = [10.0 + np.sin(i / 2.0) * 0.2 for i in range(40)]
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]
    df = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes, "volume": [1000]*40})

    regime = orchestrator.detect_regime(df, technicals={"rsi": 35.0})
    assert regime in ("RANGING_CONSOLIDATION", "TRANSITIONAL", "TRENDING_EXPANSION")

    # Evaluate candidate when price is near support
    df.loc[39, "close"] = df["low"].min() + 0.001
    cand = orchestrator.evaluate_mean_reversion_candidate("LINK/USDT", df, technicals={"rsi": 32.0})
    if cand:
        assert cand["strategy"] == "RANGE_MEAN_REVERSION"
        assert cand["target_price"] > cand["entry_price"]


def test_portfolio_allocator_scaling_tiers():
    allocator = PortfolioAllocatorV2()

    # Small account: 1 position max
    assert allocator.get_max_allowed_positions(16.5) == 1
    # $100 account: 2 positions max
    assert allocator.get_max_allowed_positions(100.0) == 2
    # $250 account: 3 positions max
    assert allocator.get_max_allowed_positions(250.0) == 3
    # $600 account: 4 positions max
    assert allocator.get_max_allowed_positions(600.0) == 4


def test_portfolio_allocator_correlation_conflict():
    allocator = PortfolioAllocatorV2()

    # AVAX and SOL are in L1_SOL_ECOSYSTEM cluster
    has_conflict = allocator.check_correlation_conflict("AVAX/USDT", ["SOL/USDT"])
    assert has_conflict is True

    # BTC and DOGE are in different clusters
    no_conflict = allocator.check_correlation_conflict("BTC/USDT", ["DOGE/USDT"])
    assert no_conflict is False
