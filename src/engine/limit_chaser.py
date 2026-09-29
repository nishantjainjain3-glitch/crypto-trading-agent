"""Maker Limit Chaser Execution Module.

Optimizes order execution by posting limit orders at the best bid/ask
and floating with the order book to capture maker fee rates before falling
back to market execution.
"""

from typing import Dict, Any, Optional
import time
import logging

logger = logging.getLogger(__name__)


class LimitChaser:
    """Manages post-only limit order submission, price adjustment, and fills."""

    def __init__(
        self,
        max_chase_attempts: int = 3,
        chase_timeout_seconds: float = 12.0,
        max_slippage_tolerance_pct: float = 0.20,
    ):
        self.max_chase_attempts = max_chase_attempts
        self.chase_timeout_seconds = chase_timeout_seconds
        self.max_slippage_tolerance_pct = max_slippage_tolerance_pct

    def compute_optimal_limit_price(
        self,
        symbol: str,
        direction: str,
        best_bid: float,
        best_ask: float,
        attempt: int = 1,
    ) -> float:
        """Calculate optimal post-only limit price to balance maker fill probability against urgency."""
        if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
            return best_bid if direction.upper() == "BUY" else best_ask

        spread = best_ask - best_bid
        if direction.upper() == "BUY":
            # Attempt 1: at best bid
            if attempt == 1:
                return round(best_bid, 6)
            # Attempt 2+: step up slightly inside spread without crossing ask
            step = min(spread * 0.40, spread - 0.000001)
            return round(best_bid + step, 6)
        else:
            if attempt == 1:
                return round(best_ask, 6)
            step = min(spread * 0.40, spread - 0.000001)
            return round(best_ask - step, 6)

    def execute_maker_buy(
        self,
        exchange_client: Any,
        symbol: str,
        quantity: float,
        current_market_price: float,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Execute buy order using limit chasing with graceful market order fallback."""
        bid = best_bid or (current_market_price * 0.9995)
        ask = best_ask or (current_market_price * 1.0005)

        initial_target_price = bid
        max_price = current_market_price * (1.0 + (self.max_slippage_tolerance_pct / 100.0))

        # Check if exchange client supports live orders
        if not exchange_client or not getattr(exchange_client, "exchange", None):
            return {
                "order_id": "SIM_MAKER_FILL",
                "symbol": symbol,
                "direction": "BUY",
                "fill_price": initial_target_price,
                "quantity": quantity,
                "order_type": "LIMIT_MAKER",
                "fee_saved_usd": round(quantity * initial_target_price * 0.00025, 4),
                "status": "FILLED",
            }

        attempts = 0
        order = None
        fill_price = current_market_price

        for attempt in range(1, self.max_chase_attempts + 1):
            limit_p = self.compute_optimal_limit_price(symbol, "BUY", bid, ask, attempt=attempt)
            if limit_p > max_price:
                logger.info(f"{symbol}: Limit chase exceeded max slippage {max_price}, executing market buy.")
                break

            try:
                formatted_qty = exchange_client.exchange.amount_to_precision(symbol, quantity)
                formatted_price = exchange_client.exchange.price_to_precision(symbol, limit_p)

                # Attempt post-only limit order
                order = exchange_client.exchange.create_order(
                    symbol=symbol,
                    type="limit",
                    side="buy",
                    amount=float(formatted_qty),
                    price=float(formatted_price),
                    params={"postOnly": True},
                )
                order_id = order.get("id")

                # Wait for fill
                start_wait = time.time()
                is_filled = False
                while (time.time() - start_wait) < (self.chase_timeout_seconds / self.max_chase_attempts):
                    time.sleep(1.5)
                    chk = exchange_client.exchange.fetch_order(order_id, symbol)
                    if chk.get("status") == "closed":
                        is_filled = True
                        fill_price = float(chk.get("average", limit_p))
                        break

                if is_filled:
                    return {
                        "order_id": order_id,
                        "symbol": symbol,
                        "direction": "BUY",
                        "fill_price": fill_price,
                        "quantity": quantity,
                        "order_type": "LIMIT_MAKER",
                        "fee_saved_usd": round(quantity * fill_price * 0.00025, 4),
                        "status": "FILLED",
                    }
                else:
                    # Cancel and re-evaluate
                    exchange_client.exchange.cancel_order(order_id, symbol)
                    # Update ticker for next attempt
                    t = exchange_client.fetch_ticker(symbol)
                    bid = t.get("last_price", limit_p)
                    ask = bid * 1.0005

            except Exception as e:
                logger.debug(f"{symbol} limit chase attempt {attempt} error: {e}")
                if order and order.get("id"):
                    try:
                        exchange_client.exchange.cancel_order(order.get("id"), symbol)
                    except Exception:
                        pass

        # Fallback to market order if limit chase timed out
        logger.info(f"{symbol}: Limit chaser falling back to market buy execution.")
        market_order = exchange_client.create_market_buy(symbol, quantity)
        return {
            "order_id": market_order.get("id"),
            "symbol": symbol,
            "direction": "BUY",
            "fill_price": market_order.get("average", current_market_price),
            "quantity": quantity,
            "order_type": "MARKET_TAKER",
            "fee_saved_usd": 0.0,
            "status": "FILLED",
        }
