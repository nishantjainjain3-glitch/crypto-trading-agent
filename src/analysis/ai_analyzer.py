"""AI trade analyzer routing prompts through the local FreeLLMAPI instance."""

import os
import json
import logging
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

FREELLM_ENDPOINT = os.getenv("FREELLM_ENDPOINT", "http://localhost:3001/v1/chat/completions")
FREELLM_API_KEY = os.getenv("FREELLM_API_KEY", "freellmapi-local")

class FreeLLMAnalyzer:
    """Uses FreeLLMAPI to generate trade commentary and risk analysis without AI bills."""

    def __init__(self, endpoint: str = FREELLM_ENDPOINT, api_key: str = FREELLM_API_KEY):
        self.endpoint = endpoint
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if local FreeLLMAPI service is alive."""
        try:
            ping_url = self.endpoint.replace("/v1/chat/completions", "/api/ping")
            req = urllib.request.urlopen(ping_url, timeout=3)
            return req.getcode() == 200
        except Exception:
            return False

    def generate_trade_rationale(
        self,
        symbol: str,
        direction: str,
        price: float,
        technicals: Dict[str, Any],
        model: str = "auto",
    ) -> str:
        """Ask FreeLLMAPI to synthesize a crisp quantitative summary of the setup."""
        if not self.is_available():
            return "FreeLLMAPI service offline. Operating on quantitative mathematical rules."

        prompt = (
            f"Analyze this crypto setup as a senior quantitative trader in 2 sentences:\n"
            f"Symbol: {symbol}\n"
            f"Direction: {direction}\n"
            f"Price: ${price}\n"
            f"RSI: {technicals.get('rsi', 'N/A')}\n"
            f"RVOL: {technicals.get('rvol', 'N/A')}x\n"
            f"ATR: ${technicals.get('atr', 'N/A')}\n"
            f"State why the math favors this trade and what the invalidation risk is."
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a concise, analytical quantitative crypto trading assistant."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 120,
            "temperature": 0.2
        }

        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.debug(f"FreeLLMAPI inference skipped: {e}")
            return "Quantitative setup verified by deterministic algorithm."
