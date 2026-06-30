#!/usr/bin/env python3
"""Create and validate manual paid-release evidence records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import clean_machine_qa, legal_release_review, provider_smoke_check

DEFAULT_CLEAN_MACHINE_QA_RECORD = "clean-machine-qa.json"
DEFAULT_LEGAL_REVIEW_RECORD = "legal-release-review.json"
DEFAULT_LIVE_PROVIDER_SMOKE_RECORD = "provider-smoke-live.json"

REQUIRED_RECORDS = {
    "clean_machine_qa_passed": "clean_machine_qa_record",
    "legal_review_completed": "legal_review_record",
    "live_provider_smoke_passed": "live_provider_smoke_record",
}

GATES: Tuple[Dict[str, Any], ...] = (
    {
        "id": "clean_machine_qa",
        "label": "Clean-machine QA",
        "flag_key": "clean_machine_qa_passed",
        "record_key": "clean_machine_qa_record",
        "default_record": DEFAULT_CLEAN_MACHINE_QA_RECORD,
        "template_command": "python3 scripts/clean_machine_qa.py template {record} --manifest gui/macos/.build/Netfix.app/Contents/Resources/release-manifest.json --dmg gui/macos/.build/Netfix-0.2.0.dmg",
        "validate_command": "python3 scripts/clean_machine_qa.py validate {record}",
        "validator": clean_machine_qa.validate,
    },
    {
        "id": "legal_review",
        "label": "Legal release review",
        "flag_key": "legal_review_completed",
        "record_key": "legal_review_record",
        "default_record": DEFAULT_LEGAL_REVIEW_RECORD,
        "template_command": "python3 scripts/legal_release_review.py template {record} --privacy-policy docs/PRIVACY_POLICY_DRAFT.md --eula docs/EULA_DRAFT.md",
        "validate_command": "python3 scripts/legal_release_review.py validate {record}",
        "validator": legal_release_review.validate,
    },
    {
        "id": "live_provider_smoke",
        "label": "Live provider smoke",
        "flag_key": "live_provider_smoke_passed",
        "record_key": "live_provider_smoke_record",
        "default_record": DEFAULT_LIVE_PROVIDER_SMOKE_RECORD,
        "template_command": "python3 scripts/provider_smoke_check.py --live --require-live --json > {record}",
        "validate_command": "python3 scripts/provider_smoke_check.py status --record {record}",
        "validator": provider_smoke_check.validate_live_record,
    },
)


def _is_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _record_exists(record: Any, evidence_file: Path) -> bool:
    if not isinstance(record, str) or not record.strip():
        return False
    value = record.strip()
    if _is_url(value):
        return True
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.exists()
    return (evidence_file.parent / candidate).exists()


def _resolve_record(record: Any, evidence_file: Path) -> Optional[Path]:
    if not isinstance(record, str) or not record.strip() or _is_url(record.strip()):
        return None
    candidate = Path(record.strip())
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    resolved = evidence_file.parent / candidate
    return resolved if resolved.exists() else None


def _template_command(path: Path) -> str:
    return (
        f"python3 scripts/release_evidence.py template {path} "
        f"--clean-machine-qa-record {DEFAULT_CLEAN_MACHINE_QA_RECORD} "
        f"--legal-review-record {DEFAULT_LEGAL_REVIEW_RECORD} "
        f"--live-provider-smoke-record {DEFAULT_LIVE_PROVIDER_SMOKE_RECORD}"
    )


def write_template(
    path: Path,
    *,
    clean_machine_qa_record: str = "",
    legal_review_record: str = "",
    live_provider_smoke_record: str = "",
) -> Dict[str, Any]:
    data = {
        "schema_version": "netfix_release_evidence.v1",
        "clean_machine_qa_passed": False,
        "clean_machine_qa_record": clean_machine_qa_record,
        "legal_review_completed": False,
        "legal_review_record": legal_review_record,
        "live_provider_smoke_passed": False,
        "live_provider_smoke_record": live_provider_smoke_record,
        "notes": [
            "Set a gate to true only after the corresponding real-world check is complete.",
            "Record paths may be prefilled while gates remain false; that does not count as release approval.",
            "Record fields must point to local files beside this evidence file or to review/smoke URLs.",
            "legal_review_record must be a local JSON file validated by legal_release_review.py.",
            "live_provider_smoke_record must be JSON from provider_smoke_check.py --live --require-live --json covering all marketed providers.",
            "This file is consumed by scripts/release_readiness.py and scripts/release_export.py.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {"ok": True, "path": str(path)}


def validate(path: Path) -> Dict[str, Any]:
    data = _load_json(path)
    missing: List[str] = []
    if data.get("schema_version") != "netfix_release_evidence.v1":
        missing.append("schema_version")
    for flag_key, record_key in REQUIRED_RECORDS.items():
        if not data.get(flag_key):
            missing.append(flag_key)
        if not _record_exists(data.get(record_key), path):
            missing.append(record_key)
    qa_record = _resolve_record(data.get("clean_machine_qa_record"), path)
    if qa_record is not None and not clean_machine_qa.validate(qa_record).get("ok"):
        if "clean_machine_qa_record" not in missing:
            missing.append("clean_machine_qa_record")
    legal_record = _resolve_record(data.get("legal_review_record"), path)
    if data.get("legal_review_completed") and (
        legal_record is None or not legal_release_review.validate(legal_record).get("ok")
    ):
        if "legal_review_record" not in missing:
            missing.append("legal_review_record")
    smoke_record = _resolve_record(data.get("live_provider_smoke_record"), path)
    if data.get("live_provider_smoke_passed") and (
        smoke_record is None or not provider_smoke_check.validate_live_record(smoke_record).get("ok")
    ):
        if "live_provider_smoke_record" not in missing:
            missing.append("live_provider_smoke_record")
    return {
        "ok": not missing,
        "path": str(path),
        "missing": missing,
    }


def _record_display_path(path: Path, value: Any, default_record: str) -> str:
    if isinstance(value, str) and value.strip():
        record = value.strip()
        if _is_url(record):
            return record
        candidate = Path(record)
        return str(candidate if candidate.is_absolute() else path.parent / candidate)
    return str(path.parent / default_record)


def _validate_record(gate: Dict[str, Any], record_path: Optional[Path]) -> Dict[str, Any]:
    if record_path is None:
        return {"ok": False, "missing": ["record"]}
    validator: Callable[[Path], Dict[str, Any]] = gate["validator"]
    try:
        return validator(record_path)
    except Exception as exc:
        return {"ok": False, "missing": ["record"], "error": str(exc)}


def _gate_next_steps(gate: Dict[str, Any], path: Path, record: Any) -> List[str]:
    record_path = _record_display_path(path, record, str(gate["default_record"]))
    steps = [
        str(gate["template_command"]).format(record=record_path),
        str(gate["validate_command"]).format(record=record_path),
    ]
    if gate["id"] != "live_provider_smoke":
        steps.append(f"Set {gate['flag_key']} to true and {gate['record_key']} to {Path(record_path).name!r} in {path}")
    else:
        steps.append(f"Set {gate['flag_key']} to true and {gate['record_key']} to {Path(record_path).name!r} in {path}")
    steps.append(f"python3 scripts/release_evidence.py validate {path}")
    steps.append(f"python3 scripts/release_readiness.py --evidence-file {path}")
    return steps


def status(path: Path) -> Dict[str, Any]:
    data = _load_json(path)
    schema_ok = data.get("schema_version") == "netfix_release_evidence.v1"
    top_level_steps = [] if schema_ok else [_template_command(path)]
    gates: List[Dict[str, Any]] = []
    for gate in GATES:
        flag_key = str(gate["flag_key"])
        record_key = str(gate["record_key"])
        record_value = data.get(record_key)
        record_path = _resolve_record(record_value, path)
        flag_ok = bool(data.get(flag_key))
        record_present = _record_exists(record_value, path)
        record_result = _validate_record(gate, record_path) if record_present else {"ok": False, "missing": [record_key]}
        if flag_ok and record_present and record_result.get("ok"):
            gate_status = "complete"
        elif flag_ok and record_present:
            gate_status = "invalid_record"
        elif flag_ok:
            gate_status = "missing_record"
        else:
            gate_status = "missing_flag"
        gates.append({
            "id": gate["id"],
            "label": gate["label"],
            "status": gate_status,
            "flag_key": flag_key,
            "flag_value": flag_ok,
            "record_key": record_key,
            "record": record_value if isinstance(record_value, str) else "",
            "record_ok": bool(record_result.get("ok")),
            "record_missing": record_result.get("missing", []),
            "next_steps": [] if gate_status == "complete" else _gate_next_steps(gate, path, record_value),
        })
    complete = sum(1 for gate in gates if gate["status"] == "complete")
    incomplete = len(gates) - complete
    return {
        "ok": bool(schema_ok and incomplete == 0),
        "path": str(path),
        "schema_ok": schema_ok,
        "summary": {
            "complete": complete,
            "incomplete": incomplete,
        },
        "next_steps": top_level_steps,
        "gates": gates,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create or validate Netfix paid-release evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Write a release-evidence.json template.")
    template.add_argument("path", type=Path)
    template.add_argument("--clean-machine-qa-record", default="", help="Optional clean-machine QA record path to prefill while leaving clean_machine_qa_passed=false.")
    template.add_argument("--legal-review-record", default="", help="Optional legal review record path to prefill while leaving legal_review_completed=false.")
    template.add_argument("--live-provider-smoke-record", default="", help="Optional live provider smoke record path to prefill while leaving live_provider_smoke_passed=false.")
    check = sub.add_parser("validate", help="Validate a release-evidence.json file.")
    check.add_argument("path", type=Path)
    stat = sub.add_parser("status", help="Show manual release evidence status and next steps.")
    stat.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    for command in (template, check, stat):
        command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.command == "template":
        result = write_template(
            args.path,
            clean_machine_qa_record=args.clean_machine_qa_record,
            legal_review_record=args.legal_review_record,
            live_provider_smoke_record=args.live_provider_smoke_record,
        )
    elif args.command == "validate":
        result = validate(args.path)
    else:
        result = status(args.path)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.command == "status":
            complete = result["summary"]["complete"]
            incomplete = result["summary"]["incomplete"]
            print(f"release evidence status: {complete} complete, {incomplete} incomplete")
            for step in result.get("next_steps", []):
                print(f"next: {step}")
            for gate in result["gates"]:
                print(f"- [{gate['status']}] {gate['id']}")
                for step in gate.get("next_steps", [])[:2]:
                    print(f"  next: {step}")
        elif result["ok"]:
            print(f"release evidence ok: {result['path']}")
        else:
            print(f"release evidence incomplete: {result['path']}")
            for item in result.get("missing", []):
                print(f"- {item}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
