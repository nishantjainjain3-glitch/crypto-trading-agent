"""Post-Trade Transaction Cost Analysis (TCA) and Implementation Shortfall Engine.

Tracks order execution slippage, decomposes costs into Spread, Delay, and Market Impact,
and feeds historical per-symbol slippage penalties into the scanner and execution routers.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_TCA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "crypto_tca_history.json"
)


class TransactionCostAnalyzer:
    """Measures and manages execution quality, slippage, and implementation shortfall."""

    def __init__(self, storage_path: str = DEFAULT_TCA_PATH):
        self.storage_path = storage_path
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if not os.path.exists(self.storage_path) or os.path.getsize(self.storage_path) == 0:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"records": [], "symbol_summary": {}}, f, indent=2)

    def load_records(self) -> List[Dict[str, Any]]:
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("records", [])
        except Exception as e:
            logger.warning(f"Failed to load TCA records: {e}")
            return []

    def record_execution(
        self,
        symbol: str,
        side: str,
        decision_price: float,
        fill_price: float,
        quantity: float,
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        order_type: str = "LIMIT",
        execution_latency_ms: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Record and analyze a completed trade execution.

        Implementation Shortfall (IS):
        - BUY: (fill_price - decision_price) / decision_price
        - SELL: (decision_price - fill_price) / decision_price
        """
        if decision_price <= 0:
            decision_price = fill_price

        side_mult = 1.0 if side.upper() == "BUY" else -1.0
        slippage_unit = (fill_price - decision_price) * side_mult
        slippage_bps = (slippage_unit / decision_price) * 10000.0
        total_shortfall_usd = slippage_unit * quantity

        # Half-spread cost if book quote was provided
        spread_bps = 0.0
        if bid_price and ask_price and ask_price > bid_price:
            mid = (ask_price + bid_price) / 2.0
            half_spread = (ask_price - mid)
            spread_bps = (half_spread / mid) * 10000.0

        market_impact_bps = max(0.0, slippage_bps - spread_bps)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "side": side.upper(),
            "decision_price": round(decision_price, 6),
            "fill_price": round(fill_price, 6),
            "quantity": quantity,
            "slippage_bps": round(slippage_bps, 2),
            "spread_bps": round(spread_bps, 2),
            "market_impact_bps": round(market_impact_bps, 2),
            "total_shortfall_usd": round(total_shortfall_usd, 4),
            "order_type": order_type,
            "execution_latency_ms": round(execution_latency_ms, 1),
        }

        # Persist record
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            records = data.get("records", [])
            records.append(record)
            if len(records) > 200:
                records = records[-200:]
            data["records"] = records

            # Update symbol summary
            sym_records = [r for r in records if r.get("symbol") == symbol]
            avg_slippage = sum(r.get("slippage_bps", 0.0) for r in sym_records) / len(sym_records)
            data.setdefault("symbol_summary", {})[symbol] = {
                "sample_count": len(sym_records),
                "avg_slippage_bps": round(avg_slippage, 2),
                "last_fill_price": fill_price,
            }

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error persisting TCA record: {e}")

        return record

    def get_symbol_slippage_penalty(self, symbol: str) -> float:
        """
        Returns a score penalty (0 to 15 points) for coins that exhibit excessive execution slippage.
        """
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sym_info = data.get("symbol_summary", {}).get(symbol, {})
            avg_bps = sym_info.get("avg_slippage_bps", 0.0)
            if avg_bps > 15.0:
                # Penalize 1 point per 2 bps over 15 bps, up to 15 points
                return min(15.0, (avg_bps - 15.0) / 2.0)
        except Exception:
            pass
        return 0.0

    def get_tca_summary(self) -> Dict[str, Any]:
        """Aggregate summary of all historical execution quality metrics."""
        records = self.load_records()
        if not records:
            return {
                "total_executions": 0,
                "avg_slippage_bps": 0.0,
                "total_shortfall_usd": 0.0,
                "status": "NO_EXECUTIONS_RECORDED",
            }

        total_shortfall = sum(r.get("total_shortfall_usd", 0.0) for r in records)
        avg_slippage = sum(r.get("slippage_bps", 0.0) for r in records) / len(records)
        avg_latency = sum(r.get("execution_latency_ms", 0.0) for r in records) / len(records)

        return {
            "total_executions": len(records),
            "avg_slippage_bps": round(avg_slippage, 2),
            "total_shortfall_usd": round(total_shortfall, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "status": "HEALTHY" if avg_slippage < 10.0 else "ELEVATED_SLIPPAGE",
        }
