import os
import logging
from typing import Dict, Any, List, Tuple, Optional
from dotenv import load_dotenv

from src.analysis.regime_service import get_current_regime
from src.engine.protections import CryptoProtectionManager

load_dotenv()
logger = logging.getLogger(__name__)


class CryptoTradeGatekeeper:
    """
    Deterministic gatekeeper that audits candidate trade setups.
    Enforces risk/reward, RVOL, 20 EMA trend, RSI limits, and Freqtrade-style protections:
    - Cooldown / StoplossGuard (stops whipsawing)
    - MaxDrawdownGuard (caps portfolio drawdown at 5%)
    - Order book depth & spread filter (rejects high-slippage or heavy sell walls)
    - Candle health (anti-falling knife, anti-chase)
    """

    def __init__(
        self,
        min_reward_to_risk: Optional[float] = None,
        min_rvol: Optional[float] = None,
        max_concurrent_positions: Optional[int] = None,
        daily_loss_limit_usd: Optional[float] = None,
        protection_manager: Optional[CryptoProtectionManager] = None,
    ):
        self.min_reward_to_risk = float(min_reward_to_risk if min_reward_to_risk is not None else os.getenv("MIN_REWARD_TO_RISK", 1.5))
        self.min_rvol = float(min_rvol if min_rvol is not None else os.getenv("MIN_RVOL_RATIO", 1.2))
        self.max_concurrent_positions = int(max_concurrent_positions if max_concurrent_positions is not None else os.getenv("MAX_CONCURRENT_POSITIONS", 1))
        self.daily_loss_limit_usd = float(daily_loss_limit_usd if daily_loss_limit_usd is not None else os.getenv("DAILY_LOSS_LIMIT_USDT", 2.0))
        self.protections = protection_manager or CryptoProtectionManager()

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
        current_equity: float = 9.27,
        peak_equity: float = 9.27,
        order_book_analysis: Optional[Dict[str, Any]] = None,
        candle_health: Optional[Dict[str, Any]] = None,
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

        # Gate 1: Protection Subsystem (Cooldown, StoplossGuard, MaxDrawdown, Daily Loss)
        prot_res = self.protections.evaluate_entry_protections(
            symbol=symbol,
            current_equity=current_equity,
            peak_equity=peak_equity,
            daily_loss_usd=daily_pnl_usd,
            daily_loss_limit_usd=self.daily_loss_limit_usd,
        )
        if not prot_res.get("allowed", True):
            for v in prot_res.get("violations", []):
                veto_reasons.append(v)

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

        # Gate 7: Order Book Depth & Spread Guard
        if order_book_analysis and not order_book_analysis.get("allowed_by_depth", True):
            for v in order_book_analysis.get("violations", []):
                veto_reasons.append(f"ORDER_BOOK_GUARD: {v}")

        # Gate 8: Candle Health & Anti-Chasing Guard
        if candle_health and not candle_health.get("allowed", True):
            for v in candle_health.get("violations", []):
                veto_reasons.append(f"CANDLE_HEALTH_GUARD: {v}")

        # Gate 9: Higher Timeframe (1H) Trend Alignment
        if direction.upper() == "BUY" and technicals.get("htf_bullish") is False and not is_liquidity_sweep:
            veto_reasons.append(
                "HTF_HEADWIND: Price is below 1-Hour 50 EMA. Counter-trend long entry prohibited."
            )

        # Gate 10: Market Laggard vs Bitcoin Filter
        if direction.upper() == "BUY" and technicals.get("is_laggard") is True and not is_liquidity_sweep:
            veto_reasons.append(
                "MARKET_LAGGARD: Coin is underperforming Bitcoin by >1.5% over 24h. Weak momentum."
            )

        passed = len(veto_reasons) == 0
        verdict = "APPROVED" if passed else "VETOED"
        return passed, verdict, veto_reasons
