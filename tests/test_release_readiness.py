import tempfile
import unittest
import json
from pathlib import Path

from scripts import clean_machine_qa
from scripts import legal_release_review
from scripts import provider_smoke_check
from scripts import release_readiness


def _write_valid_clean_machine_qa(root: Path, name: str = "clean-machine-qa.json") -> Path:
    dashboard = root / f"{name}-dashboard.png"
    web = root / f"{name}-web.png"
    dashboard.write_bytes(b"dashboard")
    web.write_bytes(b"web")
    qa_record = root / name
    qa_record.write_text(json.dumps({
        "schema_version": "netfix_clean_machine_qa.v1",
        "result": "pass",
        "app_version": "0.2.0",
        "dmg_sha256": "abc123",
        "tester": "QA",
        "machine": "clean mac",
        "checks": {check: "pass" for check in clean_machine_qa.REQUIRED_CHECKS},
        "screenshots": [dashboard.name, web.name],
    }), encoding="utf-8")
    return qa_record


def _write_valid_legal_review(root: Path, name: str = "legal-review.json") -> Path:
    privacy = root / f"{name}-privacy.md"
    eula = root / f"{name}-eula.md"
    privacy.write_text("privacy policy reviewed", encoding="utf-8")
    eula.write_text("eula reviewed", encoding="utf-8")
    legal_record = root / name
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


def _write_valid_provider_smoke(root: Path, name: str = "provider-smoke.json") -> Path:
    smoke_record = root / name
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
    return smoke_record


def _write_bundle(root: Path, *, developer_id: bool, notarized: bool, bundled_backend: bool = True, manual_evidence: bool = False) -> Path:
    bundle = root / "Netfix.app"
    (bundle / "Contents/MacOS").mkdir(parents=True)
    (bundle / "Contents/Resources/netfix").mkdir(parents=True)
    (bundle / "Contents/Resources/rules").mkdir(parents=True)
    (bundle / "Contents/Resources/gui/web").mkdir(parents=True)
    (bundle / "Contents/MacOS/Netfix").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle / "Contents/Resources/netfix.py").write_text("print('netfix')\n", encoding="utf-8")
    (bundle / "Contents/Resources/gui/web/index.html").write_text("<html></html>", encoding="utf-8")
    (bundle / "Contents/Resources/PrivacyInfo.xcprivacy").write_text("<plist/>", encoding="utf-8")
    release_evidence = {
        "clean_machine_qa_passed": manual_evidence,
        "legal_review_completed": manual_evidence,
        "live_provider_smoke_passed": manual_evidence,
    }
    if manual_evidence:
        qa_record = _write_valid_clean_machine_qa(root, "manifest-clean-machine-qa.json")
        legal_record = _write_valid_legal_review(root, "manifest-legal-review.json")
        smoke_record = _write_valid_provider_smoke(root, "manifest-provider-smoke.json")
        release_evidence.update({
            "clean_machine_qa_record": str(qa_record),
            "legal_review_record": str(legal_record),
            "live_provider_smoke_record": str(smoke_record),
        })
    manifest = {
        "name": "Netfix",
        "version": "0.2.0",
        "release_candidate": True,
        "backend_runtime": {
            "bundled_backend": bundled_backend,
            "bundled_python": False,
            "bundled_runtime_required": True,
        },
        "distribution": {
            "developer_id_signed": developer_id,
            "notarized": notarized,
            "dmg_created": True,
        },
        "release_evidence": release_evidence,
    }
    (bundle / "Contents/Resources/release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _write_evidence(root: Path, *, with_records: bool) -> Path:
    evidence = {
        "schema_version": "netfix_release_evidence.v1",
        "clean_machine_qa_passed": True,
        "legal_review_completed": True,
        "live_provider_smoke_passed": True,
    }
    if with_records:
        qa_record = _write_valid_clean_machine_qa(root)
        legal_record = _write_valid_legal_review(root)
        smoke_record = _write_valid_provider_smoke(root)
        evidence.update({
            "clean_machine_qa_record": str(qa_record),
            "legal_review_record": str(legal_record),
            "live_provider_smoke_record": str(smoke_record),
        })
    evidence_file = root / "release-evidence.json"
    evidence_file.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_file


class TestReleaseReadiness(unittest.TestCase):
    def test_flags_workspace_and_distribution_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "private.proxy-url").write_text("http://user:secret@example.com:8000", encoding="utf-8")
            bundle = _write_bundle(root, developer_id=False, notarized=False)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True)

        self.assertFalse(result["release_ready"])
        blockers = {item["id"]: item for item in result["checks"] if item["status"] == "blocker"}
        blocker_ids = set(blockers)
        self.assertIn("workspace_audit", blocker_ids)
        self.assertIn("developer_id", blocker_ids)
        self.assertIn("notarization", blocker_ids)
        self.assertIn("clean_machine_qa", blocker_ids)
        self.assertIn("legal_review", blocker_ids)
        self.assertIn("live_provider_smoke", blocker_ids)
        self.assertIn("release_audit.py", " ".join(blockers["workspace_audit"]["next_steps"]))
        self.assertIn("NETFIX_SIGN_IDENTITY", " ".join(blockers["developer_id"]["next_steps"]))
        self.assertIn("NETFIX_NOTARY_PROFILE", " ".join(blockers["notarization"]["next_steps"]))
        self.assertIn("clean_machine_qa.py status", " ".join(blockers["clean_machine_qa"]["next_steps"]))
        self.assertIn("--manifest", " ".join(blockers["clean_machine_qa"]["next_steps"]))
        self.assertIn("--dmg", " ".join(blockers["clean_machine_qa"]["next_steps"]))
        self.assertIn("legal_release_review.py status", " ".join(blockers["legal_review"]["next_steps"]))
        self.assertIn("--privacy-policy", " ".join(blockers["legal_review"]["next_steps"]))
        self.assertIn("--eula", " ".join(blockers["legal_review"]["next_steps"]))
        self.assertIn("provider_smoke_check.py status", " ".join(blockers["live_provider_smoke"]["next_steps"]))

    def test_signed_notarized_fixture_still_requires_manual_release_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True)

        self.assertFalse(result["release_ready"])
        self.assertTrue(result["technical_artifact_ready"])
        self.assertEqual(result["summary"]["manual_gate_blockers"], 3)
        blockers = {item["id"]: item for item in result["checks"] if item["status"] == "blocker"}
        self.assertIn("release_evidence.py status", " ".join(blockers["clean_machine_qa"]["next_steps"]))

    def test_readiness_rejects_blank_clean_machine_qa_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            qa_record = root / "clean-machine-qa.json"
            legal_record = _write_valid_legal_review(root)
            smoke_record = _write_valid_provider_smoke(root)
            qa_record.write_text("{}", encoding="utf-8")
            evidence_file = root / "release-evidence.json"
            evidence_file.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": str(qa_record),
                "legal_review_completed": True,
                "legal_review_record": str(legal_record),
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": str(smoke_record),
            }), encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True, evidence_file=evidence_file)

        self.assertFalse(result["release_ready"])
        blocker_ids = {item["id"] for item in result["checks"] if item["status"] == "blocker"}
        self.assertIn("clean_machine_qa", blocker_ids)

    def test_readiness_rejects_blank_legal_review_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            qa_record = _write_valid_clean_machine_qa(root)
            legal_record = root / "legal-review.json"
            smoke_record = _write_valid_provider_smoke(root)
            legal_record.write_text("{}", encoding="utf-8")
            evidence_file = root / "release-evidence.json"
            evidence_file.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": str(qa_record),
                "legal_review_completed": True,
                "legal_review_record": str(legal_record),
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": str(smoke_record),
            }), encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True, evidence_file=evidence_file)

        self.assertFalse(result["release_ready"])
        blocker_ids = {item["id"] for item in result["checks"] if item["status"] == "blocker"}
        self.assertIn("legal_review", blocker_ids)

    def test_readiness_rejects_fixture_provider_smoke_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            qa_record = _write_valid_clean_machine_qa(root)
            legal_record = _write_valid_legal_review(root)
            smoke_record = root / "provider-smoke.json"
            smoke_record.write_text(json.dumps(provider_smoke_check.run(mode="fixtures")), encoding="utf-8")
            evidence_file = root / "release-evidence.json"
            evidence_file.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": str(qa_record),
                "legal_review_completed": True,
                "legal_review_record": str(legal_record),
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": str(smoke_record),
            }), encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True, evidence_file=evidence_file)

        self.assertFalse(result["release_ready"])
        blocker_ids = {item["id"] for item in result["checks"] if item["status"] == "blocker"}
        self.assertIn("live_provider_smoke", blocker_ids)

    def test_readiness_rejects_live_provider_smoke_url_without_local_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            qa_record = _write_valid_clean_machine_qa(root)
            legal_record = _write_valid_legal_review(root)
            evidence_file = root / "release-evidence.json"
            evidence_file.write_text(json.dumps({
                "schema_version": "netfix_release_evidence.v1",
                "clean_machine_qa_passed": True,
                "clean_machine_qa_record": str(qa_record),
                "legal_review_completed": True,
                "legal_review_record": str(legal_record),
                "live_provider_smoke_passed": True,
                "live_provider_smoke_record": "https://example.com/provider-smoke.json",
            }), encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True, evidence_file=evidence_file)

        self.assertFalse(result["release_ready"])
        blocker_ids = {item["id"] for item in result["checks"] if item["status"] == "blocker"}
        self.assertIn("live_provider_smoke", blocker_ids)

    def test_clean_signed_notarized_fixture_is_ready_with_manual_release_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True, manual_evidence=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True)

        self.assertTrue(result["release_ready"])
        self.assertTrue(result["technical_artifact_ready"])
        self.assertEqual(result["summary"]["blockers"], 0)

    def test_external_release_evidence_file_can_satisfy_manual_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            evidence_file = _write_evidence(root, with_records=True)

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True, evidence_file=evidence_file)

        self.assertTrue(result["release_ready"])
        self.assertEqual(result["summary"]["manual_gate_blockers"], 0)
        evidence_checks = {item["id"]: item for item in result["checks"]}
        self.assertEqual(evidence_checks["clean_machine_qa"]["status"], "pass")
        self.assertEqual(evidence_checks["legal_review"]["status"], "pass")
        self.assertEqual(evidence_checks["live_provider_smoke"]["status"], "pass")

    def test_manual_evidence_requires_record_paths_not_only_true_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _write_bundle(root, developer_id=True, notarized=True)
            dmg = root / "Netfix.dmg"
            dmg.write_text("fake dmg", encoding="utf-8")
            evidence_file = _write_evidence(root, with_records=False)

            result = release_readiness.evaluate(root=root, bundle=bundle, dmg=dmg, skip_external=True, evidence_file=evidence_file)

        self.assertFalse(result["release_ready"])
        self.assertTrue(result["technical_artifact_ready"])
        self.assertEqual(result["summary"]["manual_gate_blockers"], 3)


if __name__ == "__main__":
    unittest.main()
