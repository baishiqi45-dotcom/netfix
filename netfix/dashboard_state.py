"""Resolve user-facing dashboard state from proxy / bridge / network signals.

Six states are exposed to the UI so the home screen can always answer
"what's going on with my Mac right now?" in plain language:

* ``no_proxy``         — nothing saved; user should paste parameters.
* ``proxy_saved``      — saved to Keychain but not yet applied to system.
* ``proxy_in_use``     — system proxy currently points to Netfix bridge.
* ``proxy_degraded``   — bridge running but a check failed; explain why.
* ``network_recovery`` — system proxy still points to a dead bridge or stale config.
* ``ready``            — saved or external proxy is up; nothing to fix.

The state is returned alongside a friendly headline / next step / colour
hint so Swift code can render it without leaking internal ids.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


_STATES = {
    "no_proxy": {
        "headline": "还没有粘贴代理参数",
        "next_step": "点「粘贴代理参数」，把服务商给的那一行粘进来。",
        "color": "secondary",
        "icon": "tray",
    },
    "proxy_saved": {
        "headline": "代理已保存到这台 Mac，但还没开始使用",
        "next_step": "点「开始使用代理」。",
        "color": "blue",
        "icon": "tray.and.arrow.down.fill",
    },
    "proxy_in_use": {
        "headline": "正在使用代理上网",
        "next_step": "Netfix 会持续检查网络状态；出问题时主动提示你。",
        "color": "green",
        "icon": "checkmark.shield.fill",
    },
    "proxy_degraded": {
        "headline": "代理还在用，但刚才一次检测没通过",
        "next_step": "点「一键诊断」看哪一项失败；常见原因是代理线路暂时不可用或账号临时失效。",
        "color": "orange",
        "icon": "exclamationmark.triangle.fill",
    },
    "network_recovery": {
        "headline": "系统网络需要恢复",
        "next_step": "点「恢复原来的网络设置」；不想恢复也可以直接退出 App。",
        "color": "red",
        "icon": "arrow.uturn.backward.circle.fill",
    },
    "ready": {
        "headline": "网络看起来正常",
        "next_step": "保持现状即可；想再确认一次就点「一键诊断」。",
        "color": "green",
        "icon": "checkmark.circle.fill",
    },
}


def states() -> Dict[str, Dict[str, str]]:
    """Return the full state table for Swift bootstrap / tests."""
    return {key: dict(value) for key, value in _STATES.items()}


def resolve(
    *,
    saved_profile_count: int,
    bridge_status: Optional[Dict[str, Any]] = None,
    last_diagnostic_status: Optional[str] = None,
    bridge_needs_recovery: bool = False,
    system_proxy_active_for_user: bool = False,
) -> Dict[str, Any]:
    """Pick one of the six dashboard states from the underlying signals."""
    bridge = bridge_status or {}
    lifecycle = bridge.get("lifecycle") if isinstance(bridge.get("lifecycle"), dict) else {}
    stale = bridge.get("stale_check") if isinstance(bridge.get("stale_check"), dict) else {}

    needs_recovery = bool(
        bridge_needs_recovery
        or lifecycle.get("status") in {"recovery_required", "check_failed"}
        or stale.get("recovery_available") is True
        or lifecycle.get("needs_attention") is True
    )

    in_use = bool(
        lifecycle.get("status") == "running_system"
        or lifecycle.get("systemPointsToBridge") is True
        or system_proxy_active_for_user
    )

    if saved_profile_count <= 0:
        state = "no_proxy"
    elif needs_recovery:
        state = "network_recovery"
    elif in_use:
        degraded = last_diagnostic_status in {"warn", "fail"}
        state = "proxy_degraded" if degraded else "proxy_in_use"
    else:
        state = "proxy_saved"

    payload = dict(_STATES.get(state, _STATES["ready"]))
    payload["state"] = state
    payload["saved_profile_count"] = int(saved_profile_count)
    payload["bridge_in_use"] = bool(in_use)
    payload["bridge_needs_recovery"] = bool(needs_recovery)
    return payload
