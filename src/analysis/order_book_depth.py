"""Level 2 Order Book Depth and Bid/Ask Imbalance Analyzer for Crypto."""

import logging
from typing import Dict, Any, List, Optional
from src.exchanges.ccxt_client import CryptoExchangeClient

logger = logging.getLogger(__name__)


def analyze_order_book_depth(
    client: Optional[CryptoExchangeClient],
    symbol: str,
    limit: int = 20,
    max_spread_bps: float = 35.0,
    min_imbalance_ratio: float = 0.65,
) -> Dict[str, Any]:
    """
    Analyzes Level 2 order book depth from Binance via CCXT.
    - Bid/Ask imbalance ratio (>1.5 = buyer dominance; <0.67 = heavy seller resistance)
    - Spread in basis points (spread_bps > 35 = illiquid or high slippage risk)
    - Large wall detection (single level quantity > 3.0x average size)
    """
    if client is None or getattr(client, "exchange", None) is None:
        return {
            "available": False,
            "symbol": symbol,
            "allowed_by_depth": True,
            "reason": "No live exchange client configured"
        }

    try:
        ob = client.exchange.fetch_order_book(symbol, limit=limit)
    except Exception as e:
        logger.warning(f"Failed to fetch order book for {symbol}: {e}")
        return {
            "available": False,
            "symbol": symbol,
            "allowed_by_depth": True,
            "reason": f"Fetch error: {e}"
        }

    bids: List[List[float]] = ob.get("bids", [])
    asks: List[List[float]] = ob.get("asks", [])

    if not bids or not asks:
        return {
            "available": False,
            "symbol": symbol,
            "allowed_by_depth": True,
            "reason": "Empty order book"
        }

    total_bid_qty = sum(b[1] for b in bids)
    total_ask_qty = sum(a[1] for a in asks)
    total_qty = total_bid_qty + total_ask_qty

    imbalance = round(total_bid_qty / total_ask_qty, 3) if total_ask_qty > 0 else 999.0

    best_bid = float(bids[0][0])
    best_bid_qty = float(bids[0][1])
    best_ask = float(asks[0][0])
    best_ask_qty = float(asks[0][1])
    mid_price = (best_bid + best_ask) / 2.0
    spread_pts = best_ask - best_bid
    spread_bps = round((spread_pts / mid_price) * 10000, 1) if mid_price > 0 else 0.0

    # Stoikov Micro-Price (fair value adjusted for top-of-book bid/ask queue imbalance)
    top_qty = best_bid_qty + best_ask_qty
    if top_qty > 0:
        micro_price = round(((best_bid * best_ask_qty) + (best_ask * best_bid_qty)) / top_qty, 4)
        micro_price_premium_bps = round(((micro_price - mid_price) / mid_price) * 10000, 2)
    else:
        micro_price = mid_price
        micro_price_premium_bps = 0.0

    # Large wall check (> 3x average level size)
    num_levels = len(bids) + len(asks)
    avg_level_size = total_qty / num_levels if num_levels > 0 else 1.0
    
    ask_walls = [
        {"price": a[0], "quantity": round(a[1], 4), "multiple": round(a[1] / avg_level_size, 2)}
        for a in asks if (a[1] / avg_level_size) >= 3.0
    ]
    bid_walls = [
        {"price": b[0], "quantity": round(b[1], 4), "multiple": round(b[1] / avg_level_size, 2)}
        for b in bids if (b[1] / avg_level_size) >= 3.0
    ]

    violations = []
    if spread_bps > max_spread_bps:
        violations.append(f"SPREAD_WIDE: Spread is {spread_bps:.1f} bps (Max: {max_spread_bps:.1f} bps)")

    if imbalance < min_imbalance_ratio:
        violations.append(f"ASK_DOMINANCE: Bid/Ask imbalance is {imbalance:.2f} (Min: {min_imbalance_ratio:.2f})")

    if ask_walls and (not bid_walls or ask_walls[0]["multiple"] > 2.0 * (bid_walls[0]["multiple"] if bid_walls else 1.0)):
        nearest_ask_wall = ask_walls[0]["price"]
        dist_pct = round(((nearest_ask_wall - mid_price) / mid_price) * 100, 2)
        if dist_pct <= 0.8:
            violations.append(f"HEAVY_SELL_WALL: Imminent sell wall at ${nearest_ask_wall:.4f} (+{dist_pct}%)")

    allowed = len(violations) == 0

    return {
        "available": True,
        "symbol": symbol,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "micro_price": micro_price,
        "micro_price_premium_bps": micro_price_premium_bps,
        "spread_bps": spread_bps,
        "imbalance_ratio": imbalance,
        "total_bid_qty": round(total_bid_qty, 2),
        "total_ask_qty": round(total_ask_qty, 2),
        "ask_walls": ask_walls[:3],
        "bid_walls": bid_walls[:3],
        "allowed_by_depth": allowed,
        "violations": violations
    }
