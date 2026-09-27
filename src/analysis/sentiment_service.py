import time
import json
import logging
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_FNG_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": {"value": 50, "classification": "Neutral"}}
_FUNDING_CACHE: Dict[str, Dict[str, Any]] = {}

def get_crypto_fear_and_greed() -> Dict[str, Any]:
    """
    Fetches the alternative.me Crypto Fear & Greed Index with 1-hour in-memory cache.
    Returns: {"value": int, "classification": str}
    """
    global _FNG_CACHE
    now = time.time()
    if (now - _FNG_CACHE["timestamp"]) < 3600.0:
        return _FNG_CACHE["data"]

    url = "https://api.alternative.me/fng/?limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoTradingBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and "data" in data and len(data["data"]) > 0:
                item = data["data"][0]
                val = int(item.get("value", 50))
                cls_name = item.get("value_classification", "Neutral")
                _FNG_CACHE = {
                    "timestamp": now,
                    "data": {"value": val, "classification": cls_name}
                }
                return _FNG_CACHE["data"]
    except Exception as e:
        logger.warning(f"Failed fetching Fear & Greed Index: {e}. Using cached/fallback value.")

    return _FNG_CACHE["data"]

def get_binance_funding_rate(symbol: str) -> float:
    """
    Fetches the latest perpetual funding rate from Binance Public Futures API.
    Cached for 5 minutes per symbol to protect rate limits.
    Returns: float (e.g. 0.0001 = 0.01% per 8h). Returns 0.0 on error or if not available.
    """
    global _FUNDING_CACHE
    clean_sym = symbol.replace("/", "").replace("-", "").upper()
    now = time.time()

    if clean_sym in _FUNDING_CACHE:
        cached = _FUNDING_CACHE[clean_sym]
        if (now - cached["timestamp"]) < 300.0:
            return cached["rate"]

    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={clean_sym}&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoTradingBot/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                rate = float(data[0].get("fundingRate", 0.0))
                _FUNDING_CACHE[clean_sym] = {"timestamp": now, "rate": rate}
                return rate
    except Exception as e:
        logger.debug(f"Funding rate lookup failed for {symbol}: {e}")

    # Fallback to 0.0 if not listed on futures or lookup fails
    _FUNDING_CACHE[clean_sym] = {"timestamp": now, "rate": 0.0}
    return 0.0
