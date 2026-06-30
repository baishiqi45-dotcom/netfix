"""In-process residential/custom proxy health monitor for the local API."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from netfix import logs, residential_proxy, settings


_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_STATE: Dict[str, Any] = {
    "running": False,
    "profile_id": None,
    "profile_name": None,
    "interval": None,
    "target_url": None,
    "target_profile": "baseline",
    "timeout": None,
    "started_at": None,
    "stopped_at": None,
    "run_count": 0,
    "last_event": None,
    "last_error": None,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    for profile in settings.get_proxy_profiles():
        if profile_id in (str(profile.get("id") or ""), str(profile.get("name") or "")):
            return profile
    return None


def _set_state(**updates: Any) -> None:
    with _LOCK:
        _STATE.update(updates)


def _snapshot() -> Dict[str, Any]:
    with _LOCK:
        state = dict(_STATE)
        thread_alive = bool(_THREAD and _THREAD.is_alive())
    state["thread_alive"] = thread_alive
    state["persisted"] = settings.get_proxy_monitor_settings()
    return {"ok": True, "monitor": state}


def _repair_action(action_id: str, label: str, detail: str, ui_type: str = "", profile_id: str = "") -> Dict[str, Any]:
    action: Dict[str, Any] = {"id": action_id, "label": label, "detail": detail}
    if ui_type:
        action["ui_action"] = {"type": ui_type, "profile_id": profile_id}
    return action


def repair_actions_for_check(check: Dict[str, Any]) -> list:
    """Return safe user-facing next steps for a failed monitor check."""
    if str(check.get("status") or "") in {"ok", "warn"} and not check.get("error"):
        return []
    error = str(check.get("error") or "")
    auth = str(check.get("auth") or "")
    profile_id = str(check.get("profile_id") or "")
    actions = []

    if error in {"proxy_auth_required", "proxy_auth_failed"} or auth == "failed":
        actions.extend([
            _repair_action(
                "update_proxy_credentials",
                "重新输入代理账号/密码",
                "供应商返回认证失败或需要认证；复制供应商最新 host、端口、用户名和密码后重新保存 Profile。",
                "replace_profile_credentials",
                profile_id,
            ),
            _repair_action(
                "save_and_restart_monitor",
                "保存后重新启动监控",
                "重新保存凭据后使用当前验证矩阵启动后台监控，确认新密码可用。",
                "start_monitor",
                profile_id,
            ),
        ])
    elif error in {"timeout", "dns_failed", "connection_refused"}:
        actions.extend([
            _repair_action(
                "check_provider_endpoint",
                "核对供应商入口",
                "确认 host、端口、协议和账号仍有效；住宅 IP 过期或供应商入口变化时需要换新凭据。",
                "replace_profile_credentials",
                profile_id,
            ),
            _repair_action(
                "choose_next_candidate",
                "切换到下一个候选代理",
                "把供应商列表重新粘贴到批量预检，选择另一个可用候选保存并监控。",
                "import_preview",
                profile_id,
            ),
        ])
    elif error in {"target_matrix_not_fully_validated", "identity_validation_failed"}:
        actions.extend([
            _repair_action(
                "review_validation_matrix",
                "检查验证矩阵",
                "当前代理可连通但没有完整通过所选目标矩阵；切换矩阵或查看失败目标后再决定是否使用。",
                "validate_profile",
                profile_id,
            ),
            _repair_action(
                "export_client_package",
                "导出客户端配置包",
                "如果系统代理路径不适合当前目标，可导出 Mihomo/Clash/sing-box 配置到目标客户端中验证。",
                "export_profile",
                profile_id,
            ),
        ])
    elif error in {"missing_keychain_password", "invalid profile", "target_profile_not_allowed", "target_url_not_allowed"}:
        actions.append(_repair_action(
            "resave_profile",
            "重新保存 Profile",
            "本地配置不完整或验证目标不被允许；重新粘贴供应商凭据并保存为新的 Profile。",
            "save_profile",
            profile_id,
        ))
    else:
        actions.extend([
            _repair_action(
                "rerun_validation",
                "重新验证",
                "网络状态可能短暂波动；先刷新监控或手动验证一次。",
                "validate_profile",
                profile_id,
            ),
            _repair_action(
                "choose_next_candidate",
                "切换到下一个候选代理",
                "如果连续失败，重新批量预检供应商列表并保存另一个候选。",
                "import_preview",
                profile_id,
            ),
        ])

    deduped = []
    seen = set()
    for action in actions:
        if action["id"] in seen:
            continue
        seen.add(action["id"])
        deduped.append(action)
    return deduped


def _record_check(profile: Dict[str, Any], result: Dict[str, Any], run_count: int) -> Dict[str, Any]:
    check = dict(result.get("proxy_check") or {})
    check["checked_at"] = _utc_now()
    repair_actions = repair_actions_for_check(check)
    check["repair_actions"] = repair_actions
    updated = dict(profile)
    updated["last_check"] = check
    settings.upsert_proxy_profile(updated)
    status = str(check.get("status") or "fail")
    event = {
        "type": "proxy_monitor",
        "event": "proxy_check",
        "status": status,
        "profile_id": profile.get("id"),
        "profile_name": profile.get("name"),
        "run": run_count,
        "headline": f"Proxy {profile.get('name') or profile.get('id')} {status}",
        "proxy_check": check,
        "repair_actions": repair_actions,
    }
    logs.append_event(event)
    return event


def run_once(
    profile_id: str,
    target_url: str = "https://www.gstatic.com/generate_204",
    timeout: int = 10,
    target_profile: str = "baseline",
) -> Dict[str, Any]:
    """Validate one saved profile and persist last_check plus a local event."""
    profile = _find_profile(profile_id)
    if profile is None:
        event = {
            "type": "proxy_monitor",
            "event": "profile_missing",
            "status": "fail",
            "profile_id": profile_id,
            "headline": f"Proxy profile not found: {profile_id}",
        }
        logs.append_event(event)
        return {"ok": False, "error": f"profile not found: {profile_id}", "event": event}
    result = residential_proxy.validate_saved_profile(
        profile,
        target_url=target_url,
        timeout=timeout,
        include_identity=target_profile != "baseline",
        target_profile=target_profile,
    )
    event = _record_check(profile, result, run_count=1)
    return {
        "ok": bool(result.get("ok")),
        "proxy_check": event.get("proxy_check"),
        "repair_actions": event.get("repair_actions", []),
        "event": event,
    }


def _loop(profile_id: str, interval: int, target_url: str, timeout: int, target_profile: str) -> None:
    run_count = 0
    try:
        while not _STOP.is_set():
            profile = _find_profile(profile_id)
            if profile is None:
                error = f"profile not found: {profile_id}"
                event = {
                    "type": "proxy_monitor",
                    "event": "profile_missing",
                    "status": "fail",
                    "profile_id": profile_id,
                    "headline": error,
                }
                logs.append_event(event)
                _set_state(running=False, last_error=error, last_event=event, stopped_at=_utc_now())
                return

            run_count += 1
            result = residential_proxy.validate_saved_profile(
                profile,
                target_url=target_url,
                timeout=timeout,
                include_identity=target_profile != "baseline",
                target_profile=target_profile,
            )
            event = _record_check(profile, result, run_count)
            _set_state(
                running=True,
                run_count=run_count,
                profile_id=profile.get("id"),
                profile_name=profile.get("name"),
                target_profile=target_profile,
                last_event=event,
                last_error=None if result.get("ok") else event.get("proxy_check", {}).get("error"),
            )
            if _STOP.wait(interval):
                break
    finally:
        _set_state(running=False, stopped_at=_utc_now())


def _stop_thread() -> None:
    global _THREAD
    thread = _THREAD
    if thread and thread.is_alive():
        _STOP.set()
        thread.join(timeout=5)
    _THREAD = None
    _STOP.clear()


def start(
    profile_id: str,
    interval: int = 60,
    target_url: str = "https://www.gstatic.com/generate_204",
    timeout: int = 10,
    target_profile: str = "baseline",
    *,
    persist: bool = True,
    restored: bool = False,
) -> Dict[str, Any]:
    """Start or replace the API-process background monitor."""
    interval = max(15, min(int(interval or 60), 3600))
    timeout = max(1, min(int(timeout or 10), 60))
    profile = _find_profile(profile_id)
    if profile is None:
        return {"ok": False, "error": f"profile not found: {profile_id}"}

    _stop_thread()
    _set_state(running=False, stopped_at=_utc_now())
    if persist:
        settings.update_proxy_monitor_settings({
            "enabled": True,
            "profile_id": str(profile.get("id") or profile_id),
            "interval": interval,
            "target_url": target_url,
            "target_profile": target_profile,
            "timeout": timeout,
            "updated_at": _utc_now(),
        })
    _STOP.clear()
    _set_state(
        running=True,
        profile_id=profile.get("id"),
        profile_name=profile.get("name"),
        interval=interval,
        target_url=target_url,
        target_profile=target_profile,
        timeout=timeout,
        started_at=_utc_now(),
        stopped_at=None,
        run_count=0,
        last_event=None,
        last_error=None,
        restored=restored,
    )
    global _THREAD
    _THREAD = threading.Thread(target=_loop, args=(str(profile.get("id") or profile_id), interval, target_url, timeout, target_profile), daemon=True)
    _THREAD.start()
    return _snapshot()


def stop(*, persist: bool = True) -> Dict[str, Any]:
    """Stop the current background monitor if it is running."""
    _stop_thread()
    if persist:
        settings.update_proxy_monitor_settings({
            "enabled": False,
            "profile_id": "",
            "updated_at": _utc_now(),
        })
    _set_state(running=False, stopped_at=_utc_now())
    return _snapshot()


def status() -> Dict[str, Any]:
    """Return current in-process monitor state."""
    return _snapshot()


def restore_from_settings() -> Dict[str, Any]:
    """Restart the persisted monitor after API/backend startup."""
    persisted = settings.get_proxy_monitor_settings()
    if not persisted.get("enabled") or not persisted.get("profile_id"):
        return {"ok": True, "restored": False, "reason": "monitor_disabled", "monitor": status().get("monitor")}
    result = start(
        str(persisted.get("profile_id") or ""),
        interval=int(persisted.get("interval") or 60),
        target_url=str(persisted.get("target_url") or "https://www.gstatic.com/generate_204"),
        timeout=int(persisted.get("timeout") or 10),
        target_profile=str(persisted.get("target_profile") or "baseline"),
        persist=False,
        restored=True,
    )
    if not result.get("ok"):
        _set_state(
            running=False,
            profile_id=persisted.get("profile_id"),
            interval=persisted.get("interval"),
            target_url=persisted.get("target_url"),
            target_profile=persisted.get("target_profile") or "baseline",
            timeout=persisted.get("timeout"),
            last_error=result.get("error"),
            stopped_at=_utc_now(),
            restored=True,
        )
    result["restored"] = bool(result.get("ok"))
    return result
