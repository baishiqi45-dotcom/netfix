import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import legal_release_review

ROOT = Path(__file__).resolve().parents[1]


class TestLegalReleaseReview(unittest.TestCase):
    def test_template_writes_pending_structured_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legal-review.json"

            result = legal_release_review.write_template(path)

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(result["path"], str(path))
        self.assertEqual(data["schema_version"], "netfix_legal_release_review.v1")
        self.assertEqual(data["result"], "pending")
        self.assertEqual(data["privacy_policy_artifact"], "")
        self.assertEqual(data["eula_artifact"], "")
        for check in legal_release_review.REQUIRED_CHECKS:
            self.assertEqual(data["checks"][check], "pending")

    def test_template_can_prefill_policy_and_eula_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "legal-review.json"
            privacy = root / "PRIVACY_POLICY_DRAFT.md"
            eula = root / "EULA_DRAFT.md"
            privacy.write_text("privacy draft", encoding="utf-8")
            eula.write_text("eula draft", encoding="utf-8")

            result = legal_release_review.write_template(path, privacy_policy=privacy, eula=eula)

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(data["privacy_policy_artifact"], str(privacy.resolve()))
        self.assertEqual(data["eula_artifact"], str(eula.resolve()))
        self.assertEqual(data["result"], "pending")
        self.assertEqual(set(data["checks"].values()), {"pending"})

    def test_template_cli_accepts_policy_and_eula_prefill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "legal-review.json"
            privacy = root / "PRIVACY_POLICY_DRAFT.md"
            eula = root / "EULA_DRAFT.md"
            privacy.write_text("privacy draft", encoding="utf-8")
            eula.write_text("eula draft", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "legal_release_review.py"),
                    "template",
                    str(path),
                    "--privacy-policy",
                    str(privacy),
                    "--eula",
                    str(eula),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data["privacy_policy_artifact"], str(privacy.resolve()))
        self.assertEqual(data["eula_artifact"], str(eula.resolve()))

    def test_validate_rejects_pending_or_incomplete_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legal-review.json"
            legal_release_review.write_template(path)

            result = legal_release_review.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("result", result["missing"])
        self.assertIn("reviewer", result["missing"])
        self.assertIn("privacy_policy_artifact", result["missing"])
        self.assertIn("eula_artifact", result["missing"])
        self.assertIn("checks.privacy_policy_reviewed", result["missing"])

    def test_status_explains_pending_record_next_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legal-review.json"
            legal_release_review.write_template(path)

            result = legal_release_review.status(path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["summary"]["checks_passed"], 0)
        self.assertEqual(result["summary"]["checks_incomplete"], len(legal_release_review.REQUIRED_CHECKS))
        self.assertIn("Use a qualified reviewer", result["next_steps"][0])
        by_check = {item["id"]: item for item in result["checks"]}
        self.assertEqual(by_check["privacy_policy_reviewed"]["status"], "pending")
        self.assertIn("privacy policy", by_check["privacy_policy_reviewed"]["next_step"])
        self.assertIn("privacy_policy_artifact", {item["id"] for item in result["fields"] if item["status"] != "complete"})

    def test_status_explains_missing_record_template_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legal-review.json"

            result = legal_release_review.status(path)

        self.assertFalse(result["schema_ok"])
        self.assertIn("legal_release_review.py template", result["next_steps"][0])

    def test_validate_accepts_complete_review_with_local_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            privacy = root / "PRIVACY_POLICY_DRAFT.md"
            eula = root / "EULA_DRAFT.md"
            privacy.write_text("privacy policy reviewed", encoding="utf-8")
            eula.write_text("eula reviewed", encoding="utf-8")
            path = root / "legal-review.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_legal_release_review.v1",
                "result": "pass",
                "reviewer": "Legal reviewer",
                "reviewed_at": "2026-06-25",
                "privacy_policy_artifact": "PRIVACY_POLICY_DRAFT.md",
                "eula_artifact": "EULA_DRAFT.md",
                "checks": {check: "pass" for check in legal_release_review.REQUIRED_CHECKS},
            }), encoding="utf-8")

            result = legal_release_review.validate(path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing"], [])

    def test_status_marks_complete_review_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            privacy = root / "PRIVACY_POLICY_DRAFT.md"
            eula = root / "EULA_DRAFT.md"
            privacy.write_text("privacy policy reviewed", encoding="utf-8")
            eula.write_text("eula reviewed", encoding="utf-8")
            path = root / "legal-review.json"
            path.write_text(json.dumps({
                "schema_version": "netfix_legal_release_review.v1",
                "result": "pass",
                "reviewer": "Legal reviewer",
                "reviewed_at": "2026-06-25",
                "privacy_policy_artifact": "PRIVACY_POLICY_DRAFT.md",
                "eula_artifact": "EULA_DRAFT.md",
                "checks": {check: "pass" for check in legal_release_review.REQUIRED_CHECKS},
            }), encoding="utf-8")

            result = legal_release_review.status(path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["fields_incomplete"], 0)
        self.assertEqual({item["status"] for item in result["checks"]}, {"pass"})

    def test_status_cli_runs_when_script_is_executed_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legal-review.json"
            legal_release_review.write_template(path)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "legal_release_review.py"),
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
        self.assertEqual(data["summary"]["checks_incomplete"], len(legal_release_review.REQUIRED_CHECKS))

    def test_validate_rejects_blank_or_placeholder_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legal-review.json"
            path.write_text("{}", encoding="utf-8")

            result = legal_release_review.validate(path)

        self.assertFalse(result["ok"])
        self.assertIn("schema_version", result["missing"])
        self.assertIn("result", result["missing"])


if __name__ == "__main__":
    unittest.main()
