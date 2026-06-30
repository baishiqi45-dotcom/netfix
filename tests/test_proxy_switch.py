import json
import unittest
from unittest.mock import patch

from netfix.cli import build_parser, cmd_proxy_switch


class FakeTier2Core:
    name = "v2rayN"

    def __init__(self):
        self.switched_to = None

    def can_api_switch(self):
        return False

    def get_active_profile(self):
        return {"id": "active", "remarks": "active"}

    def list_profiles(self):
        return [
            {"id": "active", "remarks": "active"},
            {"id": "backup", "remarks": "backup"},
        ]

    def switch_profile(self, profile_id):
        self.switched_to = profile_id
        return True


class TestProxySwitchCommand(unittest.TestCase):
    def test_dry_run_lists_candidate(self):
        parser = build_parser()
        args = parser.parse_args(["proxy-switch", "--auto", "--dry-run", "--json", "--timeout", "5"])
        with patch("builtins.print") as mock_print:
            rc = cmd_proxy_switch(args)
        self.assertEqual(rc, 0)
        calls = [c.args[0] for c in mock_print.call_args_list]
        self.assertTrue(calls)
        data = json.loads(calls[0])
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("dry_run"))
        self.assertIn("profile", data)

    def test_tier2_json_switch_rejects_yes_without_switching(self):
        parser = build_parser()
        args = parser.parse_args([
            "proxy-switch",
            "--profile",
            "backup",
            "--yes",
            "--json",
        ])
        core = FakeTier2Core()
        with patch("netfix.cli.detect_environment", return_value={}), \
                patch("netfix.cli._enrich_env", return_value={}), \
                patch("netfix.cli.get_core", return_value=core), \
                patch("builtins.print") as mock_print:
            rc = cmd_proxy_switch(args)

        self.assertEqual(rc, 1)
        self.assertIsNone(core.switched_to)
        data = json.loads(mock_print.call_args_list[0].args[0])
        self.assertFalse(data["ok"])
        self.assertIn("Tier 2", data["error"])


if __name__ == "__main__":
    unittest.main()
