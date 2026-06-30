#!/usr/bin/env python3
"""Create and validate clean-machine visual QA records for Netfix releases."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "gui/macos/.build/Netfix.app/Contents/Resources/release-manifest.json"
DEFAULT_DMG = ROOT / "gui/macos/.build/Netfix-0.2.0.dmg"

REQUIRED_CHECKS = (
    "dmg_mounts",
    "bundled_backend_smoke",
    "app_launches",
    "web_console_renders",
    "dashboard_renders",
    "logs_view_renders",
    "ask_ai_fallback_renders",
    "residential_proxy_ui_renders",
    "residential_proxy_profile_lifecycle",
    "domestic_llm_provider_setup",
    "release_readiness_reviewed",
    "no_visible_secret_in_screenshots",
)

CHECK_NEXT_STEPS = {
    "dmg_mounts": "Mount the exported DMG on a clean Mac or clean VM and verify Netfix.app appears at the volume root.",
    "bundled_backend_smoke": "Run NETFIX_REQUIRE_BUNDLED_RUNTIME=true scripts/verify_dmg_backend.sh against the exported DMG.",
    "app_launches": "Launch Netfix.app from the mounted DMG or /Applications and verify the app stays open without a backend crash.",
    "web_console_renders": "Open the local Web console from the app/backend and capture a screenshot.",
    "dashboard_renders": "Run or load a report and capture the Dashboard state.",
    "logs_view_renders": "Open Logs/Reports and verify empty, loading, and populated states render without dead clicks.",
    "ask_ai_fallback_renders": "Click Ask AI with no cloud key and verify the local fallback explanation is visible.",
    "residential_proxy_ui_renders": "Open the proxy setup UI and verify parse, deployment decision, monitor, export, and rollback surfaces render.",
    "residential_proxy_profile_lifecycle": "Using fake or test proxy credentials, verify paste/import preview, save-and-monitor, replace credentials, export package, delete Profile, and persisted-monitor cleanup paths without changing system proxy unless explicitly confirmed.",
    "domestic_llm_provider_setup": "Verify DeepSeek text setup, provider-scoped Keychain account selection, missing-key fallback, and image-question routing copy for MiniMax/Kimi/Qwen without exposing API keys in screenshots.",
    "release_readiness_reviewed": "Open release-readiness.json and confirm every remaining blocker is understood before publishing or handing off the download candidate.",
    "no_visible_secret_in_screenshots": "Review every screenshot and mask API keys, proxy passwords, account IDs, and visible secrets before attaching.",
}

FIELD_NEXT_STEPS = {
    "app_version": "Set app_version to the tested app version from release-manifest.json.",
    "dmg_sha256": "Set dmg_sha256 to shasum -a 256 gui/macos/.build/Netfix-0.2.0.dmg.",
    "tester": "Set tester to the human or team that performed this clean-machine QA.",
    "machine": "Set machine to the clean Mac/VM model and macOS version.",
    "screenshots": "Attach at least two local screenshot files beside this record: Dashboard and Web console.",
    "result": "Set result to pass only after every field and check is complete.",
}


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_version(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return ""
    data = _load_json(path)
    return str(data.get("version") or "")


def _dmg_sha(path: Optional[Path]) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    return sha256(path)


def _relative_exists(record_path: Path, value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.exists()
    return (record_path.parent / candidate).exists()


def _template_command(path: Path) -> str:
    return (
        f"python3 scripts/clean_machine_qa.py template {path} "
        f"--manifest {DEFAULT_MANIFEST} --dmg {DEFAULT_DMG}"
    )


def write_template(path: Path, *, manifest: Optional[Path] = None, dmg: Optional[Path] = None) -> Dict[str, Any]:
    manifest_path = manifest.resolve() if manifest is not None else None
    dmg_path = dmg.resolve() if dmg is not None else None
    data = {
        "schema_version": "netfix_clean_machine_qa.v1",
        "result": "pending",
        "app_version": _manifest_version(manifest_path),
        "dmg_sha256": _dmg_sha(dmg_path),
        "tester": "",
        "machine": "",
        "tested_at": "",
        "artifact": {
            "release_manifest": str(manifest_path) if manifest_path and manifest_path.exists() else "",
            "dmg": str(dmg_path) if dmg_path and dmg_path.exists() else "",
        },
        "checks": {check: "pending" for check in REQUIRED_CHECKS},
        "screenshots": [],
        "notes": [
            "Run this on a clean Mac or clean VM using the exported DMG.",
            "app_version and dmg_sha256 are prefilled only when --manifest and --dmg point to existing release artifacts.",
            "Set result to pass only after every required check is pass.",
            "Screenshots should include Dashboard and Web console states and must not show real secrets.",
            "Residential proxy lifecycle QA must use fake/test credentials unless the tester has explicit permission to use a real provider account.",
            "Domestic LLM QA should prove provider-scoped setup and fallback behavior; live provider calls require sandbox keys and separate provider-smoke evidence.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"ok": True, "path": str(path)}


def validate(path: Path) -> Dict[str, Any]:
    data = _load_json(path)
    missing: List[str] = []
    if data.get("schema_version") != "netfix_clean_machine_qa.v1":
        missing.append("schema_version")
    if data.get("result") != "pass":
        missing.append("result")
    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    for check in REQUIRED_CHECKS:
        if checks.get(check) != "pass":
            missing.append(f"checks.{check}")
    screenshots = data.get("screenshots") if isinstance(data.get("screenshots"), list) else []
    valid_screenshots = [item for item in screenshots if _relative_exists(path, item)]
    if len(valid_screenshots) < 2:
        missing.append("screenshots")
    for field in ("app_version", "dmg_sha256", "tester", "machine"):
        if not str(data.get(field) or "").strip():
            missing.append(field)
    return {
        "ok": not missing,
        "path": str(path),
        "missing": missing,
    }


def _field_status(data: Dict[str, Any], path: Path) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    for field in ("app_version", "dmg_sha256", "tester", "machine"):
        complete = bool(str(data.get(field) or "").strip())
        fields.append({
            "id": field,
            "status": "complete" if complete else "missing",
            "next_step": "" if complete else FIELD_NEXT_STEPS[field],
        })
    screenshots = data.get("screenshots") if isinstance(data.get("screenshots"), list) else []
    valid_screenshots = [item for item in screenshots if _relative_exists(path, item)]
    screenshots_complete = len(valid_screenshots) >= 2
    fields.append({
        "id": "screenshots",
        "status": "complete" if screenshots_complete else "missing",
        "valid_count": len(valid_screenshots),
        "next_step": "" if screenshots_complete else FIELD_NEXT_STEPS["screenshots"],
    })
    result_complete = data.get("result") == "pass"
    fields.append({
        "id": "result",
        "status": "complete" if result_complete else "missing",
        "next_step": "" if result_complete else FIELD_NEXT_STEPS["result"],
    })
    return fields


def status(path: Path) -> Dict[str, Any]:
    data = _load_json(path)
    schema_ok = data.get("schema_version") == "netfix_clean_machine_qa.v1"
    checks_data = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    checks: List[Dict[str, str]] = []
    for check in REQUIRED_CHECKS:
        value = str(checks_data.get(check) or "pending")
        checks.append({
            "id": check,
            "status": value,
            "next_step": "" if value == "pass" else CHECK_NEXT_STEPS[check],
        })
    fields = _field_status(data, path)
    checks_passed = sum(1 for item in checks if item["status"] == "pass")
    fields_complete = sum(1 for item in fields if item["status"] == "complete")
    ok = bool(schema_ok and validate(path).get("ok"))
    next_steps = [] if ok else []
    if not schema_ok:
        next_steps.append(_template_command(path))
    if not ok:
        next_steps.extend([
            "Run this on a clean Mac or clean VM using the exported DMG.",
            f"python3 scripts/clean_machine_qa.py validate {path}",
            f"python3 scripts/release_evidence.py status {path.parent / 'release-evidence.json'}",
        ])
    return {
        "ok": ok,
        "path": str(path),
        "schema_ok": schema_ok,
        "summary": {
            "checks_passed": checks_passed,
            "checks_incomplete": len(checks) - checks_passed,
            "fields_complete": fields_complete,
            "fields_incomplete": len(fields) - fields_complete,
        },
        "next_steps": next_steps,
        "fields": fields,
        "checks": checks,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create or validate Netfix clean-machine QA records.")
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Write a clean-machine QA JSON template.")
    template.add_argument("path", type=Path)
    template.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Release manifest used to prefill app_version.")
    template.add_argument("--dmg", type=Path, default=DEFAULT_DMG, help="DMG used to prefill dmg_sha256.")
    check = sub.add_parser("validate", help="Validate a clean-machine QA JSON record.")
    check.add_argument("path", type=Path)
    stat = sub.add_parser("status", help="Show clean-machine QA status and next steps.")
    stat.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    for command in (template, check, stat):
        command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.command == "template":
        result = write_template(args.path, manifest=args.manifest, dmg=args.dmg)
    elif args.command == "validate":
        result = validate(args.path)
    else:
        result = status(args.path)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.command == "status":
            summary = result["summary"]
            print(f"clean-machine qa status: {summary['checks_passed']} checks passed, {summary['checks_incomplete']} checks incomplete")
            for step in result.get("next_steps", []):
                print(f"next: {step}")
            for item in result.get("checks", []):
                if item["status"] != "pass":
                    print(f"- [{item['status']}] {item['id']}: {item['next_step']}")
        elif result["ok"]:
            print(f"clean-machine qa ok: {result['path']}")
        else:
            print(f"clean-machine qa incomplete: {result['path']}")
            for item in result.get("missing", []):
                print(f"- {item}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
