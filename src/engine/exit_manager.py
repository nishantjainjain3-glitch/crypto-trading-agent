"""Decaying Minimal ROI and Positive Trailing Stop Engine for Crypto Trades."""

from typing import Dict, Any, Optional

DEFAULT_CRYPTO_ROI_TABLE: Dict[int, float] = {
    0: 5.5,   # Hours 0 - 12: Trend expansion target (+5.5%)
    12: 4.0,  # Hours 12 - 24: Secondary swing target (+4.0%)
    24: 3.0,  # Hours 24 - 48: Core swing target (+3.0%)
    48: 2.0,  # Hours 48+: Minimum target floor (+2.0%, >10x Binance taker fees)
}

def evaluate_minimal_roi_exit(
    entry_price: float,
    current_price: float,
    holding_hours: float,
    roi_table: Optional[Dict[int, float]] = None
) -> Dict[str, Any]:
    """
    Evaluates whether an active trade should exit under decaying ROI rules.
    Frees capital from stagnant coins to rotate into moving opportunities.
    """
    if entry_price <= 0:
        return {
            "should_exit": False,
            "current_profit_pct": 0.0,
            "active_target_roi_pct": 0.0,
            "holding_hours": holding_hours,
        }

    table = roi_table or DEFAULT_CRYPTO_ROI_TABLE
    current_profit_pct = round(((current_price - entry_price) / entry_price) * 100, 2)

    active_target = 5.5
    for hr_threshold in sorted(table.keys(), reverse=True):
        if holding_hours >= hr_threshold:
            active_target = table[hr_threshold]
            break

    should_exit = current_profit_pct >= active_target
    reason = (
        f"Holding for {holding_hours:.1f}h hit decaying ROI target of +{active_target}% (Gain: +{current_profit_pct}%)"
        if should_exit
        else f"Hour {holding_hours:.1f}h target (+{active_target}%) not reached. Current return: {current_profit_pct}%"
    )

    return {
        "should_exit": should_exit,
        "current_profit_pct": current_profit_pct,
        "active_target_roi_pct": active_target,
        "holding_hours": holding_hours,
        "reason": reason,
    }

def compute_crypto_trailing_stop(
    entry_price: float,
    current_price: float,
    highest_price: float,
    initial_stop_loss: float,
    atr: float,
    breakeven_threshold_atr: Optional[float] = None,
    trailing_activation_atr: Optional[float] = None,
    trailing_distance_atr: Optional[float] = None,
) -> Dict[str, Any]:
    if entry_price <= 0:
        return {"effective_stop": initial_stop_loss, "breakeven_active": False, "trailing_active": False}

    be_mult = breakeven_threshold_atr
    dist_mult = trailing_distance_atr
    act_mult = trailing_activation_atr

    try:
        from src.engine.crypto_autopsy_engine import load_adaptive_hyperparams
        learned = load_adaptive_hyperparams()
        if be_mult is None and "breakeven_atr_mult" in learned:
            be_mult = float(learned["breakeven_atr_mult"])
        if dist_mult is None and "trailing_stop_atr_mult" in learned:
            dist_mult = float(learned["trailing_stop_atr_mult"])
    except Exception:
        pass

    if be_mult is None:
        be_mult = 1.0
    if dist_mult is None:
        dist_mult = 1.2
    if act_mult is None:
        act_mult = 2.0

    peak = max(highest_price, current_price, entry_price)
    profit = peak - entry_price

    breakeven_active = profit >= (be_mult * atr)
    trailing_active = profit >= (act_mult * atr)

    effective_stop = initial_stop_loss
    if trailing_active:
        trail_level = round(peak - (trailing_distance_atr * atr), 6)
        effective_stop = max(effective_stop, trail_level)
    elif breakeven_active:
        # Breakeven stop set to +0.35% above entry to guarantee net profit after exchange fees
        be_level = round(entry_price * 1.0035, 6)
        effective_stop = max(effective_stop, be_level)

    return {
        "effective_stop": effective_stop,
        "peak_price": peak,
        "breakeven_active": breakeven_active,
        "trailing_active": trailing_active,
    }
