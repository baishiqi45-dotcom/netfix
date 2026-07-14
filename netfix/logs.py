"""Local report/event log retention and cleanup helpers."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from netfix.constants import JOURNAL_DIR
from netfix import settings
from netfix.redaction import redact_report
from netfix.utils import secure_append_text, secure_write_text


EVENTS_FILE = JOURNAL_DIR / "events.jsonl"
LATEST_REPORT = JOURNAL_DIR / "last_report.json"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_events(limit: int = 100, hours: Optional[int] = 72) -> Dict[str, Any]:
    """Return recent timeline events."""
    if not EVENTS_FILE.exists():
        return {"events": []}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
    events: List[Dict[str, Any]] = []
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = redact_report({"event": event}, level="balanced").get("redacted_report", {}).get("event", event)
                if cutoff is not None:
                    event_time = _parse_timestamp(event.get("timestamp"))
                    if event_time is not None and event_time < cutoff:
                        continue
                events.append(event)
    except Exception as exc:
        return {"events": [], "error": str(exc)}
    return {"events": events[-limit:]}


def load_logs() -> Dict[str, Any]:
    """Return report/event log metadata for product UIs."""
    privacy = settings.get_privacy_settings()
    events = load_events(limit=100, hours=privacy.get("log_retention_days", 7) * 24)
    payload: Dict[str, Any] = {
        "ok": True,
        "journal_dir": str(JOURNAL_DIR),
        "latest_report_path": str(LATEST_REPORT),
        "latest_report_exists": LATEST_REPORT.exists(),
        "events_path": str(EVENTS_FILE),
        "events_exists": EVENTS_FILE.exists(),
        "events": events.get("events", []),
        "latest_report_summary": {},
        "privacy": privacy,
    }
    if events.get("error"):
        payload["events_error"] = events["error"]
    if LATEST_REPORT.exists():
        try:
            report = json.loads(LATEST_REPORT.read_text(encoding="utf-8"))
            payload["latest_report_summary"] = {
                "timestamp": report.get("meta", {}).get("timestamp"),
                "headline": report.get("explanation", {}).get("headline"),
                "root_causes": report.get("root_causes", [])[:3],
            }
        except Exception as exc:
            payload["latest_report_error"] = str(exc)
    return payload


def _proxy_error_category(error: Any) -> str:
    text = str(error or "").lower()
    if not text:
        return ""
    if "auth" in text or "401" in text or "407" in text or "password" in text:
        return "auth_failed"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "dns" in text or "resolve" in text:
        return "dns_failed"
    if "connect" in text or "refused" in text or "reset" in text:
        return "connect_failed"
    return "check_failed"


def proxy_check_summary(check: Dict[str, Any]) -> Dict[str, Any]:
    """Return a privacy-safe proxy health sample.

    Do not persist target URLs, checked_via URLs, proxy hostnames, exit IPs, or
    credentials. This shape is safe for logs, settings last_check, and UI trend
    cards.
    """
    check = check if isinstance(check, dict) else {}
    return {
        "profile_id": str(check.get("profile_id") or ""),
        "status": str(check.get("status") or "unknown"),
        "auth": str(check.get("auth") or ""),
        "tcp": str(check.get("tcp") or ""),
        "http_code": int(check.get("http_code") or 0),
        "latency_ms": int(check.get("latency_ms") or 0) if check.get("latency_ms") is not None else None,
        "error": _proxy_error_category(check.get("error")),
        "checked_at": str(check.get("checked_at") or ""),
    }


def _process_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    label = str(item.get("label") or item.get("process") or "未知 App")[:80]
    direction = str(item.get("direction") or "")[:20]
    rate = float(item.get("rate_kbps") or 0.0)
    if rate >= 10_000:
        bucket = "10Mbps+"
    elif rate >= 5_000:
        bucket = "5-10Mbps"
    elif rate >= 1_500:
        bucket = "1.5-5Mbps"
    elif rate > 0:
        bucket = "<1.5Mbps"
    else:
        bucket = "0"
    return {
        "label": label,
        "direction": direction,
        "rate_kbps": round(rate, 1),
        "rate_bucket": bucket,
        "ignored": bool(item.get("ignored")),
    }


def lag_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    """Return the public/safe lag event shape used by Dashboard."""
    event = event if isinstance(event, dict) else {}
    evidence = event.get("evidence") if isinstance(event.get("evidence"), dict) else {}
    top_processes = evidence.get("top_processes") if isinstance(evidence.get("top_processes"), list) else []
    timestamp = str(event.get("timestamp") or "")
    event_id = str(event.get("id") or f"{timestamp}:{event.get('reason_code') or event.get('headline') or ''}")
    return {
        "id": event_id,
        "schema_version": "netfix_lag_event_summary.v1",
        "timestamp": timestamp,
        "type": "lag_event",
        "status": str(event.get("status") or "warn"),
        "severity": str(event.get("severity") or event.get("status") or "warn"),
        "reason_code": str(event.get("reason_code") or ""),
        "headline": str(event.get("headline") or "网络有点卡"),
        "suspected_cause": str(event.get("suspected_cause") or event.get("headline") or ""),
        "evidence": {
            "responsiveness_rpm": evidence.get("responsiveness_rpm"),
            "base_rtt_ms": evidence.get("base_rtt_ms"),
            "top_processes": [_process_summary(item) for item in top_processes if isinstance(item, dict)][:3],
        },
    }


def load_lag_timeline(limit: int = 5, hours: Optional[int] = 168) -> Dict[str, Any]:
    """Return recent lag events only, already privacy-summarized."""
    limit = max(1, min(int(limit or 5), 50))
    events = load_events(limit=500, hours=hours).get("events", [])
    lag_events = [
        lag_event_summary(event)
        for event in events
        if isinstance(event, dict) and str(event.get("type") or "") == "lag_event"
    ]
    return {"ok": True, "events": lag_events[-limit:]}


def _proxy_trend_state(samples: List[Dict[str, Any]], median_latency: Optional[int]) -> str:
    if not samples:
        return "unknown"
    fail_count = sum(1 for item in samples if str(item.get("status") or "") not in {"ok", "warn"})
    auth_fail = any(str(item.get("auth") or "") == "failed" or "auth" in str(item.get("error") or "") for item in samples)
    if auth_fail:
        return "authFailing"
    if fail_count >= max(2, len(samples) // 2):
        return "failing"
    if median_latency is not None and median_latency > 800:
        return "slow"
    return "stable"


def load_proxy_health_trend(limit: int = 10, profile_id: str = "", hours: Optional[int] = 168) -> Dict[str, Any]:
    """Return a privacy-safe proxy-monitor trend from events.jsonl."""
    limit = max(1, min(int(limit or 10), 50))
    profile_id = str(profile_id or "")

    def _samples_from_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict) or str(event.get("type") or "") != "proxy_monitor":
                continue
            raw_check = event.get("proxy_check") if isinstance(event.get("proxy_check"), dict) else {}
            check = proxy_check_summary(raw_check)
            if profile_id and check.get("profile_id") != profile_id:
                continue
            out.append({
                "timestamp": str(event.get("timestamp") or raw_check.get("checked_at") or ""),
                **check,
            })
        return out

    events = load_events(limit=1000, hours=hours).get("events", [])
    samples = _samples_from_events(events)
    if not samples and hours is not None:
        samples = _samples_from_events(load_events(limit=1000, hours=None).get("events", []))
    samples = samples[-limit:]
    latencies = [int(item["latency_ms"]) for item in samples if isinstance(item.get("latency_ms"), int) and item["latency_ms"] > 0]
    median_latency = int(statistics.median(latencies)) if latencies else None
    ok_count = sum(1 for item in samples if item.get("status") == "ok")
    warn_count = sum(1 for item in samples if item.get("status") == "warn")
    fail_count = len(samples) - ok_count - warn_count
    return {
        "ok": True,
        "schema_version": "netfix_proxy_health_trend.v1",
        "state": _proxy_trend_state(samples, median_latency),
        "samples": samples,
        "ok_count": ok_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "median_latency_ms": median_latency,
    }


def append_event(event: Dict[str, Any], apply_retention: bool = True) -> Dict[str, Any]:
    """Append a lightweight local event for product timeline views."""
    payload = dict(event)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    payload = redact_report({"event": payload}, level="balanced").get("redacted_report", {}).get("event", payload)
    try:
        secure_append_text(EVENTS_FILE, json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        if apply_retention:
            apply_retention_policy()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "event": payload}


def prune_events(retention_days: int) -> Dict[str, Any]:
    """Drop events older than ``retention_days`` while keeping unparsable lines out."""
    retention_days = max(1, min(int(retention_days or 7), 365))
    if not EVENTS_FILE.exists():
        return {"ok": True, "retention_days": retention_days, "kept": 0, "removed": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept: List[Dict[str, Any]] = []
    removed = 0
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    removed += 1
                    continue
                event_time = _parse_timestamp(event.get("timestamp"))
                if event_time is not None and event_time < cutoff:
                    removed += 1
                    continue
                kept.append(event)
        text = "".join(json.dumps(event, ensure_ascii=False, default=str) + "\n" for event in kept)
        secure_write_text(EVENTS_FILE, text)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "retention_days": retention_days}
    return {"ok": True, "retention_days": retention_days, "kept": len(kept), "removed": removed}


def apply_retention_policy() -> Dict[str, Any]:
    """Apply the current privacy settings to the event log."""
    privacy = settings.get_privacy_settings()
    if not privacy.get("log_retention_enabled", True):
        return {"ok": True, "retention_enabled": False}
    return prune_events(int(privacy.get("log_retention_days") or 7))


def clear_logs(clear_latest_report: bool = True, clear_events: bool = True) -> Dict[str, Any]:
    """Delete local report/event logs without touching settings or Keychain."""
    removed: List[str] = []
    errors: Dict[str, str] = {}
    targets = []
    if clear_latest_report:
        targets.append(LATEST_REPORT)
    if clear_events:
        targets.append(EVENTS_FILE)
    for path in targets:
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        except Exception as exc:
            errors[str(path)] = str(exc)
    return {"ok": not errors, "removed": removed, "errors": errors}
