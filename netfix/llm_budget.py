"""Local budget and cooldown guard for optional cloud LLM calls."""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from netfix.constants import JOURNAL_DIR
from netfix.utils import secure_write_json


LLM_BUDGET_JOURNAL = JOURNAL_DIR / "llm_budget_journal.json"
LLM_BUDGET_SCHEMA = "netfix_llm_budget_journal.v1"


DEFAULT_BUDGET: Dict[str, Any] = {
    "enabled": True,
    "persist_usage_ledger": False,
    "window_seconds": 3600,
    "max_requests_per_hour": 60,
    "max_image_requests_per_hour": 12,
    "cooldown_seconds_after_rate_limit": 300,
    "cooldown_seconds_after_quota": 3600,
}

_LOCK = threading.RLock()
_REQUESTS: List[Dict[str, Any]] = []
_COOLDOWNS: Dict[str, float] = {}


def reset_state() -> None:
    """Clear in-process counters. Intended for tests and backend restart boundaries."""
    with _LOCK:
        _REQUESTS.clear()
        _COOLDOWNS.clear()


def clear_persistent_ledger() -> Dict[str, Any]:
    """Remove the local non-sensitive LLM budget ledger."""
    with _LOCK:
        _REQUESTS.clear()
        _COOLDOWNS.clear()
    try:
        if LLM_BUDGET_JOURNAL.exists():
            LLM_BUDGET_JOURNAL.unlink()
            return {"ok": True, "removed": [str(LLM_BUDGET_JOURNAL)], "errors": {}}
        return {"ok": True, "removed": [], "errors": {}}
    except Exception as exc:
        return {"ok": False, "removed": [], "errors": {str(LLM_BUDGET_JOURNAL): str(exc)}}


def _settings(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = dict(DEFAULT_BUDGET)
    if isinstance(raw, dict):
        data.update(raw)
    data["enabled"] = bool(data.get("enabled", True))
    data["persist_usage_ledger"] = bool(data.get("persist_usage_ledger", False))
    data["window_seconds"] = max(60, int(data.get("window_seconds") or 3600))
    data["max_requests_per_hour"] = max(0, int(data.get("max_requests_per_hour") or 0)) if "max_requests_per_hour" in data else 60
    data["max_image_requests_per_hour"] = max(0, int(data.get("max_image_requests_per_hour") or 0)) if "max_image_requests_per_hour" in data else 12
    data["cooldown_seconds_after_rate_limit"] = max(0, int(data.get("cooldown_seconds_after_rate_limit") or 0))
    data["cooldown_seconds_after_quota"] = max(0, int(data.get("cooldown_seconds_after_quota") or 0))
    return data


def _persistence_enabled(settings: Dict[str, Any]) -> bool:
    return bool(settings.get("enabled", True) and settings.get("persist_usage_ledger"))


def _safe_request(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    try:
        timestamp = float(item.get("timestamp"))
    except (TypeError, ValueError):
        return None
    provider = str(item.get("provider") or "")
    mode = str(item.get("mode") or "")
    if not provider or mode not in {"explain", "image_question"}:
        return None
    return {"timestamp": timestamp, "provider": provider, "mode": mode}


def _load_persisted_locked(settings: Dict[str, Any]) -> None:
    if not _persistence_enabled(settings):
        return
    try:
        raw = json.loads(LLM_BUDGET_JOURNAL.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except Exception:
        _REQUESTS.clear()
        _COOLDOWNS.clear()
        return
    if not isinstance(raw, dict):
        _REQUESTS.clear()
        _COOLDOWNS.clear()
        return

    requests = []
    for item in raw.get("requests") or []:
        safe = _safe_request(item)
        if safe:
            requests.append(safe)
    cooldowns: Dict[str, float] = {}
    if isinstance(raw.get("cooldowns"), dict):
        for provider, until in raw["cooldowns"].items():
            provider_id = str(provider or "")
            try:
                cooldown_until = float(until)
            except (TypeError, ValueError):
                continue
            if provider_id and cooldown_until > 0:
                cooldowns[provider_id] = cooldown_until

    _REQUESTS[:] = requests
    _COOLDOWNS.clear()
    _COOLDOWNS.update(cooldowns)


def _save_persisted_locked(settings: Dict[str, Any]) -> None:
    if not _persistence_enabled(settings):
        return
    if not _REQUESTS and not _COOLDOWNS and not LLM_BUDGET_JOURNAL.exists():
        return
    payload = {
        "schema_version": LLM_BUDGET_SCHEMA,
        "requests": list(_REQUESTS),
        "cooldowns": dict(_COOLDOWNS),
    }
    secure_write_json(LLM_BUDGET_JOURNAL, payload, sort_keys=True)


def _prune(now: float, window_seconds: int) -> None:
    cutoff = now - window_seconds
    _REQUESTS[:] = [item for item in _REQUESTS if float(item.get("timestamp") or 0) >= cutoff]
    expired = [provider for provider, until in _COOLDOWNS.items() if until <= now]
    for provider in expired:
        _COOLDOWNS.pop(provider, None)


def check_request(provider_id: str, mode: str, budget: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """Return whether a provider request may be attempted."""
    settings = _settings(budget)
    if not settings["enabled"]:
        return {"ok": True, "budget": {"enabled": False}}
    current = time.time() if now is None else float(now)
    window = int(settings["window_seconds"])
    with _LOCK:
        _load_persisted_locked(settings)
        _prune(current, window)
        _save_persisted_locked(settings)
        cooldown_until = float(_COOLDOWNS.get(provider_id) or 0)
        if cooldown_until > current:
            return {
                "ok": False,
                "reason_code": "provider_cooldown",
                "retry_after_s": int(cooldown_until - current),
            }
        total_count = len(_REQUESTS)
        max_total = int(settings["max_requests_per_hour"])
        if total_count >= max_total:
            return {
                "ok": False,
                "reason_code": "local_budget_exceeded",
                "limit": max_total,
                "window_s": window,
            }
        if mode == "image_question":
            image_count = sum(1 for item in _REQUESTS if item.get("mode") == "image_question")
            max_image = int(settings["max_image_requests_per_hour"])
            if image_count >= max_image:
                return {
                    "ok": False,
                    "reason_code": "local_image_budget_exceeded",
                    "limit": max_image,
                    "window_s": window,
                }
    return {"ok": True, "budget": {"window_s": window, "limit": max_total}}


def record_request(provider_id: str, mode: str, budget: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> None:
    settings = _settings(budget)
    if not settings["enabled"]:
        return
    current = time.time() if now is None else float(now)
    with _LOCK:
        _load_persisted_locked(settings)
        _prune(current, int(settings["window_seconds"]))
        if mode in {"explain", "image_question"}:
            _REQUESTS.append({"timestamp": current, "provider": str(provider_id), "mode": mode})
            _save_persisted_locked(settings)


def record_provider_result(provider_id: str, reason_code: str, budget: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> None:
    settings = _settings(budget)
    if not settings["enabled"]:
        return
    current = time.time() if now is None else float(now)
    cooldown = 0
    if reason_code == "rate_limited":
        cooldown = int(settings["cooldown_seconds_after_rate_limit"])
    elif reason_code == "quota_or_billing":
        cooldown = int(settings["cooldown_seconds_after_quota"])
    if cooldown <= 0:
        return
    with _LOCK:
        _load_persisted_locked(settings)
        _prune(current, int(settings["window_seconds"]))
        _COOLDOWNS[provider_id] = current + cooldown
        _save_persisted_locked(settings)


def status(budget: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """Return non-sensitive budget usage and cooldown status."""
    settings = _settings(budget)
    if not settings["enabled"]:
        return {
            "enabled": False,
            "persisted": False,
            "window_s": int(settings["window_seconds"]),
            "max_requests_per_hour": int(settings["max_requests_per_hour"]),
            "max_image_requests_per_hour": int(settings["max_image_requests_per_hour"]),
            "used_requests": 0,
            "remaining_requests": int(settings["max_requests_per_hour"]),
            "used_image_requests": 0,
            "remaining_image_requests": int(settings["max_image_requests_per_hour"]),
            "by_provider": {},
            "cooldowns": {},
        }
    current = time.time() if now is None else float(now)
    window = int(settings["window_seconds"])
    with _LOCK:
        _load_persisted_locked(settings)
        _prune(current, window)
        _save_persisted_locked(settings)

        by_provider: Dict[str, Dict[str, int]] = {}
        for item in _REQUESTS:
            provider = str(item.get("provider") or "")
            mode = str(item.get("mode") or "")
            if not provider:
                continue
            provider_status = by_provider.setdefault(provider, {"requests": 0, "image_requests": 0})
            provider_status["requests"] += 1
            if mode == "image_question":
                provider_status["image_requests"] += 1

        total_count = len(_REQUESTS)
        image_count = sum(1 for item in _REQUESTS if item.get("mode") == "image_question")
        max_total = int(settings["max_requests_per_hour"])
        max_image = int(settings["max_image_requests_per_hour"])
        cooldowns = {
            provider: {"retry_after_s": max(0, int(until - current))}
            for provider, until in sorted(_COOLDOWNS.items())
            if until > current
        }

    return {
        "enabled": True,
        "persisted": _persistence_enabled(settings),
        "window_s": window,
        "max_requests_per_hour": max_total,
        "max_image_requests_per_hour": max_image,
        "used_requests": total_count,
        "remaining_requests": max(0, max_total - total_count),
        "used_image_requests": image_count,
        "remaining_image_requests": max(0, max_image - image_count),
        "by_provider": by_provider,
        "cooldowns": cooldowns,
    }
