#!/usr/bin/env python3
"""Aggregate source, download, MCP, and paid-release readiness checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_audit import audit  # noqa: E402
from scripts.path_sanitizer import build_replacements, sanitize_json  # noqa: E402
from scripts.release_readiness import evaluate  # noqa: E402


DEFAULT_BUNDLE = ROOT / "gui/macos/.build/Netfix.app"
DEFAULT_DMG = ROOT / "gui/macos/.build/Netfix-0.2.0.dmg"
DEFAULT_EXPORT_ROOT = ROOT / "gui/macos/.build/release-export/Netfix-0.2.0-macos"
DEFAULT_SOURCE_EXPORT_ROOT = ROOT / "open-source-export/Netfix-0.2.0-source"


@dataclass
class PreflightCheck:
    id: str
    status: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    next_steps: List[str] = field(default_factory=list)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_export_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            yield path


def _relative_to(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _run(command: List[str], *, cwd: Path, timeout: int = 60, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=merged_env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": f"command not found: {command[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": f"command timed out after {timeout}s"}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _unique_next_steps(items: List[Dict[str, Any]], *, limit: int = 8) -> List[str]:
    steps: List[str] = []
    for item in items:
        for step in item.get("next_steps", []) or []:
            if step not in steps:
                steps.append(str(step))
            if len(steps) >= limit:
                return steps
    return steps


def _check_open_source_files(root: Path) -> PreflightCheck:
    required = [
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
    ]
    missing = [item for item in required if not (root / item).exists()]
    if missing:
        return PreflightCheck(
            "open_source_files",
            "blocker",
            "Open-source support files are missing.",
            {"missing": missing},
            [f"Add missing file: {item}" for item in missing],
        )
    return PreflightCheck("open_source_files", "pass", "Open-source support files are present.", {"required": required})


def _check_workspace_audit(root: Path) -> tuple[PreflightCheck, List[Dict[str, Any]]]:
    findings = [asdict(item) for item in audit(root, "workspace")]
    if findings:
        return (
            PreflightCheck(
                "workspace_audit",
                "blocker",
                "Source workspace still contains publish blockers.",
                {"count": len(findings), "kinds": _kind_counts(findings), "findings": findings},
                _unique_next_steps(findings),
            ),
            findings,
        )
    return (
        PreflightCheck("workspace_audit", "pass", "Source workspace audit is clean.", {"count": 0}),
        findings,
    )


def _check_source_export(source_export_root: Path) -> PreflightCheck:
    manifest_path = source_export_root / "SOURCE-EXPORT-MANIFEST.json"
    sums_path = source_export_root / "SHA256SUMS.txt"
    if not source_export_root.exists():
        return PreflightCheck(
            "source_export",
            "blocker",
            "Clean source export is missing.",
            {"source_export_root": str(source_export_root)},
            ["Run: python3 scripts/source_export.py --zip --json"],
        )
    manifest = _load_json(manifest_path)
    missing = [str(path.relative_to(source_export_root)) for path in [manifest_path, sums_path] if not path.exists()]
    audit_findings = [asdict(item) for item in audit(source_export_root, "workspace")]
    private_included = bool(manifest.get("source_workspace_included_private_artifacts")) if isinstance(manifest, dict) else None
    audit_passed = bool(manifest.get("audit_passed")) if isinstance(manifest, dict) else None
    if missing or not isinstance(manifest, dict) or private_included or not audit_passed or audit_findings:
        return PreflightCheck(
            "source_export",
            "blocker",
            "Clean source export is incomplete or unsafe.",
            {
                "source_export_root": str(source_export_root),
                "missing": missing,
                "manifest_readable": isinstance(manifest, dict),
                "private_artifacts_included": private_included,
                "audit_passed": audit_passed,
                "audit_findings": audit_findings,
            },
            ["Run: python3 scripts/source_export.py --zip --json", "Rerun: python3 scripts/release_preflight.py --skip-external --json"],
        )
    return PreflightCheck(
        "source_export",
        "pass",
        "Clean source export is present and passes release audit.",
        {
            "source_export_root": str(source_export_root),
            "zip": str(source_export_root.parent / f"{source_export_root.name}.zip"),
            "file_count": manifest.get("file_count"),
            "excluded_count": manifest.get("excluded_count"),
            "audit_passed": True,
        },
    )


def _kind_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind") or item.get("status") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _update_export_integrity(export_root: Path, record_path: Path) -> None:
    manifest_path = export_root / "export-manifest.json"
    checksums_path = export_root / "SHA256SUMS.txt"
    manifest = _load_json(manifest_path)
    if isinstance(manifest, dict):
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict):
            artifacts = {}
            manifest["artifacts"] = artifacts
        rel = _relative_to(export_root, record_path)
        artifacts[rel] = {
            "bytes": record_path.stat().st_size,
            "sha256": _sha256(record_path),
        }
        manifest["download_qa_preflight"] = {
            "record": rel,
            "download_qa_ready": bool(_load_json(record_path) or {}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        record_data = _load_json(record_path)
        if isinstance(record_data, dict):
            manifest["download_qa_preflight"]["download_qa_ready"] = bool(record_data.get("download_qa_ready"))
            manifest["download_qa_preflight"]["source_publication_ready"] = bool(record_data.get("source_publication_ready"))
            manifest["download_qa_preflight"]["paid_release_ready"] = bool(record_data.get("paid_release_ready"))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if checksums_path.exists():
        lines = [f"{_sha256(path)}  {_relative_to(export_root, path)}" for path in _iter_export_files(export_root)]
        checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    zip_path = export_root.parent / f"{export_root.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(export_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(export_root.parent))


def _record_matches_dmg(record_path: Path, dmg: Path) -> bool:
    data = _load_json(record_path)
    if not isinstance(data, dict):
        return False
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    return (
        data.get("status") == "recorded"
        and data.get("download_qa_ready") is True
        and artifacts.get("dmg_sha256") == _sha256(dmg)
    )


def write_record(result: Dict[str, Any], path: Path, *, export_root: Optional[Path] = None) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "netfix_release_preflight.v1",
        "status": "recorded",
        "created_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    artifacts: Dict[str, Any] = {}
    for item in result.get("checks", []):
        if item.get("id") != "dmg_backend_smoke":
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        if not evidence.get("dmg"):
            continue
        dmg_path = Path(str(evidence.get("dmg")))
        if dmg_path.exists():
            artifacts["dmg"] = _relative_to(export_root, dmg_path) if export_root is not None else str(dmg_path)
            artifacts["dmg_sha256"] = _sha256(dmg_path)
    if artifacts:
        record["artifacts"] = artifacts
    replacements = []
    if export_root is not None:
        paths = result.get("paths") if isinstance(result.get("paths"), dict) else {}
        zip_path = export_root.resolve().parent / f"{export_root.resolve().name}.zip"
        replacements = build_replacements([
            (path, path.name),
            (export_root, "."),
            (zip_path, zip_path.name),
            (paths.get("source_export_root"), "<source-export>"),
            (paths.get("bundle"), "<build-artifact>/Netfix.app"),
            (paths.get("dmg"), "<build-artifact>/Netfix-0.2.0.dmg"),
            (paths.get("evidence_file"), "<build-artifact>/release-evidence.json"),
            (paths.get("root"), "<source-workspace>"),
        ])
        record = sanitize_json(record, replacements)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if export_root is not None:
        export_root = export_root.resolve()
        try:
            path.relative_to(export_root)
        except ValueError:
            pass
        else:
            _update_export_integrity(export_root, path)
    return path


def _check_export(export_root: Path, *, dmg: Path) -> PreflightCheck:
    if not export_root.exists():
        return PreflightCheck(
            "download_export",
            "blocker",
            "Clean download export directory is missing.",
            {"export_root": str(export_root)},
            ["Run: python3 scripts/release_export.py --skip-external --zip --json"],
        )
    manifest_path = export_root / "export-manifest.json"
    readme_path = export_root / "README-FIRST.md"
    sums_path = export_root / "SHA256SUMS.txt"
    export_dmg = export_root / dmg.name
    missing = [str(path.relative_to(export_root)) for path in [manifest_path, readme_path, sums_path, export_dmg] if not path.exists()]
    manifest = _load_json(manifest_path) if manifest_path.exists() else None
    source_included = bool(manifest.get("source_workspace_included")) if isinstance(manifest, dict) else None
    if missing or not isinstance(manifest, dict) or source_included:
        next_steps = ["Run: python3 scripts/release_export.py --skip-external --zip --json"]
        if source_included:
            next_steps.insert(0, "Do not publish this export; it claims to include the source workspace.")
        return PreflightCheck(
            "download_export",
            "blocker",
            "Clean download export is incomplete or unsafe.",
            {
                "export_root": str(export_root),
                "missing": missing,
                "manifest_readable": isinstance(manifest, dict),
                "source_workspace_included": source_included,
            },
            next_steps,
        )
    return PreflightCheck(
        "download_export",
        "pass",
        "Clean binary download export is present and excludes the source workspace.",
        {
            "export_root": str(export_root),
            "dmg": str(export_dmg),
            "zip": str(export_root.parent / f"{export_root.name}.zip"),
            "distribution_status": manifest.get("distribution_status"),
            "source_workspace_findings_excluded_count": manifest.get("source_workspace_findings_excluded_count"),
        },
    )


def _check_mcp(root: Path, *, timeout: int, skip: bool) -> PreflightCheck:
    if skip:
        return PreflightCheck(
            "mcp_setup_smoke",
            "skipped",
            "MCP setup smoke was skipped.",
            {},
            ["Run: python3 scripts/release_preflight.py --with-dmg-smoke"],
        )
    result = _run(["bash", "scripts/install_mcp.sh", "--all", "--dry-run"], cwd=root, timeout=timeout)
    if result["ok"]:
        return PreflightCheck(
            "mcp_setup_smoke",
            "pass",
            "MCP installer dry-run and server initialization passed.",
            {"command": "bash scripts/install_mcp.sh --all --dry-run", "result": result},
        )
    return PreflightCheck(
        "mcp_setup_smoke",
        "blocker",
        "MCP installer dry-run failed.",
        {"command": "bash scripts/install_mcp.sh --all --dry-run", "result": result},
        ["Fix scripts/install_mcp.sh or netfix/mcp_server.py, then rerun release preflight."],
    )


def _check_dmg_smoke(root: Path, *, dmg: Path, timeout: int, run_smoke: bool, record_path: Optional[Path] = None) -> PreflightCheck:
    if not run_smoke:
        if record_path is not None and dmg.exists() and _record_matches_dmg(record_path, dmg):
            return PreflightCheck(
                "dmg_backend_smoke",
                "pass",
                "Bundled DMG backend smoke was already recorded for the current DMG.",
                {"dmg": str(dmg), "record": str(record_path)},
                ["Use --with-dmg-smoke to rerun the smoke if the package changed."],
            )
        return PreflightCheck(
            "dmg_backend_smoke",
            "skipped",
            "Bundled DMG backend smoke was not run.",
            {"dmg": str(dmg)},
            ["Run: python3 scripts/release_preflight.py --with-dmg-smoke"],
        )
    if not dmg.exists():
        return PreflightCheck(
            "dmg_backend_smoke",
            "blocker",
            "DMG backend smoke cannot run because the DMG is missing.",
            {"dmg": str(dmg)},
            ["Run: python3 scripts/release_export.py --skip-external --zip --json"],
        )
    result = _run(
        ["bash", "scripts/verify_dmg_backend.sh", str(dmg)],
        cwd=root,
        timeout=timeout,
        env={"NETFIX_REQUIRE_BUNDLED_RUNTIME": "true"},
    )
    if result["ok"]:
        return PreflightCheck(
            "dmg_backend_smoke",
            "pass",
            "Bundled DMG backend smoke passed.",
            {"dmg": str(dmg), "result": result},
        )
    return PreflightCheck(
        "dmg_backend_smoke",
        "blocker",
        "Bundled DMG backend smoke failed.",
        {"dmg": str(dmg), "result": result},
        ["Fix the packaged app/backend and rerun: NETFIX_REQUIRE_BUNDLED_RUNTIME=true ./scripts/verify_dmg_backend.sh <dmg>"],
    )


def preflight(
    *,
    root: Path = ROOT,
    bundle: Path = DEFAULT_BUNDLE,
    dmg: Path = DEFAULT_DMG,
    export_root: Path = DEFAULT_EXPORT_ROOT,
    source_export_root: Path = DEFAULT_SOURCE_EXPORT_ROOT,
    evidence_file: Optional[Path] = None,
    skip_external: bool = False,
    with_dmg_smoke: bool = False,
    skip_mcp_smoke: bool = False,
    timeout: int = 120,
) -> Dict[str, Any]:
    root = root.resolve()
    bundle = bundle.resolve()
    dmg = dmg.resolve()
    export_root = export_root.resolve()
    source_export_root = source_export_root.resolve()

    checks: List[PreflightCheck] = []
    checks.append(_check_open_source_files(root))
    workspace_check, workspace_findings = _check_workspace_audit(root)
    checks.append(workspace_check)
    source_export_check = _check_source_export(source_export_root)
    checks.append(source_export_check)

    readiness = evaluate(
        root=root,
        bundle=bundle,
        dmg=dmg,
        evidence_file=evidence_file,
        require_runtime=True,
        skip_external=skip_external,
    )
    readiness_blockers = [item for item in readiness.get("checks", []) if item.get("status") == "blocker"]
    checks.append(
        PreflightCheck(
            "paid_release_readiness",
            "pass" if readiness.get("release_ready") else "blocker",
            "Paid external release readiness passed." if readiness.get("release_ready") else "Paid external release still has blockers.",
            {"summary": readiness.get("summary"), "paths": readiness.get("paths")},
            _unique_next_steps(readiness_blockers),
        )
    )

    export_check = _check_export(export_root, dmg=dmg)
    checks.append(export_check)
    mcp_check = _check_mcp(root, timeout=timeout, skip=skip_mcp_smoke)
    checks.append(mcp_check)
    smoke_dmg = Path(str(export_check.evidence.get("dmg") or dmg)).resolve()
    dmg_smoke_check = _check_dmg_smoke(
        root,
        dmg=smoke_dmg,
        timeout=timeout,
        run_smoke=with_dmg_smoke,
        record_path=export_root / "download-qa-preflight.json",
    )
    checks.append(dmg_smoke_check)

    check_dicts = [asdict(item) for item in checks]
    source_publication_ready = (
        workspace_check.status == "pass"
        and checks[0].status == "pass"
    )
    source_export_ready = source_export_check.status == "pass"
    download_qa_ready = (
        export_check.status == "pass"
        and mcp_check.status == "pass"
        and dmg_smoke_check.status == "pass"
    )
    result = {
        "ok": bool((source_publication_ready or source_export_ready) and download_qa_ready and readiness.get("release_ready")),
        "source_publication_ready": source_publication_ready,
        "source_export_ready": source_export_ready,
        "download_qa_ready": download_qa_ready,
        "paid_release_ready": bool(readiness.get("release_ready")),
        "summary": {
            "checks": len(check_dicts),
            "blockers": sum(1 for item in check_dicts if item["status"] == "blocker"),
            "skipped": sum(1 for item in check_dicts if item["status"] == "skipped"),
            "workspace_findings": len(workspace_findings),
            "readiness_blockers": len(readiness_blockers),
        },
        "paths": {
            "root": str(root),
            "bundle": str(bundle),
            "dmg": str(dmg),
            "export_root": str(export_root),
            "source_export_root": str(source_export_root),
            "evidence_file": str(evidence_file.resolve()) if evidence_file else None,
        },
        "checks": check_dicts,
        "release_readiness": {
            "release_ready": readiness.get("release_ready"),
            "technical_artifact_ready": readiness.get("technical_artifact_ready"),
            "summary": readiness.get("summary"),
        },
    }
    return result


def _print_text(result: Dict[str, Any]) -> None:
    status = "READY" if result.get("ok") else "NOT READY"
    print(f"Netfix release preflight: {status}")
    print(f"- Source publication: {'READY' if result.get('source_publication_ready') else 'BLOCKED'}")
    print(f"- Clean source export: {'READY' if result.get('source_export_ready') else 'BLOCKED'}")
    print(f"- Download QA package: {'READY' if result.get('download_qa_ready') else 'NOT PROVEN'}")
    print(f"- Paid external release: {'READY' if result.get('paid_release_ready') else 'BLOCKED'}")
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    print(f"- Checks: {summary.get('checks')}  Blockers: {summary.get('blockers')}  Skipped: {summary.get('skipped')}")

    printed = 0
    print("\nBlocking or missing evidence:")
    for item in result.get("checks", []):
        if item.get("status") not in {"blocker", "skipped"}:
            continue
        printed += 1
        print(f"- [{item.get('status')}] {item.get('id')}: {item.get('message')}")
        for step in (item.get("next_steps") or [])[:4]:
            print(f"  next: {step}")
    if not printed:
        print("- none")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Netfix source/download/release preflight checks.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--dmg", type=Path, default=DEFAULT_DMG)
    parser.add_argument("--export-root", type=Path, default=DEFAULT_EXPORT_ROOT)
    parser.add_argument("--source-export-root", type=Path, default=DEFAULT_SOURCE_EXPORT_ROOT)
    parser.add_argument("--evidence-file", type=Path, default=None)
    parser.add_argument("--skip-external", action="store_true", help="Skip codesign/hdiutil checks inside release_readiness.")
    parser.add_argument("--with-dmg-smoke", action="store_true", help="Mount the exported DMG and verify the bundled backend.")
    parser.add_argument("--skip-mcp-smoke", action="store_true", help="Do not dry-run scripts/install_mcp.sh.")
    parser.add_argument("--write-record", type=Path, default=None, help="Write a machine-readable preflight record, usually <export-root>/download-qa-preflight.json.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = preflight(
        root=args.root,
        bundle=args.bundle,
        dmg=args.dmg,
        export_root=args.export_root,
        source_export_root=args.source_export_root,
        evidence_file=args.evidence_file,
        skip_external=args.skip_external,
        with_dmg_smoke=args.with_dmg_smoke,
        skip_mcp_smoke=args.skip_mcp_smoke,
        timeout=args.timeout,
    )
    if args.write_record is not None:
        written = write_record(result, args.write_record, export_root=args.export_root)
        result.setdefault("paths", {})["preflight_record"] = str(written)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
