"""Local HTTP API that wraps the netfix CLI."""
from __future__ import annotations

import json
import os
import secrets
import signal
import stat
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from netfix import agent_tools, deepseek_sidecar, dashboard_state, keychain, llm_budget, llm_explain, llm_provider, logs, network_monitor_service, proxy_bridge, proxy_monitor_service, residential_proxy, services, settings, user_facing_errors
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


def _dashboard_machine_state() -> Dict[str, Any]:
    """Return local network identity without making public-IP requests."""
    try:
        return agent_tools.get_global_state(include_public_ipv4=False)
    except TypeError:
        return agent_tools.get_global_state()
    except Exception as exc:
        return {"platform": sys.platform, "error": str(exc)}


def _number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_mbps(kbps: Optional[float]) -> Optional[str]:
    if kbps is None:
        return None
    return f"{kbps / 1000.0:.1f} Mbps"


def _metric(label: str, value: str, hint: str) -> Dict[str, str]:
    return {"label": label, "value": value, "hint": hint}


def _connection_quality_from_report(
    diagnostics: Any,
    *,
    checked_at: Any,
    stale: bool,
) -> Dict[str, Any]:
    by_name: Dict[str, Dict[str, Any]] = {}
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                by_name[item["name"]] = item

    network = by_name.get("network_quality") or {}
    path = by_name.get("path_trace") or {}
    hog = by_name.get("bandwidth_hog") or {}
    gateway = by_name.get("gateway") or {}
    network_details = network.get("details") if isinstance(network.get("details"), dict) else {}
    path_details = path.get("details") if isinstance(path.get("details"), dict) else {}
    hog_details = hog.get("details") if isinstance(hog.get("details"), dict) else {}
    gateway_details = gateway.get("details") if isinstance(gateway.get("details"), dict) else {}

    dl_kbps = _number(network_details.get("dl_throughput_kbps"))
    ul_kbps = _number(network_details.get("ul_throughput_kbps"))
    rtt_ms = _number(network_details.get("base_rtt_ms"))
    speed_sampled = dl_kbps is not None or ul_kbps is not None
    latency_sampled = rtt_ms is not None

    down = _format_mbps(dl_kbps)
    up = _format_mbps(ul_kbps)
    if down and up:
        speed_value = f"下载 {down} / 上传 {up}"
    elif down:
        speed_value = f"下载 {down}"
    elif up:
        speed_value = f"上传 {up}"
    else:
        speed_value = "未采到"
    if dl_kbps is None and ul_kbps is None:
        speed = _metric("未测", speed_value, "本机没有返回速度数据。")
    elif (dl_kbps is not None and dl_kbps < 5_000) or (ul_kbps is not None and ul_kbps < 1_000):
        speed = _metric("偏低", speed_value, "当前速度可能影响视频、下载或实时工具。")
    elif (dl_kbps or 0) >= 25_000 and (ul_kbps or 3_000) >= 3_000:
        speed = _metric("充足", speed_value, "日常浏览、开发工具和实时输出都够用。")
    else:
        speed = _metric("够用", speed_value, "日常使用够用；大文件下载可能需要等待。")

    if rtt_ms is None:
        latency = _metric("未测", "未采到", "本机没有返回延迟数据。")
    else:
        rtt_int = int(round(rtt_ms))
        if rtt_int <= 60:
            latency = _metric("低", f"延迟 {rtt_int}ms", "实时输出比较顺。")
        elif rtt_int <= 150:
            latency = _metric("中等", f"延迟 {rtt_int}ms", "实时输出会有轻微等待。")
        else:
            latency = _metric("较高", f"延迟 {rtt_int}ms", "实时输出会有明显等待。")
    destination_loss: Optional[float] = None
    hops = path_details.get("hops")
    if isinstance(hops, list):
        for hop in reversed(hops):
            if isinstance(hop, dict):
                loss = _number(hop.get("loss_percent"))
                if loss is not None:
                    destination_loss = loss
                    break
    local_gateway_loss = _number(gateway_details.get("packet_loss"))
    stability_loss = destination_loss if destination_loss is not None else local_gateway_loss
    local_fallback = destination_loss is None and local_gateway_loss is not None
    stability_sampled = stability_loss is not None
    if stability_loss is None:
        stability = _metric("未测", "未采到", "本机没有返回到达目标端的稳定性数据。")
    elif local_fallback and stability_loss <= 0:
        stability = _metric("本地稳定", "本地丢包 0%", "本机到路由器的连接稳定；不代表代理全链路。")
    elif local_fallback:
        stability = _metric("本地有波动", f"本地丢包 {stability_loss:.0f}%", "本机到路由器有波动，先检查 Wi-Fi 或网线。")
    elif stability_loss <= 0:
        stability = _metric("稳定", "丢包 0%", "路径稳定。")
    elif stability_loss <= 5:
        stability = _metric("轻微波动", f"丢包 {stability_loss:.0f}%", "有轻微波动，通常还能使用。")
    else:
        stability = _metric("不稳", f"丢包 {stability_loss:.0f}%", "换网络或代理节点后再检查。")

    hog_status = str(hog.get("status") or "")
    hog_reason = str(hog_details.get("reason") or "")
    top_names: List[str] = []
    for item in hog_details.get("top_processes") or []:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("process") or "").strip()
            if label:
                top_names.append(label)
    if hog_status in {"warn", "fail"} and hog_reason == "upload_saturated":
        value = f"{'、'.join(top_names[:3])} 上传较高" if top_names else "后台上传较高"
        background = _metric("上传较高", value, "需要实时使用时，可以暂停同步或上传后再检查。")
    elif hog_status in {"warn", "fail"} and hog_reason == "download_saturated":
        value = f"{'、'.join(top_names[:3])} 下载较高" if top_names else "后台下载较高"
        background = _metric("下载较高", value, "需要实时使用时，可以暂停下载或系统更新后再检查。")
    elif by_name.get("bandwidth_hog"):
        background = _metric("平稳", "后台占用不高", "没有看到明显上传或下载占用。")
    else:
        background = _metric("未测", "未采到", "本机没有返回后台占用数据；只看占用，不看内容。")

    background_sampled = bool(by_name.get("bandwidth_hog"))
    sampled_count = sum((speed_sampled, latency_sampled, stability_sampled, background_sampled))
    if stale:
        collection_state = "stale"
    elif sampled_count == 0:
        collection_state = "unavailable"
    elif sampled_count == 4:
        collection_state = "complete"
    else:
        collection_state = "partial"
    severe_quality = bool(
        (dl_kbps is not None and dl_kbps < 1_000)
        or (ul_kbps is not None and ul_kbps < 250)
        or (rtt_ms is not None and rtt_ms > 1_000)
        or (stability_loss is not None and stability_loss > 20)
    )
    degraded_quality = bool(
        severe_quality
        or (dl_kbps is not None and dl_kbps < 5_000)
        or (ul_kbps is not None and ul_kbps < 1_000)
        or (rtt_ms is not None and rtt_ms > 150)
        or (stability_loss is not None and stability_loss > 0)
        or hog_status in {"warn", "fail"}
        or str(network.get("status") or "") in {"warn", "fail"}
    )
    if stale:
        status = "stale"
    elif collection_state == "unavailable":
        status = "unchecked"
    elif severe_quality:
        status = "fail"
    elif degraded_quality:
        status = "warn"
    else:
        status = "ok"
    headline = {
        "stale": "上次体感数据已过期",
        "unchecked": "还没测网络体感",
        "warn": "体感需要留意",
        "fail": "当前体感较差",
        "ok": "体感顺畅",
    }.get(status, "网络体感")
    if collection_state == "unavailable":
        headline = "本机未能采样"
        detail = "检查已完成，但这台 Mac 没有返回速度、延迟或稳定性数据。"
    elif status in {"warn", "fail"}:
        if rtt_ms is not None and rtt_ms > 150:
            headline = "延迟偏高，操作会有等待"
            detail = latency["hint"]
        elif speed["label"] == "偏低":
            headline = "当前速度偏低"
            detail = speed["hint"]
        elif stability_loss is not None and stability_loss > 0:
            headline = "当前连接有波动"
            detail = stability["hint"]
        elif hog_status in {"warn", "fail"}:
            headline = "后台占用较高"
            detail = background["hint"]
        else:
            detail = "已显示本机实际返回的数据。"
    elif collection_state == "partial":
        headline = "已采到部分网络体感"
        detail = "已显示本机实际返回的数据；缺少的项目不会用猜测补齐。"
    elif collection_state == "stale":
        detail = "线路或时间已经变化，请重新检查后再参考。"
    else:
        detail = "来自最近一次检查，不会额外测速。"
    return {
        "status": status,
        "collection_state": collection_state,
        "headline": headline,
        "detail": detail,
        "speed": speed,
        "latency": latency,
        "stability": stability,
        "background_activity": background,
        "checked_at": checked_at,
        "stale": stale,
        "source": "last_report" if checked_at else "none",
    }


_ROUTE_DIAGNOSTICS = {
    "interface_state",
    "dhcp_state",
    "gateway",
    "ipv4_route",
    "dns_resolvers",
    "dns_local",
    "dns_public",
    "system_proxy_state",
    "proxy_core_status",
    "proxy_http_test",
    "proxy_socks_test",
    "proxy_auth_check",
    "pac_state",
    "node_reachability",
}
_CONNECTION_DIAGNOSTICS = {"wifi_signal", "path_trace", "network_quality", "bandwidth_hog", "mtu_probe"}
_ADVISORY_DIAGNOSTICS = {"ip_reputation", "dns_leak", "ipv6_leak", "ipv6_route", "egress_identity", "public_ip"}
_SIGNAL_STATUSES = {"ok", "warn", "fail"}


def _dashboard_channel(item: Dict[str, Any]) -> str:
    name = str(item.get("name") or "")
    layer = str(item.get("layer") or "")
    if name in _ROUTE_DIAGNOSTICS:
        return "route_health"
    if name in _CONNECTION_DIAGNOSTICS or layer in {"path", "bandwidth"}:
        return "connection_quality"
    if name in _ADVISORY_DIAGNOSTICS or layer == "egress":
        return "advisory"
    if (
        layer == "service"
        or name.endswith("_direct")
        or name.endswith("_via_proxy")
        or bool(item.get("target"))
        or "proxy_used" in item
    ):
        return "target_service"
    if layer in {"proxy", "dns", "network"}:
        return "route_health"
    return "advisory"


def _current_route_has_proxy(environment: Optional[Dict[str, Any]]) -> bool:
    env = environment if isinstance(environment, dict) else {}
    proxy = env.get("system_proxy") if isinstance(env.get("system_proxy"), dict) else {}
    for key in ("http", "https", "socks", "pac"):
        entry = proxy.get(key)
        if isinstance(entry, dict):
            if entry.get("enabled") or entry.get("server") or entry.get("host") or entry.get("endpoint") or entry.get("url"):
                return True
        elif entry:
            return True
    return False


def _dashboard_status(item: Dict[str, Any], environment: Optional[Dict[str, Any]]) -> Any:
    status = item.get("status")
    if _current_route_has_proxy(environment):
        return status
    if item.get("name") not in {"proxy_http_test", "proxy_socks_test", "proxy_auth_check"}:
        return status
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    error = str(details.get("error") or item.get("error") or "").lower()
    if "no proxy" in error or "no http proxy" in error or "no socks proxy" in error:
        return "unchecked"
    return status


def _empty_channel_summary() -> Dict[str, Any]:
    return {
        "status": "unknown",
        "ok": 0,
        "warn": 0,
        "fail": 0,
        "unknown": 0,
        "unchecked": 0,
        "notSampled": 0,
        "sample_count": 0,
    }


def _latest_dashboard_report_summary(
    *,
    current_environment: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Dict[str, Any], Dict[str, Any]]:
    latest_path = JOURNAL_DIR / "last_report.json"
    last_status: Optional[str] = None
    summary: Dict[str, Any] = {}
    egress: Dict[str, Any] = {"status": "unchecked"}
    if not latest_path.exists():
        return last_status, summary, egress
    try:
        last_report = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return last_status, summary, egress
    if not isinstance(last_report, dict):
        return last_status, summary, egress
    meta = last_report.get("meta") if isinstance(last_report.get("meta"), dict) else {}
    origin = str(meta.get("origin") or meta.get("scope") or "unknown")
    coverage = str(meta.get("coverage") or "unknown")
    report_route_signature = meta.get("route_signature")
    current_route_signature = dashboard_state.build_route_signature(current_environment)
    checked_at = meta.get("timestamp") or last_report.get("timestamp") or last_report.get("generated_at")
    diagnostics = last_report.get("diagnostics")
    diagnostic_counts: Dict[str, int] = {}
    status_rank = {"ok": 1, "warn": 2, "fail": 3}
    channels = {
        "route_health": _empty_channel_summary(),
        "connection_quality": _empty_channel_summary(),
        "target_service": _empty_channel_summary(),
        "advisory": _empty_channel_summary(),
    }
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            if isinstance(status, str) and status:
                diagnostic_counts[status] = diagnostic_counts.get(status, 0) + 1
            effective_status = _dashboard_status(item, current_environment)
            channel = channels[_dashboard_channel(item)]
            if isinstance(effective_status, str) and effective_status in channel:
                channel[effective_status] += 1
            if effective_status in _SIGNAL_STATUSES:
                channel["sample_count"] += 1
                current_channel_status = str(channel.get("status") or "unknown")
                if status_rank[effective_status] > status_rank.get(current_channel_status, 0):
                    channel["status"] = effective_status
            if item.get("name") in {"egress_identity", "ip_reputation", "public_ip"}:
                details = item.get("details") if isinstance(item.get("details"), dict) else {}
                egress = {
                    "status": status if status in {"ok", "warn", "fail"} else "unchecked",
                    "public_ipv4": details.get("public_ipv4") or details.get("ip"),
                    "isp": details.get("isp") or details.get("org"),
                    "asn": details.get("asn"),
                    "ip_type": details.get("ip_type"),
                    "risk_score": details.get("risk_score"),
                    "same_as_local": details.get("same_as_local"),
                    "cached": bool(details.get("cached")),
                    "source": item.get("name"),
                    "checked_at": checked_at,
                }
    route_channel = channels["route_health"]
    route_status = str(route_channel.get("status") or "unknown")
    if route_status not in _SIGNAL_STATUSES:
        route_status = None
    valid_sample_count = int(route_channel.get("sample_count") or 0)
    issue_count = int(route_channel.get("warn") or 0) + int(route_channel.get("fail") or 0)
    blocking_issue_count = int(route_channel.get("fail") or 0)
    advisory_count = sum(
        int(channels[channel_id].get("warn") or 0) + int(channels[channel_id].get("fail") or 0)
        for channel_id in ("connection_quality", "target_service", "advisory")
    )
    age = _age_seconds(checked_at)
    stale = bool(age is None or age > 3600)
    route_matches_current = bool(
        isinstance(report_route_signature, str)
        and report_route_signature
        and isinstance(current_route_signature, str)
        and report_route_signature == current_route_signature
    )
    invalid_reason: Optional[str] = None
    if stale:
        invalid_reason = "stale"
    elif origin not in {"doctor", "post_fix_doctor"}:
        invalid_reason = "unsupported_origin"
    elif coverage != "current_mac_full":
        invalid_reason = "incomplete_coverage"
    elif not report_route_signature:
        invalid_reason = "missing_route_signature"
    elif not current_route_signature:
        invalid_reason = "current_route_unknown"
    elif not route_matches_current:
        invalid_reason = "route_changed"
    elif valid_sample_count == 0:
        invalid_reason = "no_route_samples"
    usable_for_dashboard = invalid_reason is None
    last_status = route_status if usable_for_dashboard else None
    summary = {
        "has_report": True,
        "scope": origin,
        "origin": origin,
        "coverage": coverage,
        "checked_at": checked_at,
        "age_seconds": int(age) if age is not None else None,
        "status": route_status,
        "diagnostic_count": len(diagnostics) if isinstance(diagnostics, list) else 0,
        "diagnostic_counts": diagnostic_counts,
        "diagnostic_channels": channels,
        "valid_sample_count": valid_sample_count,
        "issue_count": issue_count,
        "blocking_issue_count": blocking_issue_count,
        "advisory_count": advisory_count,
        "stale": stale,
        "route_matches_current": route_matches_current,
        "invalid_reason": invalid_reason,
        "usable_for_dashboard": usable_for_dashboard,
        "connection_quality": _connection_quality_from_report(
            diagnostics,
            checked_at=checked_at,
            stale=bool(stale or not usable_for_dashboard),
        ),
    }
    explanation = last_report.get("explanation") if isinstance(last_report.get("explanation"), dict) else {}
    if explanation:
        summary["headline"] = explanation.get("headline")
        summary["historical_severity"] = explanation.get("severity")
    summary["severity"] = route_status or "info"
    return last_status, summary, egress


def _live_dashboard_signals(ttl_seconds: int = 10) -> Dict[str, Any]:
    """Fold the live proxy/network monitor signals into a single dict.

    The result is cached for ``ttl_seconds`` to avoid hammering the in-process
    monitor threads on every /dashboard/state poll. The shape is intentionally
    narrow: only what the dashboard verdict cares about.

    Returns an empty dict when no signal is available (e.g. monitors are off
    or not yet sampled). The dashboard verdict treats that as "no live signal"
    and falls back to the journal report + state.
    """
    now = time.monotonic()
    cache = _LIVE_SIGNALS_CACHE
    if cache["value"] is not None and (now - cache["ts"]) < ttl_seconds:
        return cache["value"]

    summary: Dict[str, Any] = {"fresh_seconds": 0}

    proxy_status: Optional[str] = None
    proxy_fresh_age: Optional[float] = None
    try:
        snap = proxy_monitor_service.status()
        monitor = snap.get("monitor") if isinstance(snap, dict) else None
        if isinstance(monitor, dict):
            last_check = monitor.get("last_check")
            if isinstance(last_check, dict):
                proxy_status = str(last_check.get("status") or "") or None
                checked_at = last_check.get("checked_at")
                if checked_at:
                    proxy_fresh_age = _age_seconds(checked_at)
            if not proxy_status:
                running = monitor.get("running")
                last_error = monitor.get("last_error")
                if running and last_error:
                    proxy_status = "fail"
                elif running:
                    proxy_status = "ok"
    except Exception:
        proxy_status = None

    network_status: Optional[str] = None
    try:
        snap = network_monitor_service.status()
        monitor = snap.get("monitor") if isinstance(snap, dict) else None
        if isinstance(monitor, dict):
            running = monitor.get("running")
            last_sample = monitor.get("last_sample")
            if isinstance(last_sample, dict):
                state = str(last_sample.get("state") or "")
                if state in {"busyUpload", "busyDownload", "slow", "recentLag"}:
                    network_status = "warn"
                elif state in {"authFailing", "failing"}:
                    network_status = "fail"
                elif state == "ok":
                    network_status = "ok"
            if network_status is None and running:
                network_status = "ok"
    except Exception:
        network_status = None

    if proxy_status:
        summary["monitor_status"] = proxy_status
        summary["proxy_monitor_status"] = proxy_status
    if network_status:
        summary["network_monitor_status"] = network_status
        summary["connection_monitor_status"] = network_status
    if proxy_status or network_status:
        ages = [a for a in (proxy_fresh_age,) if a is not None]
        if ages:
            summary["fresh_seconds"] = int(min(ages))

    _LIVE_SIGNALS_CACHE["value"] = summary
    _LIVE_SIGNALS_CACHE["ts"] = now
    return summary


_LIVE_SIGNALS_CACHE: Dict[str, Any] = {"value": None, "ts": 0.0}


def _age_seconds(value: Any) -> Optional[float]:
    """Best-effort: how many seconds ago was this iso-8601 timestamp?"""
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        from datetime import datetime, timezone
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return max(0.0, delta.total_seconds())


def _record_startup_bridge_check() -> Dict[str, Any]:
    """Run a non-mutating stale-bridge check at backend startup."""
    global _STARTUP_BRIDGE_CHECK
    checked_at = _utc_now()
    try:
        bridge_settings = settings.get_proxy_bridge_settings()
        auto_restart: Optional[Dict[str, Any]] = None
        if bridge_settings.get("auto_restart_enabled"):
            auto_restart = {
                "ok": False,
                "status": "suppressed",
                "reason_code": "action_time_confirmation_required",
                "requires_confirmation": True,
                "confirmation": residential_proxy.BRIDGE_RESTART_CONFIRMATION,
            }
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
        next_steps.append("先在 Netfix App 里点检查当前网络，再复制支持包。")
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
]

# /capabilities advertises the broader surface. /run is strictly the read-only
# subset; fix/rollback/proxy-switch go through their dedicated endpoints with
# confirmation tokens. watch and proxy-monitor live behind /watch/* and
# /proxy/monitor/* — they are NOT commands; remove them from capabilities.
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


def _run_fresh_report_after_fix(fix_id: str, timeout: int) -> Dict[str, Any]:
    """Run a follow-up report that covers the diagnostic the fix is meant to change."""
    command = "doctor" if fix_id == "disable-ipv6" else "codex"
    return run_cli([command, "--json", "--timeout", str(timeout)], timeout=timeout)


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
    reason = str(details.get("reason") or "").lower()
    reason_describes_fallback = (
        "proxy active and ipv6 default route present" in reason
        and "no public ipv6 observed" in reason
    )
    if not (details.get("fallback_risk") or reason_describes_fallback):
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

    report = _run_fresh_report_after_fix(fix_id, timeout)
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

        if path == "/timeline/lag":
            return 200, logs.load_lag_timeline(limit=5)

        if path == "/dashboard/insights":
            return 200, network_monitor_service.dashboard_insights(sample=False)

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
            environment = _environment_summary()
            last_status, report_summary, egress_summary = _latest_dashboard_report_summary(
                current_environment=environment,
            )
            live_signals = _live_dashboard_signals()
            contract = dashboard_state.build_current_mac_state(
                saved_profile_count=len(profiles),
                bridge_status=bridge,
                environment=environment,
                machine_state=_dashboard_machine_state(),
                egress_summary=egress_summary,
                last_report_summary=report_summary,
                last_diagnostic_status=last_status,
                profiles=profiles,
                live_signals=live_signals,
            )
            payload = {
                "ok": True,
                "bridge": bridge,
                "saved_profile_count": len(profiles),
                "live_signals": live_signals,
            }
            payload.update(contract)
            return 200, payload

        if path == "/llm/providers":
            return 200, {"ok": True, "providers": _llm_providers_with_status()}

        if path == "/llm/chain-readiness":
            return 200, _llm_chain_readiness()

        if path == "/settings/llm":
            return 200, {"ok": True, "settings": settings.get_llm_settings(masked=True)}

        if path == "/settings/privacy":
            return 200, {"ok": True, "settings": settings.get_privacy_settings()}

        if path == "/settings/network-activity":
            return 200, {"ok": True, "settings": settings.get_network_activity_settings()}

        if path == "/settings/proxy-bridge":
            return 200, {"ok": True, "settings": settings.get_proxy_bridge_settings()}

        if path == "/proxy/profiles":
            return 200, {"ok": True, "profiles": settings.get_proxy_profiles()}

        if path == "/proxy/profiles/grouped":
            return 200, residential_proxy.group_proxy_profiles()

        if path == "/proxy/monitor":
            return 200, proxy_monitor_service.status()

        if path == "/proxy/monitor/trend":
            return 200, logs.load_proxy_health_trend(limit=10)

        if path == "/network/monitor":
            return 200, network_monitor_service.status()

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

        if path == "/settings/network-activity":
            saved = settings.update_network_activity_settings(body)
            if saved.get("enabled"):
                monitor = network_monitor_service.start(interval=int(saved.get("interval") or 300), persist=False)
            else:
                monitor = network_monitor_service.stop(persist=False)
            return 200, {"ok": True, "settings": saved, "monitor": monitor.get("monitor")}

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
            if result.get("ok"):
                result.update(
                    residential_proxy.issue_validation_receipt(
                        parsed["profile"],
                        password=str(secret.get("password") or ""),
                    )
                )
            return (200 if result.get("ok") else 400), result

        if path == "/proxy/profiles":
            result = residential_proxy.save_proxy_profile(body)
            if result.get("ok"):
                result["deduplicated"] = bool(result.get("deduplicated"))
                if result["deduplicated"] and not isinstance(result.get("warnings"), list):
                    result["warnings"] = []
                if result["deduplicated"]:
                    result["warnings"].append(
                        "profile_reused_by_endpoint_fingerprint"
                    )
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
            if result.get("ok"):
                return 200, result
            if str(result.get("reason_code") or "").startswith("validation_receipt_"):
                return 409, result
            return 400, result

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

        if path == "/network/monitor/start":
            interval = int(body.get("interval") or settings.get_network_activity_settings().get("interval") or 300)
            return 200, network_monitor_service.start(interval=interval)

        if path == "/network/monitor/stop":
            return 200, network_monitor_service.stop()

        if path == "/proxy/bridge/recover":
            if not bool(body.get("confirmed") or body.get("confirm")) or str(body.get("confirmation") or "") != residential_proxy.BRIDGE_RECOVERY_CONFIRMATION:
                return 409, {
                    "ok": False,
                    "status": "confirmation_required",
                    "requires_confirmation": True,
                    "confirmation": residential_proxy.BRIDGE_RECOVERY_CONFIRMATION,
                }
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
            if result.get("ok"):
                updated["verification_status"] = "verified"
                updated["can_apply"] = True
                updated["validated_at"] = _utc_now()
                updated["validation_source"] = "saved_profile_check"
            else:
                updated["verification_status"] = "unverified"
                updated["can_apply"] = False
                updated.pop("validated_at", None)
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
            mode = str(body.get("mode") or "system")
            if mode == "system" and (
                selected.get("verification_status") != "verified"
                or selected.get("can_apply") is not True
            ):
                return 409, {
                    "ok": False,
                    "status": "blocked",
                    "error": "proxy profile must pass preflight validation before system apply",
                    "reason_code": "profile_not_verified",
                    "requires_validation": True,
                    "profile_id": profile_id,
                }
            if mode == "system" and (
                not bool(body.get("confirmed") or body.get("confirm"))
                or str(body.get("confirmation") or "") != residential_proxy.SYSTEM_APPLY_CONFIRMATION
            ):
                return 409, {
                    "ok": False,
                    "status": "confirmation_required",
                    "requires_confirmation": True,
                    "confirmation": residential_proxy.SYSTEM_APPLY_CONFIRMATION,
                    "profile_id": profile_id,
                }
            result = residential_proxy.apply_proxy_profile(
                selected,
                mode=mode,
                confirmed=bool(body.get("confirmed") or body.get("confirm")),
                confirmation=str(body.get("confirmation") or ""),
                network_service=str(body.get("network_service") or ""),
                target_url=str(body.get("target_url") or "https://www.gstatic.com/generate_204"),
                timeout=max(1, min(int(body.get("timeout", 10)), 60)),
                verify=True,
                rollback_on_verify_failure=True,
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
            if not bool(body.get("confirmed") or body.get("confirm")) or str(body.get("confirmation") or "") != residential_proxy.PROXY_ROLLBACK_CONFIRMATION:
                return 409, {
                    "ok": False,
                    "status": "confirmation_required",
                    "requires_confirmation": True,
                    "confirmation": residential_proxy.PROXY_ROLLBACK_CONFIRMATION,
                }
            result = residential_proxy.rollback_last_proxy_apply(
                confirmed=bool(body.get("confirmed") or body.get("confirm")),
                confirmation=str(body.get("confirmation") or ""),
            )
            if result.get("ok"):
                return 200, result
            return (404 if result.get("status") == "no_journal" else 400), result

        if path == "/proxy/profiles/cleanup-dupes":
            return 200, residential_proxy.cleanup_duplicate_profiles()

        profile_id, operation = residential_proxy.split_profile_path(path)
        if profile_id and operation == "rename":
            new_name = str(body.get("name") or "")
            result = settings.rename_proxy_profile(profile_id, new_name)
            if not result.get("ok"):
                return (404 if result.get("error") == "profile not found" else 400), result
            return 200, result

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
    network_monitor_service.restore_from_settings()
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
            network_monitor_service.stop(persist=False)


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
