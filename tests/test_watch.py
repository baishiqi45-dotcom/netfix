import json
import unittest
from unittest.mock import patch

from netfix.cli import build_parser, cmd_proxy_monitor, cmd_watch


class TestWatchCommand(unittest.TestCase):
    def test_watch_single_run_outputs_json(self):
        parser = build_parser()
        args = parser.parse_args(["watch", "--max-runs", "1", "--json", "--timeout", "5"])
        with patch("builtins.print") as mock_print:
            rc = cmd_watch(args)
        self.assertEqual(rc, 0)
        calls = [c.args[0] for c in mock_print.call_args_list]
        self.assertTrue(calls)
        data = json.loads(calls[0])
        self.assertIn("event", data)
        self.assertIn("status", data)

    def test_proxy_monitor_single_run_updates_last_check(self):
        parser = build_parser()
        args = parser.parse_args([
            "proxy-monitor",
            "--profile",
            "home-us-1",
            "--max-runs",
            "1",
            "--json",
            "--timeout",
            "5",
        ])
        profile = {
            "id": "p1",
            "name": "home-us-1",
            "protocol": "http",
            "host": "proxy.example.com",
            "port": 8000,
        }
        check = {
            "profile_id": "p1",
            "status": "ok",
            "auth": "not_required",
            "tcp": "ok",
            "http_code": 204,
            "latency_ms": 120,
        }
        with patch("netfix.cli.settings.get_proxy_profiles", return_value=[profile]), \
                patch("netfix.cli.residential_proxy.validate_saved_profile", return_value={"ok": True, "proxy_check": check}), \
                patch("netfix.cli.settings.upsert_proxy_profile") as upsert, \
                patch("builtins.print") as mock_print:
            rc = cmd_proxy_monitor(args)

        self.assertEqual(rc, 0)
        upsert.assert_called_once()
        saved = upsert.call_args.args[0]
        self.assertEqual(saved["last_check"]["status"], "ok")
        data = json.loads(mock_print.call_args_list[0].args[0])
        self.assertEqual(data["event"], "proxy_check")
        self.assertEqual(data["status"], "ok")


if __name__ == "__main__":
    unittest.main()
