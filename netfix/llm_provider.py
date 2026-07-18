"""LLM provider adapters for optional cloud explanations."""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from netfix.redaction import redact_text


PROVIDER_PRESETS = [
    {
        "id": "deepseek",
        "label": "DeepSeek（推荐，便宜量大）",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "openai_compatible": True,
        "supports_json_mode": True,
        "supports_vision": False,
        "capabilities": ["text", "json"],
        "text_priority": 10,
        "vision_priority": None,
        "cost_tier": "low",
        "domestic_priority": 1,
        "netfix_role": "primary_text",
        "image_question_status": "unsupported_provider_no_vision",
        "regions": ["cn", "global"],
        "default_temperature": 0.2,
        "default_max_tokens": 900,
        "metadata_checked_at": "2026-06-25",
        "official_docs": [
            "https://api-docs.deepseek.com/",
            "https://api-docs.deepseek.com/quick_start/pricing",
        ],
        "system_prompt": "Return strict JSON only. The word JSON is required for provider JSON mode.",
        "market": "domestic",
    },
    {
        "id": "moonshot_kimi",
        "label": "Kimi / Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
        "openai_compatible": True,
        "supports_json_mode": True,
        "supports_vision": True,
        "capabilities": ["text", "json", "vision", "video", "tools"],
        "text_priority": 20,
        "vision_priority": 20,
        "cost_tier": "medium",
        "domestic_priority": 2,
        "netfix_role": "domestic_fallback_vision_candidate",
        "image_question_status": "openai_compatible_image_url_ready",
        "regions": ["cn", "global"],
        "default_temperature": None,
        "default_max_tokens": 1200,
        "temperature_policy": "omit",
        "metadata_checked_at": "2026-06-25",
        "official_docs": [
            "https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart",
            "https://platform.moonshot.cn/docs/api-reference",
        ],
        "extra_payload": {"thinking": {"type": "disabled"}},
        "system_prompt": "Return one JSON object only. Do not include markdown fences unless unavoidable.",
        "market": "domestic",
        "notes": "国内默认入口；海外或国际账号可手动改为 https://api.moonshot.ai/v1。",
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M3",
        "openai_compatible": True,
        "supports_json_mode": False,
        "supports_vision": True,
        "capabilities": ["text", "vision", "video", "tools"],
        "text_priority": 30,
        "vision_priority": 10,
        "cost_tier": "medium",
        "domestic_priority": 3,
        "netfix_role": "domestic_fallback_vision_candidate",
        "image_question_status": "openai_compatible_image_url_ready",
        "regions": ["cn", "global"],
        "default_temperature": 1.0,
        "default_max_tokens": 1200,
        "max_tokens_field": "max_completion_tokens",
        "metadata_checked_at": "2026-06-25",
        "official_docs": [
            "https://platform.minimaxi.com/docs/api-reference/text-chat-openai",
            "https://www.minimax.io/platform/document/ChatCompletion%20v2",
        ],
        "extra_payload": {"thinking": {"type": "disabled"}},
        "system_prompt": "Return one JSON object only. Do not include thinking text or markdown outside JSON.",
        "market": "domestic",
        "notes": "国内默认入口；国际账号可手动改为 https://api.minimax.io/v1。",
    },
    {
        "id": "qwen",
        "label": "Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "vision_model": "qwen-vl-plus",
        "openai_compatible": True,
        "supports_json_mode": True,
        "supports_vision": True,
        "capabilities": ["text", "json", "vision"],
        "text_priority": 40,
        "vision_priority": 30,
        "cost_tier": "medium",
        "domestic_priority": 4,
        "netfix_role": "domestic_text_and_vision_fallback",
        "image_question_status": "openai_compatible_image_url_ready",
        "regions": ["cn"],
        "default_temperature": 0.2,
        "default_max_tokens": 900,
        "metadata_checked_at": "2026-06-25",
        "official_docs": [
            "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
            "https://help.aliyun.com/zh/model-studio/models",
        ],
        "system_prompt": "Return strict JSON only. The word JSON is required for provider JSON mode.",
        "market": "domestic",
    },
    {
        "id": "kimi_coding",
        "label": "Kimi 编程版",
        "base_url": "https://api.kimi.com/coding/v1",
        "model": "kimi-for-coding",
        "openai_compatible": True,
        "supports_json_mode": True,
        "supports_vision": False,
        "capabilities": ["text", "json"],
        "text_priority": 50,
        "vision_priority": None,
        "cost_tier": "medium",
        "domestic_priority": 5,
        "netfix_role": "domestic_text_fallback",
        "image_question_status": "unsupported_provider_no_vision",
        "regions": ["cn", "global"],
        "default_temperature": None,
        "default_max_tokens": 1200,
        "temperature_policy": "omit",
        "metadata_checked_at": "2026-06-25",
        "official_docs": [
            "https://www.kimi.com/code/docs/",
            "https://www.kimi.com/zh-cn/help/kimi-code/membership-guide",
        ],
        "system_prompt": "Return strict JSON only. The word JSON is required for provider JSON mode.",
        "market": "domestic",
        "notes": "编程版订阅 key（sk-kimi- 前缀），与 Moonshot 开放平台按量 key 不通用。",
    },
    {
        "id": "custom_openai_compatible",
        "label": "Custom OpenAI-compatible",
        "base_url": "",
        "model": "",
        "openai_compatible": True,
        "supports_json_mode": True,
        "supports_vision": False,
        "capabilities": ["text", "json"],
        "text_priority": 90,
        "vision_priority": 90,
        "cost_tier": "custom",
        "domestic_priority": 90,
        "netfix_role": "custom_compatible",
        "image_question_status": "depends_on_custom_model",
        "regions": ["custom"],
        "default_temperature": 0.2,
        "default_max_tokens": 900,
        "system_prompt": "Return strict JSON only.",
        "market": "custom",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "openai_compatible": True,
        "supports_json_mode": True,
        "supports_vision": True,
        "capabilities": ["text", "json", "vision"],
        "text_priority": 100,
        "vision_priority": 80,
        "cost_tier": "global",
        "domestic_priority": 100,
        "netfix_role": "global_optional",
        "image_question_status": "provider_supports_vision_adapter_pending",
        "regions": ["global"],
        "default_temperature": 0.2,
        "default_max_tokens": 900,
        "system_prompt": "Return strict JSON only.",
        "market": "global",
    },
]

MAX_PROVIDER_ERROR_DETAIL_CHARS = 300


def sanitize_provider_error_message(message: str) -> str:
    """Return provider error detail safe enough for local UI/API output."""
    text = redact_text(str(message))
    if len(text) > MAX_PROVIDER_ERROR_DETAIL_CHARS:
        return text[:MAX_PROVIDER_ERROR_DETAIL_CHARS] + "..."
    return text


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "provider_error",
        http_status: int = 0,
        provider_id: str = "",
    ):
        super().__init__(sanitize_provider_error_message(message))
        self.reason_code = reason_code
        self.http_status = http_status
        self.provider_id = provider_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": str(self),
            "reason_code": self.reason_code,
            "http_status": self.http_status,
            "provider": self.provider_id,
        }


def get_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    for provider in PROVIDER_PRESETS:
        if provider["id"] == provider_id:
            return dict(provider)
    return None


def provider_candidates(mode: str = "explain", domestic_only: bool = True, include_custom: bool = False, include_global: bool = False) -> List[Dict[str, Any]]:
    """Return provider candidates ordered by task capability."""
    capability = "vision" if mode == "image_question" else "text"
    priority_key = "vision_priority" if capability == "vision" else "text_priority"
    candidates = []
    for provider in PROVIDER_PRESETS:
        if provider["id"] == "custom_openai_compatible" and not include_custom:
            continue
        if provider.get("market") == "global" and not include_global:
            continue
        if domestic_only and provider.get("market") not in {"domestic", "custom"}:
            continue
        if capability not in provider.get("capabilities", []):
            continue
        priority = provider.get(priority_key)
        if priority is None:
            continue
        item = dict(provider)
        item["_priority"] = int(priority)
        candidates.append(item)
    return sorted(candidates, key=lambda item: item["_priority"])


def _classify_http_error(status: int, detail: str) -> str:
    try:
        parsed_detail = json.loads(detail)
        normalized_detail = json.dumps(parsed_detail, ensure_ascii=False)
    except Exception:
        normalized_detail = detail
    text = f"{detail} {normalized_detail}".lower()
    if "model" in text and ("not found" in text or "does not exist" in text) or any(
        marker in text for marker in ("模型不存在", "模型未找到", "模型无效")
    ):
        return "model_not_found"
    if any(marker in text for marker in ("rate limit", "too many requests")) or any(
        marker in text for marker in ("限流", "请求过于频繁", "请求频繁", "频率限制", "请求过多")
    ):
        return "rate_limited"
    if any(marker in text for marker in ("insufficient", "balance", "quota")) or any(
        marker in text for marker in ("余额不足", "额度不足", "额度用尽", "配额不足", "欠费", "充值")
    ):
        return "quota_or_billing"
    if any(marker in text for marker in ("invalid api key", "unauthorized", "forbidden")) or any(
        marker in text for marker in ("鉴权失败", "认证失败", "认证错误", "api key 无效", "密钥无效")
    ):
        return "auth_failed"
    if status in (401, 403):
        return "auth_failed"
    if status == 429:
        return "rate_limited"
    if status == 402:
        return "quota_or_billing"
    if status == 404:
        return "model_not_found"
    if status == 400 and ("response_format" in text or "json" in text):
        return "json_mode_unsupported"
    if status == 400:
        return "bad_request"
    if 500 <= status < 600:
        return "provider_unavailable"
    return "http_error"


def _extract_json_object(content: str) -> Dict[str, Any]:
    """Parse strict JSON, fenced JSON, or a single embedded JSON object."""
    candidates = [content.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    first = content.find("{")
    last = content.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(content[first : last + 1].strip())
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMProviderError("provider response content did not contain a JSON object", reason_code="invalid_json_response")


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


def parse_chat_completion_json_content(raw: str) -> Dict[str, Any]:
    """Parse OpenAI-compatible chat response content as JSON."""
    try:
        body = json.loads(raw)
        content = body["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise LLMProviderError("provider response content was not a string", reason_code="invalid_response_shape")
        parsed = _extract_json_object(content)
        usage = _usage_summary(body.get("usage"))
        if usage:
            parsed["__netfix_usage"] = usage
        return parsed
    except Exception as exc:
        if isinstance(exc, LLMProviderError):
            raise
        raise LLMProviderError("provider response was not valid JSON content", reason_code="invalid_response_shape") from exc


class OpenAICompatibleProvider:
    """Minimal OpenAI-compatible chat/completions client using stdlib only."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: int = 20, provider_id: str = "custom_openai_compatible"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.provider_id = provider_id

    def validate_settings(self) -> List[str]:
        errors = []
        if not self.base_url.startswith("https://") and not self.base_url.startswith("http://127.0.0.1"):
            errors.append("base_url must use https:// or local http://127.0.0.1")
        if not self.api_key:
            errors.append("api_key is required")
        if not self.model:
            errors.append("model is required")
        return errors

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1") or "/compatible-mode/v1" in self.base_url:
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/chat/completions"

    def _build_payload(self, messages: List[Dict[str, Any]], max_tokens: int, temperature: float) -> Dict[str, Any]:
        preset = next((item for item in PROVIDER_PRESETS if item["id"] == self.provider_id), {})
        token_field = str(preset.get("max_tokens_field") or "max_tokens")
        if token_field not in {"max_tokens", "max_completion_tokens"}:
            token_field = "max_tokens"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            token_field: max_tokens,
        }
        provider_temperature = preset.get("default_temperature", temperature)
        if preset.get("temperature_policy") != "omit" and provider_temperature is not None:
            payload["temperature"] = provider_temperature if temperature is None else temperature
        if bool(preset.get("supports_json_mode")):
            payload["response_format"] = {"type": "json_object"}
        extra_payload = preset.get("extra_payload")
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        if self.provider_id == "openai":
            payload["store"] = False
        return payload

    def complete_json(self, messages: List[Dict[str, Any]], max_tokens: int = 900, temperature: float = 0.2) -> Dict[str, Any]:
        errors = self.validate_settings()
        if errors:
            raise LLMProviderError("; ".join(errors), reason_code="invalid_settings", provider_id=self.provider_id)
        payload = self._build_payload(messages, max_tokens=max_tokens, temperature=temperature)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._chat_completions_url(),
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            reason = _classify_http_error(exc.code, detail)
            raise LLMProviderError(
                f"provider returned HTTP {exc.code}: {detail}",
                reason_code=reason,
                http_status=exc.code,
                provider_id=self.provider_id,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMProviderError(str(exc), reason_code="timeout", provider_id=self.provider_id) from exc
        except urllib.error.URLError as exc:
            raise LLMProviderError(str(exc), reason_code="network_error", provider_id=self.provider_id) from exc
        except Exception as exc:
            raise LLMProviderError(str(exc), reason_code="provider_error", provider_id=self.provider_id) from exc
        return parse_chat_completion_json_content(raw)


def list_providers() -> List[Dict[str, Any]]:
    return [dict(item) for item in PROVIDER_PRESETS]
