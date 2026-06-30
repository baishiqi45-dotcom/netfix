import json
import tempfile
import unittest
from pathlib import Path

from scripts import clean_machine_qa
from scripts import legal_release_review
from scripts.release_export import create_export


def _write_valid_clean_machine_qa(root: Path) -> Path:
    dashboard = root / "dashboard.png"
    web = root / "web.png"
    dashboard.write_bytes(b"dashboard")
    web.write_bytes(b"web")
    qa_record = root / "clean-machine-qa.json"
    qa_record.write_text(json.dumps({
        "schema_version": "netfix_clean_machine_qa.v1",
        "result": "pass",
        "app_version": "0.2.0",
        "dmg_sha256": "abc123",
        "tester": "QA",
        "machine": "clean mac",
        "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
        "screenshots": ["dashboard.png", "web.png"],
    }), encoding="utf-8")
    return qa_record


def _write_valid_legal_review(root: Path) -> Path:
    privacy = root / "PRIVACY_POLICY_DRAFT.md"
    eula = root / "EULA_DRAFT.md"
    privacy.write_text("privacy policy reviewed", encoding="utf-8")
    eula.write_text("eula reviewed", encoding="utf-8")
    legal_record = root / "legal-review.json"
    legal_record.write_text(json.dumps({
        "schema_version": "netfix_legal_release_review.v1",
        "result": "pass",
        "reviewer": "Legal reviewer",
        "reviewed_at": "2026-06-25",
        "privacy_policy_artifact": privacy.name,
        "eula_artifact": eula.name,
        "checks": {check: "pass" for check in legal_release_review.REQUIRED_CHECKS},
    }), encoding="utf-8")
    return legal_record


def _write_bundle(root: Path, *, developer_id: bool = False, notarized: bool = False, manual_evidence: bool = False) -> Path:
    bundle = root / "Netfix.app"
    (bundle / "Contents/MacOS").mkdir(parents=True)
    (bundle / "Contents/Resources/netfix").mkdir(parents=True)
    (bundle / "Contents/Resources/rules").mkdir(parents=True)
    (bundle / "Contents/Resources/gui/web").mkdir(parents=True)
    (bundle / "Contents/MacOS/Netfix").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle / "Contents/Resources/netfix.py").write_text("print('netfix')\n", encoding="utf-8")
    (bundle / "Contents/Resources/gui/web/index.html").write_text("<html></html>", encoding="utf-8")
    (bundle / "Contents/Resources/PrivacyInfo.xcprivacy").write_text("<plist/>", encoding="utf-8")
    manifest = {
        "name": "Netfix",
        "version": "0.2.0",
        "release_candidate": True,
        "backend_runtime": {
            "bundled_backend": True,
            "bundled_python": False,
            "bundled_runtime_required": True,
        },
        "distribution": {
            "developer_id_signed": developer_id,
            "notarized": notarized,
            "dmg_created": True,
        },
        "release_evidence": {
            "clean_machine_qa_passed": manual_evidence,
            "legal_review_completed": manual_evidence,
            "live_provider_smoke_passed": manual_evidence,
        },
    }
    (bundle / "Contents/Resources/release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _write_evidence(root: Path) -> Path:
    qa_record = _write_valid_clean_machine_qa(root)
    legal_record = _write_valid_legal_review(root)
    smoke_record = root / "provider-smoke.json"
    smoke_record.write_text(json.dumps({
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
    evidence = {
        "schema_version": "netfix_release_evidence.v1",
        "clean_machine_qa_passed": True,
        "clean_machine_qa_record": str(qa_record),
        "legal_review_completed": True,
        "legal_review_record": str(legal_record),
        "live_provider_smoke_passed": True,
        "live_provider_smoke_record": str(smoke_record),
    }
    evidence_file = root / "release-evidence.json"
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_file


class TestReleaseExport(unittest.TestCase):
    def test_export_excludes_sensitive_workspace_and_writes_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sensitive = root / "iphone-v2rayn-package-2026-06-14" / "cc-http.proxy-url"
            sensitive.parent.mkdir()
            sensitive.write_text("http://real-user:real-secret@proxy.example.net:8000", encoding="utf-8")
            bundle = _write_bundle(root)
            dmg = root / "Netfix-0.2.0.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")

            result = create_export(root=root, bundle=bundle, dmg=dmg, out_dir=root / "export", skip_external=True)

            export_root = Path(result["export_root"])
            self.assertTrue(result["ok"])
            self.assertFalse(result["source_workspace_included"])
            self.assertGreater(result["source_workspace_findings_excluded_count"], 0)
            self.assertTrue((export_root / "Netfix-0.2.0.dmg").exists())
            self.assertTrue((export_root / "release-manifest.json").exists())
            self.assertTrue((export_root / "release-readiness.json").exists())
            self.assertTrue((export_root / "export-manifest.json").exists())
            self.assertTrue((export_root / "README-FIRST.md").exists())
            self.assertTrue((export_root / "SHA256SUMS.txt").exists())
            self.assertFalse((export_root / "iphone-v2rayn-package-2026-06-14").exists())

            export_manifest = json.loads((export_root / "export-manifest.json").read_text(encoding="utf-8"))
            readiness = json.loads((export_root / "release-readiness.json").read_text(encoding="utf-8"))
            first_readme = (export_root / "README-FIRST.md").read_text(encoding="utf-8")
            checksum_text = (export_root / "SHA256SUMS.txt").read_text(encoding="utf-8")
            self.assertEqual(export_manifest["artifact_scope"], "downloadable-dmg-plus-metadata")
            self.assertFalse(export_manifest["source_workspace_included"])
            self.assertEqual(readiness["paths"]["root"], str(export_root))
            self.assertIn("internal QA candidate", first_readme)
            self.assertIn("release-readiness.json", first_readme)
            self.assertIn("Double-click `Netfix.app`", first_readme)
            self.assertIn("No terminal command", first_readme)
            self.assertIn("not part of the ordinary first-run flow", first_readme)
            self.assertIn("legally obtained proxy credentials", first_readme)
            self.assertIn("batch-preflight a supplier list", first_readme)
            self.assertIn("replace credentials", first_readme)
            self.assertIn("DeepSeek text setup", first_readme)
            self.assertIn("Netfix-0.2.0.dmg", checksum_text)
            self.assertIn("README-FIRST.md", checksum_text)
            self.assertIn("export-manifest.json", checksum_text)

    def test_signed_notarized_fixture_exports_as_paid_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix-0.2.0.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            evidence_file = _write_evidence(root)

            result = create_export(root=root, bundle=bundle, dmg=dmg, out_dir=root / "export", skip_external=True, evidence_file=evidence_file)

            export_root = Path(result["export_root"])
            export_manifest = json.loads((export_root / "export-manifest.json").read_text(encoding="utf-8"))
            readiness = json.loads((export_root / "release-readiness.json").read_text(encoding="utf-8"))
            self.assertTrue(result["paid_release_ready"])
            self.assertEqual(export_manifest["distribution_status"], "paid_external_candidate")
            self.assertTrue((export_root / "release-evidence.json").exists())
            self.assertTrue((export_root / "evidence" / "clean_machine_qa_record.json").exists())
            self.assertTrue((export_root / "evidence" / "clean_machine_qa_screenshot_1.png").exists())
            self.assertTrue((export_root / "evidence" / "clean_machine_qa_screenshot_2.png").exists())
            self.assertTrue((export_root / "evidence" / "legal_review_record.json").exists())
            self.assertTrue((export_root / "evidence" / "legal_review_privacy_policy_artifact.md").exists())
            self.assertTrue((export_root / "evidence" / "legal_review_eula_artifact.md").exists())
            self.assertTrue((export_root / "evidence" / "live_provider_smoke_record.json").exists())
            self.assertIn(
                "paid external candidate",
                (export_root / "README-FIRST.md").read_text(encoding="utf-8"),
            )
            checksum_text = (export_root / "SHA256SUMS.txt").read_text(encoding="utf-8")
            self.assertIn("evidence/clean_machine_qa_record.json", checksum_text)
            self.assertIn("evidence/legal_review_record.json", checksum_text)
            self.assertIn("evidence/live_provider_smoke_record.json", checksum_text)
            self.assertIn("evidence/clean_machine_qa_record.json", export_manifest["artifacts"])
            self.assertIn("evidence/legal_review_record.json", export_manifest["artifacts"])
            self.assertIn("evidence/live_provider_smoke_record.json", export_manifest["artifacts"])
            self.assertIn("evidence/clean_machine_qa_record.json", result["files"])
            self.assertTrue(readiness["release_ready"])
            self.assertEqual(readiness["paths"]["evidence_file"], str(export_root / "release-evidence.json"))


if __name__ == "__main__":
    unittest.main()
