"""Resilient process supervisor that keeps the trading bot alive 24/7."""

import os
import sys
import time
import subprocess
import urllib.request
import logging
from logging.handlers import RotatingFileHandler

os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WATCHDOG] %(message)s",
    handlers=[
        RotatingFileHandler("data/watchdog.log", maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("watchdog")

from src.engine.ip_monitor import IPMonitor

PORT = int(os.getenv("PORT", 8000))
HEALTH_URL = f"http://localhost:{PORT}/api/portfolio"
MAX_FAILED_CHECKS = 3
CHECK_INTERVAL_SECONDS = 20

def is_healthy() -> bool:
    try:
        req = urllib.request.urlopen(HEALTH_URL, timeout=8)
        return req.getcode() == 200
    except Exception:
        return False

def run_supervisor():
    logger.info("Starting Autonomous Watchdog Supervisor...")
    cmd = [sys.executable, "run.py"]

    while True:
        logger.info(f"Launching trading bot process: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd)
        failed_checks = 0
        ip_monitor = IPMonitor()
        check_counter = 0

        # Wait 10s for initial boot
        time.sleep(10)

        while True:
            # Check if process is still running
            ret = proc.poll()
            if ret is not None:
                logger.error(f"Trading bot process exited unexpectedly with code {ret}!")
                break

            if is_healthy():
                failed_checks = 0
            else:
                failed_checks += 1
                logger.warning(f"Health check failed ({failed_checks}/{MAX_FAILED_CHECKS})")
                if failed_checks >= MAX_FAILED_CHECKS:
                    logger.error("Health check threshold exceeded. Terminating and restarting process...")
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
                    break

            # Periodically verify public IP against Binance whitelist (every 60s)
            check_counter += 1
            if check_counter % 3 == 0:
                try:
                    ip_status = ip_monitor.check_ip()
                    if ip_status.get("alert"):
                        logger.critical(f"IP MISMATCH DETECTED: {ip_status.get('message')}")
                except Exception as e:
                    logger.error(f"Error checking IP status in watchdog: {e}")

            time.sleep(CHECK_INTERVAL_SECONDS)

        logger.info("Restarting trading bot in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    while True:
        try:
            run_supervisor()
        except KeyboardInterrupt:
            logger.info("Watchdog supervisor stopped by user.")
            break
        except Exception as e:
            logger.exception(f"Fatal watchdog crash, auto-recovering in 5s: {e}")
            time.sleep(5)
