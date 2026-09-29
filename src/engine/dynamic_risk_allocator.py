"""Dynamic Risk Allocator and Anti-Martingale Sizing Engine.

Calculates optimal capital allocation using fractional Kelly criterion,
current portfolio drawdown dampening, and exchange tier-specific constraints.
"""

from typing import Dict, Any, List, Optional
import math


class DynamicRiskAllocator:
    """Computes capital allocation per trade based on performance and drawdown."""

    def __init__(
        self,
        min_notional_usd: float = 5.0,
        max_portfolio_risk_pct: float = 2.5,
        default_risk_fraction: float = 0.20,
    ):
        self.min_notional_usd = min_notional_usd
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.default_risk_fraction = default_risk_fraction

    def calculate_kelly_fraction(self, trade_history: List[Dict[str, Any]]) -> float:
        """Calculate quarter-Kelly optimal fraction from closed trade history."""
        if not trade_history or len(trade_history) < 5:
            return self.default_risk_fraction

        wins = [t.get("pnl_usd", 0.0) for t in trade_history if t.get("pnl_usd", 0.0) > 0]
        losses = [abs(t.get("pnl_usd", 0.0)) for t in trade_history if t.get("pnl_usd", 0.0) < 0]

        if not wins or not losses:
            return self.default_risk_fraction

        win_rate = len(wins) / len(trade_history)
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)

        if avg_loss <= 0:
            return self.default_risk_fraction

        payoff_ratio = avg_win / avg_loss
        loss_rate = 1.0 - win_rate

        # Full Kelly: (p * b - q) / b
        full_kelly = (win_rate * payoff_ratio - loss_rate) / payoff_ratio

        if full_kelly <= 0:
            # Negative mathematical edge, fall back to conservative minimum
            return 0.05

        # Quarter-Kelly to protect against parameter uncertainty and regime shifts
        quarter_kelly = 0.25 * full_kelly

        # Clamp between 5% and 30% of portfolio
        return max(0.05, min(0.30, quarter_kelly))

    def compute_drawdown_dampener(self, current_equity: float, peak_equity: float) -> float:
        """Compute capital scaling multiplier based on current peak-to-trough drawdown."""
        if peak_equity <= 0:
            return 1.0

        drawdown = max(0.0, (peak_equity - current_equity) / peak_equity)
        # Scaled dampener: at 0% drawdown -> 1.0x, at 10% drawdown -> 0.8x, at 25% drawdown -> 0.5x
        dampener = max(0.40, 1.0 - 2.0 * drawdown)
        return round(float(dampener), 3)

    def allocate_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        free_cash_usdt: float = 0.0,
        total_equity_usdt: float = 0.0,
        peak_equity_usdt: float = 0.0,
        trade_history: Optional[List[Dict[str, Any]]] = None,
        open_positions_count: int = 0,
        max_open_positions: int = 2,
        stop_loss: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute position size in USDT and base units with exchange filter validation."""
        sl = stop_loss if stop_loss is not None else (stop_loss_price if stop_loss_price is not None else entry_price * 0.98)
        stop_loss_price = sl
        if free_cash_usdt < self.min_notional_usd:
            return {
                "allocated_usd": 0.0,
                "quantity": 0.0,
                "is_approved": False,
                "reason": f"Free cash ${free_cash_usdt:.2f} is below exchange minNotional ${self.min_notional_usd:.2f}",
            }

        if open_positions_count >= max_open_positions:
            return {
                "allocated_usd": 0.0,
                "quantity": 0.0,
                "is_approved": False,
                "reason": f"Maximum open positions ({max_open_positions}) reached",
            }

        kelly_frac = self.calculate_kelly_fraction(trade_history or [])
        dampener = self.compute_drawdown_dampener(total_equity_usdt, peak_equity_usdt)

        # Tier-based sizing:
        # For small accounts (< $50), we concentrate available capital to exceed $5 minNotional
        if total_equity_usdt < 50.0:
            # Allocate 85-90% of free cash for the single active trade
            target_usd = min(free_cash_usdt * 0.90, free_cash_usdt)
        else:
            # Standard multi-position fractional Kelly sizing
            risk_per_trade_usd = total_equity_usdt * (self.max_portfolio_risk_pct / 100.0) * dampener
            stop_dist_pct = abs(entry_price - stop_loss_price) / entry_price if entry_price > 0 else 0.02
            stop_dist_pct = max(0.01, stop_dist_pct)  # at least 1%

            size_from_risk = risk_per_trade_usd / stop_dist_pct
            size_from_kelly = total_equity_usdt * kelly_frac * dampener

            target_usd = min(size_from_risk, size_from_kelly, free_cash_usdt * 0.95)

        # Enforce minimum notional
        if target_usd < self.min_notional_usd:
            if free_cash_usdt >= self.min_notional_usd:
                target_usd = self.min_notional_usd
            else:
                return {
                    "allocated_usd": 0.0,
                    "quantity": 0.0,
                    "is_approved": False,
                    "reason": f"Calculated size ${target_usd:.2f} is below minNotional ${self.min_notional_usd:.2f}",
                }

        quantity = target_usd / entry_price if entry_price > 0 else 0.0

        return {
            "symbol": symbol,
            "allocated_usd": round(target_usd, 2),
            "quantity": round(quantity, 6),
            "kelly_fraction": round(kelly_frac, 4),
            "drawdown_dampener": dampener,
            "is_approved": True,
            "reason": "APPROVED",
        }
