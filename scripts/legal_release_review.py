#!/usr/bin/env python3
"""Create and validate legal/compliance release review records for Netfix."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVACY_POLICY = ROOT / "docs/PRIVACY_POLICY_DRAFT.md"
DEFAULT_EULA = ROOT / "docs/EULA_DRAFT.md"

REQUIRED_CHECKS = (
    "privacy_policy_reviewed",
    "eula_reviewed",
    "app_privacy_labels_reviewed",
    "paid_license_terms_reviewed",
    "residential_proxy_claims_reviewed",
    "llm_provider_terms_reviewed",
    "no_bypass_or_clean_ip_claims",
)

CHECK_NEXT_STEPS = {
    "privacy_policy_reviewed": "Review the privacy policy draft or published policy for local data, Keychain secrets, LLM uploads, probes, and proxy profile handling.",
    "eula_reviewed": "Review the EULA draft or published EULA for intended use, prohibited use, warranty limits, and proxy/LLM boundaries.",
    "app_privacy_labels_reviewed": "Map Netfix behavior to Apple App Privacy labels or Developer ID privacy disclosures before distribution.",
    "paid_license_terms_reviewed": "Review paid license, refund, update, support, and transfer terms.",
    "residential_proxy_claims_reviewed": "Review residential/custom proxy copy to ensure Netfix does not sell IPs or guarantee endpoint quality.",
    "llm_provider_terms_reviewed": "Review DeepSeek, Kimi/Moonshot, MiniMax, Qwen, custom endpoint, and optional OpenAI provider terms for marketed usage.",
    "no_bypass_or_clean_ip_claims": "Confirm public copy avoids bypass, anti-ban, clean residential IP, or evasion claims.",
}

FIELD_NEXT_STEPS = {
    "reviewer": "Set reviewer to the person or firm accountable for the release review.",
    "reviewed_at": "Set reviewed_at to the review date.",
    "privacy_policy_artifact": "Point privacy_policy_artifact to a reviewed local file or published URL.",
    "eula_artifact": "Point eula_artifact to a reviewed local file or published URL.",
    "result": "Set result to pass only after every legal/compliance check is complete.",
}


def _is_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _artifact_exists(record_path: Path, value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    artifact = value.strip()
    if _is_url(artifact):
        return True
    candidate = Path(artifact)
    if candidate.is_absolute():
        return candidate.exists()
    return (record_path.parent / candidate).exists()


def _artifact_value(path: Optional[Path]) -> str:
    if path is None or not path.exists() or not path.is_file():
        return ""
    return str(path.resolve())


def _template_command(path: Path) -> str:
    return (
        f"python3 scripts/legal_release_review.py template {path} "
        f"--privacy-policy {DEFAULT_PRIVACY_POLICY} --eula {DEFAULT_EULA}"
    )


def write_template(path: Path, *, privacy_policy: Optional[Path] = None, eula: Optional[Path] = None) -> Dict[str, Any]:
    data = {
        "schema_version": "netfix_legal_release_review.v1",
        "result": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "privacy_policy_artifact": _artifact_value(privacy_policy),
        "eula_artifact": _artifact_value(eula),
        "checks": {check: "pending" for check in REQUIRED_CHECKS},
        "notes": [
            "This is release evidence, not legal advice.",
            "privacy_policy_artifact and eula_artifact are prefilled only when --privacy-policy and --eula point to existing reviewed drafts or published artifacts.",
            "Set result to pass only after every required check is pass.",
            "privacy_policy_artifact and eula_artifact must point to reviewed local files or published URLs.",
            "Residential proxy claims must not imply Netfix sells IPs, guarantees clean IPs, or helps bypass third-party controls.",
            "LLM provider terms review must cover the marketed domestic adapters, including DeepSeek, Kimi/Moonshot, MiniMax, and Qwen.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"ok": True, "path": str(path)}


def validate(path: Path) -> Dict[str, Any]:
    data = _load_json(path)
    missing: List[str] = []
    if data.get("schema_version") != "netfix_legal_release_review.v1":
        missing.append("schema_version")
    if data.get("result") != "pass":
        missing.append("result")
    for field in ("reviewer", "reviewed_at"):
        if not str(data.get(field) or "").strip():
            missing.append(field)
    for field in ("privacy_policy_artifact", "eula_artifact"):
        if not _artifact_exists(path, data.get(field)):
            missing.append(field)
    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    for check in REQUIRED_CHECKS:
        if checks.get(check) != "pass":
            missing.append(f"checks.{check}")
    return {
        "ok": not missing,
        "path": str(path),
        "missing": missing,
    }


def _field_status(data: Dict[str, Any], path: Path) -> List[Dict[str, str]]:
    fields: List[Dict[str, str]] = []
    for field in ("reviewer", "reviewed_at"):
        complete = bool(str(data.get(field) or "").strip())
        fields.append({
            "id": field,
            "status": "complete" if complete else "missing",
            "next_step": "" if complete else FIELD_NEXT_STEPS[field],
        })
    for field in ("privacy_policy_artifact", "eula_artifact"):
        complete = _artifact_exists(path, data.get(field))
        fields.append({
            "id": field,
            "status": "complete" if complete else "missing",
            "next_step": "" if complete else FIELD_NEXT_STEPS[field],
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
    schema_ok = data.get("schema_version") == "netfix_legal_release_review.v1"
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
            "Use a qualified reviewer before marking this release evidence as pass.",
            f"python3 scripts/legal_release_review.py validate {path}",
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
    parser = argparse.ArgumentParser(description="Create or validate Netfix legal release review records.")
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Write a legal review JSON template.")
    template.add_argument("path", type=Path)
    template.add_argument("--privacy-policy", type=Path, default=DEFAULT_PRIVACY_POLICY, help="Reviewed privacy policy draft or published artifact to prefill.")
    template.add_argument("--eula", type=Path, default=DEFAULT_EULA, help="Reviewed EULA draft or published artifact to prefill.")
    check = sub.add_parser("validate", help="Validate a legal review JSON record.")
    check.add_argument("path", type=Path)
    stat = sub.add_parser("status", help="Show legal release review status and next steps.")
    stat.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    for command in (template, check, stat):
        command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.command == "template":
        result = write_template(args.path, privacy_policy=args.privacy_policy, eula=args.eula)
    elif args.command == "validate":
        result = validate(args.path)
    else:
        result = status(args.path)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.command == "status":
            summary = result["summary"]
            print(f"legal release review status: {summary['checks_passed']} checks passed, {summary['checks_incomplete']} checks incomplete")
            for step in result.get("next_steps", []):
                print(f"next: {step}")
            for item in result.get("checks", []):
                if item["status"] != "pass":
                    print(f"- [{item['status']}] {item['id']}: {item['next_step']}")
        elif result["ok"]:
            print(f"legal release review ok: {result['path']}")
        else:
            print(f"legal release review incomplete: {result['path']}")
            for item in result.get("missing", []):
                print(f"- {item}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
