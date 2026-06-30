#!/usr/bin/env python3
"""Summarize whether the current Netfix artifact is ready for paid external release."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import clean_machine_qa, legal_release_review, provider_smoke_check  # noqa: E402
from scripts.release_audit import audit  # noqa: E402

MANUAL_RELEASE_GATES = (
    (
        "clean_machine_qa",
        "clean_machine_qa_passed",
        "clean_machine_qa_record",
        "Paid external release needs a real clean-machine install and visual QA record.",
    ),
    (
        "legal_review",
        "legal_review_completed",
        "legal_review_record",
        "Paid external release needs reviewed/published privacy policy and EULA evidence.",
    ),
    (
        "live_provider_smoke",
        "live_provider_smoke_passed",
        "live_provider_smoke_record",
        "Paid external release needs live sandbox-key smoke evidence for marketed LLM providers.",
    ),
)


@dataclass
class ReadinessCheck:
    id: str
    status: str
    severity: str
    message: str
    evidence: Dict[str, Any]
    next_steps: List[str] = field(default_factory=list)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _run(command: List[str]) -> Dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=60, check=False)
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stderr": f"command not found: {command[0]}", "stdout": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "stderr": "command timed out", "stdout": ""}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _check(
    checks: List[ReadinessCheck],
    check_id: str,
    status: str,
    severity: str,
    message: str,
    *,
    next_steps: Optional[List[str]] = None,
    **evidence: Any,
) -> None:
    checks.append(ReadinessCheck(check_id, status, severity, message, evidence, next_steps or []))


def _manual_gate_next_steps(gate_id: str, evidence_path: Optional[Path]) -> List[str]:
    evidence = evidence_path or ROOT / "gui/macos/.build/release-evidence.json"
    base = evidence.parent
    if gate_id == "clean_machine_qa":
        record = base / "clean-machine-qa.json"
        return [
            f"python3 scripts/clean_machine_qa.py template {record} --manifest gui/macos/.build/Netfix.app/Contents/Resources/release-manifest.json --dmg gui/macos/.build/Netfix-0.2.0.dmg",
            f"python3 scripts/clean_machine_qa.py status {record}",
            f"python3 scripts/release_evidence.py status {evidence}",
        ]
    if gate_id == "legal_review":
        record = base / "legal-release-review.json"
        return [
            f"python3 scripts/legal_release_review.py template {record} --privacy-policy docs/PRIVACY_POLICY_DRAFT.md --eula docs/EULA_DRAFT.md",
            f"python3 scripts/legal_release_review.py status {record}",
            f"python3 scripts/release_evidence.py status {evidence}",
        ]
    if gate_id == "live_provider_smoke":
        record = base / "provider-smoke-live.json"
        return [
            f"python3 scripts/provider_smoke_check.py status --record {record}",
            f"python3 scripts/provider_smoke_check.py --live --require-live --json > {record}",
            f"python3 scripts/release_evidence.py status {evidence}",
        ]
    return [f"python3 scripts/release_evidence.py status {evidence}"]


def _release_evidence(manifest: Optional[Dict[str, Any]], evidence_file: Optional[Path], root: Path) -> tuple[Dict[str, Any], Optional[Path]]:
    evidence_path = evidence_file if evidence_file is not None else root / "gui/macos/.build/release-evidence.json"
    if not isinstance(manifest, dict):
        data: Dict[str, Any] = {}
    else:
        data = {}
        release_evidence = manifest.get("release_evidence")
        if isinstance(release_evidence, dict):
            data.update(release_evidence)
        distribution = manifest.get("distribution")
        if isinstance(distribution, dict):
            data.update({key: value for key, value in distribution.items() if key.endswith("_passed") or key.endswith("_completed")})
    if evidence_path.exists():
        external = _load_json(evidence_path)
        if isinstance(external, dict):
            external_evidence = external.get("release_evidence") if isinstance(external.get("release_evidence"), dict) else external
            data.update(external_evidence)
    return data, evidence_path


def _record_exists(record: Any, *, root: Path, evidence_path: Optional[Path]) -> bool:
    if not isinstance(record, str) or not record.strip():
        return False
    value = record.strip()
    if value.startswith("https://") or value.startswith("http://"):
        return True
    candidate = Path(value)
    candidates = [candidate] if candidate.is_absolute() else []
    if not candidate.is_absolute():
        if evidence_path is not None:
            candidates.append(evidence_path.parent / candidate)
        candidates.append(root / candidate)
    return any(path.exists() for path in candidates)


def _resolve_record(record: Any, *, root: Path, evidence_path: Optional[Path]) -> Optional[Path]:
    if not isinstance(record, str) or not record.strip():
        return None
    value = record.strip()
    if value.startswith("https://") or value.startswith("http://"):
        return None
    candidate = Path(value)
    candidates = [candidate] if candidate.is_absolute() else []
    if not candidate.is_absolute():
        if evidence_path is not None:
            candidates.append(evidence_path.parent / candidate)
        candidates.append(root / candidate)
    for path in candidates:
        if path.exists():
            return path
    return None


def _manual_gate_record_ok(gate_id: str, record: Any, *, root: Path, evidence_path: Optional[Path]) -> bool:
    if not _record_exists(record, root=root, evidence_path=evidence_path):
        return False
    if gate_id not in {"clean_machine_qa", "legal_review", "live_provider_smoke"}:
        return True
    value = str(record).strip() if isinstance(record, str) else ""
    if gate_id == "clean_machine_qa" and (value.startswith("https://") or value.startswith("http://")):
        return True
    resolved = _resolve_record(record, root=root, evidence_path=evidence_path)
    if gate_id == "clean_machine_qa":
        return bool(resolved and clean_machine_qa.validate(resolved).get("ok"))
    if gate_id == "legal_review":
        if value.startswith("https://") or value.startswith("http://"):
            return False
        return bool(resolved and legal_release_review.validate(resolved).get("ok"))
    if value.startswith("https://") or value.startswith("http://"):
        return False
    return bool(resolved and provider_smoke_check.validate_live_record(resolved).get("ok"))


def evaluate(
    *,
    root: Path = ROOT,
    bundle: Path = ROOT / "gui/macos/.build/Netfix.app",
    dmg: Path = ROOT / "gui/macos/.build/Netfix-0.2.0.dmg",
    evidence_file: Optional[Path] = None,
    require_runtime: bool = True,
    skip_external: bool = False,
) -> Dict[str, Any]:
    """Return release readiness checks for the workspace and current artifact."""
    root = root.resolve()
    bundle = bundle.resolve()
    dmg = dmg.resolve()
    checks: List[ReadinessCheck] = []

    workspace_findings = audit(root, "workspace")
    if workspace_findings:
        _check(
            checks,
            "workspace_audit",
            "blocker",
            "blocker",
            "Workspace contains release blockers; do not ship source/repository inputs as-is.",
            next_steps=[
                f"python3 scripts/release_audit.py --scope workspace --root {root} --json",
                "Do not ship source/repository inputs until proxy credentials/config artifacts are removed, rotated, or replaced with fake examples after explicit approval.",
                "Use python3 scripts/release_export.py --skip-external --json for the current binary-only candidate path; it excludes source-workspace artifacts.",
            ],
            count=len(workspace_findings),
            findings=[asdict(item) for item in workspace_findings],
        )
    else:
        _check(checks, "workspace_audit", "pass", "info", "Workspace audit has no blockers.", count=0)

    if not bundle.exists():
        _check(
            checks,
            "bundle_exists",
            "blocker",
            "blocker",
            "Netfix.app bundle is missing.",
            next_steps=["PYINSTALLER_PYTHON=/tmp/netfix-pyinstaller-venv/bin/python ./scripts/release_gate.sh --with-backend-binary --skip-pytest"],
            path=str(bundle),
        )
        manifest: Optional[Dict[str, Any]] = None
    else:
        _check(checks, "bundle_exists", "pass", "info", "Netfix.app bundle exists.", path=str(bundle))
        bundle_findings = audit(bundle, "bundle")
        if bundle_findings:
            _check(
                checks,
                "bundle_audit",
                "blocker",
                "blocker",
                "Bundle audit failed; downloadable artifact is not clean.",
                next_steps=[
                    f"python3 scripts/release_audit.py --scope bundle --root {bundle} --json",
                    "Rebuild the release candidate from the allowlist before exporting the DMG.",
                ],
                count=len(bundle_findings),
                findings=[asdict(item) for item in bundle_findings],
            )
        else:
            _check(checks, "bundle_audit", "pass", "info", "Bundle audit passed.", path=str(bundle))
        manifest_path = bundle / "Contents/Resources/release-manifest.json"
        manifest = _load_json(manifest_path)
        if manifest is None:
            _check(
                checks,
                "manifest",
                "blocker",
                "blocker",
                "release-manifest.json is missing or invalid.",
                next_steps=["Rebuild with ./gui/macos/build_app.sh --release-candidate after fixing bundle inputs."],
                path=str(manifest_path),
            )
        else:
            _check(
                checks,
                "manifest",
                "pass",
                "info",
                "release-manifest.json is readable.",
                path=str(manifest_path),
                version=manifest.get("version"),
                release_candidate=manifest.get("release_candidate"),
            )

    if manifest:
        runtime = manifest.get("backend_runtime") if isinstance(manifest.get("backend_runtime"), dict) else {}
        has_runtime = bool(runtime.get("bundled_backend") or runtime.get("bundled_python"))
        if require_runtime and not has_runtime:
            _check(
                checks,
                "bundled_runtime",
                "blocker",
                "blocker",
                "Paid external build must include a backend runtime.",
                next_steps=["PYINSTALLER_PYTHON=/tmp/netfix-pyinstaller-venv/bin/python ./scripts/release_gate.sh --with-backend-binary --skip-pytest"],
                runtime=runtime,
            )
        elif has_runtime:
            _check(checks, "bundled_runtime", "pass", "info", "Bundled backend runtime is present.", runtime=runtime)
        else:
            _check(
                checks,
                "bundled_runtime",
                "warn",
                "warning",
                "Build falls back to system Python; acceptable only for source/local development.",
                next_steps=["Build the external candidate with --with-backend-binary so the app bundles netfix-backend."],
                runtime=runtime,
            )

        distribution = manifest.get("distribution") if isinstance(manifest.get("distribution"), dict) else {}
        if distribution.get("developer_id_signed"):
            _check(checks, "developer_id", "pass", "info", "Manifest records Developer ID signing.", distribution=distribution)
        else:
            _check(
                checks,
                "developer_id",
                "blocker",
                "blocker",
                "Paid external macOS distribution needs Developer ID signing.",
                next_steps=[
                    "Export NETFIX_SIGN_IDENTITY=\"Developer ID Application: Your Name (TEAMID)\".",
                    "Run NETFIX_SIGN_IDENTITY=... ./gui/macos/build_app.sh --release-candidate.",
                    "Re-run python3 scripts/release_readiness.py --evidence-file gui/macos/.build/release-evidence.json.",
                ],
                distribution=distribution,
            )

        if distribution.get("notarized"):
            _check(checks, "notarization", "pass", "info", "Manifest records notarization.", distribution=distribution)
        else:
            _check(
                checks,
                "notarization",
                "blocker",
                "blocker",
                "Paid external macOS distribution needs notarization and stapling.",
                next_steps=[
                    "Configure NETFIX_NOTARY_PROFILE or NETFIX_NOTARY_APPLE_ID/NETFIX_NOTARY_TEAM_ID/NETFIX_NOTARY_PASSWORD.",
                    "Run ./gui/macos/build_app.sh --release-candidate with Developer ID signing and notary credentials.",
                    "Confirm .build/Netfix-0.2.0.notarization.json exists and release-manifest.json records notarized=true.",
                ],
                distribution=distribution,
            )

    evidence, evidence_path = _release_evidence(manifest, evidence_file, root)
    for gate_id, evidence_key, record_key, message in MANUAL_RELEASE_GATES:
        record = evidence.get(record_key)
        if evidence.get(evidence_key) and _manual_gate_record_ok(gate_id, record, root=root, evidence_path=evidence_path):
            _check(
                checks,
                gate_id,
                "pass",
                "info",
                f"{gate_id} evidence is present.",
                evidence_key=evidence_key,
                record_key=record_key,
                record=record,
                evidence_file=str(evidence_path) if evidence_path else None,
            )
        else:
            _check(
                checks,
                gate_id,
                "blocker",
                "blocker",
                message,
                next_steps=_manual_gate_next_steps(gate_id, evidence_path),
                evidence_key=evidence_key,
                record_key=record_key,
                record=record,
                evidence_file=str(evidence_path) if evidence_path else None,
                evidence=evidence,
            )

    if not dmg.exists():
        _check(
            checks,
            "dmg_exists",
            "blocker",
            "blocker",
            "DMG candidate is missing.",
            next_steps=["PYINSTALLER_PYTHON=/tmp/netfix-pyinstaller-venv/bin/python ./scripts/release_gate.sh --with-backend-binary --skip-pytest"],
            path=str(dmg),
        )
    else:
        _check(checks, "dmg_exists", "pass", "info", "DMG candidate exists.", path=str(dmg), size_bytes=dmg.stat().st_size)

    if not skip_external:
        if bundle.exists():
            result = _run(["codesign", "--verify", "--deep", "--strict", str(bundle)])
            _check(
                checks,
                "codesign_verify",
                "pass" if result["ok"] else "blocker",
                "info" if result["ok"] else "blocker",
                "codesign verification passed." if result["ok"] else "codesign verification failed.",
                next_steps=[] if result["ok"] else ["Fix Developer ID signing, then rerun codesign --verify --deep --strict gui/macos/.build/Netfix.app."],
                command="codesign --verify --deep --strict",
                result=result,
            )
        if dmg.exists():
            result = _run(["hdiutil", "verify", str(dmg)])
            _check(
                checks,
                "dmg_verify",
                "pass" if result["ok"] else "blocker",
                "info" if result["ok"] else "blocker",
                "DMG checksum verification passed." if result["ok"] else "DMG checksum verification failed.",
                next_steps=[] if result["ok"] else ["Rebuild the DMG with ./gui/macos/build_app.sh --release-candidate and rerun hdiutil verify."],
                command="hdiutil verify",
                result=result,
            )

    manual_gate_ids = {gate_id for gate_id, _evidence_key, _record_key, _message in MANUAL_RELEASE_GATES}
    blockers = [item for item in checks if item.status == "blocker"]
    technical_blockers = [item for item in blockers if item.id not in manual_gate_ids]
    warnings = [item for item in checks if item.status == "warn"]
    return {
        "ok": not blockers,
        "release_ready": not blockers,
        "technical_artifact_ready": not technical_blockers,
        "summary": {
            "blockers": len(blockers),
            "technical_blockers": len(technical_blockers),
            "manual_gate_blockers": len(blockers) - len(technical_blockers),
            "warnings": len(warnings),
            "checks": len(checks),
        },
        "paths": {
            "root": str(root),
            "bundle": str(bundle),
            "dmg": str(dmg),
            "evidence_file": str(evidence_path) if evidence_path else None,
        },
        "checks": [asdict(item) for item in checks],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check Netfix paid-release readiness.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, default=ROOT / "gui/macos/.build/Netfix.app")
    parser.add_argument("--dmg", type=Path, default=ROOT / "gui/macos/.build/Netfix-0.2.0.dmg")
    parser.add_argument("--evidence-file", type=Path, default=None, help="Optional release-evidence.json containing manual release gate records.")
    parser.add_argument("--no-require-runtime", action="store_true", help="Allow source/local builds without bundled runtime.")
    parser.add_argument("--skip-external", action="store_true", help="Skip codesign/hdiutil subprocess checks.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = evaluate(
        root=args.root,
        bundle=args.bundle,
        dmg=args.dmg,
        evidence_file=args.evidence_file,
        require_runtime=not args.no_require_runtime,
        skip_external=args.skip_external,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "READY" if result["release_ready"] else "NOT READY"
        print(f"Netfix paid release readiness: {status}")
        print(f"Blockers: {result['summary']['blockers']}  Warnings: {result['summary']['warnings']}")
        for item in result["checks"]:
            if item["status"] in {"blocker", "warn"}:
                print(f"- [{item['status']}] {item['id']}: {item['message']}")
                for step in item.get("next_steps", [])[:3]:
                    print(f"  next: {step}")
    return 0 if result["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
