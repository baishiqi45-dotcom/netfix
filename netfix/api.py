"""Local HTTP API that wraps the netfix CLI."""
from __future__ import annotations

import json
import os
import secrets
import signal
import stat
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from netfix import deepseek_sidecar, dashboard_state, keychain, llm_budget, llm_explain, llm_provider, logs, proxy_bridge, proxy_monitor_service, residential_proxy, services, settings, user_facing_errors
from netfix.constants import JOURNAL_DIR, REPO_ROOT, RULES_DIR, VERSION
from netfix.detect import detect_environment, get_core
from netfix.fix_engine import FixEngine
from netfix.redaction import redact_report, redact_text
from netfix.safety import FixTier
from netfix.service_runner import cancel_job, get_job, run_cli, start_job
from netfix.utils import ensure_private_dir


WEB_DIR = REPO_ROOT / "gui" / "web"
_API_TOKEN = secrets.token_urlsafe(32)
_API_TOKEN_FILE = JOURNAL_DIR / f"api-token-{os.getpid()}.txt"
_PUBLIC_GET_PATHS = {"/", "/index.html", "/health"}
MAX_JSON_BODY_BYTES = 24 * 1024 * 1024
_STARTUP_BRIDGE_CHECK: Dict[str, Any] = {}
_VISION_ADAPTER_READY_STATUSES = {
    "openai_compatible_image_url_ready",
    "provider_supports_vision_adapter_ready",
}
LLM_CHAIN_TEST_CONFIRMATION = "TEST_LLM_CHAIN"
LLM_PROVIDER_TEST_CONFIRMATION = "TEST_LLM_PROVIDER"
SYSTEM_FIX_CONFIRMATION = "APPLY_SYSTEM_FIX"
_TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_api_token_file() -> Path:
    ensure_private_dir(_API_TOKEN_FILE.parent)
    fd = os.open(str(_API_TOKEN_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(_API_TOKEN + "\n")
    try:
        os.chmod(_API_TOKEN_FILE, 0o600)
    except OSError as exc:
        raise RuntimeError("failed to secure local API token file permissions") from exc
    mode = stat.S_IMODE(os.stat(_API_TOKEN_FILE).st_mode)
    if mode != 0o600:
        raise RuntimeError(f"local API token file has unsafe permissions: {oct(mode)}")
    return _API_TOKEN_FILE


def _remove_api_token_file() -> None:
    try:
        _API_TOKEN_FILE.unlink(missing_ok=True)
    except TypeError:
        if _API_TOKEN_FILE.exists():
            _API_TOKEN_FILE.unlink()
    except OSError:
        pass


def _environment_summary() -> Dict[str, Any]:
    """Return a lightweight summary of the detected proxy/network environment."""
    try:
        env = detect_environment()
        core = get_core(env)
        inbound = core.get_inbound() or {} if core else {}
        active = core.get_active_profile() if core else None
        return {
            "ok": True,
            "gui_client": core.name if core else None,
            "active_core": core.name if core else None,
            "mixed_port": inbound.get("port") if core else env.get("mixed_port"),
            "active_profile": active,
            "profiles": core.list_profiles() if core else [],
            "system_proxy": env.get("system_proxy"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _bridge_status_payload() -> Dict[str, Any]:
    """Return bridge status plus stale detection, lifecycle, and startup evidence."""
    status = proxy_bridge.status()
    stale_check = residential_proxy.detect_stale_bridge()
    status["stale_check"] = stale_check
    status["lifecycle"] = residential_proxy.bridge_lifecycle(
        status.get("bridges", []),
        stale_check,
    )
    if _STARTUP_BRIDGE_CHECK:
        status["startup_check"] = dict(_STARTUP_BRIDGE_CHECK)
    return status


def _record_startup_bridge_check() -> Dict[str, Any]:
    """Run a non-mutating stale-bridge check at backend startup."""
    global _STARTUP_BRIDGE_CHECK
    checked_at = _utc_now()
    try:
        bridge_settings = settings.get_proxy_bridge_settings()
        auto_restart: Optional[Dict[str, Any]] = None
        if bridge_settings.get("auto_restart_enabled"):
            auto_restart = residential_proxy.restart_stale_bridge(
                confirmed=True,
                confirmation=residential_proxy.BRIDGE_RESTART_CONFIRMATION,
                idle_timeout_s=float(bridge_settings.get("idle_timeout") or 0),
            )
        status = proxy_bridge.status()
        stale_check = residential_proxy.detect_stale_bridge()
        lifecycle = residential_proxy.bridge_lifecycle(status.get("bridges", []), stale_check)
        startup_check = {
            "schema_version": "netfix_proxy_bridge_startup_check.v1",
            "checked_at": checked_at,
            "ok": bool(status.get("ok", True) and stale_check.get("ok", True)),
            "bridges_count": len(status.get("bridges", [])),
            "stale_check": stale_check,
            "lifecycle": lifecycle,
            "settings": bridge_settings,
        }
        if auto_restart is not None:
            startup_check["auto_restart"] = auto_restart
            if auto_restart.get("status") == "restarted":
                event = logs.append_event({
                    "type": "proxy_bridge_startup",
                    "status": "ok",
                    "headline": "本地桥接已按设置自动恢复",
                    "root_cause": "系统代理仍指向上次 Netfix 桥接端口，当前 Netfix 已重新启动本地桥接；没有改写系统代理。",
                    "bridge_lifecycle": "running_system",
                    "profile_id": auto_restart.get("profile_id"),
                    "network_service": auto_restart.get("network_service"),
                })
                startup_check["auto_restart_event_appended"] = bool(event.get("ok"))
        if lifecycle.get("needs_attention") or lifecycle.get("status") in {"recovery_required", "check_failed"}:
            event = logs.append_event({
                "type": "proxy_bridge_startup",
                "status": "warn" if lifecycle.get("status") == "recovery_required" else "fail",
                "headline": lifecycle.get("headline") or "桥接启动检查需要处理",
                "root_cause": lifecycle.get("detail") or stale_check.get("warning") or stale_check.get("error") or "",
                "bridge_lifecycle": lifecycle.get("status"),
                "recovery_available": lifecycle.get("recovery_available"),
                "network_service": lifecycle.get("network_service"),
                "profile_id": lifecycle.get("profile_id"),
            })
            startup_check["event_appended"] = bool(event.get("ok"))
        _STARTUP_BRIDGE_CHECK = startup_check
        return startup_check
    except Exception as exc:
        startup_check = {
            "schema_version": "netfix_proxy_bridge_startup_check.v1",
            "checked_at": checked_at,
            "ok": False,
            "lifecycle": {
                "schema_version": "netfix_proxy_bridge_lifecycle.v1",
                "status": "check_failed",
                "severity": "warning",
                "headline": "桥接启动检查失败",
                "primary_action": "refresh",
                "needs_attention": True,
                "recovery_available": False,
            },
            "error": str(exc),
        }
        try:
            event = logs.append_event({
                "type": "proxy_bridge_startup",
                "status": "fail",
                "headline": "桥接启动检查失败",
                "root_cause": str(exc),
                "bridge_lifecycle": "check_failed",
                "recovery_available": False,
            })
            startup_check["event_appended"] = bool(event.get("ok"))
        except Exception:
            startup_check["event_appended"] = False
        _STARTUP_BRIDGE_CHECK = startup_check
        return startup_check


def _llm_providers_with_status() -> List[Dict[str, Any]]:
    """Return provider presets plus local readiness metadata."""
    llm_settings = settings.load_settings().get("llm", {})
    features = llm_settings.get("features") if isinstance(llm_settings.get("features"), dict) else {}
    image_feature_enabled = bool(features.get("image_question"))
    active_provider = str(llm_settings.get("provider") or "deepseek")
    active_account = str(llm_settings.get("api_key_account") or active_provider)
    providers = []
    for provider in llm_provider.list_providers():
        item = dict(provider)
        provider_id = str(item.get("id") or "")
        account = active_account if provider_id == active_provider else provider_id
        if provider_id == active_provider:
            item["base_url"] = str(llm_settings.get("base_url") or item.get("base_url") or "")
            item["model"] = str(llm_settings.get("model") or item.get("model") or "")
        item["api_key_account"] = account
        item["api_key_set"] = keychain.has_secret(
            keychain.LLM_SERVICE,
            account,
            allow_generic_llm_override=provider_id == active_provider,
        )
        image_status = str(item.get("image_question_status") or "")
        image_adapter_ready = bool(item.get("supports_vision") and image_status in _VISION_ADAPTER_READY_STATUSES)
        item["fallback_ready"] = bool(item["api_key_set"])
        item["text_explain_ready"] = bool(item["api_key_set"])
        item["image_question_provider_supported"] = bool(item.get("supports_vision"))
        item["image_question_adapter_ready"] = image_adapter_ready
        item["image_question_ready"] = bool(item["api_key_set"] and image_adapter_ready and image_feature_enabled)
        item["netfix_mode"] = "text_report_only" if not item["image_question_ready"] else "text_and_image_question"
        providers.append(item)
    return providers


def _llm_chain_step(provider: Dict[str, Any], *, mode: str, llm_enabled: bool, image_feature_enabled: bool) -> Dict[str, Any]:
    """Return non-secret readiness for one provider in a fallback chain."""
    provider_id = str(provider.get("id") or "")
    api_key_set = bool(provider.get("api_key_set"))
    supports_vision = bool(provider.get("image_question_provider_supported"))
    adapter_ready = bool(provider.get("image_question_adapter_ready"))
    if not llm_enabled:
        status = "disabled"
        ready = False
        next_step = "Enable cloud AI explanation in Settings."
    elif mode == "image_question" and not image_feature_enabled:
        status = "feature_disabled"
        ready = False
        next_step = "Enable the image-question experiment before sending images."
    elif mode == "image_question" and not supports_vision:
        status = "unsupported"
        ready = False
        next_step = "Use MiniMax, Kimi/Moonshot, or Qwen for image-question routing."
    elif mode == "image_question" and not adapter_ready:
        status = "adapter_pending"
        ready = False
        next_step = "Wait for a validated image_url adapter before routing images here."
    elif not api_key_set:
        status = "missing_key"
        ready = False
        next_step = f"Save an API key for Keychain account '{provider.get('api_key_account') or provider_id}'."
    else:
        status = "ready"
        ready = True
        next_step = "Ready for this local fallback chain."

    model = str(provider.get("model") or "")
    if mode == "image_question" and provider.get("vision_model"):
        model = str(provider.get("vision_model") or model)
    return {
        "provider": provider_id,
        "label": provider.get("label") or provider_id,
        "mode": mode,
        "status": status,
        "ready": ready,
        "api_key_account": provider.get("api_key_account") or provider_id,
        "api_key_set": api_key_set,
        "model": model,
        "base_url": provider.get("base_url") or "",
        "supports_vision": supports_vision,
        "image_adapter_ready": adapter_ready,
        "cost_tier": provider.get("cost_tier") or "",
        "metadata_checked_at": provider.get("metadata_checked_at") or "",
        "official_docs": provider.get("official_docs") if isinstance(provider.get("official_docs"), list) else [],
        "max_tokens_field": provider.get("max_tokens_field") or "max_tokens",
        "next_step": next_step,
    }


def _llm_chain_readiness() -> Dict[str, Any]:
    """Return product-facing readiness for configured domestic text and vision chains."""
    llm_settings = settings.load_settings().get("llm", {})
    features = llm_settings.get("features") if isinstance(llm_settings.get("features"), dict) else {}
    fallback = llm_settings.get("fallback") if isinstance(llm_settings.get("fallback"), dict) else {}
    llm_enabled = bool(llm_settings.get("enabled"))
    fallback_enabled = bool(fallback.get("enabled", True))
    image_feature_enabled = bool(features.get("image_question"))
    providers = _llm_providers_with_status()
    by_id = {str(provider.get("id") or ""): provider for provider in providers}
    active_provider = str(llm_settings.get("provider") or "deepseek")

    text_ids = llm_explain._ordered_provider_ids(active_provider, llm_settings, "explain")
    if not fallback_enabled:
        text_ids = [active_provider]
    vision_ids = llm_explain._ordered_provider_ids(active_provider, llm_settings, "image_question")
    if not fallback_enabled:
        vision_ids = [provider_id for provider_id in vision_ids if provider_id == active_provider]

    def build_chain(chain_id: str, label: str, mode: str, ids: List[str]) -> Dict[str, Any]:
        steps = [
            _llm_chain_step(by_id[provider_id], mode=mode, llm_enabled=llm_enabled, image_feature_enabled=image_feature_enabled)
            for provider_id in ids
            if provider_id in by_id
        ]
        ready_count = sum(1 for step in steps if step.get("ready"))
        missing_keys = [step["provider"] for step in steps if step.get("status") == "missing_key"]
        if not llm_enabled:
            status = "disabled"
            next_step = "Enable cloud AI explanation in Settings."
        elif mode == "image_question" and not image_feature_enabled:
            status = "feature_disabled"
            next_step = "Enable image-question and save a key for MiniMax, Kimi/Moonshot, or Qwen."
        elif ready_count:
            status = "ready"
            next_step = "Configured providers are ready for this local chain."
        elif missing_keys:
            status = "missing_keys"
            next_step = "Save provider-scoped API keys for the listed domestic providers."
        else:
            status = "blocked"
            next_step = "Review provider capability and feature settings."
        return {
            "id": chain_id,
            "label": label,
            "mode": mode,
            "status": status,
            "ready": bool(status == "ready"),
            "ready_count": ready_count,
            "missing_key_providers": missing_keys,
            "next_step": next_step,
            "providers": steps,
        }

    return {
        "ok": True,
        "schema_version": "netfix_llm_chain_readiness.v1",
        "llm_enabled": llm_enabled,
        "fallback_enabled": fallback_enabled,
        "image_question_enabled": image_feature_enabled,
        "budget": llm_budget.status(llm_settings.get("budget") if isinstance(llm_settings.get("budget"), dict) else {}),
        "chains": [
            build_chain("text", "文本解释链路", "explain", text_ids),
            build_chain("image_question", "图片问诊链路", "image_question", vision_ids),
        ],
    }


def _llm_chain_test_messages(provider_id: str, mode: str) -> List[Dict[str, Any]]:
    expected = {
        "schema_version": "llm_explanation.v1",
        "headline": "provider chain test ok",
        "severity": "ok",
        "explanation": "provider chain test ok",
        "actions": [],
        "manual_steps": [],
    }
    user_text = json.dumps(
        {
            "instruction": "Return the expected_json object exactly. Do not add prose, markdown, comments, or extra keys.",
            "provider": provider_id,
            "expected_json": expected,
        },
        ensure_ascii=False,
    )
    content: Any = user_text
    if mode == "image_question":
        content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": _TINY_PNG_DATA_URL}},
        ]
    return [
        {"role": "system", "content": "You are a JSON API. Return only one valid JSON object. No markdown. No prose."},
        {"role": "user", "content": content},
    ]


def _llm_chain_test_step(provider_id: str, mode: str, llm_settings: Dict[str, Any], budget_settings: Dict[str, Any]) -> Dict[str, Any]:
    provider = llm_provider.get_provider(provider_id) or {}
    provider_settings = llm_explain._provider_settings(llm_settings, provider_id, mode=mode)
    account = str(provider_settings.get("api_key_account") or provider_id)
    api_key = keychain.get_secret(
        keychain.LLM_SERVICE,
        account,
        allow_generic_llm_override=provider_id == str(llm_settings.get("provider") or ""),
    )
    base = {
        "provider": provider_id,
        "label": provider.get("label") or provider_id,
        "mode": mode,
        "api_key_account": account,
        "model": provider_settings.get("model") or "",
    }
    if mode == "image_question":
        if not provider.get("supports_vision"):
            return {**base, "status": "skipped", "reason_code": "provider_vision_unsupported"}
        if str(provider.get("image_question_status") or "") not in _VISION_ADAPTER_READY_STATUSES:
            return {**base, "status": "skipped", "reason_code": "provider_vision_adapter_pending"}
    if not api_key:
        return {**base, "status": "skipped", "reason_code": "missing_api_key"}
    allowance = llm_budget.check_request(provider_id, mode, budget_settings)
    if not allowance.get("ok"):
        step = {**base, "status": "skipped", "reason_code": allowance.get("reason_code") or "local_budget_exceeded"}
        for key in ("retry_after_s", "limit", "window_s"):
            if key in allowance:
                step[key] = allowance[key]
        return step
    client = llm_provider.OpenAICompatibleProvider(
        base_url=str(provider_settings.get("base_url") or ""),
        api_key=api_key,
        model=str(provider_settings.get("model") or ""),
        timeout_s=int(provider_settings.get("timeout_s") or 20),
        provider_id=provider_id,
    )
    try:
        llm_budget.record_request(provider_id, mode, budget_settings)
        parsed = client.complete_json(_llm_chain_test_messages(provider_id, mode), max_tokens=256, temperature=0.0)
    except llm_provider.LLMProviderError as exc:
        llm_budget.record_provider_result(provider_id, exc.reason_code, budget_settings)
        return {
            **base,
            "status": "failed",
            "reason_code": exc.reason_code,
            "http_status": exc.http_status,
        }
    usage = parsed.pop("__netfix_usage", None)
    if parsed.get("schema_version") != "llm_explanation.v1" or not isinstance(parsed.get("headline"), str):
        return {**base, "status": "failed", "reason_code": "invalid_response_shape"}
    step = {
        **base,
        "status": "ok",
        "reason_code": None,
        "headline": str(parsed.get("headline") or "provider chain test ok"),
    }
    if isinstance(usage, dict):
        step["usage"] = usage
    return step


def _llm_chain_test(body: Dict[str, Any]) -> Dict[str, Any]:
    if body.get("confirmation") != LLM_CHAIN_TEST_CONFIRMATION:
        return {
            "ok": False,
            "error": f"confirmation must be {LLM_CHAIN_TEST_CONFIRMATION}",
            "requires_confirmation": True,
            "confirmation": LLM_CHAIN_TEST_CONFIRMATION,
        }
    llm_settings = settings.load_settings().get("llm", {})
    features = llm_settings.get("features") if isinstance(llm_settings.get("features"), dict) else {}
    fallback = llm_settings.get("fallback") if isinstance(llm_settings.get("fallback"), dict) else {}
    budget_settings = llm_settings.get("budget") if isinstance(llm_settings.get("budget"), dict) else {}
    active_provider = str(llm_settings.get("provider") or "deepseek")
    fallback_enabled = bool(fallback.get("enabled", True))
    requested = str(body.get("mode") or "all")
    valid_modes = {"all", "text", "explain", "image_question", "vision"}
    if requested not in valid_modes:
        return {
            "ok": False,
            "schema_version": "netfix_llm_chain_test.v1",
            "checked_at": _utc_now(),
            "reason_code": "invalid_mode",
            "error": "mode must be one of: all, text, explain, image_question, vision",
            "tested_count": 0,
            "chains": [],
            "warnings": [],
        }
    chain_specs = []
    if requested in {"all", "text", "explain"}:
        text_ids = llm_explain._ordered_provider_ids(active_provider, llm_settings, "explain")
        if not fallback_enabled:
            text_ids = [active_provider]
        chain_specs.append(("text", "文本解释链路", "explain", text_ids))
    if requested in {"all", "image_question", "vision"}:
        vision_ids = llm_explain._ordered_provider_ids(active_provider, llm_settings, "image_question")
        if not fallback_enabled:
            vision_ids = [provider_id for provider_id in vision_ids if provider_id == active_provider]
        chain_specs.append(("image_question", "图片问诊链路", "image_question", vision_ids))

    if not bool(llm_settings.get("enabled")):
        return {
            "ok": False,
            "schema_version": "netfix_llm_chain_test.v1",
            "checked_at": _utc_now(),
            "reason_code": "llm_disabled",
            "error": "cloud AI explanation is disabled",
            "tested_count": 0,
            "chains": [
                {
                    "id": chain_id,
                    "label": label,
                    "mode": mode,
                    "status": "skipped",
                    "ok_count": 0,
                    "failed_count": 0,
                    "skipped_count": len(provider_ids),
                    "providers": [
                        {"provider": provider_id, "mode": mode, "status": "skipped", "reason_code": "llm_disabled"}
                        for provider_id in provider_ids
                    ],
                }
                for chain_id, label, mode, provider_ids in chain_specs
            ],
            "warnings": [
                "Cloud AI explanation is disabled. Enable AI settings before running live provider tests.",
            ],
        }

    chains = []
    for chain_id, label, mode, provider_ids in chain_specs:
        if mode == "image_question" and not bool(features.get("image_question")):
            steps = [
                {"provider": provider_id, "mode": mode, "status": "skipped", "reason_code": "image_question_disabled"}
                for provider_id in provider_ids
            ]
        else:
            steps = [_llm_chain_test_step(provider_id, mode, llm_settings, budget_settings) for provider_id in provider_ids]
        failed_count = sum(1 for step in steps if step.get("status") == "failed")
        ok_count = sum(1 for step in steps if step.get("status") == "ok")
        if failed_count:
            status = "failed"
        elif ok_count:
            status = "ok"
        else:
            status = "skipped"
        chains.append({
            "id": chain_id,
            "label": label,
            "mode": mode,
            "status": status,
            "ok_count": ok_count,
            "failed_count": failed_count,
            "skipped_count": sum(1 for step in steps if step.get("status") == "skipped"),
            "providers": steps,
        })
    failed = any(chain.get("status") == "failed" for chain in chains)
    tested = sum(int(chain.get("ok_count") or 0) for chain in chains)
    return {
        "ok": bool(tested and not failed),
        "schema_version": "netfix_llm_chain_test.v1",
        "checked_at": _utc_now(),
        "tested_count": tested,
        "chains": chains,
        "warnings": [
            "This explicit test calls configured providers and may count toward provider usage or billing.",
        ],
    }


def _load_latest_report() -> Tuple[int, Any]:
    report_path = JOURNAL_DIR / "last_report.json"
    if not report_path.exists():
        return 404, {"ok": False, "error": "no latest report"}
    try:
        return 200, json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return 500, {"ok": False, "error": f"failed to read report: {exc}"}


def _support_bundle() -> Dict[str, Any]:
    """Return a redacted local support bundle for user-approved sharing."""
    generated_at = _utc_now()
    status, report = _load_latest_report()
    latest_report: Dict[str, Any] = {"exists": False, "status": status}
    headline = ""
    if status == 200 and isinstance(report, dict):
        redacted = redact_report(report, level="strict")
        redacted_report = redacted.get("redacted_report") if isinstance(redacted.get("redacted_report"), dict) else {}
        explanation = redacted_report.get("explanation") if isinstance(redacted_report.get("explanation"), dict) else {}
        headline = str(explanation.get("headline") or "")
        latest_report = {
            "exists": True,
            "status": 200,
            "timestamp": (redacted_report.get("meta") or {}).get("timestamp") if isinstance(redacted_report.get("meta"), dict) else None,
            "headline": headline,
            "root_causes": redacted_report.get("root_causes", [])[:5] if isinstance(redacted_report.get("root_causes"), list) else [],
            "fixes": redacted_report.get("fixes", [])[:5] if isinstance(redacted_report.get("fixes"), list) else [],
            "redacted_report_hash": redacted.get("redacted_report_hash"),
            "redaction_audit": redacted.get("redaction_audit") or {},
        }
    elif isinstance(report, dict):
        latest_report = {"exists": False, "status": status, "error": redact_text(str(report.get("error") or "no latest report"))}

    events_payload = logs.load_events(limit=30, hours=24 * 7)
    events = events_payload.get("events") if isinstance(events_payload.get("events"), list) else []
    redacted_events = redact_report({"events": events}, level="strict")
    safe_events = (redacted_events.get("redacted_report") or {}).get("events", [])

    log_meta = logs.load_logs()
    privacy = log_meta.get("privacy") if isinstance(log_meta.get("privacy"), dict) else settings.get_privacy_settings()
    environment = redact_report({"environment": _environment_summary()}, level="strict").get("redacted_report", {}).get("environment", {})

    next_steps: List[str] = []
    if not latest_report.get("exists"):
        next_steps.append("先在 Netfix App 里点一键诊断，再复制支持包。")
    else:
        next_steps.append("把 support_text 或整份 JSON 发给技术人员；不要再附原始代理密码、API Key 或未脱敏截图。")
    next_steps.append("如果问题和代理有关，优先在代理设置里重新粘贴供应商给的完整 host/port/user/password。")

    support_text_lines = [
        "Netfix support bundle",
        f"generated_at: {generated_at}",
        f"version: {VERSION}",
        f"latest_report: {'yes' if latest_report.get('exists') else 'no'}",
    ]
    if headline:
        support_text_lines.append(f"headline: {redact_text(headline)}")
    support_text_lines.append(f"events_count: {len(safe_events)}")
    support_text_lines.append(f"redacted_report_hash: {latest_report.get('redacted_report_hash') or '-'}")

    return {
        "ok": True,
        "schema_version": "netfix_support_bundle.v1",
        "generated_at": generated_at,
        "version": VERSION,
        "latest_report": latest_report,
        "events": {
            "count": len(safe_events),
            "items": safe_events,
            "error": redact_text(str(events_payload.get("error") or "")) if events_payload.get("error") else None,
        },
        "logs": {
            "latest_report_exists": bool(log_meta.get("latest_report_exists")),
            "events_exists": bool(log_meta.get("events_exists")),
            "privacy": privacy,
        },
        "environment": environment,
        "next_steps": next_steps,
        "support_text": "\n".join(support_text_lines),
    }


def _proxy_identity_persistence_summary(identity_report: Dict[str, Any]) -> Dict[str, Any]:
    """Return a low-detail saved identity summary without raw exit IP."""
    identity = identity_report.get("identity") if isinstance(identity_report.get("identity"), dict) else {}
    expected_geo = identity_report.get("expected_geo") if isinstance(identity_report.get("expected_geo"), dict) else {}
    dns_leak = identity_report.get("dns_leak") if isinstance(identity_report.get("dns_leak"), dict) else {}
    ipv6_leak = identity_report.get("ipv6_leak") if isinstance(identity_report.get("ipv6_leak"), dict) else {}
    targets = identity_report.get("targets") if isinstance(identity_report.get("targets"), list) else []
    return {
        "status": str(identity_report.get("status") or "unknown"),
        "country_code": str(identity.get("country_code") or ""),
        "region": str(identity.get("region") or ""),
        "city": str(identity.get("city") or ""),
        "ip_type": str(identity.get("ip_type") or ""),
        "expected_geo_status": str(expected_geo.get("status") or "not_configured"),
        "dns_leak_status": str(dns_leak.get("status") or "unknown"),
        "ipv6_leak_status": str(ipv6_leak.get("status") or "unknown"),
        "target_fail_count": len([item for item in targets if isinstance(item, dict) and item.get("status") == "fail"]),
        "warning_count": len(identity_report.get("warnings") or []) if isinstance(identity_report.get("warnings"), list) else 0,
    }


def _send_json(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    _send_session_cookie(handler)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _send_session_cookie(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header(
        "Set-Cookie",
        f"netfix_token={_API_TOKEN}; Path=/; SameSite=Strict; HttpOnly",
    )


def _send_static(handler: BaseHTTPRequestHandler, path: str) -> None:
    """Serve a static file from WEB_DIR; path '/' maps to index.html."""
    if path == "/":
        file_path = WEB_DIR / "index.html"
    else:
        safe = path.lstrip("/").replace("..", "")
        file_path = WEB_DIR / safe

    if not file_path.exists() or not file_path.is_file():
        _send_json(handler, 404, {"ok": False, "error": "not found"})
        return

    content_type = "text/html"
    if file_path.suffix == ".js":
        content_type = "application/javascript"
    elif file_path.suffix == ".css":
        content_type = "text/css"

    data = file_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    _send_session_cookie(handler)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


_CAPABILITIES_COMMANDS = [
    "codex",
    "services",
    "triage",
    "doctor",
    "layers",
    "fix",
    "rollback",
    "proxy-switch",
    "report",
    "kb",
    "watch",
    "proxy-monitor",
]

_READ_ONLY_RUN_COMMANDS = {
    "codex",
    "services",
    "triage",
    "doctor",
    "layers",
    "report",
    "kb",
}


def _known_fix_tiers() -> Dict[str, FixTier]:
    path = RULES_DIR / "symptoms.json"
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, FixTier] = {}
    for fix_id, fix in rules.get("fixes", {}).items():
        try:
            out[fix_id] = FixTier(fix.get("tier", 1))
        except ValueError:
            continue
    return out


def _strip_transport_flags(command: List[str]) -> List[str]:
    cleaned: List[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            skip_next = False
            continue
        if item == "--json":
            continue
        if item == "--timeout":
            skip_next = True
            continue
        cleaned.append(str(item))
    return cleaned


def _flag_value(command: List[str], flag: str) -> Optional[str]:
    try:
        idx = command.index(flag)
    except ValueError:
        return None
    if idx + 1 >= len(command):
        return None
    return command[idx + 1]


def _validate_fix_command(command: List[str]) -> Tuple[bool, str]:
    if "--all" in command:
        allowed = "--dry-run" in command or "--report" in command
        if allowed:
            return True, ""
        return False, "fix --all is only allowed with --dry-run or --report"

    issue = _flag_value(command, "--issue")
    if not issue:
        return False, "fix command requires --issue or --all"

    tiers = _known_fix_tiers()
    if issue not in tiers:
        return False, f"unknown fix issue: {issue}"

    if "--dry-run" in command:
        return True, ""

    tier = tiers[issue]
    if tier.value >= FixTier.CONFIRM.value:
        return False, "Tier 2 fixes must use --dry-run through the HTTP API"

    if "--yes" in command and "--report" in command:
        return True, ""

    return False, "Tier 1 fix execution requires --yes --report through the HTTP API"


def _validate_run_command(command: List[str]) -> Tuple[bool, str]:
    cleaned = _strip_transport_flags(command)
    if not cleaned:
        return False, "empty command"

    root = str(cleaned[0])
    if root in _READ_ONLY_RUN_COMMANDS:
        return True, ""

    if root == "fix":
        return _validate_fix_command(cleaned)

    if root == "rollback":
        if len(cleaned) == 1:
            return True, ""
        return False, "rollback does not accept extra arguments through /run"

    return False, f"command not allowed through /run: {root}"


def _run_fresh_codex_report(timeout: int) -> Dict[str, Any]:
    """Run a fresh user-facing report after a direct local fix."""
    return run_cli(["codex", "--json", "--timeout", str(timeout)], timeout=timeout)


def _strip_internal_secrets(value: Any) -> Any:
    """Drop internal secret carriers before returning local API payloads."""
    if isinstance(value, dict):
        return {
            key: _strip_internal_secrets(item)
            for key, item in value.items()
            if key != "_secret"
        }
    if isinstance(value, list):
        return [_strip_internal_secrets(item) for item in value]
    return value


def _friendly_diagnostic_status(status: Any) -> str:
    value = str(status or "").strip().lower()
    return {
        "ok": "正常",
        "warn": "仍有风险",
        "fail": "失败",
        "failed": "失败",
        "timeout": "超时",
    }.get(value, value or "未通过")


def _ipv6_fallback_warning_from_diagnostic(diagnostic: Dict[str, Any]) -> Dict[str, Any] | None:
    if diagnostic.get("name") != "ipv6_leak" or diagnostic.get("status") != "warn":
        return None
    details = diagnostic.get("details") if isinstance(diagnostic.get("details"), dict) else {}
    if details.get("leak_confirmed") or details.get("public_ipv6"):
        return None
    if not details.get("fallback_risk"):
        return None
    return {
        "code": "ipv6_fallback_risk",
        "message": "没有检测到公网 IPv6 泄漏，但系统仍保留 IPv6 默认路由。一般可以继续使用；如果某些 App 启动卡住，再按建议处理 IPv6。",
        "diagnostic": diagnostic.get("name"),
    }


def _friendly_diagnostic_reason(reason: Any) -> str:
    text = str(reason or "").strip()
    lower = text.lower()
    if "proxy active and ipv6 default route present" in lower and "no public ipv6 observed" in lower:
        return "没有检测到公网 IPv6 泄漏，只是系统仍保留 IPv6 默认路由。"
    if "proxy active but public ipv6 address still reachable" in lower:
        return "已经探测到公网 IPv6 仍可直连，IPv6 可能绕过代理。"
    if "public ipv6 address present and default route exists" in lower:
        return "已经探测到公网 IPv6 地址，并且系统存在 IPv6 默认路由。"
    return text


def _normalize_fix_verification_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not result.get("verification_failed"):
        return result
    diagnostic = result.get("verify_diagnostic") if isinstance(result.get("verify_diagnostic"), dict) else {}
    warning = _ipv6_fallback_warning_from_diagnostic(diagnostic)
    if not warning:
        return result

    normalized = dict(result)
    normalized["ok"] = True
    normalized["status"] = "ok"
    normalized["verified"] = True
    normalized["verification_failed"] = False
    normalized["verification_warning"] = warning
    return normalized


def _first_failed_command_reason(result: Dict[str, Any]) -> str:
    for item in result.get("executed", []) or []:
        if not isinstance(item, dict) or item.get("ok", True):
            continue
        text = str(item.get("stderr") or item.get("stdout") or item.get("reason") or "").strip()
        lower = text.lower()
        if "用户取消" in text or "user canceled" in lower or "[-128]" in lower:
            return "你取消了 macOS 管理员授权，系统网络设置没有改变。"
        if "no such file" in lower or "not found" in lower:
            return "修复脚本没有找到。请重新安装 Netfix 后再试。"
        if "permission" in lower or "not permitted" in lower or "privilege" in lower or "authorization" in lower:
            return "macOS 没有授予 Netfix 修改网络设置的权限。请重新点处理，并在系统弹窗里授权。"
        if text:
            return f"系统命令返回错误：{text[:180]}"
    return ""


def _with_user_facing_fix_error(result: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure failed fix responses never surface only status='failed' to the app."""
    if result.get("ok", True) or result.get("error"):
        return result

    if result.get("verification_failed"):
        diagnostic = result.get("verify_diagnostic") if isinstance(result.get("verify_diagnostic"), dict) else {}
        name = diagnostic.get("display_name") or diagnostic.get("name") or "复查项"
        status = _friendly_diagnostic_status(diagnostic.get("status"))
        details = diagnostic.get("details") if isinstance(diagnostic.get("details"), dict) else {}
        reason = details.get("reason") or details.get("error") or diagnostic.get("error") or ""
        card = user_facing_errors.render_error(code="fix_verification_failed")
        headline = card.get("headline", "修复命令已执行，但复查还没通过")
        next_step = card.get("next_step", "再点一次诊断；如果仍然提示同一项，按下面手动步骤继续处理。")
        message = f"{headline}（{name} {status}）。{next_step}"
        if reason:
            message += f"\n详情：{_friendly_diagnostic_reason(reason)[:180]}"
        result["error"] = message
        result["error_card"] = card
        result["reason_code"] = "fix_verification_failed"
        return result

    status = str(result.get("status") or "").lower()
    command_reason = _first_failed_command_reason(result)
    if status == "cancelled" or "取消" in command_reason:
        card = user_facing_errors.render_error(code="fix_cancelled")
        result["error"] = command_reason or card.get("headline", "你取消了这次修复，系统设置没有改变。")
        result["error_card"] = card
        result["reason_code"] = "fix_cancelled"
        return result

    if command_reason:
        card = user_facing_errors.render_error(code="fix_command_failed")
        result["error"] = f"{card.get('headline', '修复没有跑完')}：{command_reason}\n{card.get('next_step', '')}"
        result["error_card"] = card
        result["reason_code"] = "fix_command_failed"
        return result

    card = user_facing_errors.render_error(message=str(result.get("error") or ""))
    result["error"] = (
        card.get("headline", "修复没有完成，但 Netfix 内部服务没有给出明确原因。")
        + " "
        + card.get("next_step", "请点「查看日志」，把最近一次修复日志拿来排查。")
    )
    result["error_card"] = card
    result["reason_code"] = f"fix_{status}" if status else "fix_failed"
    return result


def _execute_confirmed_fix(body: Dict[str, Any]) -> Tuple[int, Any]:
    fix_id = str(body.get("fix_id") or body.get("issue") or "").strip()
    if not fix_id:
        return 400, {"ok": False, "error": "fix_id is required"}

    tiers = _known_fix_tiers()
    if fix_id not in tiers:
        return 404, {"ok": False, "error": f"unknown fix issue: {fix_id}"}

    timeout = int(body.get("timeout") or 90)
    tier = tiers[fix_id]
    requires_confirmation = tier.value >= FixTier.CONFIRM.value
    dry_run = bool(body.get("dry_run"))
    confirmed = bool(body.get("confirmed") or body.get("confirm"))
    confirmation = str(body.get("confirmation") or "")
    if requires_confirmation and not dry_run and (not confirmed or confirmation != SYSTEM_FIX_CONFIRMATION):
        return 409, {
            "ok": False,
            "error": f"confirmation must be {SYSTEM_FIX_CONFIRMATION}",
            "requires_confirmation": True,
            "confirmation": SYSTEM_FIX_CONFIRMATION,
            "fix_id": fix_id,
        }

    env = detect_environment()
    core = get_core(env)
    result = FixEngine().execute(
        fix_id,
        dry_run=dry_run,
        auto_confirm=not requires_confirmation,
        confirmed=bool(requires_confirmation and confirmed and confirmation == SYSTEM_FIX_CONFIRMATION),
        env=env,
        core=core,
    )
    if body.get("dry_run"):
        return 200, result
    result = _normalize_fix_verification_result(result)
    if not result.get("ok", True):
        return 400, _with_user_facing_fix_error(result)

    report = _run_fresh_codex_report(timeout)
    if not report.get("ok"):
        return 502, {
            "ok": False,
            "error": report.get("error") or "fix executed, but follow-up diagnosis failed",
            "fix_result": result,
            "diagnosis": report,
        }
    payload = report.get("result") or report
    if isinstance(payload, dict) and result.get("verification_warning"):
        payload = dict(payload)
        payload["fix_result"] = _strip_internal_secrets(result)
    return 200, payload


def _ensure_json_command(command: List[str], timeout: int) -> List[str]:
    """Append ``--json`` and ``--timeout`` unless already present."""
    cmd = list(command)
    if "--json" not in cmd:
        cmd.append("--json")
    if "--timeout" not in cmd:
        cmd.extend(["--timeout", str(timeout)])
    return cmd


class APIRequestHandler(BaseHTTPRequestHandler):
    """JSON-only request handler for the netfix HTTP API."""

    default_timeout: int = 60

    def log_message(self, format: str, *args: Any) -> None:  # noqa: ARG002
        # Keep the API quiet on stdout; log lines go to stderr if desired.
        pass

    def _read_body(self) -> Optional[Dict[str, Any]]:
        self._body_error = ""
        length = self.headers.get("Content-Length")
        if not length:
            self._body_error = "missing JSON body"
            return None
        try:
            size = int(length)
            if size > MAX_JSON_BODY_BYTES:
                self._body_error = f"request body too large; max {MAX_JSON_BODY_BYTES // (1024 * 1024)} MiB"
                return None
            data = self.rfile.read(size)
            return json.loads(data.decode("utf-8"))
        except Exception:
            if not self._body_error:
                self._body_error = "invalid JSON body"
            return None

    def _body_error_message(self) -> str:
        return getattr(self, "_body_error", "") or "invalid JSON body"

    def _is_safe_browser_origin(self) -> bool:
        """Reject browser cross-site POSTs to localhost control endpoints.

        Non-browser clients such as curl and MCP normally omit Origin/Referer and
        remain allowed. Browser requests with an Origin/Referer must match the
        local API host exactly.
        """
        expected_host = self.headers.get("Host", "")
        for header in ("Origin", "Referer"):
            value = self.headers.get(header)
            if not value:
                continue
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"}:
                return False
            if parsed.netloc != expected_host:
                return False
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return False
        return True

    def _has_valid_api_token(self) -> bool:
        header_token = self.headers.get("X-Netfix-Token", "")
        auth = self.headers.get("Authorization", "")
        bearer_token = auth[len("Bearer "):] if auth.startswith("Bearer ") else ""
        cookie_token = ""
        for part in self.headers.get("Cookie", "").split(";"):
            name, sep, value = part.strip().partition("=")
            if sep and name == "netfix_token":
                cookie_token = value
                break
        return header_token == _API_TOKEN or bearer_token == _API_TOKEN or cookie_token == _API_TOKEN

    def _is_public_get_path(self, path: str) -> bool:
        return path in _PUBLIC_GET_PATHS or path.startswith("/gui/web/")

    def _route_get(self, path: str) -> Optional[Tuple[int, Any]]:
        if path in ("/", "/index.html") or path.startswith("/gui/web/"):
            _send_static(self, path)
            return None

        if path == "/health":
            return 200, {"ok": True, "version": VERSION}

        if path == "/session":
            return 410, {"ok": False, "error": "session token endpoint removed; use the bootstrapped local API token"}

        if path == "/capabilities":
            return 200, {
                "commands": _CAPABILITIES_COMMANDS,
                "service_groups": services.list_groups(),
            }

        if path.startswith("/jobs/"):
            job_id = path[len("/jobs/"):]
            job = get_job(job_id)
            if job is None:
                return 404, {"ok": False, "error": "job not found"}
            return 200, job

        if path == "/report/latest":
            return _load_latest_report()

        if path == "/services/groups":
            return 200, services.load_services()

        if path == "/events":
            return 200, logs.load_events(limit=50, hours=24)

        if path == "/logs":
            return 200, logs.load_logs()

        if path == "/support/bundle":
            return 200, _support_bundle()

        if path == "/environment":
            return 200, _environment_summary()

        if path == "/user-facing/errors":
            return 200, {
                "ok": True,
                "schema_version": "netfix_user_facing_errors.v1",
                "codes": user_facing_errors.all_codes(),
            }

        if path == "/dashboard/state":
            bridge = _bridge_status_payload()
            profiles = settings.get_proxy_profiles()
            last_status: Optional[str] = None
            latest_path = JOURNAL_DIR / "last_report.json"
            if latest_path.exists():
                try:
                    import json as _json
                    last_report = _json.loads(latest_path.read_text(encoding="utf-8"))
                    diagnostics = last_report.get("diagnostics") if isinstance(last_report, dict) else None
                    if isinstance(diagnostics, list):
                        for item in diagnostics:
                            status = (item or {}).get("status") if isinstance(item, dict) else None
                            if status in {"fail", "warn", "ok"}:
                                last_status = status
                                break
                except Exception:
                    last_status = None
            return 200, {
                "ok": True,
                "schema_version": "netfix_dashboard_state.v1",
                "state": dashboard_state.resolve(
                    saved_profile_count=len(profiles),
                    bridge_status=bridge,
                    last_diagnostic_status=last_status,
                ),
                "bridge": bridge,
                "saved_profile_count": len(profiles),
            }

        if path == "/llm/providers":
            return 200, {"ok": True, "providers": _llm_providers_with_status()}

        if path == "/llm/chain-readiness":
            return 200, _llm_chain_readiness()

        if path == "/settings/llm":
            return 200, {"ok": True, "settings": settings.get_llm_settings(masked=True)}

        if path == "/settings/privacy":
            return 200, {"ok": True, "settings": settings.get_privacy_settings()}

        if path == "/settings/proxy-bridge":
            return 200, {"ok": True, "settings": settings.get_proxy_bridge_settings()}

        if path == "/proxy/profiles":
            return 200, {"ok": True, "profiles": settings.get_proxy_profiles()}

        if path == "/proxy/monitor":
            return 200, proxy_monitor_service.status()

        if path == "/proxy/bridge":
            return 200, _bridge_status_payload()

        if path == "/proxy/validation-targets":
            return 200, residential_proxy.validation_target_profiles()

        profile_id, operation = residential_proxy.split_profile_path(path)
        if profile_id and operation is None:
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    return 200, {"ok": True, "profile": profile}
            return 404, {"ok": False, "error": "profile not found"}
        if profile_id and operation == "health":
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    return 200, {"ok": True, "profile_id": profile_id, "last_check": profile.get("last_check")}
            return 404, {"ok": False, "error": "profile not found"}

        return 404, {"ok": False, "error": "not found"}

    def _route_post(self, path: str) -> Tuple[int, Any]:
        if not self._is_safe_browser_origin():
            return 403, {"ok": False, "error": "cross-origin local API request rejected"}
        if not self._has_valid_api_token():
            return 403, {"ok": False, "error": "missing or invalid local API token"}

        if path == "/run":
            body = self._read_body()
            if body is None:
                return 400, {"ok": False, "error": self._body_error_message()}

            command = body.get("command")
            if not isinstance(command, list) or not command:
                return 400, {"ok": False, "error": "body.command must be a non-empty list"}

            timeout = int(body.get("timeout", self.default_timeout))
            async_flag = bool(body.get("async", False))
            allowed, error = _validate_run_command(command)
            if not allowed:
                return 403, {"ok": False, "error": error}

            if async_flag:
                job_id = start_job(_ensure_json_command(command, timeout), timeout=timeout)
                return 202, {"ok": True, "job_id": job_id}

            # Return HTTP 200 for a successful API dispatch; the wrapped CLI result
            # carries its own ``ok`` field so callers can distinguish CLI failures.
            result = run_cli(_ensure_json_command(command, timeout), timeout=timeout)
            return 200, result

        if path == "/fixes/execute":
            body = self._read_body()
            if body is None:
                return 400, {"ok": False, "error": self._body_error_message()}
            return _execute_confirmed_fix(body)

        if path.startswith("/jobs/") and path.endswith("/cancel"):
            job_id = path[len("/jobs/"):-len("/cancel")]
            if not job_id:
                return 400, {"ok": False, "error": "missing job id"}
            job = cancel_job(job_id)
            if job is None:
                return 404, {"ok": False, "error": "job not found"}
            return 200, {**job, "ok": True}

        body = self._read_body()
        if body is None:
            return 400, {"ok": False, "error": self._body_error_message()}

        if path == "/settings/llm":
            payload = dict(body)
            api_key = str(payload.pop("api_key", "") or "")
            provider = str(payload.get("provider") or "custom_openai_compatible")
            account = str(payload.get("api_key_account") or provider)
            payload["api_key_account"] = account
            if api_key:
                stored = keychain.set_secret(keychain.LLM_SERVICE, account, api_key)
                if not stored.get("ok"):
                    return 400, {"ok": False, "error": stored.get("error", "failed to store API key")}
                payload["api_key_account"] = account
                payload["api_key_set"] = True
            saved = settings.update_llm_settings(payload)
            return 200, {"ok": True, "settings": saved}

        if path == "/settings/privacy":
            saved = settings.update_privacy_settings(body)
            prune = logs.apply_retention_policy()
            return 200, {"ok": True, "settings": saved, "retention": prune}

        if path == "/settings/proxy-bridge":
            saved = settings.update_proxy_bridge_settings(body)
            return 200, {"ok": True, "settings": saved}

        if path == "/logs/prune":
            days = int(body.get("retention_days") or settings.get_privacy_settings().get("log_retention_days") or 7)
            return 200, logs.prune_events(days)

        if path == "/logs/clear":
            result = logs.clear_logs(
                clear_latest_report=bool(body.get("latest_report", True)),
                clear_events=bool(body.get("events", True)),
            )
            return (200 if result.get("ok") else 500), result

        if path == "/data/clear":
            if body.get("confirm") != "DELETE_NETFIX_LOCAL_DATA":
                return 400, {"ok": False, "error": "confirm must be DELETE_NETFIX_LOCAL_DATA"}
            snapshot = settings.load_settings()
            result = {
                "ok": True,
                "logs": logs.clear_logs(clear_latest_report=True, clear_events=True),
                "settings": settings.clear_settings(),
                "llm_budget": llm_budget.clear_persistent_ledger(),
                "keychain": keychain.delete_known_netfix_secrets(snapshot) if bool(body.get("keychain", True)) else {"ok": True, "deleted": [], "missing": [], "errors": {}},
            }
            result["ok"] = all(part.get("ok") for part in result.values() if isinstance(part, dict))
            return (200 if result["ok"] else 500), result

        if path == "/llm/test":
            llm_settings = settings.load_settings().get("llm", {})
            if body.get("confirmation") != LLM_PROVIDER_TEST_CONFIRMATION:
                return 200, {
                    "ok": False,
                    "error": f"confirmation must be {LLM_PROVIDER_TEST_CONFIRMATION}",
                    "requires_confirmation": True,
                    "confirmation": LLM_PROVIDER_TEST_CONFIRMATION,
                }
            if not bool(llm_settings.get("enabled")):
                return 400, {"ok": False, "error": "cloud AI explanation is disabled", "reason_code": "llm_disabled"}
            account = str(llm_settings.get("api_key_account") or llm_settings.get("provider") or "default")
            api_key = keychain.get_secret(keychain.LLM_SERVICE, account, allow_generic_llm_override=True)
            if not api_key:
                return 400, {"ok": False, "error": "missing API key"}
            provider = llm_provider.OpenAICompatibleProvider(
                base_url=str(llm_settings.get("base_url") or ""),
                api_key=api_key,
                model=str(llm_settings.get("model") or ""),
                timeout_s=int(llm_settings.get("timeout_s") or 20),
                provider_id=str(llm_settings.get("provider") or "custom_openai_compatible"),
            )
            try:
                result = provider.complete_json(
                    _llm_chain_test_messages(str(llm_settings.get("provider") or "custom_openai_compatible"), "explain"),
                    max_tokens=256,
                    temperature=0.0,
                )
            except llm_provider.LLMProviderError as exc:
                return 502, {"ok": False, "error": str(exc), "reason_code": exc.reason_code, "http_status": exc.http_status}
            return 200, {"ok": True, "result": result, "provider_used": str(llm_settings.get("provider") or "custom_openai_compatible")}

        if path == "/llm/chain-test":
            result = _llm_chain_test(body)
            return (
                200
                if result.get("ok")
                or result.get("requires_confirmation")
                or (
                    result.get("schema_version") == "netfix_llm_chain_test.v1"
                    and result.get("reason_code") != "invalid_mode"
                )
                else 400
            ), result

        if path == "/llm/import-deepseek-sidecar-key":
            if body.get("confirmation") != deepseek_sidecar.CONFIRMATION:
                return 200, {
                    "ok": False,
                    "error": f"confirmation must be {deepseek_sidecar.CONFIRMATION}",
                    "requires_confirmation": True,
                    "confirmation": deepseek_sidecar.CONFIRMATION,
                }
            result = deepseek_sidecar.import_sidecar_key(
                account=str(body.get("api_key_account") or "deepseek"),
                enable_llm=bool(body.get("enable_llm", True)),
            )
            return (200 if result.get("ok") else 400), result

        if path == "/explain_llm":
            status, loaded = _load_latest_report()
            if status != 200:
                return status, loaded
            report = loaded
            result = llm_explain.explain_with_llm(
                report=report,
                question=str(body.get("question") or ""),
                mode=str(body.get("mode") or "explain"),
                redaction_level=str(body.get("redaction_level") or "balanced"),
                upload_confirmed=bool(body.get("upload_confirmed") or body.get("upload_consent_confirmed")),
                allow_fallback=body.get("allow_fallback") if isinstance(body.get("allow_fallback"), bool) else None,
                image_inputs=body.get("images") if isinstance(body.get("images"), list) else None,
            )
            return 200, {"ok": True, "result": result}

        if path == "/proxy/parse":
            parsed = residential_proxy.parse_proxy_input(body)
            parsed.pop("_secret", None)
            return (200 if parsed.get("ok") else 400), parsed

        if path == "/proxy/import-preview":
            preview = residential_proxy.parse_proxy_bundle(body)
            return (200 if preview.get("ok") else 400), preview

        if path == "/proxy/validate":
            parsed = residential_proxy.parse_proxy_input(body)
            if not parsed.get("ok"):
                parsed.pop("_secret", None)
                return 400, parsed
            secret = parsed.pop("_secret", {})
            identity_target_urls = body.get("identity_target_urls")
            if not isinstance(identity_target_urls, list):
                identity_target_urls = None
            result = residential_proxy.validate_proxy_profile(
                parsed["profile"],
                target_url=str(body.get("target_url") or "https://www.gstatic.com/generate_204"),
                timeout=max(1, min(int(body.get("timeout", 10)), 60)),
                password=str(secret.get("password") or ""),
                include_identity=bool(body.get("include_identity")),
                target_profile=str(body.get("target_profile") or "baseline"),
                identity_target_urls=[str(item) for item in identity_target_urls] if identity_target_urls else None,
            )
            result["profile"] = parsed["profile"]
            return (200 if result.get("ok") else 400), result

        if path == "/proxy/profiles":
            result = residential_proxy.save_proxy_profile(body)
            if result.get("ok") and bool(body.get("start_monitor") or body.get("auto_start_monitor")):
                profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
                profile_id = str(profile.get("id") or "")
                if profile_id:
                    monitor = proxy_monitor_service.start(
                        profile_id=profile_id,
                        interval=max(5, min(int(body.get("monitor_interval") or body.get("interval") or 60), 24 * 60 * 60)),
                        target_url=str(body.get("target_url") or "https://www.gstatic.com/generate_204"),
                        target_profile=str(body.get("target_profile") or "baseline"),
                        timeout=max(1, min(int(body.get("timeout", 10)), 60)),
                    )
                    result["monitor"] = monitor
                    if not monitor.get("ok"):
                        if not isinstance(result.get("warnings"), list):
                            result["warnings"] = []
                        result["warnings"].append("profile_saved_but_monitor_start_failed")
                else:
                    result["monitor"] = {"ok": False, "error": "profile_id_missing"}
                    if not isinstance(result.get("warnings"), list):
                        result["warnings"] = []
                    result["warnings"].append("profile_saved_but_monitor_start_failed")
            result = _strip_internal_secrets(result)
            return (200 if result.get("ok") else 400), result

        if path == "/proxy/monitor/start":
            profile_id = str(body.get("profile_id") or body.get("profile") or "")
            if not profile_id:
                return 400, {"ok": False, "error": "profile_id is required"}
            result = proxy_monitor_service.start(
                profile_id=profile_id,
                interval=int(body.get("interval") or 60),
                target_url=str(body.get("target_url") or "https://www.gstatic.com/generate_204"),
                target_profile=str(body.get("target_profile") or "baseline"),
                timeout=max(1, min(int(body.get("timeout", 10)), 60)),
            )
            return (200 if result.get("ok") else 404), result

        if path == "/proxy/monitor/stop":
            return 200, proxy_monitor_service.stop()

        if path == "/proxy/bridge/recover":
            result = residential_proxy.recover_stale_bridge(
                confirmed=bool(body.get("confirmed") or body.get("confirm")),
                confirmation=str(body.get("confirmation") or ""),
            )
            if result.get("ok"):
                return 200, result
            return (404 if result.get("status") == "no_journal" else 400), result

        profile_id, operation = residential_proxy.split_profile_path(path)
        if profile_id and operation == "replace":
            monitor_state = proxy_monitor_service.status().get("monitor", {})
            result = residential_proxy.replace_proxy_profile(profile_id, body)
            if not result.get("ok"):
                return (404 if result.get("error") == "profile not found" else 400), result
            should_start_monitor = bool(body.get("start_monitor") or body.get("auto_start_monitor"))
            monitor_matches = str(monitor_state.get("profile_id") or "") == profile_id
            if should_start_monitor or (monitor_state.get("running") and monitor_matches):
                interval = body.get("monitor_interval") or body.get("interval") or monitor_state.get("interval") or 60
                target_url = str(body.get("target_url") or monitor_state.get("target_url") or "https://www.gstatic.com/generate_204")
                target_profile = str(body.get("target_profile") or monitor_state.get("target_profile") or "baseline")
                timeout = body.get("timeout") or monitor_state.get("timeout") or 10
                monitor = proxy_monitor_service.start(
                    profile_id=profile_id,
                    interval=max(5, min(int(interval), 24 * 60 * 60)),
                    target_url=target_url,
                    target_profile=target_profile,
                    timeout=max(1, min(int(timeout), 60)),
                )
                result["monitor"] = monitor
                if not monitor.get("ok"):
                    if not isinstance(result.get("warnings"), list):
                        result["warnings"] = []
                    result["warnings"].append("profile_replaced_but_monitor_start_failed")
            return 200, result

        if profile_id and operation == "delete":
            monitor_state = proxy_monitor_service.status().get("monitor", {})
            result = residential_proxy.delete_proxy_profile(profile_id)
            if not result.get("ok"):
                return 404, result
            monitor_stopped = False
            monitor_persisted_cleared = False
            persisted = monitor_state.get("persisted") if isinstance(monitor_state.get("persisted"), dict) else {}
            running_matches = monitor_state.get("running") and str(monitor_state.get("profile_id") or "") == profile_id
            persisted_matches = persisted.get("enabled") and str(persisted.get("profile_id") or "") == profile_id
            if running_matches or persisted_matches:
                proxy_monitor_service.stop()
                monitor_stopped = bool(running_matches)
                monitor_persisted_cleared = bool(persisted_matches)
            result["monitor_stopped"] = monitor_stopped
            result["monitor_persisted_cleared"] = monitor_persisted_cleared
            return 200, result

        if profile_id and operation == "health":
            selected = None
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    selected = profile
                    break
            if selected is None:
                return 404, {"ok": False, "error": "profile not found"}
            return 200, {"ok": True, "profile_id": profile_id, "last_check": selected.get("last_check")}

        if profile_id and operation == "validate":
            selected = None
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    selected = profile
                    break
            if selected is None:
                return 404, {"ok": False, "error": "profile not found"}
            identity_target_urls = body.get("identity_target_urls")
            if not isinstance(identity_target_urls, list):
                identity_target_urls = None
            result = residential_proxy.validate_saved_profile(
                selected,
                target_url=str(body.get("target_url") or "https://www.gstatic.com/generate_204"),
                timeout=max(1, min(int(body.get("timeout", 10)), 60)),
                include_identity=bool(body.get("include_identity")),
                target_profile=str(body.get("target_profile") or "baseline"),
                identity_target_urls=[str(item) for item in identity_target_urls] if identity_target_urls else None,
            )
            updated = dict(selected)
            updated["last_check"] = result.get("proxy_check")
            identity_report = result.get("identity_report")
            if isinstance(identity_report, dict):
                privacy = settings.get_privacy_settings()
                if privacy.get("persist_proxy_identity_report"):
                    updated["last_identity_report"] = identity_report
                    updated.pop("last_identity_summary", None)
                else:
                    updated.pop("last_identity_report", None)
                    updated["last_identity_summary"] = _proxy_identity_persistence_summary(identity_report)
            settings.upsert_proxy_profile(updated)
            result["profile"] = updated
            return (200 if result.get("ok") else 400), result

        if profile_id and operation == "apply-dry-run":
            selected = None
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    selected = profile
                    break
            if selected is None:
                return 404, {"ok": False, "error": "profile not found"}
            result = residential_proxy.apply_dry_run(selected, mode=str(body.get("mode") or "system"))
            return (200 if result.get("ok") else 400), result

        if profile_id and operation == "apply":
            selected = None
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    selected = profile
                    break
            if selected is None:
                return 404, {"ok": False, "error": "profile not found"}
            result = residential_proxy.apply_proxy_profile(
                selected,
                mode=str(body.get("mode") or "system"),
                confirmed=bool(body.get("confirmed") or body.get("confirm")),
                confirmation=str(body.get("confirmation") or ""),
                network_service=str(body.get("network_service") or ""),
                target_url=str(body.get("target_url") or "https://www.gstatic.com/generate_204"),
                timeout=max(1, min(int(body.get("timeout", 10)), 60)),
                verify=bool(body.get("verify", True)),
                rollback_on_verify_failure=bool(body.get("rollback_on_verify_failure", True)),
                target_profile=str(body.get("target_profile") or "baseline"),
            )
            if result.get("ok"):
                return 200, result
            if result.get("status") == "blocked":
                return 409, result
            return 400, result

        if profile_id and operation == "export":
            selected = None
            for profile in settings.get_proxy_profiles():
                if profile.get("id") == profile_id:
                    selected = profile
                    break
            if selected is None:
                return 404, {"ok": False, "error": "profile not found"}
            result = residential_proxy.export_client_profile(selected, fmt=str(body.get("format") or "all"))
            return (200 if result.get("ok") else 400), result

        if path == "/proxy/profiles/rollback":
            result = residential_proxy.rollback_last_proxy_apply(
                confirmed=bool(body.get("confirmed") or body.get("confirm")),
                confirmation=str(body.get("confirmation") or ""),
            )
            if result.get("ok"):
                return 200, result
            return (404 if result.get("status") == "no_journal" else 400), result

        if path != "/run":
            return 404, {"ok": False, "error": "not found"}

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if not self._is_public_get_path(path) and not self._has_valid_api_token():
                _send_json(self, 403, {"ok": False, "error": "missing or invalid local API token"})
                return
            routed = self._route_get(path)
            if routed is None:
                return
            status, body = routed
            _send_json(self, status, body)
        except Exception as exc:
            _send_json(self, 500, {"ok": False, "error": f"internal error: {exc}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            status, body = self._route_post(path)
            _send_json(self, status, body)
        except Exception as exc:
            _send_json(self, 500, {"ok": False, "error": f"internal error: {exc}"})


def create_server(host: str = "127.0.0.1", port: int = 0, timeout: int = 60) -> ThreadingHTTPServer:
    """Create a bound HTTP server; port 0 requests an ephemeral port."""
    APIRequestHandler.default_timeout = timeout
    return ThreadingHTTPServer((host, port), APIRequestHandler)


def run_server(host: str = "127.0.0.1", port: int = 0, timeout: int = 60) -> None:
    """Start the API server in a background thread and block until interrupted."""
    server = create_server(host, port, timeout)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stop_requested = threading.Event()
    old_sigterm = signal.getsignal(signal.SIGTERM)

    def _request_stop(_signum: int, _frame: Any) -> None:
        stop_requested.set()

    try:
        signal.signal(signal.SIGTERM, _request_stop)
    except ValueError:
        old_sigterm = None

    addr = server.server_address
    token_file = _write_api_token_file()
    print(f"netfix API listening on http://{addr[0]}:{addr[1]} token_file={token_file}", flush=True)
    proxy_monitor_service.restore_from_settings()
    _record_startup_bridge_check()

    try:
        while thread.is_alive() and not stop_requested.is_set():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if old_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, old_sigterm)
            except ValueError:
                pass
        try:
            server.shutdown()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            _remove_api_token_file()
            proxy_monitor_service.stop(persist=False)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    try:
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    except ValueError:
        port = 0
    try:
        timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    except ValueError:
        timeout = 60
    run_server(host=host, port=port, timeout=timeout)
