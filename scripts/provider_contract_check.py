#!/usr/bin/env python3
"""Offline contract checks for netfix OpenAI-compatible LLM providers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from netfix.llm_provider import (
    OpenAICompatibleProvider,
    list_providers,
    parse_chat_completion_json_content,
)


DOMESTIC_ORDER = ["deepseek", "moonshot_kimi", "minimax", "qwen"]
ALLOWED_CAPABILITIES = {"text", "json", "vision", "video", "tools", "streaming"}
ALLOWED_MAX_TOKEN_FIELDS = {"max_tokens", "max_completion_tokens"}
SAMPLE_RESPONSE = json.dumps({
    "id": "chatcmpl-contract",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "schema_version": "llm_explanation.v1",
                    "headline": "ok",
                    "severity": "ok",
                    "explanation": "contract fixture",
                    "actions": [],
                    "manual_steps": [],
                }),
            },
            "finish_reason": "stop",
        }
    ],
})


def check_provider(provider: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    provider_id = str(provider.get("id") or "")
    base_url = str(provider.get("base_url") or "")
    model = str(provider.get("model") or "")
    market = str(provider.get("market") or "")
    if provider_id != "custom_openai_compatible" and not base_url.startswith("https://"):
        findings.append({"provider": provider_id, "kind": "base-url", "message": "base_url must use https"})
    if provider_id != "custom_openai_compatible" and not model:
        findings.append({"provider": provider_id, "kind": "model", "message": "model must be set"})
    if market == "domestic":
        if provider.get("metadata_checked_at") != "2026-06-25":
            findings.append({"provider": provider_id, "kind": "metadata", "message": "domestic provider metadata must record the latest official-doc check date"})
        docs = provider.get("official_docs")
        if not isinstance(docs, list) or not docs or any(not str(item).startswith("https://") for item in docs):
            findings.append({"provider": provider_id, "kind": "metadata", "message": "domestic provider must include https official_docs evidence URLs"})
    if provider.get("openai_compatible") is not True:
        findings.append({"provider": provider_id, "kind": "compatibility", "message": "provider must be OpenAI-compatible"})
    if not isinstance(provider.get("supports_json_mode"), bool):
        findings.append({"provider": provider_id, "kind": "json-mode", "message": "supports_json_mode must be explicit"})
    capabilities = provider.get("capabilities")
    if not isinstance(capabilities, list) or "text" not in capabilities:
        findings.append({"provider": provider_id, "kind": "capabilities", "message": "capabilities must include text"})
    elif any(str(item) not in ALLOWED_CAPABILITIES for item in capabilities):
        findings.append({"provider": provider_id, "kind": "capabilities", "message": f"capabilities must use product vocabulary: {sorted(ALLOWED_CAPABILITIES)}"})
    if provider.get("supports_json_mode") and (not isinstance(capabilities, list) or "json" not in capabilities):
        findings.append({"provider": provider_id, "kind": "capabilities", "message": "JSON-mode providers must include json capability"})
    if not provider.get("supports_json_mode") and isinstance(capabilities, list) and "json" in capabilities:
        findings.append({"provider": provider_id, "kind": "capabilities", "message": "providers without JSON mode must not include json capability"})
    if provider.get("supports_vision") and (not isinstance(capabilities, list) or "vision" not in capabilities):
        findings.append({"provider": provider_id, "kind": "capabilities", "message": "vision providers must include vision capability"})
    if not provider.get("supports_vision") and isinstance(capabilities, list) and "vision" in capabilities:
        findings.append({"provider": provider_id, "kind": "capabilities", "message": "providers without vision support must not include vision capability"})
    if provider.get("supports_vision") and market == "domestic" and provider.get("image_question_status") != "openai_compatible_image_url_ready":
        findings.append({"provider": provider_id, "kind": "vision-adapter", "message": "domestic vision providers must declare a ready OpenAI-compatible image_url adapter"})
    if not provider.get("system_prompt"):
        findings.append({"provider": provider_id, "kind": "prompt", "message": "provider must declare a system_prompt"})
    if provider.get("default_max_tokens") is None:
        findings.append({"provider": provider_id, "kind": "tokens", "message": "provider must declare default_max_tokens"})
    if provider.get("text_priority") is None:
        findings.append({"provider": provider_id, "kind": "priority", "message": "provider must declare text_priority"})
    token_field = str(provider.get("max_tokens_field") or "max_tokens")
    if token_field not in ALLOWED_MAX_TOKEN_FIELDS:
        findings.append({"provider": provider_id, "kind": "payload", "message": f"max_tokens_field must be one of {sorted(ALLOWED_MAX_TOKEN_FIELDS)}"})

    client = OpenAICompatibleProvider(base_url or "https://127.0.0.1/v1", "contract-key", model or "contract-model", provider_id=provider_id)
    url = client._chat_completions_url()
    if not url.endswith("/chat/completions"):
        findings.append({"provider": provider_id, "kind": "chat-url", "message": "chat URL must end with /chat/completions"})
    payload = client._build_payload([{"role": "user", "content": "{}"}], 64, 0.0)
    if token_field not in payload:
        findings.append({"provider": provider_id, "kind": "payload", "message": f"payload must use configured token field {token_field}"})
    if token_field != "max_tokens" and "max_tokens" in payload:
        findings.append({"provider": provider_id, "kind": "payload", "message": "payload must not include legacy max_tokens when provider selects a newer token field"})
    if provider_id == "minimax" and token_field != "max_completion_tokens":
        findings.append({"provider": provider_id, "kind": "payload", "message": "MiniMax OpenAI chat preset must use max_completion_tokens"})
    if market == "domestic" and "store" in payload:
        findings.append({"provider": provider_id, "kind": "payload", "message": "domestic payload must omit OpenAI store field"})
    if bool(provider.get("supports_json_mode")) != ("response_format" in payload):
        findings.append({"provider": provider_id, "kind": "payload", "message": "response_format must match supports_json_mode"})
    return findings


def run() -> Dict[str, Any]:
    providers = list_providers()
    ids = [item.get("id") for item in providers]
    findings: List[Dict[str, str]] = []
    if ids[:4] != DOMESTIC_ORDER:
        findings.append({"provider": "all", "kind": "order", "message": f"domestic provider order must be {DOMESTIC_ORDER}"})
    for provider in providers:
        findings.extend(check_provider(provider))
    parsed = parse_chat_completion_json_content(SAMPLE_RESPONSE)
    if parsed.get("schema_version") != "llm_explanation.v1":
        findings.append({"provider": "fixture", "kind": "response", "message": "fixture response did not parse to expected schema"})
    return {
        "ok": not findings,
        "provider_ids": ids,
        "checked": len(providers),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline provider contract checks.")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"provider contract check passed: {result['checked']} providers")
    else:
        print(f"provider contract check failed: {len(result['findings'])} finding(s)", file=sys.stderr)
        for finding in result["findings"]:
            print(f"- {finding['provider']} {finding['kind']}: {finding['message']}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
