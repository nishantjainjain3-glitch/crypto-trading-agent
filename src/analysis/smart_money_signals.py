"""Binance Web3 Smart Money live signal and net inflow feed integration."""

import logging
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8
UA_HEADER = {"User-Agent": "binance-web3/3.0 (Skill)", "Content-Type": "application/json"}

# Binance Web3 Endpoints
SMART_MONEY_SIGNAL_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/web/signal/smart-money/ai"
SMART_MONEY_INFLOW_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/tracker/wallet/token/inflow/rank/query/ai"


def fetch_smart_money_signals(chain_id: str = "56", page_size: int = 50) -> List[Dict[str, Any]]:
    """Fetch real-time smart money wallet buy/sell signals from Binance Web3 API."""
    try:
        payload = {"chainId": chain_id, "page": 1, "pageSize": min(page_size, 100)}
        res = requests.post(SMART_MONEY_SIGNAL_URL, json=payload, headers=UA_HEADER, timeout=TIMEOUT_SECONDS)
        if res.status_code == 200:
            data = res.json().get("data", {})
            return data.get("list", []) if isinstance(data, dict) else (data or [])
    except Exception as e:
        logger.debug(f"Failed fetching smart money signals on chain {chain_id}: {e}")
    return []


def fetch_smart_money_inflows(chain_id: str = "56", period: str = "24h") -> List[Dict[str, Any]]:
    """Fetch tokens with the highest smart money net inflow from Binance Web3 API."""
    try:
        payload = {"chainId": chain_id, "tagType": 2, "period": period}
        res = requests.post(SMART_MONEY_INFLOW_URL, json=payload, headers=UA_HEADER, timeout=TIMEOUT_SECONDS)
        if res.status_code == 200:
            return res.json().get("data", []) or []
    except Exception as e:
        logger.debug(f"Failed fetching smart money inflows on chain {chain_id}: {e}")
    return []


def analyze_smart_money_backing(symbol: str) -> Dict[str, Any]:
    """
    Cross-references a candidate token against Binance Web3 smart money signals.
    Checks BSC (56) and Solana (CT_501) for whale and institutional accumulation.
    """
    base_coin = symbol.split("/")[0].upper()
    
    # Query smart money signals across major chains
    signals_bsc = fetch_smart_money_signals(chain_id="56", page_size=50)
    signals_sol = fetch_smart_money_signals(chain_id="CT_501", page_size=50)
    all_signals = signals_bsc + signals_sol

    matched_signals = [
        s for s in all_signals
        if s.get("ticker", "").upper() == base_coin or s.get("ticker", "").upper() == f"${base_coin}"
    ]

    if matched_signals:
        best_sig = matched_signals[0]
        direction = best_sig.get("direction", "buy").upper()
        sm_count = best_sig.get("smartMoneyCount", 1)
        exit_rate_str = str(best_sig.get("exitRate", "0%")).replace("%", "")
        try:
            exit_rate = float(exit_rate_str)
        except ValueError:
            exit_rate = 0.0

        is_active = best_sig.get("status") == "active"
        is_accumulating = direction == "BUY" and exit_rate < 50.0

        return {
            "has_signal": True,
            "is_accumulating": is_accumulating,
            "direction": direction,
            "smart_money_count": sm_count,
            "exit_rate_pct": exit_rate,
            "status": best_sig.get("status", "unknown"),
            "max_gain": best_sig.get("maxGain", "0%"),
            "alert_price": best_sig.get("alertPrice"),
            "rationale": f"Binance Smart Money Signal: {sm_count} smart wallets buying ({direction}) with {exit_rate}% exit rate.",
        }

    return {
        "has_signal": False,
        "is_accumulating": False,
        "direction": "NEUTRAL",
        "smart_money_count": 0,
        "exit_rate_pct": 0.0,
        "rationale": "No direct on-chain smart money whale signal active.",
    }
