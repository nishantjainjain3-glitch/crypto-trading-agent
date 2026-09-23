"""Telegram notification dispatcher for crypto alerts and daily wraps."""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Sends real-time trading notifications to Telegram."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        
        env_enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
        self.enabled = enabled if enabled is not None else env_enabled

    def send_message(self, message: str) -> bool:
        """Send Markdown-formatted text message to Telegram channel/user."""
        if not self.enabled or not self.bot_token or not self.chat_id:
            logger.debug("Telegram alerts disabled or missing credentials.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                return True
            logger.warning(f"Telegram API response: {resp.status_code} - {resp.text}")
            return False
        except Exception as e:
            logger.error(f"Failed sending Telegram alert: {e}")
            return False
