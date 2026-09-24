"""Service interface to read and update crypto market regime data."""

import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

REGIME_REPORT_FILE = os.path.join("data", "regime_report", "crypto_regime.json")

def get_current_regime() -> Dict[str, Any]:
    """Retrieve the latest regime score and component breakdown."""
    if os.path.exists(REGIME_REPORT_FILE):
        try:
            with open(REGIME_REPORT_FILE, "r") as f:
                data = json.load(f)
            composite = data.get("composite", {})
            components = data.get("components", {})
            return {
                "score": composite.get("score", 50.0),
                "zone": composite.get("zone", "NEUTRAL"),
                "guidance": composite.get("guidance", "Normal market conditions"),
                "as_of": data.get("metadata", {}).get("as_of", ""),
                "btc_trend": components.get("btc_trend", {}).get("signal", "N/A"),
                "funding": components.get("funding", {}).get("signal", "N/A"),
                "momentum": components.get("momentum_thrust", {}).get("signal", "N/A"),
            }
        except Exception as e:
            logger.error(f"Error reading regime report: {e}")

    # Fallback default
    return {
        "score": 50.0,
        "zone": "NEUTRAL",
        "guidance": "Neutral baseline regime",
        "as_of": "",
        "btc_trend": "Unknown",
        "funding": "Baseline",
        "momentum": "Neutral",
    }
