"""Adversarial trade gatekeeper enforcing multi-tier safety checks before execution."""

import logging
from typing import Dict, Any, List, Tuple, Optional

from src.analysis.regime_service import get_current_regime

logger = logging.getLogger(__name__)

class CryptoTradeGatekeeper:
    """
    Deterministic gatekeeper that audits candidate trade setups.
    
    Any failed gate results in an immediate VETO with a documented reason.
    """

    def __init__(
        self,
        min_reward_to_risk: float = 1.5,
        min_rvol: float = 1.2,
        max_concurrent_positions: int = 3,
        daily_loss_limit_usd: float = 500.0,
    ):
        self.min_reward_to_risk = float(min_reward_to_risk)
        self.min_rvol = float(min_rvol)
        self.max_concurrent_positions = int(max_concurrent_positions)
        self.daily_loss_limit_usd = float(daily_loss_limit_usd)

    def evaluate_candidate(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        technicals: Dict[str, Any],
        active_positions: Dict[str, Any],
        daily_pnl_usd: float,
        is_liquidity_sweep: bool = False,
        regime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, List[str]]:
        """
        Evaluate candidate setup against all safety gates.
        Returns: (passed: bool, verdict: str, veto_reasons: List[str])
        """
        veto_reasons = []
        regime = regime_info or get_current_regime()

        # Gate 0: Macro Regime Defense (Veto speculative longs if macro is RISK_OFF)
        if regime.get("zone") == "RISK_OFF" and direction.upper() == "BUY" and not is_liquidity_sweep:
            veto_reasons.append(
                f"MACRO_REGIME_DEFENSE: Market regime is {regime.get('zone')} (Score: {regime.get('score')}/100). Speculative breakout longs restricted."
            )

        # Gate 1: Daily Loss Circuit Breaker
        if daily_pnl_usd <= -abs(self.daily_loss_limit_usd):
            veto_reasons.append(
                f"DAILY_LOSS_CIRCUIT_BREAKER_TRIGGERED: Current day PnL ${daily_pnl_usd:.2f} <= -${self.daily_loss_limit_usd:.2f}"
            )

        # Gate 2: Maximum Concurrent Positions Cap
        if len(active_positions) >= self.max_concurrent_positions and symbol not in active_positions:
            veto_reasons.append(
                f"MAX_POSITIONS_REACHED: Currently holding {len(active_positions)}/{self.max_concurrent_positions} active trades."
            )

        # Gate 3: Mathematical Risk-to-Reward Ratio
        risk = abs(entry_price - stop_loss)
        reward = abs(target_price - entry_price)
        if risk <= 0:
            veto_reasons.append("INVALID_RISK: Stop loss cannot equal entry price.")
        else:
            rr_ratio = reward / risk
            if rr_ratio < self.min_reward_to_risk:
                veto_reasons.append(
                    f"INSUFFICIENT_RR: Reward-to-Risk {rr_ratio:.2f} < {self.min_reward_to_risk:.2f} minimum required."
                )

        # Gate 4: Relative Volume (RVOL)
        rvol = technicals.get("rvol", 1.0)
        if rvol < self.min_rvol:
            veto_reasons.append(
                f"INSUFFICIENT_VOLUME: Relative volume {rvol:.2f}x < {self.min_rvol:.2f}x threshold."
            )

        # Gate 5: Trend & Regime Filter
        # If buying, price should be surfing above 20 EMA, unless it is a confirmed SSL liquidity sweep
        if direction.upper() == "BUY":
            above_20_ema = technicals.get("above_20_ema", True)
            if not above_20_ema and not is_liquidity_sweep:
                veto_reasons.append(
                    "TREND_VIOLATION: Price below 20 EMA without confirmed liquidity sweep."
                )

            # Gate 6: Overbought RSI long protection
            rsi = technicals.get("rsi", 50.0)
            if rsi > 78.0:
                veto_reasons.append(
                    f"RSI_OVERBOUGHT: RSI is {rsi:.1f} (> 78.0), high exhaustion risk."
                )

        if direction.upper() == "SELL":
            rsi = technicals.get("rsi", 50.0)
            if rsi < 22.0:
                veto_reasons.append(
                    f"RSI_OVERSOLD: RSI is {rsi:.1f} (< 22.0), high bounce risk."
                )

        passed = len(veto_reasons) == 0
        verdict = "APPROVED" if passed else "VETOED"
        return passed, verdict, veto_reasons
