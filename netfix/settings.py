"""Local netfix settings stored outside diagnostic reports."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

from netfix.constants import JOURNAL_DIR
from netfix.utils import secure_write_json


SETTINGS_PATH = JOURNAL_DIR / "settings.json"


DEFAULT_SETTINGS: Dict[str, Any] = {
    "version": 1,
    "llm": {
        "enabled": False,
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_account": "deepseek",
        "api_key_set": False,
        "timeout_s": 20,
        "max_tokens": 900,
        "temperature": 0.2,
        "redaction_level": "balanced",
        "upload_consent": "ask_each_time",
        "features": {
            "explain": True,
            "repair_steps": True,
            "residential_proxy_guide": True,
            "image_question": False,
        },
        "fallback": {
            "enabled": True,
            "domestic_only": True,
            "include_custom": False,
            "include_global": False,
            "chain": ["deepseek", "moonshot_kimi", "minimax", "qwen"],
            "vision_chain": ["minimax", "moonshot_kimi", "qwen"],
        },
        "budget": {
            "enabled": True,
            "persist_usage_ledger": True,
            "max_requests_per_hour": 60,
            "max_image_requests_per_hour": 12,
            "cooldown_seconds_after_rate_limit": 300,
            "cooldown_seconds_after_quota": 3600,
        },
    },
    "proxy_profiles": [],
    "proxy_monitor": {
        "enabled": False,
        "profile_id": "",
        "interval": 60,
        "target_url": "https://www.gstatic.com/generate_204",
        "target_profile": "baseline",
        "timeout": 10,
        "updated_at": "",
    },
    "proxy_bridge": {
        "auto_restart_enabled": False,
        "idle_timeout": 0,
        "updated_at": "",
    },
    "privacy": {
        "log_retention_enabled": True,
        "log_retention_days": 7,
        "save_latest_report": True,
        "persist_proxy_identity_report": False,
    },
}


_LLM_ALLOWED_KEYS = {
    "enabled",
    "provider",
    "base_url",
    "model",
    "api_key_account",
    "api_key_set",
    "timeout_s",
    "max_tokens",
    "temperature",
    "redaction_level",
    "upload_consent",
    "features",
    "fallback",
    "budget",
}

_PRIVACY_ALLOWED_KEYS = {
    "log_retention_enabled",
    "log_retention_days",
    "save_latest_report",
    "persist_proxy_identity_report",
}

_PROXY_MONITOR_ALLOWED_KEYS = {
    "enabled",
    "profile_id",
    "interval",
    "target_url",
    "target_profile",
    "timeout",
    "updated_at",
}

_PROXY_BRIDGE_ALLOWED_KEYS = {
    "auto_restart_enabled",
    "idle_timeout",
    "updated_at",
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(path: Path = SETTINGS_PATH) -> Dict[str, Any]:
    """Load settings, returning defaults when the file is absent or invalid."""
    if not path.exists():
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_SETTINGS)
    return _deep_merge(DEFAULT_SETTINGS, raw)


def save_settings(settings: Dict[str, Any], path: Path = SETTINGS_PATH) -> Path:
    """Persist non-secret settings as JSON."""
    safe = copy.deepcopy(settings)
    safe.setdefault("version", 1)
    secure_write_json(path, safe, sort_keys=True)
    return path


def clear_settings(path: Path = SETTINGS_PATH) -> Dict[str, Any]:
    """Delete local non-secret settings."""
    try:
        if path.exists():
            path.unlink()
            return {"ok": True, "removed": [str(path)]}
        return {"ok": True, "removed": []}
    except Exception as exc:
        return {"ok": False, "removed": [], "error": str(exc)}


def get_llm_settings(masked: bool = True) -> Dict[str, Any]:
    """Return LLM settings without exposing the API key."""
    settings = load_settings().get("llm", {})
    out = copy.deepcopy(settings)
    out.pop("api_key", None)
    stored_api_key_set = bool(out.get("api_key_set"))
    account = str(out.get("api_key_account") or out.get("provider") or "default")
    try:
        from netfix import keychain

        actual_api_key_set = keychain.has_secret(
            keychain.LLM_SERVICE,
            account,
            allow_generic_llm_override=True,
        )
        out["api_key_set"] = actual_api_key_set if actual_api_key_set or keychain.is_available() else stored_api_key_set
    except Exception:
        out["api_key_set"] = stored_api_key_set
    if masked:
        out["api_key"] = "********" if out.get("api_key_set") else ""
    return out


def update_llm_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Merge validated LLM settings into the local settings file."""
    settings = load_settings()
    llm = settings.setdefault("llm", copy.deepcopy(DEFAULT_SETTINGS["llm"]))
    previous_provider = str(llm.get("provider") or "")
    previous_account = str(llm.get("api_key_account") or "")
    for key, value in payload.items():
        if key in _LLM_ALLOWED_KEYS:
            llm[key] = value

    provider = str(llm.get("provider") or "custom_openai_compatible")
    llm["provider"] = provider
    if "api_key_account" not in payload and provider != previous_provider and previous_account == previous_provider:
        llm["api_key_account"] = provider
    else:
        llm["api_key_account"] = str(llm.get("api_key_account") or provider)
    llm["timeout_s"] = max(1, min(int(llm.get("timeout_s") or 20), 120))
    llm["max_tokens"] = max(128, min(int(llm.get("max_tokens") or 900), 8000))
    llm["temperature"] = max(0.0, min(float(llm.get("temperature") or 0.2), 2.0))
    if llm.get("redaction_level") not in {"strict", "balanced"}:
        llm["redaction_level"] = "balanced"
    if llm.get("upload_consent") not in {"ask_each_time", "always", "never"}:
        llm["upload_consent"] = "ask_each_time"
    fallback = llm.get("fallback")
    if not isinstance(fallback, dict):
        fallback = copy.deepcopy(DEFAULT_SETTINGS["llm"]["fallback"])
    fallback["enabled"] = bool(fallback.get("enabled", True))
    fallback["domestic_only"] = bool(fallback.get("domestic_only", True))
    fallback["include_custom"] = bool(fallback.get("include_custom", False))
    fallback["include_global"] = bool(fallback.get("include_global", False))
    chain = fallback.get("chain")
    fallback["chain"] = [str(item) for item in chain] if isinstance(chain, list) else list(DEFAULT_SETTINGS["llm"]["fallback"]["chain"])
    vision_chain = fallback.get("vision_chain")
    fallback["vision_chain"] = [str(item) for item in vision_chain] if isinstance(vision_chain, list) else list(DEFAULT_SETTINGS["llm"]["fallback"]["vision_chain"])
    llm["fallback"] = fallback
    budget = llm.get("budget")
    if not isinstance(budget, dict):
        budget = copy.deepcopy(DEFAULT_SETTINGS["llm"]["budget"])
    budget["enabled"] = bool(budget.get("enabled", True))
    budget["persist_usage_ledger"] = bool(budget.get("persist_usage_ledger", DEFAULT_SETTINGS["llm"]["budget"]["persist_usage_ledger"]))
    budget["max_requests_per_hour"] = max(0, min(int(budget.get("max_requests_per_hour") or 0), 10000))
    budget["max_image_requests_per_hour"] = max(0, min(int(budget.get("max_image_requests_per_hour") or 0), 10000))
    budget["cooldown_seconds_after_rate_limit"] = max(0, min(int(budget.get("cooldown_seconds_after_rate_limit") or 0), 86400))
    budget["cooldown_seconds_after_quota"] = max(0, min(int(budget.get("cooldown_seconds_after_quota") or 0), 86400))
    llm["budget"] = budget
    if not budget["enabled"] or not budget["persist_usage_ledger"]:
        try:
            from netfix import llm_budget

            llm_budget.clear_persistent_ledger()
        except Exception:
            pass

    save_settings(settings)
    return get_llm_settings(masked=True)


def get_proxy_profiles() -> list:
    """Return saved residential/custom proxy profiles without credentials."""
    settings = load_settings()
    profiles = settings.get("proxy_profiles", [])
    return copy.deepcopy(profiles) if isinstance(profiles, list) else []


def upsert_proxy_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Insert or update a non-secret proxy profile."""
    settings = load_settings()
    profiles = settings.setdefault("proxy_profiles", [])
    existing_idx = None
    for idx, item in enumerate(profiles):
        if item.get("id") == profile.get("id"):
            existing_idx = idx
            break
    if existing_idx is None:
        profiles.append(copy.deepcopy(profile))
    else:
        profiles[existing_idx] = copy.deepcopy(profile)
    save_settings(settings)
    return copy.deepcopy(profile)


def delete_proxy_profile(profile_id: str) -> Dict[str, Any]:
    """Delete one saved proxy profile by id without touching other profiles."""
    profile_id = str(profile_id or "")
    settings = load_settings()
    profiles = settings.get("proxy_profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    removed = None
    kept = []
    for profile in profiles:
        if isinstance(profile, dict) and str(profile.get("id") or "") == profile_id and removed is None:
            removed = copy.deepcopy(profile)
            continue
        kept.append(profile)
    if removed is None:
        return {"ok": False, "error": "profile not found", "profile_id": profile_id}
    settings["proxy_profiles"] = kept
    save_settings(settings)
    return {"ok": True, "profile_id": profile_id, "profile": removed}


def get_proxy_monitor_settings() -> Dict[str, Any]:
    """Return persisted residential/custom proxy monitor settings."""
    data = load_settings().get("proxy_monitor", {})
    out = copy.deepcopy(data) if isinstance(data, dict) else copy.deepcopy(DEFAULT_SETTINGS["proxy_monitor"])
    out["enabled"] = bool(out.get("enabled", False))
    out["profile_id"] = str(out.get("profile_id") or "")
    out["interval"] = max(15, min(int(out.get("interval") or 60), 3600))
    out["target_url"] = str(out.get("target_url") or "https://www.gstatic.com/generate_204")
    out["timeout"] = max(1, min(int(out.get("timeout") or 10), 60))
    out["updated_at"] = str(out.get("updated_at") or "")
    return out


def update_proxy_monitor_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist non-secret proxy monitor settings."""
    data = load_settings()
    monitor = data.setdefault("proxy_monitor", copy.deepcopy(DEFAULT_SETTINGS["proxy_monitor"]))
    for key, value in payload.items():
        if key in _PROXY_MONITOR_ALLOWED_KEYS:
            monitor[key] = value
    monitor["enabled"] = bool(monitor.get("enabled", False))
    monitor["profile_id"] = str(monitor.get("profile_id") or "")
    monitor["interval"] = max(15, min(int(monitor.get("interval") or 60), 3600))
    monitor["target_url"] = str(monitor.get("target_url") or "https://www.gstatic.com/generate_204")
    monitor["timeout"] = max(1, min(int(monitor.get("timeout") or 10), 60))
    monitor["updated_at"] = str(monitor.get("updated_at") or "")
    save_settings(data)
    return get_proxy_monitor_settings()


def get_proxy_bridge_settings() -> Dict[str, Any]:
    """Return persisted local bridge lifecycle preferences."""
    data = load_settings().get("proxy_bridge", {})
    out = copy.deepcopy(data) if isinstance(data, dict) else copy.deepcopy(DEFAULT_SETTINGS["proxy_bridge"])
    out["auto_restart_enabled"] = bool(out.get("auto_restart_enabled", False))
    out["idle_timeout"] = max(0, min(int(out.get("idle_timeout") or 0), 86400))
    out["updated_at"] = str(out.get("updated_at") or "")
    return out


def update_proxy_bridge_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist non-secret local bridge lifecycle preferences."""
    data = load_settings()
    bridge = data.setdefault("proxy_bridge", copy.deepcopy(DEFAULT_SETTINGS["proxy_bridge"]))
    for key, value in payload.items():
        if key in _PROXY_BRIDGE_ALLOWED_KEYS:
            bridge[key] = value
    bridge["auto_restart_enabled"] = bool(bridge.get("auto_restart_enabled", False))
    bridge["idle_timeout"] = max(0, min(int(bridge.get("idle_timeout") or 0), 86400))
    bridge["updated_at"] = str(bridge.get("updated_at") or "")
    save_settings(data)
    return get_proxy_bridge_settings()


def get_privacy_settings() -> Dict[str, Any]:
    """Return local privacy/log-retention settings."""
    data = load_settings().get("privacy", {})
    out = copy.deepcopy(data) if isinstance(data, dict) else copy.deepcopy(DEFAULT_SETTINGS["privacy"])
    out["log_retention_enabled"] = bool(out.get("log_retention_enabled", True))
    out["log_retention_days"] = max(1, min(int(out.get("log_retention_days") or 7), 365))
    out["save_latest_report"] = bool(out.get("save_latest_report", True))
    out["persist_proxy_identity_report"] = bool(out.get("persist_proxy_identity_report", False))
    return out


def update_privacy_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist local privacy/log-retention settings."""
    data = load_settings()
    privacy = data.setdefault("privacy", copy.deepcopy(DEFAULT_SETTINGS["privacy"]))
    for key, value in payload.items():
        if key in _PRIVACY_ALLOWED_KEYS:
            privacy[key] = value
    privacy["log_retention_enabled"] = bool(privacy.get("log_retention_enabled", True))
    privacy["log_retention_days"] = max(1, min(int(privacy.get("log_retention_days") or 7), 365))
    privacy["save_latest_report"] = bool(privacy.get("save_latest_report", True))
    privacy["persist_proxy_identity_report"] = bool(privacy.get("persist_proxy_identity_report", False))
    save_settings(data)
    return get_privacy_settings()
