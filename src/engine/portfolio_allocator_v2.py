"""Portfolio Allocator V2: Capital Scaling Tiers and Asset Correlation Filter.

Dynamically scales max concurrent positions based on account equity and prevents
over-concentration in correlated assets as capital grows.
"""

from typing import Dict, Any, List, Optional
import numpy as np


# Estimated cross-asset correlation matrix for crypto universe
DEFAULT_CORRELATION_CLUSTERS = {
    "MAJOR": ["BTC/USDT", "ETH/USDT"],
    "L1_SOL_ECOSYSTEM": ["SOL/USDT", "SUI/USDT", "AVAX/USDT", "NEAR/USDT"],
    "PAYMENTS": ["XRP/USDT", "XLM/USDT", "HBAR/USDT"],
    "MEMES": ["DOGE/USDT", "PUMP/USDT", "PEPE/USDT"],
    "ORACLES_DEFI": ["LINK/USDT", "UNI/USDT", "ONDO/USDT", "ENA/USDT"],
}


class PortfolioAllocatorV2:
    """Scales portfolio capacity and enforces cluster diversification."""

    def __init__(self, min_notional_usd: float = 5.0):
        self.min_notional_usd = min_notional_usd
        self.clusters = DEFAULT_CORRELATION_CLUSTERS

    def get_max_allowed_positions(self, total_equity_usd: float) -> int:
        """Determine maximum concurrent positions based on capital tier."""
        if total_equity_usd < 50.0:
            return 1
        elif total_equity_usd < 150.0:
            return 2
        elif total_equity_usd < 500.0:
            return 3
        else:
            return 4

    def check_correlation_conflict(self, candidate_symbol: str, active_symbols: List[str]) -> bool:
        """Return True if candidate is in the same correlation cluster as an active holding."""
        if not active_symbols:
            return False

        candidate_cluster = None
        for cluster_name, syms in self.clusters.items():
            if candidate_symbol in syms:
                candidate_cluster = cluster_name
                break

        if not candidate_cluster:
            return False

        for active in active_symbols:
            if active in self.clusters.get(candidate_cluster, []):
                return True  # Correlated holding exists

        return False

    def compute_tier_allocation(
        self,
        candidate_symbol: str,
        total_equity_usd: float,
        free_cash_usd: float,
        active_symbols: List[str],
    ) -> Dict[str, Any]:
        """Compute capital budget for a candidate trade."""
        max_positions = self.get_max_allowed_positions(total_equity_usd)

        if len(active_symbols) >= max_positions and candidate_symbol not in active_symbols:
            return {
                "allocated_usd": 0.0,
                "allowed": False,
                "reason": f"Maximum positions for tier reached ({len(active_symbols)}/{max_positions})",
                "max_positions": max_positions,
            }

        # Check correlation conflict if multiple positions are enabled
        if max_positions > 1 and self.check_correlation_conflict(candidate_symbol, active_symbols):
            return {
                "allocated_usd": 0.0,
                "allowed": False,
                "reason": f"Correlation conflict: already holding asset in same cluster as {candidate_symbol}",
                "max_positions": max_positions,
            }

        # Allocation per position
        target_allocation_pct = 1.0 / max_positions
        target_usd = min(total_equity_usd * target_allocation_pct, free_cash_usd * 0.92)

        if target_usd < self.min_notional_usd:
            if free_cash_usd >= self.min_notional_usd:
                target_usd = min(free_cash_usd * 0.92, self.min_notional_usd * 1.05)
            else:
                return {
                    "allocated_usd": 0.0,
                    "allowed": False,
                    "reason": f"Insufficient cash (${free_cash_usd:.2f}) for minNotional",
                    "max_positions": max_positions,
                }

        return {
            "allocated_usd": round(target_usd, 2),
            "allowed": True,
            "max_positions": max_positions,
            "reason": "APPROVED",
        }
