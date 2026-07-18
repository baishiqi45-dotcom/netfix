"""Tests for netfix.proactive_alerts."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from netfix import proactive_alerts


class _TempHome(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["HOME"] = self._tmp.name
        # 阻断 ~/.netfix 复用
        import shutil
        shutil.rmtree(Path(self._tmp.name) / ".netfix", ignore_errors=True)
        proactive_alerts.clear_alerts()

    def tearDown(self):
        self._tmp.cleanup()


class TestExitIpChange(_TempHome):
    def test_exit_ip_type_change_emits_alert(self):
        a = proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="datacenter",
            previous_risk=15.0,
            current_risk=72.0,
        )
        self.assertIsNotNone(a)
        self.assertEqual(a["alert_type"], "exit_ip_type_change")
        self.assertEqual(a["payload"]["from_type"], "residential")
        self.assertEqual(a["payload"]["to_type"], "datacenter")

    def test_no_alert_when_ip_hash_unchanged(self):
        proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="residential",
            previous_risk=15.0,
            current_risk=20.0,
        )
        alerts = proactive_alerts.list_alerts(active_only=False)
        self.assertEqual(alerts, [])

    def test_no_alert_when_type_unchanged(self):
        # 住宅 → 住宅 不触发
        self.assertIsNone(proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="residential",
            previous_risk=15.0,
            current_risk=20.0,
        ))


class TestDnsSpike(_TempHome):
    def test_dns_spike_emits_alert_when_rate_jumps(self):
        a = proactive_alerts.detect_dns_failure_rate_spike(
            recent_total=10,
            recent_failed=6,
            baseline_failure_rate=0.05,
        )
        self.assertIsNotNone(a)
        self.assertEqual(a["alert_type"], "dns_failure_rate_spike")
        self.assertEqual(a["payload"]["window_failed"], 6)

    def test_no_alert_when_rate_stable(self):
        # 基线 0.05, 当前 0.05（低于 0.4 阈值）
        a = proactive_alerts.detect_dns_failure_rate_spike(
            recent_total=10,
            recent_failed=0,
            baseline_failure_rate=0.05,
        )
        self.assertIsNone(a)


class TestNodeTimeout(_TempHome):
    def test_three_consecutive_timeouts_triggers(self):
        a = proactive_alerts.detect_node_consecutive_timeout(
            profile_id="jp-1",
            consecutive_timeouts=3,
        )
        self.assertIsNotNone(a)
        self.assertEqual(a["alert_type"], "node_consecutive_timeout")
        self.assertEqual(a["payload"]["profile_id"], "jp-1")

    def test_no_alert_with_only_two_timeouts(self):
        a = proactive_alerts.detect_node_consecutive_timeout(
            profile_id="jp-1",
            consecutive_timeouts=2,
        )
        self.assertIsNone(a)


class TestRttSpike(_TempHome):
    def test_rtt_above_500ms_consecutive_triggers(self):
        a = proactive_alerts.detect_rtt_spike(
            current_rtt_ms=620,
            baseline_rtt_ms=180,
            gateway_rtt_ms=10,
            proxy_rtt_ms=620,
        )
        self.assertIsNotNone(a)
        self.assertEqual(a["alert_type"], "rtt_spike")
        self.assertEqual(a["payload"]["layer"], "proxy_node")

    def test_rtt_below_threshold_no_alert(self):
        a = proactive_alerts.detect_rtt_spike(
            current_rtt_ms=120,
            baseline_rtt_ms=100,
            gateway_rtt_ms=10,
            proxy_rtt_ms=120,
        )
        self.assertIsNone(a)


class TestToCard(_TempHome):
    def test_to_card_returns_minimal_card(self):
        a = proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="datacenter",
            previous_risk=15.0,
            current_risk=72.0,
            fingerprint="fp1",
        )
        self.assertIsNotNone(a)
        card = proactive_alerts.to_card(a, scenario_id="ai-service-risk-control")
        self.assertIn("headline", card)
        self.assertIn("body", card)
        self.assertEqual(card["alert_type"], "exit_ip_type_change")
        self.assertIn("buttons", card)
        self.assertTrue(len(card["buttons"]) >= 1)

    def test_dismiss_alert(self):
        a = proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="datacenter",
            previous_risk=15.0,
            current_risk=72.0,
        )
        self.assertIsNotNone(a)
        self.assertTrue(proactive_alerts.dismiss_alert(a["alert_id"]))
        # 再次触发应该被冷却
        a2 = proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="datacenter",
            previous_risk=15.0,
            current_risk=72.0,
        )
        self.assertIsNone(a2)


if __name__ == "__main__":
    unittest.main()
