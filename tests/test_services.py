import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from netfix import services


class TestLoadServices(unittest.TestCase):
    def test_builtin_loads_groups(self):
        data = services.load_services()
        self.assertIn("groups", data)
        ids = [g["id"] for g in data["groups"]]
        self.assertIn("ai", ids)
        self.assertIn("dev", ids)

    def test_user_override_merges(self):
        with TemporaryDirectory() as tmp:
            user_file = Path(tmp) / "services.json"
            user_file.write_text(
                json.dumps({"groups": [{"id": "custom", "name": "Custom", "services": []}]}),
                encoding="utf-8",
            )
            with patch.object(services, "user_services_path", return_value=user_file):
                data = services.load_services()
                ids = [g["id"] for g in data["groups"]]
                self.assertIn("custom", ids)
                self.assertIn("ai", ids)


class TestCheckServices(unittest.TestCase):
    def test_direct_endpoint_returns_status(self):
        results = services.check_services(
            group_ids=["common"],
            proxy_url=None,
            mixed_port=59999,
            use_system_proxy=False,
            timeout=2,
            parallel=False,
        )
        # common group has google/youtube/twitter/telegram
        self.assertTrue(len(results) >= 4)
        for r in results:
            self.assertIn(r.get("status"), {"ok", "warn", "fail"})

    def test_codex_compat_produces_legacy_names(self):
        results = services.check_services(
            group_ids=["ai"],
            proxy_url=None,
            mixed_port=59999,
            use_system_proxy=False,
            timeout=2,
            parallel=False,
        )
        compat = services.codex_compat_diagnostics(results)
        names = [c.get("name") for c in compat]
        self.assertIn("codex_api_direct", names)


if __name__ == "__main__":
    unittest.main()
