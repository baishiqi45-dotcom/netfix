import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import release_evidence
from scripts import clean_machine_qa
from scripts import legal_release_review
from scripts import provider_smoke_check

ROOT = Path(__file__).resolve().parents[1]


def _write_valid_legal_review(root: Path, name: str = "legal-review.json") -> Path:
    privacy = root / f"{name}-privacy.md"
    eula = root / f"{name}-eula.md"
    privacy.write_text("privacy policy reviewed", encoding="utf-8")
    eula.write_text("eula reviewed", encoding="utf-8")
    legal = root / name
    legal.write_text(json.dumps({
        "schema_version": "netfix_legal_release_review.v1",
        "result": "pass",
        "reviewer": "Legal reviewer",
        "reviewed_at": "2026-06-25",
        "privacy_policy_artifact": privacy.name,
        "eula_artifact": eula.name,
        "checks": {check: "pass" for check in legal_release_review.REQUIRED_CHECKS},
    }), encoding="utf-8")
    return legal


class TestReleaseEvidence(unittest.TestCase):
    def test_template_writes_required_manual_gate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"

            result = release_evidence.write_template(path)

            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["path"], str(path))
        self.assertEqual(data["schema_version"], "netfix_release_evidence.v1")
        self.assertFalse(data["clean_machine_qa_passed"])
        self.assertFalse(data["legal_review_completed"])
        self.assertFalse(data["live_provider_smoke_passed"])
        self.assertEqual(data["clean_machine_qa_record"], "")
        self.assertEqual(data["legal_review_record"], "")
        self.assertEqual(data["live_provider_smoke_record"], "")

    def test_template_can_prefill_record_paths_without_passing_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"

            result = release_evidence.write_template(
                path,
                clean_machine_qa_record="clean-machine-qa.json",
                legal_review_record="legal-release-review.json",
                live_provider_smoke_record="provider-smoke-live.json",
            )

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertFalse(data["clean_machine_qa_passed"])
        self.assertFalse(data["legal_review_completed"])
        self.assertFalse(data["live_provider_smoke_passed"])
        self.assertEqual(data["clean_machine_qa_record"], "clean-machine-qa.json")
        self.assertEqual(data["legal_review_record"], "legal-release-review.json")
        self.assertEqual(data["live_provider_smoke_record"], "provider-smoke-live.json")

    def test_template_cli_accepts_prefilled_record_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "release_evidence.py"),
                    "template",
                    str(path),
                    "--clean-machine-qa-record",
                    "clean-machine-qa.json",
                    "--legal-review-record",
                    "legal-release-review.json",
                    "--live-provider-smoke-record",
                    "provider-smoke-live.json",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["clean_machine_qa_record"], "clean-machine-qa.json")
        self.assertEqual(data["legal_review_record"], "legal-release-review.json")
        self.assertEqual(data["live_provider_smoke_record"], "provider-smoke-live.json")

    def test_status_resolves_prefilled_relative_record_paths_to_evidence_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "release-evidence.json"
            release_evidence.write_template(
                path,
                clean_machine_qa_record="clean-machine-qa.json",
                legal_review_record="legal-release-review.json",
                live_provider_smoke_record="provider-smoke-live.json",
            )

            result = release_evidence.status(path)

        by_gate = {item["id"]: item for item in result["gates"]}
        self.assertIn(str(root / "clean-machine-qa.json"), by_gate["clean_machine_qa"]["next_steps"][0])
        self.assertIn(str(root / "legal-release-review.json"), by_gate["legal_review"]["next_steps"][0])
        self.assertIn(str(root / "provider-smoke-live.json"), by_gate["live_provider_smoke"]["next_steps"][0])

    def test_status_explains_next_steps_for_blank_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"
            release_evidence.write_template(path)

            result = release_evidence.status(path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"], {"complete": 0, "incomplete": 3})
        by_gate = {item["id"]: item for item in result["gates"]}
        self.assertEqual(by_gate["clean_machine_qa"]["status"], "missing_flag")
        self.assertIn("clean_machine_qa.py template", by_gate["clean_machine_qa"]["next_steps"][0])
        self.assertIn("--manifest", by_gate["clean_machine_qa"]["next_steps"][0])
        self.assertIn("--dmg", by_gate["clean_machine_qa"]["next_steps"][0])
        self.assertEqual(by_gate["legal_review"]["status"], "missing_flag")
        self.assertIn("legal_release_review.py template", by_gate["legal_review"]["next_steps"][0])
        self.assertIn("--privacy-policy", by_gate["legal_review"]["next_steps"][0])
        self.assertIn("--eula", by_gate["legal_review"]["next_steps"][0])
        self.assertEqual(by_gate["live_provider_smoke"]["status"], "missing_flag")
        self.assertIn("provider_smoke_check.py --live --require-live --json", by_gate["live_provider_smoke"]["next_steps"][0])

    def test_status_explains_missing_evidence_file_template_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"

            result = release_evidence.status(path)

        self.assertFalse(result["schema_ok"])
        self.assertIn("release_evidence.py template", result["next_steps"][0])
        self.assertIn("--clean-machine-qa-record", result["next_steps"][0])
        self.assertIn("--legal-review-record", result["next_steps"][0])

    def test_validate_accepts_complete_evidence_with_record_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web.png"
            dashboard.write_bytes(b"dashboard")
            web.write_bytes(b"web")
            qa = root / "qa.json"
            legal = _write_valid_legal_review(root, "legal.json")
            smoke = root / "smoke.json"
            qa.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "clean mac",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web.png"],
            }), encoding="utf-8")
            smoke.write_text('{"ok": true}', encoding="utf-8")
            smoke.write_text(json.dumps({
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
            path = root / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "qa.json",
                "legal_review_completed": True,
                "legal_review_record": "legal.json",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "smoke.json",
            }), encoding="utf-8")

            result = release_evidence.validate(path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])

    def test_status_marks_complete_evidence_gates_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web.png"
            dashboard.write_bytes(b"dashboard")
            web.write_bytes(b"web")
            qa = root / "qa.json"
            legal = _write_valid_legal_review(root, "legal.json")
            smoke = root / "smoke.json"
            qa.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "clean mac",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web.png"],
            }), encoding="utf-8")
            smoke.write_text(json.dumps({
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
            path = root / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "qa.json",
                "legal_review_completed": True,
                "legal_review_record": "legal.json",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "smoke.json",
            }), encoding="utf-8")

            result = release_evidence.status(path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"], {"complete": 3, "incomplete": 0})
        self.assertEqual({item["status"] for item in result["gates"]}, {"complete"})

    def test_status_rejects_fixture_smoke_as_invalid_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            smoke = root / "smoke.json"
            smoke.write_text(json.dumps(provider_smoke_check.run(mode="fixtures")), encoding="utf-8")
            path = root / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": False,
                "clean_machine_qa_record": "",
                "legal_review_completed": False,
                "legal_review_record": "",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "smoke.json",
            }), encoding="utf-8")

            result = release_evidence.status(path)

        by_gate = {item["id"]: item for item in result["gates"]}
        self.assertFalse(result["ok"])
        self.assertEqual(by_gate["live_provider_smoke"]["status"], "invalid_record")
        self.assertIn("provider_smoke_check.py --live --require-live --json", by_gate["live_provider_smoke"]["next_steps"][0])
        self.assertIn("provider_smoke_check.py status --record", by_gate["live_provider_smoke"]["next_steps"][1])

    def test_status_cli_runs_when_script_is_executed_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"
            release_evidence.write_template(path)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "release_evidence.py"),
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
        self.assertEqual(data["summary"], {"complete": 0, "incomplete": 3})

    def test_validate_rejects_true_flags_without_record_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "",
                "legal_review_completed": True,
                "legal_review_record": "missing.md",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "",
            }), encoding="utf-8")

            result = release_evidence.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("clean_machine_qa_record", result["missing"])
        self.assertIn("legal_review_record", result["missing"])
        self.assertIn("live_provider_smoke_record", result["missing"])

    def test_validate_rejects_blank_legal_review_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web.png"
            dashboard.write_bytes(b"dashboard")
            web.write_bytes(b"web")
            qa = root / "qa.json"
            legal = root / "legal.json"
            smoke = root / "smoke.json"
            qa.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "clean mac",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web.png"],
            }), encoding="utf-8")
            legal.write_text("{}", encoding="utf-8")
            smoke.write_text(json.dumps({
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
            path = root / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "qa.json",
                "legal_review_completed": True,
                "legal_review_record": "legal.json",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "smoke.json",
            }), encoding="utf-8")

            result = release_evidence.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("legal_review_record", result["missing"])

    def test_validate_rejects_fixture_provider_smoke_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web.png"
            dashboard.write_bytes(b"dashboard")
            web.write_bytes(b"web")
            qa = root / "qa.json"
            qa.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "clean mac",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web.png"],
            }), encoding="utf-8")
            legal = _write_valid_legal_review(root, "legal.json")
            smoke = root / "smoke.json"
            smoke.write_text(json.dumps(provider_smoke_check.run(mode="fixtures")), encoding="utf-8")
            path = root / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "qa.json",
                "legal_review_completed": True,
                "legal_review_record": "legal.json",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "smoke.json",
            }), encoding="utf-8")

            result = release_evidence.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("live_provider_smoke_record", result["missing"])

    def test_validate_rejects_live_provider_smoke_url_without_local_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = root / "dashboard.png"
            web = root / "web.png"
            dashboard.write_bytes(b"dashboard")
            web.write_bytes(b"web")
            qa = root / "qa.json"
            qa.write_text(json.dumps({
                "schema_version": "netfix_clean_machine_qa.v1",
                "result": "pass",
                "app_version": "0.2.0",
                "dmg_sha256": "abc123",
                "tester": "QA",
                "machine": "clean mac",
                "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
                "screenshots": ["dashboard.png", "web.png"],
            }), encoding="utf-8")
            legal = _write_valid_legal_review(root, "legal.json")
            path = root / "release-evidence.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": "qa.json",
                "legal_review_completed": True,
                "legal_review_record": "legal.json",
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "https://example.com/provider-smoke.json",
            }), encoding="utf-8")

            result = release_evidence.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("live_provider_smoke_record", result["missing"])


if __name__ == "__main__":
    unittest.main()
