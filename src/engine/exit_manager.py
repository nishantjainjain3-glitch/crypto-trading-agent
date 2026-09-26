"""Decaying Minimal ROI and Positive Trailing Stop Engine for Crypto Trades."""

from typing import Dict, Any, Optional

DEFAULT_CRYPTO_ROI_TABLE: Dict[int, float] = {
    0: 2.2,  # Hours 0 - 2: Full breakout target (+2.2%)
    2: 1.4,  # Hours 2 - 6: Standard swing target (+1.4%)
    6: 0.8,  # Hours 6 - 12: Decaying target (+0.8%)
    12: 0.5, # Hours 12+: Free stagnant capital (+0.5%, well above 0.15% roundtrip taker fees)
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

    active_target = 2.2
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
    breakeven_threshold_atr: float = 0.5,
    trailing_activation_atr: float = 1.75,
    trailing_distance_atr: float = 1.0,
) -> Dict[str, Any]:
    """Calculates updated dynamic stop loss, breakeven trigger, and trailing stop levels."""
    if entry_price <= 0:
        return {"effective_stop": initial_stop_loss, "breakeven_active": False, "trailing_active": False}

    peak = max(highest_price, current_price, entry_price)
    profit = peak - entry_price

    breakeven_active = profit >= (breakeven_threshold_atr * atr)
    trailing_active = profit >= (trailing_activation_atr * atr)

    effective_stop = initial_stop_loss
    if trailing_active:
        trail_level = round(peak - (trailing_distance_atr * atr), 6)
        effective_stop = max(effective_stop, trail_level)
    elif breakeven_active:
        be_level = round(entry_price * 1.0008, 6)
        effective_stop = max(effective_stop, be_level)

    return {
        "effective_stop": effective_stop,
        "peak_price": peak,
        "breakeven_active": breakeven_active,
        "trailing_active": trailing_active,
    }
