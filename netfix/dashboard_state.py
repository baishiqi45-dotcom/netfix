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

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


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
        "next_step": "点「检查当前网络」看哪一项失败；常见原因是代理线路暂时不可用或账号临时失效。",
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
        "next_step": "保持现状即可；想再确认一次就点「检查当前网络」。",
        "color": "green",
        "icon": "checkmark.circle.fill",
    },
    "unknown": {
        "headline": "暂时读不到这台 Mac 的代理状态",
        "next_step": "点「检查当前网络」重新读取；代理、日志和设置仍可使用。",
        "color": "secondary",
        "icon": "questionmark.circle",
    },
}


_ACTION_COPY = {
    "paste_proxy": ("粘贴代理参数", "flow:proxy_setup"),
    "start_saved_proxy": ("继续设置代理", "flow:proxy_setup"),
    "recover_system_proxy": ("恢复原来的网络设置", "recover:stale_bridge"),
    "verify_current_proxy": ("检查当前网络", "run:doctor"),
    "diagnose": ("检查当前网络", "run:doctor"),
    "none": ("无需操作", "none"),
}


def states() -> Dict[str, Dict[str, str]]:
    """Return the full state table for Swift bootstrap / tests."""
    return {key: dict(value) for key, value in _STATES.items()}


def _redact_endpoint(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if "@" not in value:
        return value
    scheme, sep, rest = value.partition("://")
    if sep:
        return f"{scheme}://***:***@{rest.rsplit('@', 1)[-1]}"
    return f"***:***@{value.rsplit('@', 1)[-1]}"


def _proxy_entry_enabled(entry: Any) -> bool:
    if isinstance(entry, str):
        return bool(entry)
    if isinstance(entry, dict):
        if "enabled" in entry:
            return bool(entry.get("enabled"))
        return any(bool(entry.get(key)) for key in ("server", "host", "endpoint", "url"))
    return bool(entry)


def _normalize_proxy_entry(entry: Any) -> Any:
    if isinstance(entry, dict):
        out = dict(entry)
        for key in ("password", "secret", "token"):
            out.pop(key, None)
        for key, value in list(out.items()):
            out[key] = _redact_endpoint(value)
        return out
    return _redact_endpoint(entry)


def _proxy_detection_status(environment: Optional[Dict[str, Any]]) -> str:
    env = environment if isinstance(environment, dict) else {}
    if env.get("ok") is False:
        return "unknown"
    proxy = env.get("system_proxy")
    if isinstance(proxy, dict) and proxy.get("_detection_status") == "unknown":
        return "unknown"
    return "ok"


def _route_proxy_value(entry: Any) -> Any:
    if isinstance(entry, dict):
        if "enabled" in entry and not entry.get("enabled"):
            return None
        endpoint = entry.get("endpoint") or entry.get("url")
        if not endpoint:
            host = entry.get("server") or entry.get("host")
            port = entry.get("port")
            endpoint = f"{host}:{port}" if host and port else host
        return _redact_endpoint(endpoint)
    return _redact_endpoint(entry)


def build_route_signature(environment: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return an opaque, non-secret identity for the currently selected route."""
    env = environment if isinstance(environment, dict) else {}
    if _proxy_detection_status(env) != "ok":
        return None
    proxy = env.get("system_proxy") if isinstance(env.get("system_proxy"), dict) else {}
    profile = env.get("active_profile") if isinstance(env.get("active_profile"), dict) else {}
    facts = {
        "system_proxy": {
            key: _route_proxy_value(proxy.get(key))
            for key in ("http", "https", "socks", "pac")
        },
        "active_core": env.get("active_core") or env.get("gui_client"),
        "active_profile_id": profile.get("id"),
        "mixed_port": env.get("mixed_port"),
    }
    encoded = json.dumps(facts, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    # Keep the opaque value short enough that balanced report redaction does
    # not mistake it for a bearer token. The digest still identifies route
    # changes without persisting the proxy endpoint or profile id.
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    return f"route:v1:{digest}"


def _system_proxy_summary(environment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    proxy = (environment or {}).get("system_proxy")
    if not isinstance(proxy, dict):
        proxy = {}
    active_keys: List[str] = [
        key for key in ("http", "https", "socks", "pac") if _proxy_entry_enabled(proxy.get(key))
    ]
    manual_keys = [key for key in active_keys if key in {"http", "https", "socks"}]
    if not active_keys:
        kind = "none"
    elif "pac" in active_keys and manual_keys:
        kind = "mixed"
    elif "pac" in active_keys:
        kind = "pac"
    elif {"http", "https"}.issubset(set(active_keys)) and len(active_keys) == 2:
        kind = "http_https"
    elif "socks" in active_keys and len(active_keys) > 1:
        kind = "mixed"
    elif "socks" in active_keys:
        kind = "socks"
    else:
        kind = active_keys[0]
    return {
        "active": bool(active_keys),
        "detection_status": _proxy_detection_status(environment),
        "kind": kind,
        "redacted": {key: _normalize_proxy_entry(proxy.get(key)) for key in ("http", "https", "socks", "pac") if proxy.get(key)},
        "network_service": proxy.get("network_service") or proxy.get("service"),
    }


def _bridge_facts(bridge_status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    bridge = bridge_status or {}
    lifecycle = bridge.get("lifecycle") if isinstance(bridge.get("lifecycle"), dict) else {}
    stale = bridge.get("stale_check") if isinstance(bridge.get("stale_check"), dict) else {}
    status = str(lifecycle.get("status") or bridge.get("status") or "unknown")
    recovery_available = bool(stale.get("recovery_available") or lifecycle.get("recovery_available"))
    needs_recovery = bool(status == "recovery_required" or recovery_available)
    in_use = bool(status == "running_system" or lifecycle.get("systemPointsToBridge") is True)
    return {
        "lifecycle_status": status,
        "in_use": in_use,
        "needs_recovery": needs_recovery,
        "recovery_available": bool(recovery_available or status == "recovery_required"),
        "profile_id": lifecycle.get("profile_id") or stale.get("profile_id") or bridge.get("profile_id"),
    }


def _machine_summary(machine_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    machine = machine_state or {}
    return {
        "platform": machine.get("platform"),
        "primary_interface": machine.get("primary_interface"),
        "self_ipv4": machine.get("self_ipv4"),
        "self_ipv6": machine.get("self_ipv6") or [],
        "gateway": machine.get("gateway"),
        "has_ipv6_default_route": bool(machine.get("has_ipv6_default_route")),
    }


def _egress_summary(egress_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    egress = egress_summary or {}
    status = egress.get("status") if egress.get("status") in {"unchecked", "ok", "warn", "fail", "stale"} else "unchecked"
    return {
        "status": status,
        "public_ipv4": egress.get("public_ipv4") or egress.get("ip"),
        "isp": egress.get("isp"),
        "asn": egress.get("asn"),
        "ip_type": egress.get("ip_type"),
        "risk_score": egress.get("risk_score"),
        "same_as_local": egress.get("same_as_local"),
        "cached": bool(egress.get("cached")),
        "source": egress.get("source"),
        "checked_at": egress.get("checked_at"),
    }


def _action_copy(action_id: Optional[str]) -> Tuple[str, str]:
    return _ACTION_COPY.get(str(action_id or "diagnose"), _ACTION_COPY["diagnose"])


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness(checked_at: Any, stale: Any = None) -> Dict[str, Any]:
    parsed = _parse_datetime(checked_at)
    age_seconds: Optional[int] = None
    if parsed:
        age_seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    if stale is None:
        stale = bool(age_seconds is not None and age_seconds > 3600)
    return {
        "checked_at": checked_at,
        "age_seconds": age_seconds,
        "stale": bool(stale),
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _diagnostic_counts(summary: Dict[str, Any]) -> Dict[str, int]:
    raw = summary.get("diagnostic_counts") if isinstance(summary.get("diagnostic_counts"), dict) else {}
    counts: Dict[str, int] = {}
    for key, value in raw.items():
        counts[str(key)] = _safe_int(value)
    return counts


def _severity_from_report(summary: Dict[str, Any]) -> Optional[str]:
    severity = summary.get("severity") or summary.get("status")
    if severity in {"ok", "info", "warn", "fail"}:
        return str(severity)
    return None


def _status_from_report(summary: Dict[str, Any]) -> Optional[str]:
    status = summary.get("status")
    if status in {"ok", "warn", "fail"}:
        return str(status)
    return None


def _metric(raw: Any, *, label: str, value: str, hint: str) -> Dict[str, str]:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "label": str(raw.get("label") or label),
        "value": str(raw.get("value") or value),
        "hint": str(raw.get("hint") or hint),
    }


def build_connection_quality(last_report_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalize the dashboard's first-screen network feel strip.

    The API extracts metrics from the latest report when available. This helper
    guarantees App/Web can always render the four user-facing cells without
    parsing diagnostics or silently hiding speed / latency when no sample exists.
    """
    summary = last_report_summary if isinstance(last_report_summary, dict) else {}
    if summary.get("has_report") and summary.get("usable_for_dashboard") is False:
        # Keep historical or route-mismatched metrics in last_report_summary;
        # the current-route strip must not render them as current evidence.
        summary = {}
    raw = summary.get("connection_quality") if isinstance(summary.get("connection_quality"), dict) else {}
    checked_at = raw.get("checked_at") or summary.get("checked_at")
    stale = bool(raw.get("stale") if "stale" in raw else summary.get("stale"))
    collection_state = str(raw.get("collection_state") or "")
    if stale:
        collection_state = "stale"
    elif collection_state not in {"never_run", "complete", "partial", "unavailable"}:
        collection_state = "unavailable" if summary.get("has_report") or checked_at else "never_run"
    copy = {
        "never_run": ("unchecked", "还没检查网络体感", "运行一次检查后，这里会显示实际采到的数据。"),
        "complete": (str(raw.get("status") or "ok"), str(raw.get("headline") or "网络体感已测"), str(raw.get("detail") or "来自最近一次完整检查，不会额外测速。")),
        "partial": (str(raw.get("status") or "partial"), str(raw.get("headline") or "已采到部分数据"), str(raw.get("detail") or "有些项目本机没有返回结果，已显示可用部分。")),
        "unavailable": ("unchecked", "本机未能采样", "检查已完成，但这台 Mac 没有返回速度、延迟或稳定性数据。"),
        "stale": ("stale", "上次体感数据已过期", "线路或时间已经变化，请重新检查后再参考。"),
    }
    status, headline, detail = copy[collection_state]
    missing_hint = "本机未返回这项数据。"
    source = str(raw.get("source") or ("last_report" if checked_at else "none"))
    return {
        "status": status,
        "headline": headline,
        "detail": detail,
        "collection_state": collection_state,
        "speed": _metric(raw.get("speed"), label="未测", value="未采到", hint=missing_hint),
        "latency": _metric(raw.get("latency"), label="未测", value="未采到", hint=missing_hint),
        "stability": _metric(raw.get("stability"), label="未测", value="未采到", hint=missing_hint),
        "background_activity": _metric(raw.get("background_activity"), label="未测", value="未采到", hint="本机未返回这项数据；只看占用，不看内容。"),
        "checked_at": checked_at,
        "stale": collection_state == "stale",
        "source": source,
    }


def _next_step_for_action(label: str, *, prefix: Optional[str] = None) -> str:
    if prefix:
        return f"{prefix}，下一步点「{label}」。"
    if label == "无需操作":
        return "当前没有需要立即处理的动作。"
    return f"下一步点「{label}」。"


def build_dashboard_verdict(
    *,
    state: Dict[str, Any],
    last_report_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the single user-facing dashboard verdict for App/Web v2."""
    summary = last_report_summary if isinstance(last_report_summary, dict) else {}
    decision = state.get("decision") if isinstance(state.get("decision"), dict) else {}
    state_id = str(state.get("state") or decision.get("ui_state") or "ready")
    effective_route = str(decision.get("effective_route") or "")
    action_id = str(decision.get("primary_action") or "diagnose")
    action_label, action_target = _action_copy(action_id)
    checked_at = summary.get("checked_at")
    freshness = _freshness(checked_at, summary.get("stale"))
    diagnostic_counts = _diagnostic_counts(summary)
    issue_count = _safe_int(summary.get("issue_count"))
    blocking_issue_count = _safe_int(summary.get("blocking_issue_count"))
    advisory_count = _safe_int(summary.get("advisory_count"))
    report_status = _status_from_report(summary)
    report_severity = _severity_from_report(summary)
    valid_sample_count = _safe_int(summary.get("valid_sample_count"))
    connection_quality = (
        summary.get("connection_quality")
        if isinstance(summary.get("connection_quality"), dict)
        else {}
    )
    quality_status = str(connection_quality.get("status") or "unknown")
    fresh_report = bool(
        freshness["checked_at"]
        and not freshness["stale"]
        and summary.get("usable_for_dashboard") is True
        and summary.get("route_matches_current") is True
        and summary.get("coverage") == "current_mac_full"
        and valid_sample_count > 0
    )
    if not fresh_report:
        report_status = None
        report_severity = None
        issue_count = 0
        blocking_issue_count = 0
        advisory_count = 0

    status = "unknown"
    severity = str(decision.get("severity") or "info")
    usability = "unknown"
    # Verdict narrative copy comes from state/decision, NOT from the journal
    # report's `explanation.headline`. A stale codex/triage run from another
    # scope must not leak its headline into the home verdict.
    headline = str(decision.get("headline") or state.get("headline") or "当前状态未知")
    detail = str(summary.get("detail") or summary.get("description") or "") if fresh_report else ""
    prefix: Optional[str] = None
    route_health = report_status if fresh_report and report_status else str(decision.get("route_health") or "unknown")
    if route_health not in {"unknown", "ok", "warn", "fail"}:
        route_health = "unknown"

    if state_id == "network_recovery" or effective_route == "recovery_required":
        status = "blocked"
        severity = "fail"
        usability = "blocked"
        issue_count = max(issue_count, 1)
        blocking_issue_count = max(blocking_issue_count, 1)
        headline = str(decision.get("headline") or state.get("headline") or "系统网络需要恢复")
        detail = "系统代理仍指向需要恢复的配置；先恢复，再继续检查。"
        prefix = "先恢复系统网络设置"
        route_health = "fail"
    elif fresh_report and issue_count > 0 and (report_status == "fail" or report_severity == "fail"):
        status = "degraded"
        severity = "fail"
        usability = "degraded"
        if not detail:
            detail = "最新检查发现当前连接路径有失败项。"
        prefix = "最新检查有失败项"
    elif fresh_report and (issue_count > 0 or report_status == "warn" or report_severity == "warn"):
        status = "attention"
        severity = "warn"
        usability = "usable"
        if not detail:
            detail = "最新检查有需要确认的项目，但未发现必须立即恢复的阻断。"
        prefix = "最新检查需要确认"
    elif state_id == "proxy_degraded" and route_health in {"warn", "fail"}:
        status = "degraded" if route_health == "fail" else "attention"
        severity = "fail" if route_health == "fail" else "warn"
        usability = "degraded"
        detail = "当前线路刚刚返回了异常信号；重新检查后再决定是否换线路。"
        prefix = "当前线路需要复查"
    elif state_id == "no_proxy":
        status = "unknown"
        severity = "info"
        usability = "unknown"
        headline = str(decision.get("headline") or state.get("headline") or "还没有粘贴代理参数")
        detail = "当前没有 Netfix 保存或启用的代理；仍可以先检查当前网络。"
    elif state_id == "proxy_saved":
        status = "attention"
        severity = "info"
        usability = "unknown"
        headline = str(decision.get("headline") or state.get("headline") or "代理已保存到这台 Mac")
        detail = "代理已经保存，但系统网络还没有切到这条线路。"
    elif fresh_report and quality_status in {"warn", "fail"}:
        # Keep route ownership/health separate from user-perceived quality.
        # A slow but reachable route is not a broken proxy, yet the single
        # verdict must acknowledge the delay instead of showing a green
        # "normal" headline next to a high-latency metric.
        status = "attention"
        severity = "warn"
        usability = "degraded"
        headline = str(connection_quality.get("headline") or "网络可用，但体感需要留意")
        quality_detail = str(connection_quality.get("detail") or "当前速度、延迟或稳定性需要留意。")
        detail = f"当前线路可用；{quality_detail}"
        prefix = "线路可用但体感需要留意"
    elif fresh_report:
        # Only emit a green ok status when the report actually has diagnostics
        # and they are not silent "unchecked"/"unknown" placeholders. A report
        # whose every status is unchecked is functionally no signal.
        counts_alive = any(
            value for key, value in diagnostic_counts.items() if key in {"ok", "warn", "fail"}
        )
        if counts_alive:
            status = "ok"
            severity = "ok" if report_status == "ok" or report_severity == "ok" else "info"
            usability = "usable"
        else:
            status = "unknown"
            severity = "info"
            usability = "unknown"
        if not detail:
            detail = "最新检查没有发现当前范围里的失败项。" if status == "ok" else "最新一轮检查没有给出有效证据。"
    else:
        # No fresh report: severity must not be ok, and status must be
        # unknown regardless of route. We still describe the route copy
        # below.
        status = "unknown"
        severity = "info"
        usability = "unknown"
        if effective_route == "external_system_proxy":
            headline = "检测到系统代理，尚未确认可用"
        if not detail:
            detail = (
                "这台 Mac 正在使用系统代理；点「检查当前网络」确认速度、延迟和目标网站连通性。"
                if effective_route == "external_system_proxy"
                else "还没有本轮检查证据；当前只显示系统代理和本机网络身份。"
            )

    verdict = {
        "status": status,
        "severity": severity if severity in {"ok", "info", "warn", "fail"} else "info",
        "usability": usability,
        "route_health": route_health,
        "headline": headline,
        "detail": detail,
        "next_step": _next_step_for_action(action_label, prefix=prefix),
        "issue_count": issue_count,
        "blocking_issue_count": blocking_issue_count,
        "advisory_count": advisory_count,
        "diagnostic_counts": diagnostic_counts,
        "primary_action": {
            "id": action_id,
            "label": action_label,
            "enabled": action_id != "none",
            "target": action_target,
            "requires_confirmation": bool(decision.get("requires_confirmation")),
        },
        "freshness": freshness,
    }
    if effective_route == "netfix_applied":
        verdict["secondary_action"] = {
            "id": "stop_and_restore",
            "label": "停止使用并恢复原设置",
            "enabled": True,
            "target": "recover:stale_bridge",
            "requires_confirmation": True,
        }
    return verdict


def build_dashboard_presentation(
    verdict: Dict[str, Any],
    *,
    current_state: Optional[str] = None,
    effective_route: Optional[str] = None,
) -> Dict[str, Any]:
    """Return dashboard section gating for first screen vs technical evidence.

    The presentation contract must reflect BOTH the verdict (severity, freshness,
    issue counts) and the high-level state/route. The result is consumed by
    macOS DashboardView and the Web console; both must honor the same gating.
    """
    visible_sections = ["current_status", "connection_quality"]
    collapsed_sections: List[str] = ["diagnostic_evidence"]
    suppressed_sections: List[Dict[str, str]] = []

    # AI remains an explicitly opened auxiliary tool. A warning must not add
    # another first-screen narrative or disclosure beside the one verdict.
    suppressed_sections.append({"id": "ai", "reason": "optional_support"})

    # Always suppress the historical/log chrome on first paint.
    suppressed_sections.extend([
        {"id": "first_aid", "reason": "not_current_scope"},
        {"id": "diagnose_goals", "reason": "not_current_scope"},
        {"id": "network_quality", "reason": "merged_into_connection_quality"},
        {"id": "latest_result", "reason": "merged_into_current_status"},
        {"id": "logs", "reason": "history_only"},
        {"id": "proxy_trend", "reason": "history_only"},
        {"id": "recent_events", "reason": "history_only"},
    ])

    def unique(values: List[str]) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for value in values:
            if value not in seen:
                out.append(value)
                seen.add(value)
        return out

    visible_sections = unique(visible_sections)
    collapsed_sections = [item for item in unique(collapsed_sections) if item not in set(visible_sections)]
    occupied = set(visible_sections) | set(collapsed_sections)
    suppressed_unique: List[Dict[str, str]] = []
    suppressed_seen: set[str] = set()
    for item in suppressed_sections:
        section_id = str(item.get("id") or "")
        if not section_id or section_id in occupied or section_id in suppressed_seen:
            continue
        suppressed_unique.append({"id": section_id, "reason": str(item.get("reason") or "not_current_scope")})
        suppressed_seen.add(section_id)

    return {
        "visible_sections": visible_sections,
        "collapsed_sections": collapsed_sections,
        "suppressed_sections": suppressed_unique,
    }


def _decision_for_state(
    *,
    state: str,
    effective_route: str,
    headline: str,
    next_step: str,
    reason_codes: List[str],
    route_health: str = "unknown",
) -> Dict[str, Any]:
    action_map = {
        "no_proxy": ("paste_proxy", False, "info"),
        "proxy_saved": ("start_saved_proxy", True, "info"),
        "proxy_in_use": ("diagnose", False, "ok"),
        "proxy_degraded": ("diagnose", False, "warn"),
        "network_recovery": ("recover_system_proxy", True, "fail"),
        "ready": ("verify_current_proxy" if effective_route == "external_system_proxy" else "diagnose", False, "ok"),
        "unknown": ("diagnose", False, "info"),
    }
    primary_action, requires_confirmation, severity = action_map.get(state, ("diagnose", False, "info"))
    return {
        "ui_state": state,
        "effective_route": effective_route,
        "severity": severity,
        "primary_action": primary_action,
        "reason_codes": reason_codes,
        "headline": headline,
        "next_step": next_step,
        "requires_confirmation": requires_confirmation,
        "route_health": route_health,
    }


_NEGATIVE_STATUSES = {"warn", "fail"}


def _last_status_is_negative(value: Optional[str]) -> bool:
    return isinstance(value, str) and value in _NEGATIVE_STATUSES


def resolve(
    *,
    saved_profile_count: int,
    bridge_status: Optional[Dict[str, Any]] = None,
    last_diagnostic_status: Optional[str] = None,
    bridge_needs_recovery: bool = False,
    system_proxy_active_for_user: bool = False,
    live_signals: Optional[Dict[str, Any]] = None,
    system_proxy_detection_status: str = "ok",
) -> Dict[str, Any]:
    """Pick one of the six dashboard states from the underlying signals.

    `last_diagnostic_status` of `None`, `""`, or any "unknown/unchecked/notSampled"
    sentinel is intentionally treated as "no fresh verification" — the home view
    should still claim a known Netfix route, but the verdict layer below must not
    emit a green checkmark for a stale or absent report. Live monitor signals
    (when supplied) can also push a Netfix-applied or external proxy route down
    to a degraded state.
    """
    bridge = _bridge_facts(bridge_status)
    needs_recovery = bool(bridge_needs_recovery or bridge.get("needs_recovery"))
    netfix_in_use = bool(bridge.get("in_use"))
    external_system_proxy = bool(system_proxy_active_for_user and not netfix_in_use)
    live = live_signals if isinstance(live_signals, dict) else {}
    live_status_raw = live.get("proxy_monitor_status") or live.get("monitor_status") or live.get("status")
    live_status_negative = isinstance(live_status_raw, str) and live_status_raw in _NEGATIVE_STATUSES
    last_negative = _last_status_is_negative(last_diagnostic_status)

    if needs_recovery:
        state = "network_recovery"
        effective_route = "netfix_applied"
        reason_codes = ["bridge_needs_recovery"]
    elif netfix_in_use:
        degraded = last_negative or live_status_negative
        state = "proxy_degraded" if degraded else "proxy_in_use"
        effective_route = "netfix_applied"
        if last_negative:
            reason_codes = [f"last_diagnostic_{last_diagnostic_status}"]
        elif live_status_negative:
            reason_codes = [f"live_monitor_{live_status_raw}"]
        else:
            reason_codes = ["netfix_bridge_in_use"]
    elif external_system_proxy:
        # External system proxy route: only show "ready" when there is no
        # negative report AND no live monitor failure. If the latest journal
        # report says warn/fail, OR live proxy/network monitor reports
        # warn/fail, surface degraded so the user is not lulled into a green
        # checkmark for a broken proxy.
        if last_negative:
            state = "proxy_degraded"
            effective_route = "external_system_proxy"
            reason_codes = [f"external_proxy_last_{last_diagnostic_status}"]
        elif live_status_negative:
            state = "proxy_degraded"
            effective_route = "external_system_proxy"
            reason_codes = [f"external_proxy_live_{live_status_raw}"]
        else:
            state = "ready"
            effective_route = "external_system_proxy"
            reason_codes = ["external_system_proxy_active"]
    elif system_proxy_detection_status != "ok":
        state = "unknown"
        effective_route = "unknown"
        reason_codes = ["system_proxy_state_unavailable"]
    elif saved_profile_count > 0:
        state = "proxy_saved"
        effective_route = "saved_only"
        reason_codes = ["saved_profile_not_applied"]
    else:
        state = "no_proxy"
        effective_route = "none"
        reason_codes = ["no_saved_profile_or_system_proxy"]

    payload = dict(_STATES.get(state, _STATES["ready"]))
    payload["state"] = state
    payload["saved_profile_count"] = int(saved_profile_count)
    payload["bridge_in_use"] = bool(netfix_in_use or system_proxy_active_for_user)
    payload["bridge_needs_recovery"] = bool(needs_recovery)
    route_health = "fail" if needs_recovery else (
        str(last_diagnostic_status)
        if last_diagnostic_status in {"ok", "warn", "fail"}
        else (str(live_status_raw) if live_status_raw in {"ok", "warn", "fail"} else "unknown")
    )
    payload["decision"] = _decision_for_state(
        state=state,
        effective_route=effective_route,
        headline=str(payload["headline"]),
        next_step=str(payload["next_step"]),
        reason_codes=reason_codes,
        route_health=route_health,
    )
    return payload


def build_current_mac_state(
    *,
    saved_profile_count: int,
    bridge_status: Optional[Dict[str, Any]] = None,
    environment: Optional[Dict[str, Any]] = None,
    machine_state: Optional[Dict[str, Any]] = None,
    egress_summary: Optional[Dict[str, Any]] = None,
    last_report_summary: Optional[Dict[str, Any]] = None,
    last_diagnostic_status: Optional[str] = None,
    profiles: Optional[List[Dict[str, Any]]] = None,
    live_signals: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the authoritative current-Mac dashboard contract."""
    system_proxy = _system_proxy_summary(environment)
    bridge = _bridge_facts(bridge_status)
    state = resolve(
        saved_profile_count=saved_profile_count,
        bridge_status=bridge_status,
        last_diagnostic_status=last_diagnostic_status,
        bridge_needs_recovery=bool(bridge.get("needs_recovery")),
        system_proxy_active_for_user=bool(system_proxy.get("active")),
        live_signals=live_signals,
        system_proxy_detection_status=str(system_proxy.get("detection_status") or "unknown"),
    )
    selected = None
    for profile in profiles or []:
        if isinstance(profile, dict):
            selected = str(profile.get("id") or "") or None
            if selected:
                break
    proxy = {
        "saved": {
            "count": int(saved_profile_count),
            "selected_profile_id": selected,
        },
        "system": system_proxy,
        "bridge": bridge,
        "applied": {
            "active": state["decision"]["effective_route"] in {"netfix_applied", "external_system_proxy"},
            "owner": "external" if state["decision"]["effective_route"] == "external_system_proxy" else ("netfix" if bridge.get("in_use") or bridge.get("needs_recovery") else "none"),
            "profile_id": bridge.get("profile_id"),
            "via": "system_proxy" if system_proxy.get("active") else "none",
        },
        "verified": _verified_status(
            current_state=state["state"],
            live_signals=live_signals,
            last_report_summary=last_report_summary,
        ),
    }
    verdict = build_dashboard_verdict(state=state, last_report_summary=last_report_summary)
    connection_quality = build_connection_quality(last_report_summary)
    presentation = build_dashboard_presentation(
        verdict,
        current_state=state["state"],
        effective_route=state["decision"]["effective_route"],
    )
    return {
        "schema_version": "netfix_current_mac_state.v2",
        "decision": dict(state["decision"]),
        "verdict": verdict,
        "presentation": presentation,
        "connection_quality": connection_quality,
        "machine": _machine_summary(machine_state),
        "proxy": proxy,
        "egress": _egress_summary(egress_summary),
        "last_report_summary": last_report_summary or {},
        "state": state,
        "live_signals": live_signals or {},
        # Top-level copies of the verdict narrative so the macOS app
        # (DashboardStateResponse.headline / detail / next_step) and the
        # Web console can render the verdict without having to know the
        # nested `verdict.*` location. Always keep these three in sync.
        "headline": str(verdict.get("headline") or ""),
        "detail": str(verdict.get("detail") or ""),
        "next_step": str(verdict.get("next_step") or ""),
    }


def _verified_status(
    *,
    current_state: str,
    live_signals: Optional[Dict[str, Any]],
    last_report_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute proxy.verified.status from state + live signals + last report.

    A green 'ok' is only emitted when the current state is proxy_in_use, the
    live monitor signals agree, and the journal report (when present) is
    fresh. Any disagreement pushes the status to warn/fail.
    """
    live = live_signals if isinstance(live_signals, dict) else {}
    live_status_raw = live.get("proxy_monitor_status") or live.get("monitor_status") or live.get("status")
    live_status = live_status_raw if live_status_raw in {"ok", "warn", "fail"} else None
    summary = last_report_summary if isinstance(last_report_summary, dict) else {}
    checked_at = summary.get("checked_at")
    evidence_is_current = bool(
        checked_at
        and not summary.get("stale")
        and summary.get("usable_for_dashboard") is True
        and summary.get("route_matches_current") is True
        and summary.get("coverage") == "current_mac_full"
        and _safe_int(summary.get("valid_sample_count")) > 0
    )
    report_status = summary.get("status") if summary.get("status") in {"ok", "warn", "fail"} else None
    if current_state == "network_recovery":
        status = "fail"
        source = "bridge_state"
    elif live_status in {"warn", "fail"}:
        status = str(live_status)
        source = "live_monitor"
    elif evidence_is_current and report_status:
        status = str(report_status)
        source = "last_report"
    else:
        status = "unknown"
        source = "none"
    return {
        "status": status,
        "checked_at": checked_at if evidence_is_current else None,
        "live_status": live_status,
        "source": source,
    }
