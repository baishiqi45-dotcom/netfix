#!/usr/bin/env python3
"""Recorded-fixture and optional live smoke checks for LLM providers."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from netfix import keychain
from netfix.llm_provider import (
    LLMProviderError,
    OpenAICompatibleProvider,
    get_provider,
    parse_chat_completion_json_content,
)


DOMESTIC_PROVIDERS = ["deepseek", "moonshot_kimi", "minimax", "qwen"]
FIXTURE_FILES = {
    "deepseek": ("text", "deepseek_text.json"),
    "qwen": ("image_question", "qwen_image_question.json"),
    "moonshot_kimi": ("image_question", "moonshot_kimi_image_question.json"),
    "minimax": ("image_question", "minimax_image_question.json"),
}
DEFAULT_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "llm_providers"
TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _providers(providers: Optional[Iterable[str]]) -> List[str]:
    if providers is None:
        return list(DOMESTIC_PROVIDERS)
    out = [str(item).strip() for item in providers if str(item).strip()]
    return out or list(DOMESTIC_PROVIDERS)


def _task_for(provider_id: str) -> str:
    return FIXTURE_FILES.get(provider_id, ("text", ""))[0]


def _env_key_for_provider(provider_id: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", provider_id).strip("_").upper() or "DEFAULT"
    return f"NETFIX_LLM_API_KEY_{suffix}"


def _usage(parsed: Dict[str, Any]) -> Dict[str, int]:
    usage = parsed.get("__netfix_usage")
    return dict(usage) if isinstance(usage, dict) else {}


def _validate_parsed(provider_id: str, task: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
    required = {
        "schema_version": "llm_explanation.v1",
        "severity": "ok",
    }
    for key, expected in required.items():
        if parsed.get(key) != expected:
            return {
                "provider": provider_id,
                "task": task,
                "status": "failed",
                "reason_code": "invalid_fixture_schema",
                "message": f"{key} expected {expected!r}",
            }
    headline = str(parsed.get("headline") or "")
    if not headline:
        return {
            "provider": provider_id,
            "task": task,
            "status": "failed",
            "reason_code": "invalid_fixture_schema",
            "message": "headline is empty",
        }
    return {
        "provider": provider_id,
        "task": task,
        "status": "ok",
        "headline": headline,
        "usage": _usage(parsed),
    }


def _fixture_result(provider_id: str, fixture_dir: Path) -> Dict[str, Any]:
    task, filename = FIXTURE_FILES.get(provider_id, ("text", f"{provider_id}.json"))
    path = fixture_dir / filename
    if not path.exists():
        return {
            "provider": provider_id,
            "task": task,
            "status": "failed",
            "reason_code": "missing_fixture",
            "message": str(path),
        }
    try:
        parsed = parse_chat_completion_json_content(path.read_text(encoding="utf-8"))
    except LLMProviderError as exc:
        return {
            "provider": provider_id,
            "task": task,
            "status": "failed",
            "reason_code": exc.reason_code,
            "message": str(exc),
        }
    return _validate_parsed(provider_id, task, parsed)


def _live_messages(provider_id: str, task: str) -> List[Dict[str, Any]]:
    user_text = json.dumps(
        {
            "schema_version": "llm_explanation.v1",
            "instruction": "Return exactly one JSON object for a netfix provider smoke check.",
            "provider": provider_id,
            "expected_fields": ["schema_version", "headline", "severity", "explanation", "actions", "manual_steps"],
        },
        ensure_ascii=False,
    )
    if task == "image_question":
        content: Any = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": TINY_PNG_DATA_URL}},
        ]
    else:
        content = user_text
    return [
        {"role": "system", "content": "Return strict JSON only. No markdown fences unless unavoidable."},
        {"role": "user", "content": content},
    ]


def _live_result(provider_id: str, require_live: bool) -> Dict[str, Any]:
    provider = get_provider(provider_id)
    task = _task_for(provider_id)
    if not provider:
        return {"provider": provider_id, "task": task, "status": "failed", "reason_code": "unknown_provider"}
    api_key = keychain.get_secret(keychain.LLM_SERVICE, provider_id, allow_generic_llm_override=False)
    if not api_key:
        return {
            "provider": provider_id,
            "task": task,
            "status": "failed" if require_live else "skipped",
            "reason_code": "missing_api_key",
        }
    client = OpenAICompatibleProvider(
        base_url=str(provider.get("base_url") or ""),
        api_key=api_key,
        model=str(provider.get("vision_model") if task == "image_question" and provider.get("vision_model") else provider.get("model") or ""),
        timeout_s=int(os.environ.get("NETFIX_LLM_SMOKE_TIMEOUT", "30")),
        provider_id=provider_id,
    )
    try:
        parsed = client.complete_json(_live_messages(provider_id, task), max_tokens=256, temperature=0.0)
    except LLMProviderError as exc:
        return {
            "provider": provider_id,
            "task": task,
            "status": "failed",
            "reason_code": exc.reason_code,
            "http_status": exc.http_status,
            "message": str(exc),
        }
    return _validate_parsed(provider_id, task, parsed)


def run(
    *,
    mode: str = "fixtures",
    providers: Optional[Iterable[str]] = None,
    require_live: bool = False,
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
) -> Dict[str, Any]:
    provider_ids = _providers(providers)
    if mode not in {"fixtures", "live"}:
        raise ValueError("mode must be fixtures or live")
    results = [
        _fixture_result(provider_id, fixture_dir) if mode == "fixtures" else _live_result(provider_id, require_live)
        for provider_id in provider_ids
    ]
    failed = [item for item in results if item.get("status") == "failed"]
    return {
        "ok": not failed,
        "mode": mode,
        "checked": len(results),
        "providers": provider_ids,
        "results": results,
    }


def validate_live_record(path: Path, required_providers: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    data = _load_json(path)
    required = _providers(required_providers)
    missing: List[str] = []
    if data.get("mode") != "live":
        missing.append("mode")
    if data.get("ok") is not True:
        missing.append("ok")
    providers = data.get("providers") if isinstance(data.get("providers"), list) else []
    results = data.get("results") if isinstance(data.get("results"), list) else []
    by_provider = {str(item.get("provider")): item for item in results if isinstance(item, dict)}
    for provider_id in required:
        if provider_id not in providers or provider_id not in by_provider:
            missing.append(f"provider.{provider_id}")
            continue
        item = by_provider[provider_id]
        if item.get("status") != "ok":
            missing.append(f"provider.{provider_id}.status")
        if item.get("task") != _task_for(provider_id):
            missing.append(f"provider.{provider_id}.task")
    return {
        "ok": not missing,
        "path": str(path),
        "missing": missing,
    }


def _provider_status(provider_id: str) -> Dict[str, Any]:
    task = _task_for(provider_id)
    ready = keychain.has_secret(keychain.LLM_SERVICE, provider_id, allow_generic_llm_override=False)
    return {
        "provider": provider_id,
        "task": task,
        "api_key_account": provider_id,
        "api_key_ready": ready,
        "env_key": _env_key_for_provider(provider_id),
        "next_step": "" if ready else f"Save a provider-scoped Keychain item for account {provider_id!r} or set {_env_key_for_provider(provider_id)} for this smoke run.",
    }


def status(
    *,
    record: Optional[Path] = None,
    providers: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    provider_ids = _providers(providers)
    provider_statuses = [_provider_status(provider_id) for provider_id in provider_ids]
    ready_count = sum(1 for item in provider_statuses if item["api_key_ready"])
    if record is None:
        record_status = {
            "ok": False,
            "path": "",
            "status": "missing_record",
            "missing": ["record"],
            "next_step": "python3 scripts/provider_smoke_check.py --live --require-live --json > gui/macos/.build/provider-smoke-live.json",
        }
    elif not record.exists():
        record_status = {
            "ok": False,
            "path": str(record),
            "status": "missing_record",
            "missing": ["record"],
            "next_step": f"python3 scripts/provider_smoke_check.py --live --require-live --json > {record}",
        }
    else:
        validation = validate_live_record(record, provider_ids)
        record_status = {
            "ok": bool(validation.get("ok")),
            "path": str(record),
            "status": "complete" if validation.get("ok") else "invalid_record",
            "missing": validation.get("missing", []),
            "next_step": "" if validation.get("ok") else f"Regenerate with: python3 scripts/provider_smoke_check.py --live --require-live --json > {record}",
        }
    return {
        "ok": ready_count == len(provider_statuses) and bool(record_status.get("ok")),
        "summary": {
            "providers_ready": ready_count,
            "providers_missing": len(provider_statuses) - ready_count,
            "record_ok": bool(record_status.get("ok")),
        },
        "providers": provider_statuses,
        "record": record_status,
        "next_steps": [
            "Configure provider-scoped keys for every marketed domestic provider.",
            "Run: python3 scripts/provider_smoke_check.py --live --require-live --json > gui/macos/.build/provider-smoke-live.json",
            "Attach provider-smoke-live.json through scripts/release_evidence.py and scripts/release_readiness.py.",
        ],
    }


def _main_status(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Show live provider smoke readiness without calling providers.")
    parser.add_argument("--record", type=Path, default=None, help="optional provider-smoke-live.json to validate")
    parser.add_argument("--provider", action="append", dest="providers", help="provider id to check; repeatable")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args(argv)
    result = status(record=args.record, providers=args.providers)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"provider smoke status: {result['summary']['providers_ready']} provider key(s) ready, {result['summary']['providers_missing']} missing")
        if result["record"]["path"]:
            print(f"record: {result['record']['status']} {result['record']['path']}")
        else:
            print("record: missing")
        for item in result["providers"]:
            if not item["api_key_ready"]:
                print(f"- [{item['task']}] {item['provider']}: {item['next_step']}")
        if result["record"].get("next_step"):
            print(f"next: {result['record']['next_step']}")
    return 0 if result["ok"] else 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "status":
        return _main_status(argv[1:])
    parser = argparse.ArgumentParser(description="Run LLM provider fixture or optional live smoke checks.")
    parser.add_argument("--live", action="store_true", help="call live providers using provider-scoped Keychain/env keys")
    parser.add_argument("--require-live", action="store_true", help="treat missing live keys as failures")
    parser.add_argument("--provider", action="append", dest="providers", help="provider id to check; repeatable")
    parser.add_argument("--fixture-dir", default=str(DEFAULT_FIXTURE_DIR), help="recorded fixture directory")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args(argv)

    result = run(
        mode="live" if args.live else "fixtures",
        providers=args.providers,
        require_live=bool(args.require_live),
        fixture_dir=Path(args.fixture_dir),
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"provider smoke {result['mode']} passed: {result['checked']} provider(s)")
        for item in result["results"]:
            print(f"- {item['provider']} {item['task']}: {item['status']}")
    else:
        print(f"provider smoke {result['mode']} failed", file=sys.stderr)
        for item in result["results"]:
            if item.get("status") == "failed":
                print(f"- {item['provider']} {item.get('reason_code')}: {item.get('message', '')}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
