"""Constant Proportion Portfolio Insurance (CPPI) and Dynamic Drawdown Cushion Engine.

Enforces an institutional mathematical floor on portfolio equity.
Scales allowable risk exposure proportionally to the distance between current equity
and the maximum drawdown floor, ensuring the account cannot breach drawdown limits.
"""

import math
from typing import Dict, Any, Optional


class CPPIRiskCushion:
    """
    CPPI Capital Protection Engine.

    Floor Equity = Peak Equity * (1 - max_drawdown_pct)
    Cushion = max(0, Current Equity - Floor Equity)
    Max Risk Exposure = Multiplier * Cushion
    """

    def __init__(
        self,
        max_drawdown_pct: float = 5.0,  # 5% maximum permissible account drawdown
        multiplier: float = 3.0,        # Exposure multiplier
        min_notional_usd: float = 5.0,  # Binance Spot minNotional threshold
    ):
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.multiplier = float(multiplier)
        self.min_notional_usd = float(min_notional_usd)

    def evaluate_cushion(
        self,
        current_equity: float,
        peak_equity: float,
    ) -> Dict[str, Any]:
        """
        Evaluate the remaining drawdown cushion and maximum permissible exposure.
        """
        if peak_equity <= 0:
            peak_equity = current_equity

        peak_equity = max(peak_equity, current_equity)
        floor_equity = peak_equity * (1.0 - self.max_drawdown_pct / 100.0)
        cushion = max(0.0, current_equity - floor_equity)
        current_drawdown_pct = ((peak_equity - current_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0

        max_risk_capital = self.multiplier * cushion
        is_safe = cushion > 0.05 and current_drawdown_pct < self.max_drawdown_pct

        return {
            "current_equity": round(current_equity, 4),
            "peak_equity": round(peak_equity, 4),
            "floor_equity": round(floor_equity, 4),
            "cushion_usd": round(cushion, 4),
            "current_drawdown_pct": round(current_drawdown_pct, 2),
            "max_drawdown_limit_pct": self.max_drawdown_pct,
            "max_risk_capital_usd": round(max_risk_capital, 4),
            "trading_allowed": is_safe,
            "status": "HEALTHY" if current_drawdown_pct < (self.max_drawdown_pct * 0.6) else (
                "CAUTION_DRAWDOWN" if is_safe else "DRAWDOWN_FLOOR_BREACH"
            ),
        }

    def constrain_allocation(
        self,
        proposed_usd: float,
        current_equity: float,
        peak_equity: float,
    ) -> Dict[str, Any]:
        """
        Constrains a candidate trade's dollar allocation so it cannot breach the CPPI floor.
        """
        cushion_info = self.evaluate_cushion(current_equity, peak_equity)
        if not cushion_info["trading_allowed"]:
            return {
                "allocated_usd": 0.0,
                "allowed": False,
                "reason": f"CPPI_FLOOR_PROTECTION: Current drawdown ({cushion_info['current_drawdown_pct']}%) exhausted safety cushion (${cushion_info['cushion_usd']}).",
                "cushion_info": cushion_info,
            }

        max_allowed = cushion_info["max_risk_capital_usd"]

        # If micro-account (< $25), allow minimum notional if cushion > 0
        if current_equity <= 25.0 and max_allowed < self.min_notional_usd:
            if cushion_info["cushion_usd"] > 0.10:
                final_usd = min(proposed_usd, current_equity * 0.95)
            else:
                return {
                    "allocated_usd": 0.0,
                    "allowed": False,
                    "reason": f"CPPI_CUSHION_TOO_TIGHT: Cushion ${cushion_info['cushion_usd']:.2f} insufficient for exchange minNotional ${self.min_notional_usd}.",
                    "cushion_info": cushion_info,
                }
        else:
            final_usd = min(proposed_usd, max_allowed)

        return {
            "allocated_usd": round(final_usd, 2),
            "allowed": final_usd >= self.min_notional_usd,
            "capped": final_usd < proposed_usd,
            "cushion_info": cushion_info,
        }
