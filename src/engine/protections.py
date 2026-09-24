"""Crypto Protection Subsystem based on Freqtrade Protections."""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWNS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "crypto_trade_cooldowns.json"
)


class CryptoProtectionManager:
    """
    Freqtrade Protection Subsystem for Crypto Spot Trading.
    1. StoplossGuard: Locks a coin for 48 hours if stopped out twice in 48h.
    2. MaxDrawdownProtection: Freezes new entries if rolling drawdown exceeds 5.0%.
    3. DailyLossGuard: Halts trading if daily loss exceeds limit.
    4. AntiFallingKnifeGuard: Ensures pullbacks have bounced off the 24h lows (>25% range position).
    5. AntiChaseGuard: Vetoes entries if price is >2.5% beyond the breakout trigger.
    """

    def __init__(self, storage_path: str = DEFAULT_COOLDOWNS_FILE):
        self.storage_path = storage_path
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"cooldowns": {}, "stoploss_history": []}, f, indent=2)

    def _load_data(self) -> Dict[str, Any]:
        self._ensure_storage()
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cooldowns file: {e}")
            return {"cooldowns": {}, "stoploss_history": []}

    def _save_data(self, data: Dict[str, Any]):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cooldowns file: {e}")

    def is_in_cooldown(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """Returns (True, reason) if symbol is currently locked under active cooldown."""
        data = self._load_data()
        cooldowns = data.get("cooldowns", {})
        clean_sym = symbol.upper()

        if clean_sym not in cooldowns:
            return False, None

        cd = cooldowns[clean_sym]
        expires_str = cd.get("expires_at", "")
        try:
            expires_at = datetime.fromisoformat(expires_str)
            now = datetime.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if now < expires_at:
                remaining_hours = round((expires_at - now).total_seconds() / 3600.0, 1)
                return True, f"{cd.get('reason', 'Cooldown active')} (Expires in {remaining_hours}h)"
            else:
                del cooldowns[clean_sym]
                self._save_data(data)
                return False, None
        except Exception:
            return False, None

    def set_cooldown(self, symbol: str, hours: float, reason: str):
        """Enforces a temporary cooldown lockout on a cryptocurrency symbol."""
        clean_sym = symbol.upper()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=hours)

        data = self._load_data()
        data["cooldowns"][clean_sym] = {
            "symbol": clean_sym,
            "reason": reason,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "duration_hours": hours,
        }
        self._save_data(data)
        logger.info(f"Cooldown locked {clean_sym} for {hours}h: {reason}")

    def clear_cooldown(self, symbol: str):
        """Manually clears cooldown for a symbol."""
        clean_sym = symbol.upper()
        data = self._load_data()
        if clean_sym in data.get("cooldowns", {}):
            del data["cooldowns"][clean_sym]
            self._save_data(data)

    def record_stoploss_hit(self, symbol: str, exit_price: float, loss_pct: float) -> bool:
        """
        Freqtrade StoplossGuard.
        If 2 or more stoplosses occur on this symbol within 48 hours -> 48h lockout.
        """
        clean_sym = symbol.upper()
        now = datetime.now(timezone.utc)

        data = self._load_data()
        history = data.get("stoploss_history", [])

        history.append({
            "symbol": clean_sym,
            "exit_price": exit_price,
            "loss_pct": loss_pct,
            "timestamp": now.isoformat(),
        })

        cutoff = now - timedelta(hours=48)
        recent_hits = []
        for h in history:
            if h.get("symbol") == clean_sym:
                try:
                    ts = datetime.fromisoformat(h["timestamp"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        recent_hits.append(h)
                except Exception:
                    pass

        data["stoploss_history"] = history[-50:]
        self._save_data(data)

        if len(recent_hits) >= 2:
            self.set_cooldown(
                symbol=clean_sym,
                hours=48.0,
                reason=f"StoplossGuard: {len(recent_hits)} stop-loss hits in last 48 hours (Whipsaw Protection)",
            )
            return True
        return False

    def evaluate_entry_protections(
        self,
        symbol: str,
        current_equity: float,
        peak_equity: float,
        daily_loss_usd: float = 0.0,
        max_drawdown_pct: float = 5.0,
        daily_loss_limit_usd: float = 2.0,
    ) -> Dict[str, Any]:
        """Audits whether a new entry is permitted under portfolio protection guards."""
        clean_sym = symbol.upper()
        violations = []

        in_cd, cd_reason = self.is_in_cooldown(clean_sym)
        if in_cd:
            violations.append(f"COOLDOWN_ACTIVE: {cd_reason}")

        if peak_equity > 0:
            dd_pct = max(0.0, ((peak_equity - current_equity) / peak_equity) * 100.0)
            if dd_pct >= max_drawdown_pct:
                violations.append(f"MAX_DRAWDOWN_GUARD: Portfolio drawdown is {dd_pct:.1f}% (Limit: {max_drawdown_pct:.1f}%)")

        if daily_loss_usd <= -abs(daily_loss_limit_usd):
            violations.append(f"DAILY_LOSS_GUARD: Daily loss is ${abs(daily_loss_usd):.2f} (Limit: ${daily_loss_limit_usd:.2f})")

        allowed = len(violations) == 0
        return {
            "allowed": allowed,
            "symbol": clean_sym,
            "violations": violations,
            "in_cooldown": in_cd,
            "guard_status": "PASS" if allowed else "BLOCKED",
        }

    def evaluate_candle_health(
        self,
        symbol: str,
        current_price: float,
        high_24h: float,
        low_24h: float,
        strategy: str = "PULLBACK",
        trigger_price: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Intraday health check:
        - Prevents buying falling knives (pullback must hold above 25% of 24h range).
        - Prevents chasing extended green candles (>2.5% above trigger).
        """
        if current_price <= 0:
            return {"allowed": False, "violations": ["INVALID_PRICE: Price is <= 0"]}

        violations = []
        if high_24h > low_24h:
            range_pos = (current_price - low_24h) / (high_24h - low_24h)
        else:
            range_pos = 0.5

        if strategy.upper() in ["PULLBACK", "SSL_SWEEP"] and range_pos < 0.25:
            violations.append(f"FALLING_KNIFE: Price is at {range_pos * 100:.1f}% of 24h range (< 25% threshold)")

        if trigger_price > 0 and current_price > (trigger_price * 1.025):
            excess_pct = round(((current_price - trigger_price) / trigger_price) * 100, 2)
            violations.append(f"OVER_EXTENDED: Price chased +{excess_pct}% above trigger (Limit: +2.5%)")

        allowed = len(violations) == 0
        return {
            "allowed": allowed,
            "symbol": symbol.upper(),
            "range_position_pct": round(range_pos * 100, 1),
            "violations": violations,
        }
