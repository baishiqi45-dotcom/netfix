import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import provider_smoke_check

ROOT = Path(__file__).resolve().parents[1]


class TestProviderSmokeCheck(unittest.TestCase):
    def test_fixture_smoke_covers_domestic_text_and_vision_providers(self):
        result = provider_smoke_check.run(mode="fixtures")

        self.assertTrue(result["ok"], result.get("results"))
        checked = {item["provider"]: item for item in result["results"]}
        self.assertEqual(set(checked), {"deepseek", "moonshot_kimi", "minimax", "qwen"})
        self.assertEqual(checked["deepseek"]["task"], "text")
        self.assertEqual(checked["qwen"]["task"], "image_question")
        self.assertEqual(checked["moonshot_kimi"]["task"], "image_question")
        self.assertEqual(checked["minimax"]["task"], "image_question")
        self.assertEqual(checked["deepseek"]["usage"]["total_tokens"], 19)
        self.assertNotIn("sk-", str(result))

    def test_live_smoke_skips_without_provider_keys(self):
        with patch("scripts.provider_smoke_check.keychain.get_secret", return_value=None):
            result = provider_smoke_check.run(mode="live", providers=["deepseek"], require_live=False)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["results"][0]["status"], "skipped")
        self.assertEqual(result["results"][0]["reason_code"], "missing_api_key")

    def test_require_live_fails_when_provider_key_missing(self):
        with patch("scripts.provider_smoke_check.keychain.get_secret", return_value=None):
            result = provider_smoke_check.run(mode="live", providers=["deepseek"], require_live=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["results"][0]["status"], "failed")
        self.assertEqual(result["results"][0]["reason_code"], "missing_api_key")

    def test_validate_live_record_accepts_required_domestic_live_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "provider-smoke.json"
            path.write_text(json.dumps({
                "ok": True,
                "mode": "live",
                "checked": 4,
                "providers": ["deepseek", "moonshot_kimi", "minimax", "qwen"],
                "results": [
                    {"provider": "deepseek", "task": "text", "status": "ok"},
                    {"provider": "moonshot_kimi", "task": "image_question", "status": "ok"},
                    {"provider": "minimax", "task": "image_question", "status": "ok"},
                    {"provider": "qwen", "task": "image_question", "status": "ok"},
                ],
            }), encoding="utf-8")

            result = provider_smoke_check.validate_live_record(path)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["missing"], [])

    def test_validate_live_record_rejects_fixture_mode_and_skipped_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture-smoke.json"
            fixture_path.write_text(json.dumps(provider_smoke_check.run(mode="fixtures")), encoding="utf-8")
            skipped_path = Path(tmp) / "skipped-smoke.json"
            skipped_path.write_text(json.dumps({
                "ok": True,
                "mode": "live",
                "checked": 1,
                "providers": ["deepseek"],
                "results": [{"provider": "deepseek", "task": "text", "status": "skipped", "reason_code": "missing_api_key"}],
            }), encoding="utf-8")

            fixture_result = provider_smoke_check.validate_live_record(fixture_path)
            skipped_result = provider_smoke_check.validate_live_record(skipped_path)

        self.assertFalse(fixture_result["ok"])
        self.assertIn("mode", fixture_result["missing"])
        self.assertFalse(skipped_result["ok"])
        self.assertIn("provider.deepseek.status", skipped_result["missing"])
        self.assertIn("provider.moonshot_kimi", skipped_result["missing"])

    def test_status_reports_required_domestic_providers_without_reading_secret_values(self):
        with patch("scripts.provider_smoke_check.keychain.has_secret", return_value=False) as has_secret, \
                patch("scripts.provider_smoke_check.keychain.get_secret", side_effect=AssertionError("must not read secret")):
            result = provider_smoke_check.status()

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["providers_ready"], 0)
        self.assertEqual(result["summary"]["providers_missing"], 4)
        by_provider = {item["provider"]: item for item in result["providers"]}
        self.assertEqual(by_provider["deepseek"]["task"], "text")
        self.assertEqual(by_provider["moonshot_kimi"]["task"], "image_question")
        self.assertIn("NETFIX_LLM_API_KEY_DEEPSEEK", by_provider["deepseek"]["next_step"])
        self.assertEqual(has_secret.call_count, 4)

    def test_status_validates_complete_live_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "provider-smoke-live.json"
            record.write_text(json.dumps({
                "ok": True,
                "mode": "live",
                "checked": 4,
                "providers": ["deepseek", "moonshot_kimi", "minimax", "qwen"],
                "results": [
                    {"provider": "deepseek", "task": "text", "status": "ok"},
                    {"provider": "moonshot_kimi", "task": "image_question", "status": "ok"},
                    {"provider": "minimax", "task": "image_question", "status": "ok"},
                    {"provider": "qwen", "task": "image_question", "status": "ok"},
                ],
            }), encoding="utf-8")

            with patch("scripts.provider_smoke_check.keychain.has_secret", return_value=True):
                result = provider_smoke_check.status(record=record)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["record"]["ok"])
        self.assertEqual(result["summary"]["providers_ready"], 4)

    def test_status_rejects_fixture_record_for_live_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "provider-smoke-fixture.json"
            record.write_text(json.dumps(provider_smoke_check.run(mode="fixtures")), encoding="utf-8")

            with patch("scripts.provider_smoke_check.keychain.has_secret", return_value=True):
                result = provider_smoke_check.status(record=record)

        self.assertFalse(result["ok"])
        self.assertFalse(result["record"]["ok"])
        self.assertIn("mode", result["record"]["missing"])

    def test_status_cli_runs_when_script_is_executed_directly(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "provider_smoke_check.py"),
                "status",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertEqual(len(data["providers"]), 4)
        self.assertFalse(data["record"]["ok"])
        self.assertEqual(data["record"]["status"], "missing_record")


if __name__ == "__main__":
    unittest.main()
