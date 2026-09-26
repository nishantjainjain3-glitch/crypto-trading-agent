import os
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class CounterfactualTracker:
    """
    Mechanical Counterfactual Ledger inspired by Phil (core/counterfactual.py).
    Records candidate trade setups that were vetoed by gatekeeper filters,
    and tracks their hypothetical market performance to measure empirical
    filter efficiency (dollars saved vs profit missed).
    """

    def __init__(
        self,
        ledger_path: str = "data/counterfactual_ledger.json",
        attribution_path: str = "data/gatekeeper_attribution.json",
        default_stake_usd: float = 15.0,
        expiry_hours: float = 12.0,
        cooldown_minutes: float = 15.0,
    ):
        self.ledger_path = ledger_path
        self.attribution_path = attribution_path
        self.default_stake_usd = default_stake_usd
        self.expiry_hours = expiry_hours
        self.cooldown_minutes = cooldown_minutes
        self.entries: List[Dict[str, Any]] = []
        self._load_ledger()

    def _load_ledger(self):
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read counterfactual ledger: {e}. Starting fresh.")
                self.entries = []
        else:
            self.entries = []
            self._save_ledger()

    def _save_ledger(self):
        try:
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving counterfactual ledger: {e}")

    def _extract_primary_gate(self, veto_reason: str) -> str:
        """Extracts standard gate identifier from reason string."""
        if not veto_reason:
            return "UNKNOWN_FILTER"
        reason_str = veto_reason.strip()
        if ":" in reason_str:
            gate = reason_str.split(":", 1)[0].strip()
            return gate
        tokens = reason_str.split()
        return tokens[0].strip() if tokens else "UNKNOWN_FILTER"

    def record_declined_setup(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        atr: float,
        veto_reasons: List[str],
        score: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Records a declined candidate setup if valid and not recently registered.
        """
        if entry_price <= 0 or stop_loss <= 0 or target_price <= 0:
            return None
        if not veto_reasons:
            return None

        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Deduplication check: do not record if same symbol was declined within cooldown
        for item in reversed(self.entries):
            if item["symbol"] == symbol and item.get("status") == "OPEN":
                try:
                    entry_t = datetime.fromisoformat(item["entry_time"].replace(" UTC", "")).replace(tzinfo=timezone.utc)
                    if (now - entry_t).total_seconds() < (self.cooldown_minutes * 60.0):
                        return None
                except Exception:
                    pass

        primary_gate = self._extract_primary_gate(veto_reasons[0])

        entry = {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol,
            "direction": direction.upper(),
            "entry_price": float(entry_price),
            "stop_loss": float(stop_loss),
            "target_price": float(target_price),
            "atr": float(atr),
            "score": float(score),
            "primary_gate": primary_gate,
            "all_veto_reasons": veto_reasons,
            "hypothetical_stake_usd": self.default_stake_usd,
            "status": "OPEN",
            "outcome": "PENDING",
            "entry_time": now_iso,
            "exit_time": None,
            "exit_price": None,
            "highest_price": float(entry_price),
            "lowest_price": float(entry_price),
            "hypothetical_pnl_usd": 0.0,
            "saved_loss_usd": 0.0,
            "missed_profit_usd": 0.0,
        }

        self.entries.append(entry)
        self._save_ledger()
        self.recompute_attribution()
        logger.info(f"Recorded counterfactual declined setup {symbol} vetoed by {primary_gate}")
        return entry

    def evaluate_open_counterfactuals(self, market_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Updates open counterfactual trades with current market quotes.
        Resolves targets, stops, or expirations.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        resolved = []

        for item in self.entries:
            if item.get("status") != "OPEN":
                continue

            symbol = item["symbol"]
            current_p = market_prices.get(symbol)
            if not current_p or current_p <= 0:
                continue

            entry_p = item["entry_price"]
            direction = item.get("direction", "BUY")
            stop_loss = item["stop_loss"]
            target_p = item["target_price"]
            stake = item.get("hypothetical_stake_usd", self.default_stake_usd)

            item["highest_price"] = max(item.get("highest_price", entry_p), current_p)
            item["lowest_price"] = min(item.get("lowest_price", entry_p), current_p)

            # Check expiry
            try:
                entry_t = datetime.fromisoformat(item["entry_time"].replace(" UTC", "")).replace(tzinfo=timezone.utc)
                hours_open = (now - entry_t).total_seconds() / 3600.0
            except Exception:
                hours_open = 0.0

            if direction == "BUY":
                if current_p >= target_p:
                    item["status"] = "RESOLVED"
                    item["outcome"] = "MISSED_PROFIT"
                    item["exit_price"] = target_p
                    item["exit_time"] = now_iso
                    pnl_raw = stake * ((target_p - entry_p) / entry_p)
                    # Deduct roundtrip taker fee ~0.15%
                    item["missed_profit_usd"] = round(max(0.0, pnl_raw - (stake * 0.0015)), 2)
                    item["hypothetical_pnl_usd"] = item["missed_profit_usd"]
                    resolved.append(item)
                elif current_p <= stop_loss:
                    item["status"] = "RESOLVED"
                    item["outcome"] = "SAVED_LOSS"
                    item["exit_price"] = stop_loss
                    item["exit_time"] = now_iso
                    saved_raw = stake * ((entry_p - stop_loss) / entry_p)
                    item["saved_loss_usd"] = round(saved_raw, 2)
                    item["hypothetical_pnl_usd"] = -round(saved_raw, 2)
                    resolved.append(item)
                elif hours_open >= self.expiry_hours:
                    item["status"] = "EXPIRED"
                    item["outcome"] = "EXPIRED"
                    item["exit_price"] = current_p
                    item["exit_time"] = now_iso
                    net_diff = stake * ((current_p - entry_p) / entry_p)
                    item["hypothetical_pnl_usd"] = round(net_diff, 2)
                    resolved.append(item)

        if resolved:
            self._save_ledger()
            self.recompute_attribution()

        return resolved

    def recompute_attribution(self) -> Dict[str, Any]:
        """
        Aggregates financial efficiency by gatekeeper filter rule.
        """
        attribution: Dict[str, Any] = {}

        for item in self.entries:
            gate = item.get("primary_gate", "OTHER")
            if gate not in attribution:
                attribution[gate] = {
                    "total_vetoed": 0,
                    "resolved_count": 0,
                    "open_count": 0,
                    "saved_losses_usd": 0.0,
                    "missed_profits_usd": 0.0,
                    "net_benefit_usd": 0.0,
                    "saved_trades_count": 0,
                    "missed_trades_count": 0,
                }

            attr = attribution[gate]
            attr["total_vetoed"] += 1

            status = item.get("status")
            if status == "OPEN":
                attr["open_count"] += 1
            else:
                attr["resolved_count"] += 1
                saved = item.get("saved_loss_usd", 0.0)
                missed = item.get("missed_profit_usd", 0.0)
                attr["saved_losses_usd"] = round(attr["saved_losses_usd"] + saved, 2)
                attr["missed_profits_usd"] = round(attr["missed_profits_usd"] + missed, 2)
                attr["net_benefit_usd"] = round(attr["saved_losses_usd"] - attr["missed_profits_usd"], 2)

                if item.get("outcome") == "SAVED_LOSS":
                    attr["saved_trades_count"] += 1
                elif item.get("outcome") == "MISSED_PROFIT":
                    attr["missed_trades_count"] += 1

        try:
            with open(self.attribution_path, "w", encoding="utf-8") as f:
                json.dump(attribution, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving gatekeeper attribution: {e}")

        return attribution

    def get_summary(self) -> Dict[str, Any]:
        """Returns overall counterfactual performance summary."""
        total_vetoed = len(self.entries)
        open_count = sum(1 for e in self.entries if e.get("status") == "OPEN")
        resolved_count = total_vetoed - open_count
        total_saved = round(sum(e.get("saved_loss_usd", 0.0) for e in self.entries), 2)
        total_missed = round(sum(e.get("missed_profit_usd", 0.0) for e in self.entries), 2)
        net_saved = round(total_saved - total_missed, 2)

        return {
            "total_vetoed_setups": total_vetoed,
            "open_counterfactuals": open_count,
            "resolved_counterfactuals": resolved_count,
            "total_capital_saved_usd": total_saved,
            "total_profit_missed_usd": total_missed,
            "net_filter_benefit_usd": net_saved,
        }
