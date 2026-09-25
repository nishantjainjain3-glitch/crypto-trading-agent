"""Continuous Public IP Whitelist Monitor and Alert Dispatcher."""

import os
import json
import time
import logging
import urllib.request
import subprocess
from typing import Dict, Any, List, Optional
from src.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

WHITELIST_FILE = os.path.join("data", "whitelisted_ips.json")
STATUS_FILE = os.path.join("data", "ip_status.json")
DEFAULT_KNOWN_IPS = ["152.59.152.111", "152.59.153.213", "49.37.100.175"]


def load_whitelisted_ips() -> List[str]:
    """Load known whitelisted IPs from disk or initialize with known addresses."""
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(f"Error loading whitelisted IPs: {e}")
    save_whitelisted_ips(DEFAULT_KNOWN_IPS)
    return DEFAULT_KNOWN_IPS


def save_whitelisted_ips(ips: List[str]):
    """Persist whitelisted IPs to disk."""
    os.makedirs(os.path.dirname(WHITELIST_FILE), exist_ok=True)
    with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
        json.dump(ips, f, indent=2)


def get_public_ip() -> Optional[str]:
    """Query current public IP address with multiple fast fallbacks."""
    endpoints = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
    ]
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    ip = resp.read().decode("utf-8").strip()
                    if ip and len(ip) <= 45 and "." in ip:
                        return ip
        except Exception:
            continue
    return None


def trigger_desktop_notification(new_ip: str):
    """Play alert sound and display Windows balloon notification asynchronously."""
    ps_cmd = (
        f"Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Media.SystemSounds]::Exclamation.Play(); "
        f"$notify = New-Object System.Windows.Forms.NotifyIcon; "
        f"$notify.Icon = [System.Drawing.SystemIcons]::Warning; "
        f"$notify.Visible = $True; "
        f"$notify.ShowBalloonTip(15000, 'Binance IP Alert', 'Public IP changed to {new_ip}. Add to Binance whitelist to continue trading.', [System.Windows.Forms.ToolTipIcon]::Warning); "
        f"Start-Sleep -Seconds 15; "
        f"$notify.Dispose();"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        logger.debug(f"Could not dispatch desktop notification: {e}")


class IPMonitor:
    """Monitors public IP against Binance trusted whitelist."""

    def __init__(self):
        self.notifier = TelegramNotifier()
        self.whitelisted_ips = load_whitelisted_ips()
        self.last_checked_ip = None
        self.last_alert_time = 0

    def check_ip(self) -> Dict[str, Any]:
        """Perform an IP check, verify against whitelist, and dispatch alerts if changed."""
        self.whitelisted_ips = load_whitelisted_ips()
        current_ip = get_public_ip()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC")

        if not current_ip:
            logger.warning("Could not determine current public IP.")
            return {
                "status": "UNKNOWN",
                "alert": False,
                "current_ip": self.last_checked_ip,
                "whitelisted_ips": self.whitelisted_ips,
                "last_checked": now_str,
                "message": "Public IP query timed out.",
            }

        self.last_checked_ip = current_ip
        is_whitelisted = current_ip in self.whitelisted_ips

        result = {
            "status": "WHITELISTED" if is_whitelisted else "UNAUTHORIZED_IP",
            "alert": not is_whitelisted,
            "current_ip": current_ip,
            "whitelisted_ips": self.whitelisted_ips,
            "last_checked": now_str,
        }

        if not is_whitelisted:
            result["message"] = f"CRITICAL: IP changed to {current_ip}. Not in Binance whitelist!"
            logger.critical(f"Public IP {current_ip} is NOT in Binance whitelist! Whitelisted: {self.whitelisted_ips}")
            
            # Rate limit alerts to once every 5 minutes
            if time.time() - self.last_alert_time > 300:
                self.last_alert_time = time.time()
                trigger_desktop_notification(current_ip)
                msg = (
                    f"⚠️ *Binance IP Whitelist Alert*\n\n"
                    f"Your public IP address changed to `{current_ip}`.\n"
                    f"Current whitelist: `{', '.join(self.whitelisted_ips)}`\n\n"
                    f"👉 Please add `{current_ip}` to your Binance API key whitelist immediately."
                )
                self.notifier.send_message(msg)
        else:
            result["message"] = f"Public IP {current_ip} is active and whitelisted."

        # Save status file
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving IP status file: {e}")

        return result
