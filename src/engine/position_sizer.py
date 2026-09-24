import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class PositionSizer:
    """
    Ray Fu 1% ATR Volatility Position Sizer.
    
    Rules:
    - Never risk more than target_risk_pct (default 1.0%) of total equity on any trade.
    - Stop loss distance is derived from ATR (typically 1.5x - 2.0x ATR) or structure wicks.
    - Quantity = (Total Capital * Risk Pct) / (Entry Price - Stop Loss)
    - Enforces maximum capital allocation per position (e.g. 33% max) to ensure diversification,
      adapting to 95% for micro accounts (<= $25) to satisfy exchange minNotional ($5.00).
    """

    def __init__(
        self,
        total_capital: Optional[float] = None,
        risk_pct_per_trade: Optional[float] = None,
        max_capital_per_trade_pct: Optional[float] = None,
    ):
        if total_capital is None:
            total_capital = float(os.getenv("PAPER_CAPITAL_USDT", "9.27"))
        if risk_pct_per_trade is None:
            risk_pct_per_trade = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "5.0"))
        if max_capital_per_trade_pct is None:
            max_capital_per_trade_pct = 95.0 if total_capital <= 25.0 else 33.33
        self.total_capital = float(total_capital)
        self.risk_pct_per_trade = float(risk_pct_per_trade)
        self.max_capital_per_trade_pct = float(max_capital_per_trade_pct)

    def calculate_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        atr: float,
        current_equity: float,
    ) -> Dict[str, Any]:
        """Compute exact position size, risk amount, and capital commitment."""
        if entry_price <= 0:
            raise ValueError("Entry price must be positive.")

        equity = current_equity if current_equity > 0 else self.total_capital
        dollar_risk_target = equity * (self.risk_pct_per_trade / 100.0)

        # Distance to stop loss
        stop_distance = abs(entry_price - stop_loss)
        min_stop_distance = max(atr * 0.5, entry_price * 0.005)  # At least 0.5% buffer

        if stop_distance < min_stop_distance:
            stop_distance = min_stop_distance
            logger.info(f"{symbol}: Stop distance too tight, expanded to {stop_distance:.4f}")

        # Raw quantity
        raw_quantity = dollar_risk_target / stop_distance
        gross_capital = raw_quantity * entry_price

        # Cap at max allocation per position (allow up to 95% for accounts <= 25 to satisfy minNotional)
        cap_pct = 95.0 if equity <= 25.0 else self.max_capital_per_trade_pct
        max_capital_allowed = equity * (cap_pct / 100.0)
        if gross_capital > max_capital_allowed:
            capped_quantity = max_capital_allowed / entry_price
            effective_risk = capped_quantity * stop_distance
            gross_capital = max_capital_allowed
            quantity = capped_quantity
            was_capped = True
        else:
            quantity = raw_quantity
            effective_risk = dollar_risk_target
            was_capped = False

        # Format units based on price tier
        precision = 4 if entry_price < 10 else (3 if entry_price < 100 else 6)
        formatted_qty = round(quantity, precision)

        return {
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "stop_distance": round(stop_distance, 4),
            "stop_distance_pct": round((stop_distance / entry_price) * 100, 2),
            "target_risk_usd": round(dollar_risk_target, 2),
            "effective_risk_usd": round(effective_risk, 2),
            "quantity": formatted_qty,
            "allocated_capital_usd": round(gross_capital, 2),
            "was_capped": was_capped,
            "equity_at_entry": round(equity, 2),
        }
