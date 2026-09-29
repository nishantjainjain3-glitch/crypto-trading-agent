"""Autonomous Self-Optimization Engine.

Analyzes counterfactual shadow trades, gatekeeper attribution, and market volatility
to dynamically calibrate risk parameters and strategy thresholds.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)


class SelfOptimizationEngine:
    """Evaluates strategy attribution and tunes execution parameters autonomously."""

    def __init__(self, data_dir: str = DEFAULT_DATA_DIR):
        self.data_dir = data_dir
        self.attribution_path = os.path.join(data_dir, "gatekeeper_attribution.json")
        self.ledger_path = os.path.join(data_dir, "counterfactual_ledger.json")
        self.log_path = os.path.join(data_dir, "self_optimization_log.json")
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def audit_gatekeeper_efficiency(self) -> Dict[str, Any]:
        """Calculates quantitative efficiency per safety gate from resolved counterfactuals."""
        attribution = {}
        if os.path.exists(self.attribution_path):
            try:
                with open(self.attribution_path, "r", encoding="utf-8") as f:
                    attribution = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read gatekeeper attribution: {e}")

        audit_results = {}
        for gate_name, data in attribution.items():
            saved = float(data.get("saved_loss_usd", 0.0))
            missed = float(data.get("missed_profit_usd", 0.0))
            total_impact = saved - missed
            total_volume = saved + missed
            vetoes = int(data.get("vetoes_count", 0))

            if total_volume > 0:
                efficiency_pct = round((saved / total_volume) * 100.0, 2)
            else:
                efficiency_pct = 100.0 if saved >= 0 else 0.0

            if efficiency_pct >= 70.0:
                health = "HEALTHY_PROTECTION"
                action = "MAINTAIN"
            elif efficiency_pct >= 45.0:
                health = "BALANCED"
                action = "MAINTAIN"
            else:
                health = "RESTRICTIVE"
                action = "CALIBRATE_LOOSER"

            audit_results[gate_name] = {
                "vetoes_count": vetoes,
                "saved_loss_usd": round(saved, 4),
                "missed_profit_usd": round(missed, 4),
                "net_benefit_usd": round(total_impact, 4),
                "efficiency_pct": efficiency_pct,
                "health": health,
                "action": action,
            }

        return audit_results

    def calibrate_volatility_regime(
        self,
        technicals_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Calculates market volatility across watchlist and calibrates swing targets."""
        atr_pcts = []
        if technicals_list:
            for tech in technicals_list:
                atr_p = tech.get("atr_pct", 0.0)
                if atr_p > 0:
                    atr_pcts.append(atr_p)

        avg_atr_pct = round(sum(atr_pcts) / len(atr_pcts), 2) if atr_pcts else 2.2

        if avg_atr_pct >= 3.0:
            regime = "HIGH_VOLATILITY"
            recommended_rvol = 1.20
            recommended_target_mult = 4.5
            recommended_min_target_pct = 5.5
            recommended_stop_pct = 2.2
        elif avg_atr_pct <= 1.8:
            regime = "LOW_VOLATILITY"
            recommended_rvol = 0.95
            recommended_target_mult = 3.2
            recommended_min_target_pct = 4.0
            recommended_stop_pct = 1.5
        else:
            regime = "NORMAL_VOLATILITY"
            recommended_rvol = 1.10
            recommended_target_mult = 3.8
            recommended_min_target_pct = 4.5
            recommended_stop_pct = 1.8

        return {
            "regime": regime,
            "avg_atr_pct": avg_atr_pct,
            "recommended_rvol": recommended_rvol,
            "recommended_target_mult": recommended_target_mult,
            "recommended_min_target_pct": recommended_min_target_pct,
            "recommended_stop_pct": recommended_stop_pct,
        }

    def run_optimization_cycle(
        self,
        gatekeeper: Optional[Any] = None,
        technicals_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Executes a full self-optimization cycle and applies parameter calibration."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        gate_audit = self.audit_gatekeeper_efficiency()
        vol_calib = self.calibrate_volatility_regime(technicals_list)

        # Check if INSUFFICIENT_VOLUME needs loosening based on audit or regime
        applied_rvol = vol_calib["recommended_rvol"]
        vol_gate = gate_audit.get("INSUFFICIENT_VOLUME", {})
        if vol_gate.get("health") == "RESTRICTIVE":
            applied_rvol = max(0.85, applied_rvol - 0.15)

        # Apply to gatekeeper instance if provided
        if gatekeeper:
            gatekeeper.min_rvol = round(applied_rvol, 2)
            logger.info(f"Self-Optimizer adjusted Gatekeeper min_rvol to {applied_rvol:.2f}x")

        record = {
            "timestamp": now_utc,
            "market_regime": vol_calib["regime"],
            "avg_atr_pct": vol_calib["avg_atr_pct"],
            "applied_rvol": round(applied_rvol, 2),
            "target_atr_multiplier": vol_calib["recommended_target_mult"],
            "min_target_pct": vol_calib["recommended_min_target_pct"],
            "stop_pct": vol_calib["recommended_stop_pct"],
            "gates_evaluated": len(gate_audit),
            "gate_audit": gate_audit,
        }

        # Save to log
        try:
            history = []
            if os.path.exists(self.log_path):
                with open(self.log_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append(record)
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(history[-50:], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to record self-optimization event: {e}")

        return record

    def get_latest_adaptation(self) -> Dict[str, Any]:
        """Returns the most recent adaptation snapshot."""
        if not os.path.exists(self.log_path):
            return {}
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            return history[-1] if history else {}
        except Exception:
            return {}
