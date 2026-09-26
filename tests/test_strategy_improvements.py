"""Unit tests for strategy improvements: 0.5 ATR breakeven, 1H trend gate, and RS ranking."""

import pytest
from src.engine.exit_manager import compute_crypto_trailing_stop
from src.engine.crypto_gatekeeper import CryptoTradeGatekeeper


def test_breakeven_activates_at_half_atr():
    entry = 100.0
    atr = 2.0
    stop = 97.0
    current = 101.1  # +1.1 > 0.5 * atr (1.0)

    res = compute_crypto_trailing_stop(
        entry_price=entry,
        current_price=current,
        highest_price=current,
        initial_stop_loss=stop,
        atr=atr,
        breakeven_threshold_atr=0.5,
    )
    assert res["breakeven_active"] is True
    assert res["effective_stop"] >= entry * 1.0008


def test_gatekeeper_vetoes_counter_trend_1h():
    gk = CryptoTradeGatekeeper()
    technicals = {
        "above_20_ema": True,
        "rsi": 55.0,
        "rvol": 1.5,
        "htf_bullish": False,  # 1-Hour downtrend headwind
    }
    passed, verdict, vetoes = gk.evaluate_candidate(
        symbol="BNB/USDT",
        direction="BUY",
        entry_price=600.0,
        stop_loss=590.0,
        target_price=620.0,
        technicals=technicals,
        active_positions={},
        daily_pnl_usd=0.0,
    )
    assert not passed
    assert any("HTF_HEADWIND" in v for v in vetoes)


def test_gatekeeper_vetoes_market_laggard():
    gk = CryptoTradeGatekeeper()
    technicals = {
        "above_20_ema": True,
        "rsi": 52.0,
        "rvol": 1.4,
        "htf_bullish": True,
        "is_laggard": True,  # Underperforming BTC by >1.5%
    }
    passed, verdict, vetoes = gk.evaluate_candidate(
        symbol="AVAX/USDT",
        direction="BUY",
        entry_price=25.0,
        stop_loss=24.0,
        target_price=27.0,
        technicals=technicals,
        active_positions={},
        daily_pnl_usd=0.0,
    )
    assert not passed
    assert any("MARKET_LAGGARD" in v for v in vetoes)
