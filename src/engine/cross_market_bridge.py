"""Peer Capability Bridge for Crypto Trading Agent (Binance USDT Spot).
Exchanges engineering capabilities, risk modules, and diagnostic tools with the Indian Trading Agent.

Architectural Rule:
- Crypto bot focuses 100% on crypto market data, pairs, and execution.
- No Indian equities, Nifty, India VIX, or Indian policy data are evaluated.
- Shares quantitative tools (order book depth, SMC liquidity sweeps, MFE/MAE autopsies) and imports peer tools (readiness scorecard, zero-cost AI router).
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("CryptoPeerCapabilityBridge")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRATCH_DIR = os.path.dirname(PROJECT_ROOT)
SHARED_BUS_PATH = os.path.join(SCRATCH_DIR, "cross_market_intelligence.json")


def _read_shared_bus() -> Dict[str, Any]:
    if os.path.exists(SHARED_BUS_PATH):
        try:
            with open(SHARED_BUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug("Error reading shared capability bus: %s", e)
    return {}


class CryptoCrossMarketBridge:
    """Manages peer engineering exchange with the Indian desk."""

    def __init__(self, bus_path: str = SHARED_BUS_PATH):
        self.bus_path = bus_path

    def publish_status(
        self,
        capabilities: Optional[List[str]] = None,
        active_improvements: Optional[List[str]] = None,
        assistance_requests: Optional[List[str]] = None,
        borrowed_capabilities: Optional[List[str]] = None,
    ):
        """Broadcasts current capabilities and performance to the shared bus."""
        bus_data = _read_shared_bus()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Load local crypto performance metrics
        ledger_path = os.path.join(PROJECT_ROOT, "data", "crypto_paper_ledger.json")
        benchmarks = {
            "win_rate_pct": 42.11,
            "profit_factor": 0.78,
            "max_drawdown_pct": 3.69,
            "total_trades": 19,
        }
        if os.path.exists(ledger_path):
            try:
                with open(ledger_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    benchmarks["win_rate_pct"] = d.get("win_rate_pct", 42.11)
                    benchmarks["profit_factor"] = d.get("profit_factor", 0.78)
                    benchmarks["max_drawdown_pct"] = d.get("max_drawdown_pct", 3.69)
                    benchmarks["total_trades"] = d.get("total_trades", 19)
            except Exception:
                pass

        bus_data["crypto_desk"] = {
            "desk_id": "CRYPTO_WORKSTATION",
            "market_focus": "Binance Spot (USDT)",
            "currency": "USDT",
            "last_updated": now_str,
            "available_capabilities": capabilities or [
                "order_book_depth_analyzer",
                "liquidity_sweep_detector",
                "mfe_mae_autopsy_engine",
                "counterfactual_tracker",
                "dynamic_breakeven_ratchet",
                "readiness_scorecard_auditor",
            ],
            "performance_benchmarks": benchmarks,
            "active_improvements": active_improvements or [
                "Tightened breakeven ratchet to 0.8 ATR to curb trailing stop lag.",
                "Enforced 45-minute post-loss cooldown to prevent revenge trading.",
                "Integrated 100-point institutional readiness scorecard auditor.",
            ],
            "peer_assistance_requests": assistance_requests or [],
            "borrowed_capabilities": borrowed_capabilities or [
                "readiness_scorecard_auditor",
                "zero_cost_ai_fleet",
            ],
        }
        bus_data["last_bus_update"] = now_str

        tmp_path = f"{self.bus_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(bus_data, f, indent=2)
            os.replace(tmp_path, self.bus_path)
            logger.info("Published crypto engineering status to capability bus.")
        except Exception as e:
            logger.error("Error writing to capability bus: %s", e)

    def publish_telemetry(self, *args, **kwargs):
        """Backwards-compatible alias that forwards to publish_status."""
        return self.publish_status()

    def audit_peer_capabilities(self) -> Dict[str, Any]:
        """
        Audits what algorithms and tools the Indian desk possesses.
        Checks if the crypto bot is lacking any tools that the peer has already built.
        """
        bus_data = _read_shared_bus()
        indian_desk = bus_data.get("indian_desk", {})
        peer_caps = set(indian_desk.get("available_capabilities", []))
        my_caps = {
            "order_book_depth_analyzer",
            "liquidity_sweep_detector",
            "mfe_mae_autopsy_engine",
            "counterfactual_tracker",
            "dynamic_breakeven_ratchet",
            "readiness_scorecard_auditor",
        }

        lacking = list(peer_caps - my_caps)
        return {
            "peer_desk_id": indian_desk.get("desk_id", "INDIAN_MARKET_WORKSTATION"),
            "peer_capabilities": list(peer_caps),
            "lacking_capabilities": lacking,
            "peer_improvements": indian_desk.get("active_improvements", []),
        }


crypto_cross_bridge = CryptoCrossMarketBridge()
