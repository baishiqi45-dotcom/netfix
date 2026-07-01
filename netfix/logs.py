"""Local report/event log retention and cleanup helpers."""
from __future__ import annotations

import json
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
