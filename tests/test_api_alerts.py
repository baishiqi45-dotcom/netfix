"""HTTP API tests for the /alerts proactive-alert routes (Swift client contract)."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from netfix import api, proactive_alerts


class TestAlertsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server: HTTPServer = api.create_server(host="127.0.0.1", port=0, timeout=5)
        cls.server.timeout = 1
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        deadline = time.time() + 5
        while not cls.server.server_address[1] and time.time() < deadline:
            time.sleep(0.01)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._alert_file = Path(self._tmp.name) / "proactive_alerts.json"
        self._patch = patch.object(proactive_alerts, "ALERT_FILE", self._alert_file)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    # -- helpers ------------------------------------------------------------

    def _get(self, path):
        req = Request(f"{self.base}{path}", headers={"X-Netfix-Token": api._API_TOKEN})
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.headers.get("Content-Type"), "application/json")
            return json.loads(resp.read().decode("utf-8"))

    def _get_error(self, path, expected_status):
        req = Request(f"{self.base}{path}", headers={"X-Netfix-Token": api._API_TOKEN})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, expected_status)
        return json.loads(ctx.exception.read().decode("utf-8"))

    def _post_json(self, path, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", "X-Netfix-Token": api._API_TOKEN},
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            self.assertEqual(resp.headers.get("Content-Type"), "application/json")
            return json.loads(resp.read().decode("utf-8"))

    def _post_json_error(self, path, body, expected_status):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", "X-Netfix-Token": api._API_TOKEN},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=20)
        self.assertEqual(ctx.exception.code, expected_status)
        return json.loads(ctx.exception.read().decode("utf-8"))

    def _emit(self, fingerprint="fp-1"):
        alert = proactive_alerts.detect_exit_ip_type_change(
            previous_type="residential",
            current_type="datacenter",
            previous_risk=15.0,
            current_risk=72.0,
            fingerprint=fingerprint,
        )
        self.assertIsNotNone(alert)
        return alert

    @staticmethod
    def _parse_iso(value):
        return datetime.fromisoformat(value)

    # -- GET /alerts ---------------------------------------------------------

    def test_get_alerts_empty(self):
        data = self._get("/alerts")
        self.assertTrue(data["ok"])
        self.assertEqual(data["alerts"], [])
        self.assertEqual(data["schema_version"], "proactive_alerts.v1")

    def test_get_alerts_shape(self):
        stored = self._emit()
        data = self._get("/alerts")
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["alerts"]), 1)
        alert = data["alerts"][0]
        self.assertEqual(alert["alert_id"], stored["alert_id"])
        self.assertEqual(alert["alert_type"], "exit_ip_type_change")
        self.assertEqual(alert["severity"], "fail")
        self.assertTrue(alert["headline"])  # required by the Swift model
        self.assertTrue(alert["detail"])
        self.assertEqual(
            alert["suggested_actions"],
            ["check_ai_service", "switch_node", "dismiss"],
        )
        # evidence carries the raw payload plus a human-readable summary
        self.assertEqual(alert["evidence"]["from_type"], "residential")
        self.assertEqual(alert["evidence"]["to_type"], "datacenter")
        self.assertTrue(alert["evidence"]["summary"])
        # ISO8601 timestamps
        created = self._parse_iso(alert["created_at"])
        self.assertEqual(created.tzinfo, timezone.utc)
        self._parse_iso(alert["expires_at"])
        self.assertFalse(alert["dismissed"])
        self._parse_iso(alert["cooldown_until"])

    def test_get_alerts_excludes_dismissed_by_default(self):
        stored = self._emit()
        proactive_alerts.dismiss_alert(stored["alert_id"])
        data = self._get("/alerts")
        self.assertEqual(data["alerts"], [])
        data = self._get("/alerts?include_dismissed=1")
        self.assertEqual(len(data["alerts"]), 1)
        self.assertTrue(data["alerts"][0]["dismissed"])

    def test_get_alerts_unknown_subpath_404(self):
        self._get_error("/alerts/some-id", 404)

    def test_old_active_route_removed(self):
        self._get_error("/alerts/active", 404)

    # -- POST /alerts/<id>/decide -------------------------------------------

    def test_decide_dismiss(self):
        stored = self._emit()
        data = self._post_json(f"/alerts/{stored['alert_id']}/decide", {"action": "dismiss"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "proactive_alerts.v1")
        self.assertEqual(data["alerts"], [])  # dismissed alerts leave the default list
        raw = proactive_alerts.list_alerts(active_only=False, include_dismissed=True)
        self.assertTrue(raw[0]["dismissed"])

    def test_decide_remind_later_default_cooldown(self):
        stored = self._emit()
        before = time.time()
        data = self._post_json(f"/alerts/{stored['alert_id']}/decide", {"action": "remind_later"})
        self.assertTrue(data["ok"])
        raw = proactive_alerts.list_alerts(active_only=False, include_dismissed=True)
        self.assertFalse(raw[0]["dismissed"])  # remind_later does not dismiss
        self.assertGreaterEqual(raw[0]["cooldown_until"], before + 1800)
        self.assertLessEqual(raw[0]["cooldown_until"], time.time() + 1800)

    def test_decide_remind_later_explicit_cooldown(self):
        stored = self._emit()
        before = time.time()
        data = self._post_json(
            f"/alerts/{stored['alert_id']}/decide",
            {"action": "remind_later", "cooldown_seconds": 60},
        )
        self.assertTrue(data["ok"])
        raw = proactive_alerts.list_alerts(active_only=False, include_dismissed=True)
        self.assertGreaterEqual(raw[0]["cooldown_until"], before + 60)
        self.assertLessEqual(raw[0]["cooldown_until"], time.time() + 60)

    def test_decide_business_action_marks_dismissed(self):
        for action in (
            "check_ai_service",
            "switch_node",
            "start_read_only_check",
            "test_other_nodes",
            "open_proxy_app",
            "view_bandwidth_hogs",
        ):
            stored = self._emit(fingerprint=f"fp-{action}")
            data = self._post_json(f"/alerts/{stored['alert_id']}/decide", {"action": action})
            self.assertTrue(data["ok"], action)
            raw = proactive_alerts.list_alerts(active_only=False, include_dismissed=True)
            by_id = {a["alert_id"]: a for a in raw}
            self.assertTrue(by_id[stored["alert_id"]]["dismissed"], action)

    def test_decide_unknown_alert_404(self):
        data = self._post_json_error("/alerts/nope/decide", {"action": "dismiss"}, 404)
        self.assertFalse(data["ok"])
        self.assertIn("error", data)

    def test_decide_missing_action_400(self):
        stored = self._emit()
        data = self._post_json_error(f"/alerts/{stored['alert_id']}/decide", {}, 400)
        self.assertFalse(data["ok"])

    # -- POST /alerts/<id>/dismiss ------------------------------------------

    def test_dismiss_endpoint(self):
        stored = self._emit()
        data = self._post_json(f"/alerts/{stored['alert_id']}/dismiss", {})
        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "proactive_alerts.v1")
        self.assertEqual(data["alerts"], [])
        raw = proactive_alerts.list_alerts(active_only=False, include_dismissed=True)
        self.assertTrue(raw[0]["dismissed"])

    def test_dismiss_unknown_alert_404(self):
        data = self._post_json_error("/alerts/nope/dismiss", {}, 404)
        self.assertFalse(data["ok"])

    def test_old_dismiss_route_removed(self):
        self._post_json_error("/alerts/dismiss", {"alert_id": "x"}, 404)

    def test_old_scan_route_removed(self):
        self._post_json_error("/alerts/scan", {}, 404)

    # -- POST /alerts/<id>/cooldown -----------------------------------------

    def test_cooldown_endpoint(self):
        stored = self._emit()
        before = time.time()
        data = self._post_json(f"/alerts/{stored['alert_id']}/cooldown", {"seconds": 300})
        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "proactive_alerts.v1")
        self.assertEqual(len(data["alerts"]), 1)  # cooldown does not dismiss
        raw = proactive_alerts.list_alerts(active_only=False, include_dismissed=True)
        self.assertFalse(raw[0]["dismissed"])
        self.assertGreaterEqual(raw[0]["cooldown_until"], before + 300)
        self.assertLessEqual(raw[0]["cooldown_until"], time.time() + 300)
        cooldown_iso = data["alerts"][0]["cooldown_until"]
        self.assertGreaterEqual(self._parse_iso(cooldown_iso).timestamp(), before + 300)

    def test_cooldown_missing_seconds_400(self):
        stored = self._emit()
        data = self._post_json_error(f"/alerts/{stored['alert_id']}/cooldown", {}, 400)
        self.assertFalse(data["ok"])

    def test_cooldown_non_positive_seconds_400(self):
        stored = self._emit()
        for seconds in (0, -5):
            data = self._post_json_error(
                f"/alerts/{stored['alert_id']}/cooldown", {"seconds": seconds}, 400
            )
            self.assertFalse(data["ok"])

    def test_cooldown_unknown_alert_404(self):
        data = self._post_json_error("/alerts/nope/cooldown", {"seconds": 60}, 404)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
