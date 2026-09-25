"""Unit tests for IP whitelist monitoring and mismatch alerting."""

import os
import json
import pytest
from unittest.mock import patch
from src.engine.ip_monitor import IPMonitor, load_whitelisted_ips, save_whitelisted_ips


def test_load_and_save_whitelisted_ips(tmp_path):
    test_file = str(tmp_path / "whitelisted_ips.json")
    with patch("src.engine.ip_monitor.WHITELIST_FILE", test_file):
        initial = load_whitelisted_ips()
        assert "152.59.152.111" in initial

        custom_ips = ["1.2.3.4", "5.6.7.8"]
        save_whitelisted_ips(custom_ips)
        loaded = load_whitelisted_ips()
        assert loaded == custom_ips


def test_ip_monitor_whitelisted_match(tmp_path):
    test_status = str(tmp_path / "ip_status.json")
    with patch("src.engine.ip_monitor.STATUS_FILE", test_status), \
         patch("src.engine.ip_monitor.get_public_ip", return_value="152.59.152.111"), \
         patch("src.engine.ip_monitor.load_whitelisted_ips", return_value=["152.59.152.111", "152.59.153.213"]):
        monitor = IPMonitor()
        res = monitor.check_ip()
        assert res["status"] == "WHITELISTED"
        assert res["alert"] is False
        assert res["current_ip"] == "152.59.152.111"


def test_ip_monitor_unauthorized_ip_triggers_alert(tmp_path):
    test_status = str(tmp_path / "ip_status.json")
    with patch("src.engine.ip_monitor.STATUS_FILE", test_status), \
         patch("src.engine.ip_monitor.get_public_ip", return_value="103.200.15.42"), \
         patch("src.engine.ip_monitor.load_whitelisted_ips", return_value=["152.59.152.111", "152.59.153.213"]), \
         patch("src.engine.ip_monitor.trigger_desktop_notification") as mock_toast:
        monitor = IPMonitor()
        res = monitor.check_ip()
        assert res["status"] == "UNAUTHORIZED_IP"
        assert res["alert"] is True
        assert res["current_ip"] == "103.200.15.42"
        mock_toast.assert_called_once_with("103.200.15.42")
