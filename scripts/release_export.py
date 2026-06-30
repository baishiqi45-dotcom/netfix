#!/usr/bin/env python3
"""Create a clean downloadable Netfix release export directory.

This script deliberately exports only the distributable DMG plus release
metadata. It never copies the source workspace, local cases, or proxy packages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_audit import audit  # noqa: E402
from scripts.release_readiness import evaluate  # noqa: E402


DEFAULT_BUNDLE = ROOT / "gui/macos/.build/Netfix.app"
DEFAULT_DMG = ROOT / "gui/macos/.build/Netfix-0.2.0.dmg"
DEFAULT_OUT = ROOT / "gui/macos/.build/release-export"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _is_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _resolve_evidence_record(record: str, *, root: Path, evidence_file: Path) -> Optional[Path]:
    if not record or _is_url(record):
        return None
    candidate = Path(record)
    candidates = [candidate] if candidate.is_absolute() else [evidence_file.parent / candidate, root / candidate]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _copy_clean_machine_qa_dependencies(record_path: Path, target: Path, evidence_dir: Path) -> list[Path]:
    data = _load_json(record_path)
    screenshots = data.get("screenshots") if isinstance(data.get("screenshots"), list) else []
    copied: list[Path] = []
    rewritten: list[str] = []
    for index, item in enumerate(screenshots, start=1):
        if not isinstance(item, str) or not item.strip() or item.startswith("http://") or item.startswith("https://"):
            continue
        source = Path(item)
        if not source.is_absolute():
            source = record_path.parent / source
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix or ".png"
        screenshot_target = evidence_dir / f"clean_machine_qa_screenshot_{index}{suffix}"
        shutil.copy2(source, screenshot_target)
        copied.append(screenshot_target)
        rewritten.append(screenshot_target.name)
    if copied:
        data["screenshots"] = rewritten
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return copied


def _copy_legal_review_dependencies(record_path: Path, target: Path, evidence_dir: Path) -> list[Path]:
    data = _load_json(record_path)
    copied: list[Path] = []
    for field in ("privacy_policy_artifact", "eula_artifact"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip() or _is_url(value.strip()):
            continue
        source = Path(value.strip())
        if not source.is_absolute():
            source = record_path.parent / source
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix or ".md"
        artifact_target = evidence_dir / f"legal_review_{field}{suffix}"
        shutil.copy2(source, artifact_target)
        copied.append(artifact_target)
        data[field] = artifact_target.name
    if copied:
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return copied


def _copy_release_evidence(source: Path, *, root: Path, export_root: Path) -> tuple[Optional[Path], list[Path]]:
    if not source.exists():
        return None, []
    data = _load_json(source)
    if not data:
        return None, []
    copied_records: list[Path] = []
    evidence_dir = export_root / "evidence"
    for key, value in list(data.items()):
        if not key.endswith("_record") or not isinstance(value, str) or _is_url(value):
            continue
        record_path = _resolve_evidence_record(value, root=root, evidence_file=source)
        if record_path is None:
            continue
        evidence_dir.mkdir(exist_ok=True)
        suffix = record_path.suffix or ".txt"
        target = evidence_dir / f"{key}{suffix}"
        shutil.copy2(record_path, target)
        data[key] = target.relative_to(export_root).as_posix()
        copied_records.append(target)
        if key == "clean_machine_qa_record":
            copied_records.extend(_copy_clean_machine_qa_dependencies(record_path, target, evidence_dir))
        if key == "legal_review_record":
            copied_records.extend(_copy_legal_review_dependencies(record_path, target, evidence_dir))
    copied_evidence = export_root / "release-evidence.json"
    copied_evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return copied_evidence, copied_records


def _iter_export_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            yield path


def _relative_export_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_first_readme(
    path: Path,
    *,
    version: str,
    dmg_name: str,
    readiness: Dict[str, Any],
    source_workspace_findings_count: int,
) -> None:
    release_ready = bool(readiness.get("release_ready"))
    distribution_status = "paid external candidate" if release_ready else "internal QA candidate"
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    blockers = summary.get("blockers", 0)
    warnings = summary.get("warnings", 0)
    if release_ready:
        status_copy = (
            "This package is marked as a paid external candidate by release-readiness.json. "
            "Keep the included evidence files with the package for auditability."
        )
    else:
        status_copy = (
            "This package is an internal QA candidate, not a paid external release. "
            "release-readiness.json still reports unresolved blockers; do not publish it as a paid download yet."
        )

    text = f"""# Netfix {version} macOS Download

Status: {distribution_status}

{status_copy}

## Files

- `{dmg_name}`: macOS app disk image.
- `release-manifest.json`: build/runtime/distribution metadata from the app bundle.
- `release-readiness.json`: paid-release readiness result and blocker next steps.
- `release-evidence.json`: manual release evidence flags and record references, when present.
- `evidence/`: copied local evidence records and reviewed artifacts, when present; pending records do not mean a gate passed.
- `export-manifest.json`: export scope, artifact hashes, and distribution status.
- `SHA256SUMS.txt`: SHA-256 checksums for every exported file.

## Install And First Run

1. Open `{dmg_name}`.
2. Double-click `Netfix.app`, or drag it to Applications and open it from Launchpad.
3. Netfix starts its local engine by itself. No terminal command, Python command, or `127.0.0.1` URL is required for normal use.
4. Complete the local privacy/onboarding flow, then click "一键诊断" in the macOS app.
5. If a run fails, use the recovery panel to retry, copy the failure detail, and open logs/reports.

## QA Checksum

For internal QA or support handoff, compare `shasum -a 256 {dmg_name}` with `SHA256SUMS.txt`. This is not part of the ordinary first-run flow.

## AI Provider Setup

Netfix prioritizes domestic model providers for cloud explanations: DeepSeek for low-cost text explanation, then Kimi/Moonshot, MiniMax, and Qwen as configured fallbacks. Image-question workflows use only providers configured as multimodal candidates; DeepSeek remains text-only in this product.

API keys should be entered through the app/Web settings so they are stored in Keychain or provider-scoped environment variables. Do not paste API keys into reports, screenshots, or support messages.

Before marketing AI support, QA should verify DeepSeek text setup, provider-scoped Keychain account selection, missing-key fallback, and MiniMax/Kimi/Qwen image-question routing copy. Live provider verification requires sandbox keys and `provider-smoke-live.json` evidence.

## Residential Or Custom Proxy Setup

Netfix does not sell proxy IPs and does not guarantee clean, unblockable, or risk-free residential IP quality. It helps users deploy, validate, monitor, export, and recover their own legally obtained proxy credentials.

Supported first-run path:

1. Paste legally obtained proxy credentials, or batch-preflight a supplier list, in the proxy setup UI.
2. Review the parsed deployment decision and choose one candidate before saving.
3. Validate connectivity and optional exit identity hints.
4. Save the profile to Keychain.
5. Use monitoring, client config export, app-env preview, or confirmed system apply according to the decision shown by Netfix.
6. On a clean-machine QA pass, replace credentials for that Profile, verify the Profile id is preserved, export the client package again, then delete the Profile and confirm any persisted monitor intent is cleared.

Authenticated HTTP/HTTPS and SOCKS profiles can use a local 127.0.0.1 bridge for macOS Web/Secure Web proxy traffic and require keeping Netfix running until rollback/recovery.

## Release Readiness

- Current status: {distribution_status}
- Blockers reported: {blockers}
- Warnings reported: {warnings}
- Source workspace included: no
- Source workspace findings excluded from this export: {source_workspace_findings_count}

Use `release-readiness.json` as the authority for whether this package can be sold externally. The source workspace may still contain local proxy/config artifacts; this export intentionally excludes them.
"""
    path.write_text(text, encoding="utf-8")


def create_export(
    *,
    root: Path = ROOT,
    bundle: Path = DEFAULT_BUNDLE,
    dmg: Path = DEFAULT_DMG,
    out_dir: Path = DEFAULT_OUT,
    version: str = "0.2.0",
    evidence_file: Optional[Path] = None,
    skip_external: bool = False,
    make_zip: bool = False,
) -> Dict[str, Any]:
    root = root.resolve()
    bundle = bundle.resolve()
    dmg = dmg.resolve()
    out_dir = out_dir.resolve()

    manifest_path = bundle / "Contents/Resources/release-manifest.json"
    if not bundle.exists():
        raise FileNotFoundError(f"missing app bundle: {bundle}")
    if not dmg.exists():
        raise FileNotFoundError(f"missing DMG: {dmg}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing release manifest: {manifest_path}")

    export_name = f"Netfix-{version}-macos"
    export_root = out_dir / export_name
    if export_root.exists():
        shutil.rmtree(export_root)
    export_root.mkdir(parents=True)

    exported_dmg = export_root / dmg.name
    exported_bundle_manifest = export_root / "release-manifest.json"
    exported_readiness = export_root / "release-readiness.json"
    exported_manifest = export_root / "export-manifest.json"
    first_readme = export_root / "README-FIRST.md"
    checksums_path = export_root / "SHA256SUMS.txt"

    shutil.copy2(dmg, exported_dmg)
    shutil.copy2(manifest_path, exported_bundle_manifest)

    source_manifest = _load_json(manifest_path)
    source_evidence = evidence_file.resolve() if evidence_file is not None else root / "gui/macos/.build/release-evidence.json"
    copied_evidence, copied_evidence_records = _copy_release_evidence(source_evidence, root=root, export_root=export_root)
    receipt_path = source_manifest.get("distribution", {}).get("notarization_receipt") if isinstance(source_manifest.get("distribution"), dict) else None
    copied_receipt: Optional[Path] = None
    if receipt_path:
        candidate = Path(str(receipt_path))
        if candidate.exists():
            copied_receipt = export_root / candidate.name
            shutil.copy2(candidate, copied_receipt)

    readiness = evaluate(
        root=export_root,
        bundle=bundle,
        dmg=exported_dmg,
        evidence_file=copied_evidence or source_evidence,
        require_runtime=True,
        skip_external=skip_external,
    )
    exported_readiness.write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    source_workspace_findings = audit(root, "workspace")
    _write_first_readme(
        first_readme,
        version=version,
        dmg_name=exported_dmg.name,
        readiness=readiness,
        source_workspace_findings_count=len(source_workspace_findings),
    )
    artifacts: Dict[str, Dict[str, Any]] = {}
    for path in (
        [exported_dmg, exported_bundle_manifest, exported_readiness, first_readme]
        + ([copied_evidence] if copied_evidence else [])
        + copied_evidence_records
        + ([copied_receipt] if copied_receipt else [])
    ):
        if path is None:
            continue
        artifacts[_relative_export_path(export_root, path)] = {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }

    distribution = source_manifest.get("distribution") if isinstance(source_manifest.get("distribution"), dict) else {}
    export_data = {
        "schema_version": "netfix_release_export.v1",
        "name": "Netfix",
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_workspace_included": False,
        "source_workspace_findings_excluded_count": len(source_workspace_findings),
        "artifact_scope": "downloadable-dmg-plus-metadata",
        "distribution_status": "paid_external_candidate" if readiness.get("release_ready") else "internal_qa_candidate",
        "paid_release_ready": bool(readiness.get("release_ready")),
        "developer_id_signed": bool(distribution.get("developer_id_signed")),
        "notarized": bool(distribution.get("notarized")),
        "artifacts": artifacts,
        "notes": [
            "This export intentionally excludes the source workspace and local proxy/config artifacts.",
            "README-FIRST.md explains first-run steps, release status, AI provider setup, and residential/custom proxy boundaries.",
            "Do not market as paid external release until release-readiness.json reports release_ready=true, including manual clean-machine QA, legal review, and live provider smoke evidence.",
        ],
    }
    exported_manifest.write_text(json.dumps(export_data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    checksum_lines = []
    for path in _iter_export_files(export_root):
        checksum_lines.append(f"{_sha256(path)}  {_relative_export_path(export_root, path)}")
    checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    zip_path: Optional[Path] = None
    if make_zip:
        zip_path = out_dir / f"{export_name}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(export_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(out_dir))

    result = {
        "ok": True,
        "export_root": str(export_root),
        "zip": str(zip_path) if zip_path else None,
        "paid_release_ready": bool(readiness.get("release_ready")),
        "source_workspace_included": False,
        "source_workspace_findings_excluded_count": len(source_workspace_findings),
        "files": [_relative_export_path(export_root, path) for path in _iter_export_files(export_root)],
    }
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create a clean Netfix release export directory.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--dmg", type=Path, default=DEFAULT_DMG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--evidence-file", type=Path, default=None, help="Optional release-evidence.json to copy into the export and use for readiness.")
    parser.add_argument("--skip-external", action="store_true", help="Skip codesign/hdiutil checks inside readiness JSON.")
    parser.add_argument("--zip", action="store_true", help="Also create a zip containing the export directory.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = create_export(
            root=args.root,
            bundle=args.bundle,
            dmg=args.dmg,
            out_dir=args.out_dir,
            version=args.version,
            evidence_file=args.evidence_file,
            skip_external=args.skip_external,
            make_zip=args.zip,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"release export failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Created release export: {result['export_root']}")
        print(f"Paid release ready: {result['paid_release_ready']}")
        if result.get("zip"):
            print(f"Zip: {result['zip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
