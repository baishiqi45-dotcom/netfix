import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import release_preflight
from scripts.release_export import _write_verify_download_script
from scripts.source_export import create_source_export


def _write_bundle(root: Path, *, signed: bool = False, notarized: bool = False) -> Path:
    bundle = root / "gui" / "macos" / ".build" / "Netfix.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "Resources" / "netfix").mkdir(parents=True)
    (bundle / "Contents" / "Resources" / "rules").mkdir(parents=True)
    (bundle / "Contents" / "Resources" / "gui" / "web").mkdir(parents=True)
    (bundle / "Contents" / "MacOS" / "Netfix").write_text("#!/bin/sh\n", encoding="utf-8")
    (bundle / "Contents" / "Resources" / "netfix.py").write_text("print('netfix')\n", encoding="utf-8")
    (bundle / "Contents" / "Resources" / "PrivacyInfo.xcprivacy").write_text("<plist/>", encoding="utf-8")
    (bundle / "Contents" / "Resources" / "gui" / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
    manifest = {
        "version": "0.2.0",
        "release_candidate": True,
        "backend_runtime": {
            "bundled_backend": True,
            "bundled_python": False,
            "bundled_runtime_required": True,
        },
        "distribution": {
            "developer_id_signed": signed,
            "notarized": notarized,
            "dmg_created": True,
        },
    }
    (bundle / "Contents" / "Resources" / "release-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return bundle


def _write_open_source_files(root: Path) -> None:
    for rel in ["LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md"]:
        (root / rel).write_text("ok\n", encoding="utf-8")
    (root / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
    (root / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("ok\n", encoding="utf-8")
    (root / ".github" / "ISSUE_TEMPLATE" / "bug_report.md").write_text("ok\n", encoding="utf-8")


def _write_export(root: Path, dmg: Path) -> Path:
    export_root = root / "gui" / "macos" / ".build" / "release-export" / "Netfix-0.2.0-macos"
    export_root.mkdir(parents=True)
    (export_root / dmg.name).write_text("fake dmg", encoding="utf-8")
    (export_root / "README-FIRST.md").write_text("read me first", encoding="utf-8")
    (export_root / "release-manifest.json").write_text(json.dumps({"version": "0.2.0"}), encoding="utf-8")
    (export_root / "release-readiness.json").write_text(json.dumps({"release_ready": False}), encoding="utf-8")
    _write_verify_download_script(export_root / "verify-download.py")
    (export_root / "SHA256SUMS.txt").write_text("checksum  Netfix-0.2.0.dmg\n", encoding="utf-8")
    (export_root / "export-manifest.json").write_text(
        json.dumps({
            "schema_version": "netfix_release_export.v1",
            "artifact_scope": "downloadable-dmg-plus-metadata",
            "source_workspace_included": False,
            "distribution_status": "internal_qa_candidate",
            "source_workspace_findings_excluded_count": 2,
            "artifacts": {},
        }),
        encoding="utf-8",
    )
    return export_root


def _fake_run(command, *, cwd, timeout=60, env=None):
    joined = " ".join(command)
    if "install_mcp.sh" in joined:
        return {"ok": True, "returncode": 0, "stdout": "Netfix MCP setup finished.", "stderr": ""}
    if "verify_dmg_backend.sh" in joined:
        return {"ok": True, "returncode": 0, "stdout": "DMG backend verification passed", "stderr": ""}
    return {"ok": False, "returncode": 2, "stdout": "", "stderr": f"unexpected command: {joined}"}


def test_preflight_separates_source_blockers_from_clean_download_export():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_open_source_files(root)
        sensitive = root / "private-proxy-package-2026-06-14" / "private.proxy-url"
        sensitive.parent.mkdir()
        sensitive.write_text("http://user:password@example.com:8000", encoding="utf-8")
        bundle = _write_bundle(root)
        dmg = root / "gui" / "macos" / ".build" / "Netfix-0.2.0.dmg"
        dmg.write_text("fake dmg", encoding="utf-8")
        export_root = _write_export(root, dmg)
        source_export = create_source_export(root=root, out_dir=root / "open-source-export")

        with patch("scripts.release_preflight._run", side_effect=_fake_run):
            result = release_preflight.preflight(
                root=root,
                bundle=bundle,
                dmg=dmg,
                export_root=export_root,
                source_export_root=Path(source_export["export_root"]),
                skip_external=True,
                with_dmg_smoke=False,
            )

    assert result["ok"] is False
    assert result["source_publication_ready"] is False
    assert result["source_export_ready"] is True
    assert result["download_qa_ready"] is False
    assert result["paid_release_ready"] is False
    by_id = {item["id"]: item for item in result["checks"]}
    assert by_id["workspace_audit"]["status"] == "blocker"
    assert by_id["source_export"]["status"] == "pass"
    assert by_id["source_export"]["evidence"]["audit_passed"] is True
    assert by_id["download_export"]["status"] == "pass"
    assert by_id["mcp_setup_smoke"]["status"] == "pass"
    assert by_id["dmg_backend_smoke"]["status"] == "skipped"


def test_preflight_marks_download_qa_ready_only_after_dmg_smoke():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_open_source_files(root)
        bundle = _write_bundle(root)
        dmg = root / "gui" / "macos" / ".build" / "Netfix-0.2.0.dmg"
        dmg.write_text("fake dmg", encoding="utf-8")
        export_root = _write_export(root, dmg)

        with patch("scripts.release_preflight._run", side_effect=_fake_run):
            result = release_preflight.preflight(
                root=root,
                bundle=bundle,
                dmg=dmg,
                export_root=export_root,
                skip_external=True,
                with_dmg_smoke=True,
            )

    assert result["source_publication_ready"] is True
    assert result["download_qa_ready"] is True
    assert result["paid_release_ready"] is False
    by_id = {item["id"]: item for item in result["checks"]}
    assert by_id["dmg_backend_smoke"]["status"] == "pass"
    assert by_id["paid_release_readiness"]["status"] == "blocker"


def test_write_record_updates_export_manifest_and_checksums():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_open_source_files(root)
        bundle = _write_bundle(root)
        dmg = root / "gui" / "macos" / ".build" / "Netfix-0.2.0.dmg"
        dmg.write_text("fake dmg", encoding="utf-8")
        export_root = _write_export(root, dmg)
        (export_root / "download-qa-preflight.json").write_text(
            json.dumps({"schema_version": "netfix_release_preflight.v1", "status": "not_run"}),
            encoding="utf-8",
        )
        (export_root / "SHA256SUMS.txt").write_text("old  old\n", encoding="utf-8")
        zip_path = export_root.parent / f"{export_root.name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(export_root / "download-qa-preflight.json", export_root.name + "/download-qa-preflight.json")

        with patch("scripts.release_preflight._run", side_effect=_fake_run):
            result = release_preflight.preflight(
                root=root,
                bundle=bundle,
                dmg=dmg,
                export_root=export_root,
                skip_external=True,
                with_dmg_smoke=True,
            )
        record_path = export_root / "download-qa-preflight.json"
        release_preflight.write_record(result, record_path, export_root=export_root)

        record = json.loads(record_path.read_text(encoding="utf-8"))
        manifest = json.loads((export_root / "export-manifest.json").read_text(encoding="utf-8"))
        checksums = (export_root / "SHA256SUMS.txt").read_text(encoding="utf-8")
        record_text = record_path.read_text(encoding="utf-8")
        assert str(root) not in record_text
        assert str(bundle) not in record_text
        assert str(dmg) not in record_text
        assert record["schema_version"] == "netfix_release_preflight.v1"
        assert record["status"] == "recorded"
        assert record["download_qa_ready"] is True
        assert record["paid_release_ready"] is False
        assert record["artifacts"]["dmg_sha256"]
        assert manifest["download_qa_preflight"]["record"] == "download-qa-preflight.json"
        assert manifest["download_qa_preflight"]["download_qa_ready"] is True
        assert "download-qa-preflight.json" in manifest["artifacts"]
        assert "download-qa-preflight.json" in checksums
        with zipfile.ZipFile(zip_path) as archive:
            zipped_text = archive.read(export_root.name + "/download-qa-preflight.json").decode("utf-8")
            zipped = json.loads(zipped_text)
        assert str(root) not in zipped_text
        assert zipped["status"] == "recorded"
        assert zipped["download_qa_ready"] is True
        strict_verify = __import__("subprocess").run(
            ["python3", "verify-download.py", "--require-recorded-preflight", "--json"],
            cwd=str(export_root),
            text=True,
            capture_output=True,
            check=False,
        )
        assert strict_verify.returncode == 0, strict_verify.stderr
        strict_data = json.loads(strict_verify.stdout)
        assert strict_data["ok"] is True
        assert strict_data["download_qa_ready"] is True

        with patch("scripts.release_preflight._run", side_effect=_fake_run):
            trusted = release_preflight.preflight(
                root=root,
                bundle=bundle,
                dmg=dmg,
                export_root=export_root,
                skip_external=True,
                with_dmg_smoke=False,
            )
        by_id = {item["id"]: item for item in trusted["checks"]}
        assert trusted["download_qa_ready"] is True
        assert by_id["dmg_backend_smoke"]["status"] == "pass"
        assert "already recorded" in by_id["dmg_backend_smoke"]["message"]
