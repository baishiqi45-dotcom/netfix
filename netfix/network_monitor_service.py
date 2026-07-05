"""Lightweight local network-activity monitor.

This service is intentionally narrow: it samples coarse per-process bandwidth
via the existing ``bandwidth_hog`` diagnostic, keeps healthy samples in memory,
and only writes privacy-safe lag events to ``events.jsonl``.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from netfix import logs, settings
from netfix.constants import JOURNAL_DIR
from netfix.layers import bandwidth, path  # noqa: F401 - import registers diagnostics and exposes callables


_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: Optional[threading.Thread] = None
_STATE: Dict[str, Any] = {
    "running": False,
    "interval": None,
    "started_at": None,
    "stopped_at": None,
    "run_count": 0,
    "last_sample": None,
    "last_event": None,
    "last_error": None,
    "consecutive_hog_count": 0,
    "last_lag_event_at": 0.0,
    "restored": False,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_state(**updates: Any) -> None:
    with _LOCK:
        _STATE.update(updates)


def _snapshot() -> Dict[str, Any]:
    with _LOCK:
        state = dict(_STATE)
        thread_alive = bool(_THREAD and _THREAD.is_alive())
    state["thread_alive"] = thread_alive
    state["settings"] = settings.get_network_activity_settings()
    return {"ok": True, "monitor": state}


def _latest_network_quality() -> Optional[Dict[str, Any]]:
    latest = JOURNAL_DIR / "last_report.json"
    if not latest.exists():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None
    diagnostics = payload.get("diagnostics") if isinstance(payload, dict) else None
    if not isinstance(diagnostics, list):
        return None
    for item in diagnostics:
        if isinstance(item, dict) and item.get("name") == "network_quality":
            return item
    return None


def _quality_is_bad(quality: Optional[Dict[str, Any]]) -> bool:
    if not quality:
        return False
    if quality.get("status") in {"warn", "fail"}:
        return True
    details = quality.get("details") if isinstance(quality.get("details"), dict) else {}
    rpm = details.get("responsiveness_rpm")
    base_rtt = details.get("base_rtt_ms")
    try:
        if rpm is not None and float(rpm) < 200:
            return True
        if base_rtt is not None and float(base_rtt) > 200:
            return True
    except (TypeError, ValueError):
        return False
    return False


def _rule_matches_process(rule: Dict[str, Any], process: Dict[str, Any]) -> bool:
    if not rule.get("enabled", True):
        return False
    needle = str(rule.get("match") or "").strip().lower()
    if not needle:
        return False
    haystacks = [
        str(process.get("process") or "").lower(),
        str(process.get("label") or "").lower(),
    ]
    return any(needle in value for value in haystacks)


def _safe_process(item: Dict[str, Any], whitelist: List[Dict[str, Any]]) -> Dict[str, Any]:
    process = str(item.get("process") or "")[:120]
    label = str(item.get("label") or process or "未知 App")[:80]
    direction = str(item.get("direction") or "")[:20]
    rate = float(item.get("rate_kbps") or 0.0)
    safe = {
        "process": process,
        "label": label,
        "direction": direction,
        "rate_kbps": round(rate, 1),
        "is_hog": bool(item.get("is_hog")),
        "ignored": False,
    }
    safe["ignored"] = any(_rule_matches_process(rule, safe) for rule in whitelist)
    return safe


def _summarize_activity(bandwidth_diag: Dict[str, Any], whitelist: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    whitelist = whitelist or []
    details = bandwidth_diag.get("details") if isinstance(bandwidth_diag.get("details"), dict) else {}
    reason = str(details.get("reason") or "")
    status = str(bandwidth_diag.get("status") or "unknown")
    raw_processes = details.get("top_processes") if isinstance(details.get("top_processes"), list) else []
    top_processes = [_safe_process(item, whitelist) for item in raw_processes if isinstance(item, dict)][:3]
    active_hogs = [item for item in top_processes if item.get("is_hog") and not item.get("ignored")]

    if status == "unknown":
        state = "unavailable"
        headline = "暂时没法读取后台占用"
    elif active_hogs and reason == "upload_saturated":
        state = "busyUpload"
        headline = "后台上传疑似挤满网络"
    elif active_hogs and reason == "download_saturated":
        state = "busyDownload"
        headline = "后台下载疑似占满网络"
    elif top_processes:
        state = "quiet"
        headline = "没有看到明显后台占用"
    else:
        state = "quiet"
        headline = "没有看到明显后台占用"

    return {
        "schema_version": "netfix_network_activity.v1",
        "state": state,
        "status": status,
        "reason": reason,
        "headline": headline,
        "top_processes": top_processes,
        "privacy_note": "只看 App 名称、上传/下载方向和粗略速度；不看网址、远端 IP 或内容。",
        "sampled_at": _utc_now(),
    }


def _lag_event(activity: Dict[str, Any], quality: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    details = quality.get("details") if isinstance(quality, dict) and isinstance(quality.get("details"), dict) else {}
    top = [
        {
            "label": item.get("label"),
            "process": item.get("process"),
            "direction": item.get("direction"),
            "rate_kbps": item.get("rate_kbps"),
            "ignored": item.get("ignored"),
        }
        for item in activity.get("top_processes", [])
        if isinstance(item, dict) and item.get("is_hog") and not item.get("ignored")
    ][:3]
    reason = "upload_saturated" if activity.get("state") == "busyUpload" else "download_saturated"
    return {
        "schema_version": "netfix_lag_event.v1",
        "type": "lag_event",
        "timestamp": _utc_now(),
        "status": "warn",
        "severity": "warn",
        "reason_code": reason,
        "headline": "后台上传疑似挤满网络" if reason == "upload_saturated" else "后台下载疑似占满网络",
        "suspected_cause": "、".join(str(item.get("label") or item.get("process") or "") for item in top if item),
        "evidence": {
            "responsiveness_rpm": details.get("responsiveness_rpm"),
            "base_rtt_ms": details.get("base_rtt_ms"),
            "top_processes": top,
        },
    }


def run_once(*, record_event: bool = True, include_quality_probe: bool = False) -> Dict[str, Any]:
    """Sample current network activity once and maybe record a lag event."""
    config = settings.get_network_activity_settings()
    try:
        bandwidth_diag = bandwidth.bandwidth_hog({}, None, timeout=8)
        quality = _latest_network_quality()
        if include_quality_probe and bandwidth_diag.get("status") in {"warn", "fail"}:
            quality = path.network_quality({}, None, timeout=20)
        activity = _summarize_activity(bandwidth_diag, config.get("process_whitelist", []))
        quality_bad = _quality_is_bad(quality)
        has_active_hog = activity.get("state") in {"busyUpload", "busyDownload"}
        with _LOCK:
            consecutive = int(_STATE.get("consecutive_hog_count") or 0)
            consecutive = consecutive + 1 if has_active_hog else 0
            _STATE["consecutive_hog_count"] = consecutive

        event = None
        now = time.time()
        cooldown = int(config.get("lag_event_cooldown_s") or 600)
        should_record = bool(has_active_hog and (quality_bad or consecutive >= 2))
        with _LOCK:
            last_event_at = float(_STATE.get("last_lag_event_at") or 0.0)
        if record_event and should_record and now - last_event_at >= cooldown:
            event = _lag_event(activity, quality)
            logs.append_event(event)
            with _LOCK:
                _STATE["last_lag_event_at"] = now
        _set_state(
            run_count=int(_STATE.get("run_count") or 0) + 1,
            last_sample=activity,
            last_event=event,
            last_error=None,
        )
        return {
            "ok": True,
            "activity": activity,
            "quality_bad": quality_bad,
            "lag_event": event,
        }
    except Exception as exc:
        _set_state(last_error=str(exc))
        return {"ok": False, "error": str(exc)}


def _loop(interval: int) -> None:
    try:
        while not _STOP.is_set():
            run_once(record_event=True, include_quality_probe=False)
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


def start(*, interval: Optional[int] = None, persist: bool = True, restored: bool = False) -> Dict[str, Any]:
    config = settings.get_network_activity_settings()
    interval_i = max(60, min(int(interval or config.get("interval") or 300), 3600))
    _stop_thread()
    if persist:
        settings.update_network_activity_settings({"enabled": True, "interval": interval_i, "updated_at": _utc_now()})
    _set_state(
        running=True,
        interval=interval_i,
        started_at=_utc_now(),
        stopped_at=None,
        run_count=0,
        last_error=None,
        restored=restored,
    )
    global _THREAD
    _THREAD = threading.Thread(target=_loop, args=(interval_i,), daemon=True)
    _THREAD.start()
    return _snapshot()


def stop(*, persist: bool = True) -> Dict[str, Any]:
    _stop_thread()
    if persist:
        settings.update_network_activity_settings({"enabled": False, "updated_at": _utc_now()})
    _set_state(running=False, stopped_at=_utc_now())
    return _snapshot()


def status() -> Dict[str, Any]:
    return _snapshot()


def restore_from_settings() -> Dict[str, Any]:
    config = settings.get_network_activity_settings()
    if not config.get("enabled"):
        return {"ok": True, "restored": False, "reason": "network_activity_disabled", "monitor": status().get("monitor")}
    result = start(interval=int(config.get("interval") or 300), persist=False, restored=True)
    result["restored"] = bool(result.get("ok"))
    return result


def dashboard_insights(*, sample: bool = True) -> Dict[str, Any]:
    """Return the compact Dashboard insight payload."""
    if sample:
        run_once(record_event=True, include_quality_probe=False)
    with _LOCK:
        activity = _STATE.get("last_sample")
    if not isinstance(activity, dict):
        activity = {
            "schema_version": "netfix_network_activity.v1",
            "state": "notSampled",
            "status": "unknown",
            "reason": "not_sampled",
            "headline": "还没采样",
            "top_processes": [],
            "privacy_note": "只看 App 名称、上传/下载方向和粗略速度；不看网址、远端 IP 或内容。",
            "sampled_at": "",
        }
    return {
        "ok": True,
        "schema_version": "netfix_dashboard_insights.v1",
        "network_activity": activity,
        "lag_events": logs.load_lag_timeline(limit=5).get("events", []),
        "proxy_health_trend": logs.load_proxy_health_trend(limit=10),
        "monitor": status().get("monitor"),
    }
