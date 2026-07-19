"""netfix AI network assistant layer with local safety gates."""
from __future__ import annotations

import copy
import base64
import json
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from netfix import explain, keychain, llm_budget
from netfix.llm_provider import LLMProviderError, OpenAICompatibleProvider, get_provider, provider_candidates
from netfix.redaction import redact_report, redact_text
from netfix.settings import load_settings


VALID_SEVERITIES = {"ok", "warn", "fail"}
MAX_IMAGE_INPUTS = 3
MAX_IMAGE_DATA_URL_CHARS = 6_250_000
MAX_QUESTION_CHARS = 2_000
MAX_HISTORY_MESSAGES = 20
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}

# confirmation_request 通用机制：把原来只针对"上传脱敏报告"的 needs_upload_confirmation
# 升级为覆盖所有破坏性 / 隐私类操作的统一气泡。SwiftUI 端 AIChatView 用同一个渲染管线。
CONFIRMATION_CATEGORIES = {
    "upload_redacted_report": {
        "summary": "需要把脱敏后的诊断报告发给 AI 供应商",
        "impact": "读取脱敏报告；代理密码 / 订阅链接 / Keychain 内容不会发送",
        "magic_word": "UPLOAD_REDACTED_REPORT",
    },
    "upload_image": {
        "summary": "需要把脱敏后的截图发给 AI 视觉模型",
        "impact": "图中可见文字会原样发送；文件元数据已被剥离",
        "magic_word": "UPLOAD_IMAGE",
    },
    "change_system_setting": {
        "summary": "需要修改系统网络设置",
        "impact": "会调用 networksetup / scutil；可能短暂影响网络",
        "magic_word": "APPLY_SYSTEM_FIX",
    },
    "switch_proxy_node": {
        "summary": "需要切换到另一个代理节点",
        "impact": "会更新代理客户端配置并重启代理内核",
        "magic_word": "APPLY_PROXY_PROFILE",
    },
    "disable_ipv6": {
        "summary": "需要临时禁用 IPv6",
        "impact": "所有 IPv6 流量会暂时失效，恢复后自动开启",
        "magic_word": "APPLY_SYSTEM_FIX",
    },
    "flush_dns": {
        "summary": "需要刷新 DNS 缓存",
        "impact": "只清缓存，不改系统配置",
        "magic_word": "FLUSH_DNS_CACHE",
    },
    "renew_dhcp": {
        "summary": "需要续租 DHCP",
        "impact": "会丢弃当前 IP 地址并重新获取",
        "magic_word": "APPLY_SYSTEM_FIX",
    },
    "reset_system_proxy": {
        "summary": "需要重置系统代理",
        "impact": "当前系统代理设置会被备份并替换",
        "magic_word": "APPLY_SYSTEM_FIX",
    },
}


def build_confirmation_request(
    category: str,
    *,
    reason_code: str = "",
    preview: Optional[Dict[str, Any]] = None,
    expires_in_seconds: int = 300,
) -> Dict[str, Any]:
    """Build a generic confirmation_request dict for the SwiftUI bubble.

    The frontend matches on `category` to decide which copy / icon / confirmation
    magic phrase to render. `magic_word` is the legacy field name retained so the
    existing Tier 2 confirmation flow stays compatible (see `tests/test_docs_contract.py`).
    """
    spec = CONFIRMATION_CATEGORIES.get(category) or {
        "summary": "需要执行一个破坏性操作",
        "impact": "请确认后果",
        "magic_word": "APPLY_SYSTEM_FIX",
    }
    return {
        "request_id": f"confirm-{int(time.time() * 1000)}",
        "category": category,
        "summary": spec["summary"],
        "impact": spec["impact"],
        "reason_code": reason_code or category,
        "preview": preview or {},
        "magic_word": spec["magic_word"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)).isoformat(),
    }


def merge_confirmation_request(payload: Dict[str, Any], request: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach a confirmation_request to a fallback payload and clear the legacy field."""
    if not request:
        payload["confirmation_request"] = None
        return payload
    payload["confirmation_request"] = request
    # 兼容旧字段：当前端仍未升级时仍能看到 needs_upload_confirmation 提示
    if request.get("category") in {"upload_redacted_report", "upload_image"}:
        payload["needs_upload_confirmation"] = True
    return payload


FALLBACK_REASON_LABELS = {
    "llm_disabled": "云端 AI 解释未启用，当前使用本地规则解释。",
    "upload_consent_never": "当前设置为永不上传，已使用本地规则解释。",
    "upload_consent_required": "需要先确认本次上传脱敏报告或图片，未确认时不会调用云端模型。",
    "image_question_disabled": "请先在设置里启用图片问诊实验入口，再发送图片给 MiniMax/Kimi/Qwen 等视觉模型。",
    "image_input_missing": "没有收到可用图片；请重新选择 PNG、JPEG、WebP 或 GIF 图片后再试。",
    "image_unsupported_format": "图片问诊只支持 PNG、JPEG、WebP 或 GIF；请先转换图片格式后再发送。",
    "provider_vision_unsupported": "当前供应商不支持图片问诊；请配置 MiniMax、Kimi 或 Qwen API Key，或开启国内备用链路。",
    "missing_api_key": "没有可用 API Key；请先配置 DeepSeek、Kimi、MiniMax 或 Qwen 的 Keychain API Key。",
    "local_budget_exceeded": "已达到本地云端 AI 请求预算，当前使用本地规则解释。可稍后重试或调高预算。",
    "local_image_budget_exceeded": "已达到本地图片问诊预算，当前使用本地规则解释。可稍后重试或调高预算。",
    "provider_cooldown": "供应商刚刚触发限流或额度错误，Netfix 正在本地冷却该供应商以避免继续计费或失败。",
    "rate_limited": "供应商返回限流；请稍后重试，或使用已配置的备用国内模型。",
    "quota_or_billing": "供应商额度或计费不可用；请检查余额、套餐或 API Key 权限。",
    "auth_failed": "供应商认证失败；请检查 API Key 是否正确。",
    "model_not_found": "供应商找不到当前模型；请检查模型名或切换到预设模型。",
    "timeout": "供应商响应超时；当前使用本地规则解释。",
    "network_error": "无法连接供应商；当前使用本地规则解释。",
}


def _fallback_reason_label(reason: str) -> str:
    code = str(reason or "")
    if code.startswith("provider_error:"):
        code = code.split(":", 1)[1].strip()
    return FALLBACK_REASON_LABELS.get(code, f"云端 AI 暂不可用（{reason}），当前使用本地规则解释。")


def reset_llm_budget_state() -> None:
    llm_budget.reset_state()


def _usage_summary(usage: Any) -> Optional[Dict[str, int]]:
    if not isinstance(usage, dict):
        return None
    summary: Dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        try:
            summary[key] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return summary or None


def _fallback(
    report: Dict[str, Any],
    reason: str,
    redacted: Dict[str, Any],
    *,
    fallback_chain: Optional[List[Dict[str, Any]]] = None,
    needs_upload_confirmation: bool = False,
    confirmation_request: Optional[Dict[str, Any]] = None,
    plan_steps: Optional[List[Dict[str, Any]]] = None,
    observations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if report:
        local = explain.explain_report(report)
        headline = local.get("headline", "本地规则解释")
        severity = local.get("severity", "warn")
        explanation = local.get("explanation", "")
        evidence = local.get("evidence", [])
        actions = local.get("actions", [])
        manual_steps = local.get("manual_steps", [])
    else:
        # 无诊断报告时降级为通用网络问答卡片，引导用户先跑诊断。
        headline = "还没运行诊断，先按通用网络问答来聊"
        severity = "ok"
        explanation = (
            "你还没有运行网络诊断，我先按通用网络知识回答。想拿到针对这台 Mac 的准确结论，"
            "请先运行 python3 netfix.py triage（或点击 App 里的检查），再把报告发给我。"
        )
        evidence = []
        actions = []
        manual_steps = []
    return {
        "schema_version": "llm_explanation.v1",
        "source": "fallback",
        "fallback_reason": reason,
        "fallback_reason_label": _fallback_reason_label(reason),
        "failure_reason_code": reason,
        "provider_used": None,
        "fallback_chain": fallback_chain or [],
        "needs_upload_confirmation": needs_upload_confirmation,
        "confirmation_request": confirmation_request,
        "headline": headline,
        "severity": severity,
        "explanation": explanation,
        "evidence": evidence,
        "actions": actions,
        "manual_steps": manual_steps,
        "plan_steps": plan_steps or [],
        "observations": observations or [],
        "redaction_audit": redacted.get("redaction_audit", {}),
        "redacted_report_hash": redacted.get("redacted_report_hash"),
    }


def _plan_steps_from_intake(intake_hint: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert a symptom_intake result into a default plan_steps trail.

    Each plan step has the shape:
        {"tool": "<mcp_tool_name>", "label": "<人话>", "why": "<reason>", "status": "pending"}
    The status stays "pending" until the SwiftUI client runs the matching tool
    and feeds back the observation.
    """
    if not isinstance(intake_hint, dict):
        return []
    steps: List[Dict[str, Any]] = []
    for tool in intake_hint.get("suggested_tools") or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("tool") or "").strip()
        if not name:
            continue
        steps.append({
            "tool": name,
            "label": _tool_step_label(name),
            "why": str(tool.get("why") or ""),
            "status": "pending",
        })
    if not steps and intake_hint.get("matched_symptoms"):
        # 没有工具建议但有命中症状：放一个最低成本的「跑一次诊断」作为兜底。
        steps.append({
            "tool": "netfix_triage",
            "label": "跑一次五层诊断",
            "why": "已识别到症状关键词，先跑一次诊断收集证据",
            "status": "pending",
        })
    return steps


def _observations_from_intake(intake_hint: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert a symptom_intake result into an observation trail for SwiftUI."""
    if not isinstance(intake_hint, dict):
        return []
    observations: List[Dict[str, Any]] = []
    matched = intake_hint.get("matched_symptoms") or []
    if matched and isinstance(matched[0], dict):
        first = matched[0]
        observations.append({
            "fact": f"症状关键词命中：{first.get('name') or first.get('id') or ''}",
            "confidence": float(first.get("confidence") or 0.0),
            "source": "symptom_intake",
        })
    if intake_hint.get("note"):
        observations.append({
            "fact": str(intake_hint.get("note")),
            "confidence": 0.0,
            "source": "symptom_intake",
        })
    return observations


def _tool_step_label(tool_name: str) -> str:
    """Return a 短人话 label for a tool name so the SwiftUI plan card stays readable."""
    mapping = {
        "netfix_codex": "跑 Codex / OpenAI 健康检查",
        "netfix_services": "探测常用海外服务",
        "netfix_triage": "跑五层诊断",
        "netfix_doctor": "跑完整诊断",
        "netfix_get_global_state": "查看主网络路径",
        "netfix_get_dns_state": "查看 DNS 状态",
        "netfix_get_proxy_state": "查看系统代理",
        "netfix_get_listeners": "查看本地监听端口",
        "netfix_get_ip_reputation": "查出口 IP 信誉",
        "netfix_check_proxy_auth": "检测代理认证状态",
        "netfix_test_proxy_for_url": "走代理测试目标",
        "netfix_test_direct_for_url": "直连测试目标",
        "netfix_dns_resolve": "解析目标域名",
        "netfix_trace_path": "跟踪网络路径",
        "netfix_proxy_switch": "切换代理节点",
    }
    return mapping.get(tool_name, tool_name.replace("_", " ").replace("netfix ", ""))


def _allowed_action_map(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    actions: Dict[str, Dict[str, Any]] = {}
    for fix in report.get("fixes", []):
        if isinstance(fix, dict) and fix.get("id"):
            action_id = str(fix["id"])
            tier = int(fix.get("tier") or 3)
            actions[action_id] = {
                "id": action_id,
                "label": str(fix.get("label") or fix.get("name") or action_id),
                "tier": tier,
                "needs_confirm": bool(fix.get("needs_confirm", tier >= 2)),
            }
    for action in report.get("explanation", {}).get("actions", []):
        if isinstance(action, dict) and action.get("id"):
            action_id = str(action["id"])
            tier = int(actions.get(action_id, {}).get("tier") or action.get("tier") or 3)
            actions[action_id] = {
                "id": action_id,
                "label": str(action.get("label") or actions.get(action_id, {}).get("label") or action_id),
                "tier": tier,
                "needs_confirm": bool(action.get("needs_confirm", actions.get(action_id, {}).get("needs_confirm", tier >= 2))),
            }
    return actions


def _allowed_action_ids(report: Dict[str, Any]) -> Set[str]:
    return set(_allowed_action_map(report))


def sanitize_llm_response(raw: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and downscope LLM output before rendering it."""
    data = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    data["schema_version"] = "llm_explanation.v1"
    data["source"] = "llm"
    if data.get("severity") not in VALID_SEVERITIES:
        data["severity"] = "warn"
    for field in ("headline", "explanation"):
        if not isinstance(data.get(field), str):
            data[field] = ""

    allowed = _allowed_action_map(report)
    safe_actions: List[Dict[str, Any]] = []
    for action in data.get("actions", []):
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id") or "")
        if action_id not in allowed:
            continue
        local = allowed[action_id]
        safe = {
            "id": action_id,
            "label": str(local.get("label") or action.get("label") or action_id),
            "tier": int(local.get("tier") or 3),
            "needs_confirm": bool(local.get("needs_confirm", True)),
            "reason": str(action.get("reason") or ""),
        }
        safe_actions.append(safe)
    data["actions"] = safe_actions

    evidence = data.get("evidence")
    data["evidence"] = evidence if isinstance(evidence, list) else []
    manual = data.get("manual_steps")
    data["manual_steps"] = manual if isinstance(manual, list) else []
    data.pop("command", None)
    data.pop("commands", None)

    # P0-A.3: 自动给首个 tier≥2 修复动作挂上 confirmation_request，UI 端能用同一个气泡组件
    # 渲染上传确认 / 修改系统设置 / 切换节点等所有破坏性操作。
    data["confirmation_request"] = _first_tier2_confirmation_request(safe_actions)
    data["needs_upload_confirmation"] = bool(data.get("confirmation_request"))

    redacted_output = redact_report({"llm_response": data}, level="balanced").get("redacted_report", {})
    safe_output = redacted_output.get("llm_response")
    if isinstance(safe_output, dict):
        data = safe_output
    return data


_ACTION_TO_CONFIRMATION_CATEGORY = {
    "flush-dns-cache": "flush_dns",
    "renew-dhcp": "renew_dhcp",
    "disable-ipv6": "disable_ipv6",
    "reset-system-proxy": "reset_system_proxy",
    "disable-auto-proxy": "change_system_setting",
    "check-proxy-core": "change_system_setting",
}


def _first_tier2_confirmation_request(safe_actions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a confirmation_request for the first tier>=2 action, or None.

    swiftui renders the same bubble for upload / switch_proxy_node / change_system_setting;
    magic_word stays compatible with existing Tier 2 confirmation tokens.
    """
    for action in safe_actions:
        tier = int(action.get("tier") or 3)
        if tier < 2:
            continue
        action_id = str(action.get("id") or "")
        category = _ACTION_TO_CONFIRMATION_CATEGORY.get(action_id, "change_system_setting")
        return build_confirmation_request(
            category,
            reason_code=f"action_{action_id}",
            preview={"action_id": action_id, "label": action.get("label") or action_id},
        )
    return None


def _provider_settings(base_settings: Dict[str, Any], provider_id: str, mode: str = "explain") -> Dict[str, Any]:
    preset = get_provider(provider_id) or {}
    if provider_id == base_settings.get("provider"):
        data = dict(base_settings)
    else:
        data = {
            "provider": provider_id,
            "base_url": preset.get("base_url", ""),
            "model": preset.get("model", ""),
            "api_key_account": provider_id,
            "timeout_s": base_settings.get("timeout_s", 20),
            "max_tokens": preset.get("default_max_tokens") or base_settings.get("max_tokens", 900),
            "temperature": preset.get("default_temperature") if preset.get("default_temperature") is not None else base_settings.get("temperature", 0.2),
        }
    if not data.get("base_url"):
        data["base_url"] = preset.get("base_url", "")
    if not data.get("model"):
        data["model"] = preset.get("model", "")
    if mode == "image_question" and preset.get("vision_model"):
        data["model"] = preset.get("vision_model", data.get("model", ""))
    data["api_key_account"] = str(data.get("api_key_account") or provider_id)
    return data


def _ordered_provider_ids(active_provider: str, llm_settings: Dict[str, Any], mode: str) -> List[str]:
    fallback_settings = llm_settings.get("fallback")
    if not isinstance(fallback_settings, dict):
        fallback_settings = {}
    candidates = provider_candidates(
        mode=mode,
        domestic_only=bool(fallback_settings.get("domestic_only", True)),
        include_custom=bool(fallback_settings.get("include_custom", False)),
        include_global=bool(fallback_settings.get("include_global", False)),
    )
    candidate_ids = [str(item["id"]) for item in candidates]
    chain_key = "vision_chain" if mode == "image_question" else "chain"
    configured_chain = fallback_settings.get(chain_key)
    if isinstance(configured_chain, list) and configured_chain:
        ordered = [str(item) for item in configured_chain if str(item) in candidate_ids]
        ordered.extend([item for item in candidate_ids if item not in ordered])
    else:
        ordered = candidate_ids
    if active_provider in ordered:
        ordered.remove(active_provider)
        return [active_provider] + ordered
    if mode == "image_question":
        return ordered
    return [active_provider] + ordered


def _image_data_url(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("data_url") or item.get("url") or "")
    return ""


def _image_mime_type(data_url: str) -> str:
    if not data_url[:32].lower().startswith("data:image/"):
        return ""
    header = data_url.split(",", 1)[0].lower()
    mime = header[5:].split(";", 1)[0]
    return "image/jpeg" if mime == "image/jpg" else mime


def _sniff_image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return ""


def _parse_base64_image_data_url(url: str) -> Optional[tuple[str, bytes]]:
    if "," not in url:
        return None
    header, encoded = url.split(",", 1)
    header_lower = header.lower()
    if not header_lower.startswith("data:image/"):
        return None
    declared_mime = _image_mime_type(url)
    if declared_mime not in ALLOWED_IMAGE_MIME_TYPES:
        return None
    params = [part.strip() for part in header_lower.split(";")[1:]]
    if "base64" not in params:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        return None
    actual_mime = _sniff_image_mime(raw)
    if actual_mime != declared_mime:
        return None
    return actual_mime, raw


def _strip_png_metadata(data: bytes) -> Optional[tuple[bytes, int]]:
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        return None
    offset = len(signature)
    chunks: List[bytes] = []
    stripped = 0
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            return None
        chunk = data[offset:end]
        kind = data[offset + 4 : offset + 8]
        # PNG critical chunks have an uppercase first byte. Ancillary chunks
        # carry metadata such as tEXt/iTXt/zTXt/eXIf and are stripped.
        if 65 <= kind[0] <= 90:
            chunks.append(chunk)
        else:
            stripped += 1
        offset = end
        if kind == b"IEND":
            saw_iend = True
            break
    if not saw_iend:
        return None
    if offset < len(data):
        stripped += 1
    if not stripped:
        return data, 0
    return signature + b"".join(chunks), stripped


def _strip_jpeg_metadata(data: bytes) -> Optional[tuple[bytes, int]]:
    if not data.startswith(b"\xff\xd8"):
        return None
    out = bytearray(data[:2])
    offset = 2
    stripped = 0
    while offset < len(data):
        if data[offset] != 0xFF:
            return None
        marker = data[offset + 1] if offset + 1 < len(data) else 0
        if marker in {0xD9, 0xDA}:  # EOI or scan data begins
            out.extend(data[offset:])
            break
        if offset + 4 > len(data):
            return None
        length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        if length < 2:
            return None
        end = offset + 2 + length
        if end > len(data):
            return None
        segment = data[offset:end]
        if 0xE1 <= marker <= 0xEF or marker == 0xFE:
            stripped += 1
        else:
            out.extend(segment)
        offset = end
    return (bytes(out), stripped) if stripped else (data, 0)


def _strip_webp_metadata(data: bytes) -> Optional[tuple[bytes, int]]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    riff_size = struct.unpack("<I", data[4:8])[0]
    container_end = 8 + riff_size
    if container_end > len(data) or container_end < 12:
        return None
    offset = 12
    chunks: List[bytes] = []
    stripped = 0
    metadata_chunks = {b"EXIF", b"XMP ", b"ICCP"}
    while offset < container_end:
        if offset + 8 > container_end:
            return None
        kind = data[offset : offset + 4]
        size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        payload_end = offset + 8 + size
        padded_end = payload_end + (size % 2)
        if payload_end > container_end or padded_end > container_end:
            return None
        if kind in metadata_chunks:
            stripped += 1
        else:
            chunks.append(data[offset:padded_end])
        offset = padded_end
    if container_end < len(data):
        stripped += 1
    if not stripped:
        return data, 0
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body, stripped


def _gif_subblocks_end(data: bytes, offset: int) -> Optional[int]:
    while offset < len(data):
        size = data[offset]
        offset += 1
        end = offset + size
        if end > len(data):
            return None
        offset = end
        if size == 0:
            return offset
    return None


def _strip_gif_metadata(data: bytes) -> Optional[tuple[bytes, int]]:
    if not data.startswith((b"GIF87a", b"GIF89a")) or len(data) < 13:
        return None
    packed = data[10]
    global_color_table_size = 3 * (2 ** ((packed & 0x07) + 1)) if packed & 0x80 else 0
    offset = 13 + global_color_table_size
    if offset > len(data):
        return None
    out = bytearray(data[:offset])
    stripped = 0
    metadata_extensions = {0x01, 0xFE, 0xFF}  # plain text, comment, application
    while offset < len(data):
        marker = data[offset]
        if marker == 0x3B:  # trailer
            out.append(marker)
            if offset + 1 < len(data):
                stripped += 1
            return (bytes(out), stripped) if stripped else (data, 0)
        if marker == 0x21:  # extension
            if offset + 2 > len(data):
                return None
            label = data[offset + 1]
            if label == 0xF9:  # graphics control extension
                if offset + 8 > len(data) or data[offset + 2] != 4 or data[offset + 7] != 0:
                    return None
                out.extend(data[offset : offset + 8])
                offset += 8
                continue
            end = _gif_subblocks_end(data, offset + 2)
            if end is None:
                return None
            if label in metadata_extensions:
                stripped += 1
            else:
                out.extend(data[offset:end])
            offset = end
            continue
        if marker == 0x2C:  # image descriptor
            if offset + 10 > len(data):
                return None
            descriptor_end = offset + 10
            local_packed = data[offset + 9]
            local_color_table_size = 3 * (2 ** ((local_packed & 0x07) + 1)) if local_packed & 0x80 else 0
            image_data_start = descriptor_end + local_color_table_size
            if image_data_start >= len(data):
                return None
            end = _gif_subblocks_end(data, image_data_start + 1)
            if end is None:
                return None
            out.extend(data[offset:end])
            offset = end
            continue
        return None
    return None


def _sanitize_image_data_url(url: str, audit: Dict[str, Any]) -> Optional[tuple[str, str]]:
    parsed = _parse_base64_image_data_url(url)
    if parsed is None:
        return None
    mime, raw = parsed
    sanitized = raw
    stripped = 0
    if mime == "image/png":
        stripped_result = _strip_png_metadata(raw)
    elif mime == "image/jpeg":
        stripped_result = _strip_jpeg_metadata(raw)
    elif mime == "image/webp":
        stripped_result = _strip_webp_metadata(raw)
    elif mime == "image/gif":
        stripped_result = _strip_gif_metadata(raw)
    else:
        stripped_result = None
    if stripped_result is None:
        return None
    sanitized, stripped = stripped_result
    if stripped:
        audit["metadata_stripped"] = int(audit.get("metadata_stripped") or 0) + stripped
        audit["bytes_before"] = int(audit.get("bytes_before") or 0) + len(raw)
        audit["bytes_after"] = int(audit.get("bytes_after") or 0) + len(sanitized)
    return f"data:{mime};base64,{base64.b64encode(sanitized).decode('ascii')}", mime


def _prepare_image_inputs(image_inputs: Optional[List[Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Accept only safe inline data URLs so netfix never fetches user-provided remote images."""
    audit: Dict[str, Any] = {"images": 0, "metadata_stripped": 0, "mime_types": []}
    if not isinstance(image_inputs, list):
        return [], audit
    normalized: List[Dict[str, Any]] = []
    for item in image_inputs:
        url = _image_data_url(item)
        if not url[:32].lower().startswith("data:image/"):
            continue
        if len(url) > MAX_IMAGE_DATA_URL_CHARS:
            continue
        sanitized = _sanitize_image_data_url(url, audit)
        if sanitized is None:
            continue
        url, mime = sanitized
        audit["images"] = int(audit.get("images") or 0) + 1
        audit["mime_types"].append(mime)
        normalized.append({"type": "image_url", "image_url": {"url": url}})
        if len(normalized) >= MAX_IMAGE_INPUTS:
            break
    return normalized, audit


def _normalize_image_inputs(image_inputs: Optional[List[Any]]) -> List[Dict[str, Any]]:
    normalized, _audit = _prepare_image_inputs(image_inputs)
    return normalized


def _has_unsupported_image_format(image_inputs: Optional[List[Any]]) -> bool:
    if not isinstance(image_inputs, list):
        return False
    for item in image_inputs:
        url = _image_data_url(item)
        if url[:32].lower().startswith("data:image/") and _image_mime_type(url) not in ALLOWED_IMAGE_MIME_TYPES:
            return True
    return False


def _sanitize_history(history: Optional[List[Any]]) -> List[Dict[str, str]]:
    """Keep recent user/assistant turns; truncate and redact each message."""
    if not isinstance(history, list):
        return []
    normalized: List[Dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        normalized.append({
            "role": role,
            "content": redact_text(content.strip()[:MAX_QUESTION_CHARS]),
        })
    return normalized[-MAX_HISTORY_MESSAGES:]


def _build_messages(
    report: Dict[str, Any],
    question: str,
    mode: str,
    redacted: Dict[str, Any],
    provider_id: str,
    image_inputs: Optional[List[Any]] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    preset = get_provider(provider_id) or {}
    system = (
        "You are netfix's AI network assistant. You can chat with the user "
        "across multiple turns. Return strict JSON only. "
        "Do not invent shell commands. Only recommend action ids already present "
        "in the local report. Tier and execution are enforced locally. "
        "If the user has not run a diagnostic yet, answer general networking "
        "questions and naturally guide them to run a diagnostic first, such as "
        "`python3 netfix.py triage` or the check button in the Netfix app. "
        + str(preset.get("system_prompt") or "")
    )
    report_available = bool(report)
    user_payload = {
        "mode": mode,
        "question": question,
        "report_available": report_available,
        "redacted_report": redacted["redacted_report"] if report_available else None,
        "redaction_audit": redacted["redaction_audit"],
        "allowed_action_ids": sorted(_allowed_action_ids(report)),
        "schema": {
            "schema_version": "llm_explanation.v1",
            "headline": "string",
            "severity": "ok|warn|fail",
            "explanation": "string",
            "evidence": [{"diagnostic": "string", "status": "ok|warn|fail", "why": "string"}],
            "actions": [{"id": "known fix id", "label": "string", "tier": 1, "needs_confirm": False, "reason": "string"}],
            "manual_steps": [{"id": "string", "description": "string", "steps": ["string"]}],
            "residential_proxy_guide": {"status": "not_configured|valid|auth_failed|not_residential|unknown", "steps": []},
        },
    }
    if not report_available:
        user_payload["note"] = (
            "用户尚未运行诊断；请当作通用网络问答回答，"
            "并自然引导用户先运行诊断（如 python3 netfix.py triage 或点击 App 里的检查）。"
        )
    user_text = json.dumps(user_payload, ensure_ascii=False, default=str)
    user_content: Any = user_text
    if mode == "image_question":
        parts: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
        prepared = image_inputs if isinstance(image_inputs, list) else []
        if prepared and all(isinstance(item, dict) and item.get("type") == "image_url" for item in prepared):
            parts.extend(prepared)  # already normalized and metadata-stripped
        else:
            parts.extend(_normalize_image_inputs(image_inputs))
        user_content = parts
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for item in history or []:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_content})
    return messages


def explain_with_llm(
    report: Optional[Dict[str, Any]],
    question: str = "",
    mode: str = "explain",
    redaction_level: str = "balanced",
    upload_confirmed: bool = False,
    allow_fallback: Optional[bool] = None,
    image_inputs: Optional[List[Any]] = None,
    history: Optional[List[Any]] = None,
    intake_hint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Explain a report or chat about networking using an optional cloud LLM, with local fallback.

    intake_hint: optional precomputed symptom_intake result dict with keys
        matched_symptoms / suggested_checks / suggested_tools / note. When supplied,
    the local rule layer derives a default plan_steps + observations snapshot so
    the SwiftUI client can render a plan/act/observe trail before the cloud LLM
    responds (and even when the cloud LLM is offline / has fallen back).
    """
    if not isinstance(report, dict):
        report = {}
    history_messages = _sanitize_history(history)
    plan_steps = _plan_steps_from_intake(intake_hint)
    observations = _observations_from_intake(intake_hint)
    llm_settings = load_settings().get("llm", {})
    saved_redaction_level = str(llm_settings.get("redaction_level") or "balanced")
    requested_redaction_level = str(redaction_level or "balanced")
    effective_redaction_level = (
        "strict"
        if "strict" in {saved_redaction_level, requested_redaction_level}
        else "balanced"
    )
    redacted = redact_report(report, level=effective_redaction_level)
    question = redact_text(str(question or "").strip()[:MAX_QUESTION_CHARS])
    if not llm_settings.get("enabled"):
        return _fallback(report, "llm_disabled", redacted, plan_steps=plan_steps, observations=observations)
    if llm_settings.get("upload_consent") == "never":
        return _fallback(report, "upload_consent_never", redacted, plan_steps=plan_steps, observations=observations)
    prepared_image_inputs: List[Dict[str, Any]] = []
    image_redaction_audit: Dict[str, Any] = {}
    if mode == "image_question":
        features = llm_settings.get("features") if isinstance(llm_settings.get("features"), dict) else {}
        if not bool(features.get("image_question")):
            return _fallback(report, "image_question_disabled", redacted, plan_steps=plan_steps, observations=observations)
        prepared_image_inputs, image_redaction_audit = _prepare_image_inputs(image_inputs)
        if not prepared_image_inputs:
            if _has_unsupported_image_format(image_inputs):
                return _fallback(report, "image_unsupported_format", redacted, plan_steps=plan_steps, observations=observations)
            return _fallback(report, "image_input_missing", redacted, plan_steps=plan_steps, observations=observations)
        if not upload_confirmed:
            return _fallback(
                report,
                "upload_consent_required",
                redacted,
                needs_upload_confirmation=True,
                confirmation_request=build_confirmation_request(
                    "upload_image",
                    reason_code="upload_consent_required",
                    preview={"mime_count": len(image_redaction_audit.get("mime_types") or [])},
                ),
                plan_steps=plan_steps,
                observations=observations,
            )
    if mode != "image_question" and llm_settings.get("upload_consent") == "ask_each_time" and not upload_confirmed:
        return _fallback(
            report,
            "upload_consent_required",
            redacted,
            needs_upload_confirmation=True,
            confirmation_request=build_confirmation_request(
                "upload_redacted_report",
                reason_code="upload_consent_required",
                preview={"redaction_level": effective_redaction_level},
            ),
            plan_steps=plan_steps,
            observations=observations,
        )

    active_provider = str(llm_settings.get("provider") or "custom_openai_compatible")
    fallback_settings = llm_settings.get("fallback")
    fallback_enabled = bool(fallback_settings.get("enabled", True)) if isinstance(fallback_settings, dict) else True
    if allow_fallback is not None:
        fallback_enabled = bool(allow_fallback)
    provider_ids = _ordered_provider_ids(active_provider, llm_settings, mode)
    if not fallback_enabled:
        if mode == "image_question" and not (get_provider(active_provider) or {}).get("supports_vision"):
            return _fallback(report, "provider_vision_unsupported", redacted)
        provider_ids = [active_provider]

    fallback_chain: List[Dict[str, Any]] = []
    budget_settings = llm_settings.get("budget") if isinstance(llm_settings.get("budget"), dict) else {}
    for provider_id in provider_ids:
        provider_settings = _provider_settings(llm_settings, provider_id, mode=mode)
        account = str(provider_settings.get("api_key_account") or provider_id)
        api_key = keychain.get_secret(
            keychain.LLM_SERVICE,
            account,
            allow_generic_llm_override=provider_id == active_provider,
        )
        if not api_key:
            fallback_chain.append({"provider": provider_id, "status": "skipped", "reason_code": "missing_api_key"})
            continue
        allowance = llm_budget.check_request(provider_id, mode, budget_settings)
        if not allowance.get("ok"):
            skipped = {
                "provider": provider_id,
                "status": "skipped",
                "reason_code": allowance.get("reason_code") or "local_budget_exceeded",
            }
            for key in ("retry_after_s", "limit", "window_s"):
                if key in allowance:
                    skipped[key] = allowance[key]
            fallback_chain.append(skipped)
            continue
        provider = OpenAICompatibleProvider(
            base_url=str(provider_settings.get("base_url") or ""),
            api_key=api_key,
            model=str(provider_settings.get("model") or ""),
            timeout_s=int(provider_settings.get("timeout_s") or 20),
            provider_id=provider_id,
        )
        messages = _build_messages(
            report,
            question,
            mode,
            redacted,
            provider_id,
            image_inputs=prepared_image_inputs if mode == "image_question" else image_inputs,
            history=history_messages,
        )
        max_tokens = int(provider_settings.get("max_tokens") or 900)
        temperature = float(provider_settings.get("temperature") if provider_settings.get("temperature") is not None else 0.2)
        # invalid_json_response 常见于推理模型把 max_tokens 耗尽导致 JSON 截断：
        # 首次失败后把 max_tokens 翻倍重试一次，仍失败才进 fallback 链。
        llm_budget.record_request(provider_id, mode, budget_settings)
        raw = None
        last_exc: Optional[LLMProviderError] = None
        for attempt, tokens in enumerate((max_tokens, max_tokens * 2)):
            if attempt > 0:
                llm_budget.record_request(provider_id, mode, budget_settings)
            try:
                raw = provider.complete_json(
                    messages=messages,
                    max_tokens=tokens,
                    temperature=temperature,
                )
                last_exc = None
                break
            except LLMProviderError as exc:
                last_exc = exc
                if exc.reason_code != "invalid_json_response":
                    break
        if last_exc is not None:
            exc = last_exc
            llm_budget.record_provider_result(provider_id, exc.reason_code, budget_settings)
            fallback_chain.append({
                "provider": provider_id,
                "status": "failed",
                "reason_code": exc.reason_code,
                "http_status": exc.http_status,
                "message": str(exc),
            })
            continue

        usage = _usage_summary(raw.pop("__netfix_usage", None))
        data = sanitize_llm_response(raw, report)
        ok_step = {"provider": provider_id, "status": "ok", "reason_code": None}
        if usage:
            ok_step["usage"] = usage
        fallback_chain.append(ok_step)
        data["provider_used"] = provider_id
        data["failure_reason_code"] = None
        data["fallback_chain"] = fallback_chain
        if usage:
            data["provider_usage"] = usage
        if image_redaction_audit:
            data["image_redaction_audit"] = image_redaction_audit
        data["redaction_audit"] = redacted["redaction_audit"]
        data["redacted_report_hash"] = redacted["redacted_report_hash"]
        data["plan_steps"] = plan_steps
        data["observations"] = observations
        return data

    reason = fallback_chain[-1]["reason_code"] if fallback_chain else "missing_api_key"
    return _fallback(
        report,
        f"provider_error: {reason}",
        redacted,
        fallback_chain=fallback_chain,
        plan_steps=plan_steps,
        observations=observations,
    )
