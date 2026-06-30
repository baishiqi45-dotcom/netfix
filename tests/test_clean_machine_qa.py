import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import clean_machine_qa

ROOT = Path(__file__).resolve().parents[1]


class TestCleanMachineQA(unittest.TestCase):
    def test_template_writes_pending_structured_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean-machine-qa.json"

            result = clean_machine_qa.write_template(path)

            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["path"], str(path))
        self.assertEqual(data["schema_version"], "netfix_clean_machine_qa.v1")
        self.assertEqual(data["result"], "pending")
        for check in clean_machine_qa.REQUIRED_CHECKS:
            self.assertEqual(data["checks"][check], "pending")
        self.assertIn("residential_proxy_profile_lifecycle", data["checks"])
        self.assertIn("domestic_llm_provider_setup", data["checks"])
        self.assertIn("release_readiness_reviewed", data["checks"])
        self.assertEqual(data["screenshots"], [])

    def test_template_can_prefill_version_and_dmg_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "clean-machine-qa.json"
            manifest = root / "release-manifest.json"
            dmg = root / "Netfix-0.2.0.dmg"
            manifest.write_text(json.dumps({"version": "0.2.0"}), encoding="utf-8")
            dmg.write_bytes(b"fake dmg")
            expected_sha = clean_machine_qa.sha256(dmg)

            result = clean_machine_qa.write_template(path, manifest=manifest, dmg=dmg)

            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(data["app_version"], "0.2.0")
        self.assertEqual(data["dmg_sha256"], expected_sha)
        self.assertEqual(data["artifact"]["release_manifest"], str(manifest.resolve()))
        self.assertEqual(data["artifact"]["dmg"], str(dmg.resolve()))

    def test_template_cli_accepts_manifest_and_dmg_prefill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "clean-machine-qa.json"
            manifest = root / "release-manifest.json"
            dmg = root / "Netfix-0.2.0.dmg"
            manifest.write_text(json.dumps({"version": "0.2.0"}), encoding="utf-8")
            dmg.write_bytes(b"fake dmg")
            expected_sha = clean_machine_qa.sha256(dmg)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "clean_machine_qa.py"),
                    "template",
                    str(path),
                    "--manifest",
                    str(manifest),
                    "--dmg",
                    str(dmg),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["app_version"], "0.2.0")
        self.assertEqual(data["dmg_sha256"], expected_sha)

    def test_validate_rejects_pending_or_incomplete_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "dashboard.png"
            screenshot.write_bytes(b"fake png")
            path = root / "clean-machine-qa.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "checks": {
                    "dmg_mounts": "pass",
                    "bundled_backend_smoke": "pass",
                    "app_launches": "pending",
                },
                "screenshots": ["dashboard.png"],
            }), encoding="utf-8")

            result = clean_machine_qa.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("checks.app_launches", result["missing"])
        self.assertIn("checks.web_console_renders", result["missing"])

    def test_status_explains_pending_record_next_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean-machine-qa.json"
            clean_machine_qa.write_template(path)

            result = clean_machine_qa.status(path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["checks_passed"], 0)
        self.assertEqual(result["summary"]["checks_incomplete"], len(clean_machine_qa.REQUIRED_CHECKS))
        self.assertIn("Run this on a clean Mac", result["next_steps"][0])
        by_check = {item["id"]: item for item in result["checks"]}
        self.assertEqual(by_check["app_launches"]["status"], "pending")
        self.assertIn("Launch Netfix.app", by_check["app_launches"]["next_step"])
        self.assertIn("replace credentials", by_check["residential_proxy_profile_lifecycle"]["next_step"])
        self.assertIn("DeepSeek", by_check["domestic_llm_provider_setup"]["next_step"])
        self.assertIn("release-readiness.json", by_check["release_readiness_reviewed"]["next_step"])
        self.assertIn("screenshots", {item["id"] for item in result["fields"] if item["status"] != "complete"})

    def test_status_explains_missing_record_template_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean-machine-qa.json"

            result = clean_machine_qa.status(path)

        self.assertFalse(result["schema_ok"])
        self.assertIn("clean_machine_qa.py template", result["next_steps"][0])

    def test_validate_accepts_complete_record_with_screenshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web-console.png"
            dashboard.write_bytes(b"fake dashboard")
            web.write_bytes(b"fake web")
            path = root / "clean-machine-qa.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "macOS clean VM",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web-console.png"],
            }), encoding="utf-8")

            result = clean_machine_qa.validate(path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])

    def test_status_marks_complete_record_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web-console.png"
            dashboard.write_bytes(b"fake dashboard")
            web.write_bytes(b"fake web")
            path = root / "clean-machine-qa.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "macOS clean VM",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web-console.png"],
            }), encoding="utf-8")

            result = clean_machine_qa.status(path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["fields_incomplete"], 0)
        self.assertEqual({item["status"] for item in result["checks"]}, {"pass"})

    def test_status_cli_runs_when_script_is_executed_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean-machine-qa.json"
            clean_machine_qa.write_template(path)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "clean_machine_qa.py"),
                    "status",
                    str(path),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertEqual(data["summary"]["checks_incomplete"], len(clean_machine_qa.REQUIRED_CHECKS))

    def test_release_evidence_rejects_blank_clean_machine_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qa_record = root / "clean-machine-qa.json"
            qa_record.write_text("{}", encoding="utf-8")
            legal = root / "legal.md"
            smoke = root / "smoke.json"
            legal.write_text("legal review completed", encoding="utf-8")
            smoke.write_text('{"ok": true}', encoding="utf-8")
            evidence = root / "release-evidence.json"
            evidence.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "clean-machine-qa.json",
                "legal_review_completed": True,
                "legal_review_record": "legal.md",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "smoke.json",
            }), encoding="utf-8")

            from scripts import release_evidence
            result = release_evidence.validate(evidence)

        self.assertFalse(result["ok"])
        self.assertIn("clean_machine_qa_record", result["missing"])


if __name__ == "__main__":
    unittest.main()
