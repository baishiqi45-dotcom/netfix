import time
import unittest
from unittest.mock import patch

from netfix import proxy_monitor_service


PROFILE = {
    "id": "p1",
    "name": "home-us-1",
    "protocol": "http",
    "host": "proxy.example.com",
    "port": 8000,
}

CHECK = {
    "profile_id": "p1",
    "status": "ok",
    "auth": "not_required",
    "tcp": "ok",
    "target": "https://www.gstatic.com/generate_204",
    "http_code": 204,
    "latency_ms": 120,
    "error": None,
    "checked_via": "http://proxy.example.com:8000",
}


class TestProxyMonitorService(unittest.TestCase):
    def tearDown(self):
        proxy_monitor_service.stop(persist=False)

    def test_run_once_updates_last_check_and_event(self):
        with patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[PROFILE]), \
                patch("netfix.proxy_monitor_service.residential_proxy.validate_saved_profile", return_value={"ok": True, "proxy_check": CHECK}) as validate_saved, \
                patch("netfix.proxy_monitor_service.settings.upsert_proxy_profile") as upsert, \
                patch("netfix.proxy_monitor_service.logs.append_event") as append_event:
            result = proxy_monitor_service.run_once("home-us-1", timeout=1, target_profile="ai_dev")

        self.assertTrue(result["ok"])
        self.assertEqual(validate_saved.call_args.kwargs["target_profile"], "ai_dev")
        self.assertTrue(validate_saved.call_args.kwargs["include_identity"])
        saved = upsert.call_args.args[0]
        self.assertEqual(saved["last_check"]["status"], "ok")
        self.assertIn("checked_at", saved["last_check"])
        self.assertNotIn("target", saved["last_check"])
        self.assertNotIn("checked_via", saved["last_check"])
        event = append_event.call_args.args[0]
        self.assertEqual(event["type"], "proxy_monitor")
        self.assertEqual(event["status"], "ok")
        self.assertNotIn("target", event["proxy_check"])
        self.assertNotIn("checked_via", event["proxy_check"])
        self.assertNotIn("proxy.example.com", str(event))

    def test_failed_check_records_repair_actions(self):
        failed_check = dict(CHECK)
        failed_check.update({
            "status": "fail",
            "auth": "failed",
            "http_code": 407,
            "error": "proxy_auth_required",
        })
        with patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[PROFILE]), \
                patch("netfix.proxy_monitor_service.residential_proxy.validate_saved_profile", return_value={"ok": False, "proxy_check": failed_check}), \
                patch("netfix.proxy_monitor_service.settings.upsert_proxy_profile") as upsert, \
                patch("netfix.proxy_monitor_service.logs.append_event") as append_event:
            result = proxy_monitor_service.run_once("p1", timeout=1, target_profile="ai_dev")

        self.assertFalse(result["ok"])
        action_ids = [item["id"] for item in result["repair_actions"]]
        self.assertIn("update_proxy_credentials", action_ids)
        self.assertIn("save_and_restart_monitor", action_ids)
        by_id = {item["id"]: item for item in result["repair_actions"]}
        self.assertEqual(by_id["update_proxy_credentials"]["ui_action"]["type"], "replace_profile_credentials")
        self.assertEqual(by_id["update_proxy_credentials"]["ui_action"]["profile_id"], "p1")
        self.assertEqual(by_id["save_and_restart_monitor"]["ui_action"]["type"], "start_monitor")
        saved = upsert.call_args.args[0]
        self.assertEqual([item["id"] for item in saved["last_check"]["repair_actions"]], action_ids)
        event = append_event.call_args.args[0]
        self.assertEqual([item["id"] for item in event["repair_actions"]], action_ids)

    def test_target_matrix_failure_suggests_export_and_matrix_review(self):
        failed_check = dict(CHECK)
        failed_check.update({
            "status": "fail",
            "error": "target_matrix_not_fully_validated",
        })
        with patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[PROFILE]), \
                patch("netfix.proxy_monitor_service.residential_proxy.validate_saved_profile", return_value={"ok": False, "proxy_check": failed_check}), \
                patch("netfix.proxy_monitor_service.settings.upsert_proxy_profile"), \
                patch("netfix.proxy_monitor_service.logs.append_event"):
            result = proxy_monitor_service.run_once("p1", timeout=1, target_profile="ai_dev")

        action_ids = [item["id"] for item in result["repair_actions"]]
        self.assertIn("review_validation_matrix", action_ids)
        self.assertIn("export_client_package", action_ids)
        by_id = {item["id"]: item for item in result["repair_actions"]}
        self.assertEqual(by_id["review_validation_matrix"]["ui_action"]["type"], "validate_profile")
        self.assertEqual(by_id["export_client_package"]["ui_action"]["type"], "export_profile")

    def test_start_runs_background_check_and_stop(self):
        with patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[PROFILE]), \
                patch("netfix.proxy_monitor_service.residential_proxy.validate_saved_profile", return_value={"ok": True, "proxy_check": CHECK}), \
                patch("netfix.proxy_monitor_service.settings.upsert_proxy_profile") as upsert, \
                patch("netfix.proxy_monitor_service.settings.update_proxy_monitor_settings") as monitor_settings, \
                patch("netfix.proxy_monitor_service.logs.append_event"):
            started = proxy_monitor_service.start("p1", interval=15, timeout=1)
            self.assertTrue(started["ok"])
            deadline = time.time() + 5
            while upsert.call_count == 0 and time.time() < deadline:
                time.sleep(0.05)
            self.assertGreaterEqual(upsert.call_count, 1)
            stopped = proxy_monitor_service.stop()

        self.assertTrue(stopped["ok"])
        self.assertFalse(stopped["monitor"]["running"])
        saved = monitor_settings.call_args_list[0].args[0]
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["profile_id"], "p1")
        self.assertEqual(saved["target_profile"], "baseline")
        cleared = monitor_settings.call_args_list[-1].args[0]
        self.assertFalse(cleared["enabled"])

    def test_start_missing_profile_fails_without_thread(self):
        with patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[]):
            result = proxy_monitor_service.start("missing", interval=15, timeout=1)
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])
        self.assertFalse(proxy_monitor_service.status()["monitor"]["running"])

    def test_process_stop_can_preserve_persisted_monitor_config(self):
        with patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[PROFILE]), \
                patch("netfix.proxy_monitor_service.residential_proxy.validate_saved_profile", return_value={"ok": True, "proxy_check": CHECK}), \
                patch("netfix.proxy_monitor_service.settings.upsert_proxy_profile"), \
                patch("netfix.proxy_monitor_service.settings.update_proxy_monitor_settings") as monitor_settings, \
                patch("netfix.proxy_monitor_service.logs.append_event"):
            started = proxy_monitor_service.start("p1", interval=15, timeout=1, target_profile="ai_dev")
            self.assertTrue(started["ok"])
            stopped = proxy_monitor_service.stop(persist=False)

        self.assertFalse(stopped["monitor"]["running"])
        self.assertEqual(stopped["monitor"]["target_profile"], "ai_dev")
        self.assertEqual(monitor_settings.call_count, 1)
        self.assertTrue(monitor_settings.call_args.args[0]["enabled"])
        self.assertEqual(monitor_settings.call_args.args[0]["target_profile"], "ai_dev")

    def test_restore_from_settings_restarts_persisted_monitor(self):
        persisted = {
            "enabled": True,
            "profile_id": "p1",
            "interval": 15,
            "target_url": "https://www.gstatic.com/generate_204",
            "target_profile": "ai_dev",
            "timeout": 1,
        }
        with patch("netfix.proxy_monitor_service.settings.get_proxy_monitor_settings", return_value=persisted), \
                patch("netfix.proxy_monitor_service.settings.get_proxy_profiles", return_value=[PROFILE]), \
                patch("netfix.proxy_monitor_service.residential_proxy.validate_saved_profile", return_value={"ok": True, "proxy_check": CHECK}), \
                patch("netfix.proxy_monitor_service.settings.upsert_proxy_profile"), \
                patch("netfix.proxy_monitor_service.settings.update_proxy_monitor_settings") as monitor_settings, \
                patch("netfix.proxy_monitor_service.logs.append_event"):
            result = proxy_monitor_service.restore_from_settings()

        self.assertTrue(result["ok"])
        self.assertTrue(result["restored"])
        self.assertTrue(result["monitor"]["running"])
        self.assertTrue(result["monitor"]["restored"])
        self.assertEqual(result["monitor"]["target_profile"], "ai_dev")
        monitor_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
