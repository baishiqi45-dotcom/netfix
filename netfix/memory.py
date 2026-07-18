"""Netfix MEMORY.md long-term memory store.

The format is roughly the one used by Claude Code's auto-MEMORY file: a
human-readable Markdown document appending one bullet per real fix or
diagnosis so we can grep / re-read prior context for the next session.

Public surface:

* ``class MemoryStore`` — class-based store (P0 conversational requirement)
* Module-level helpers keep back-compat with the existing
  :mod:`netfix.agent_memory` pipeline (proactive alerts still import the
  dataclass-style helpers). New code should use ``MemoryStore``.

Schema
------
The document lives at ``<base_dir>/memory/MEMORY.md``. The store also keeps a
JSON sidecar ``<base_dir>/memory/entries.jsonl`` so we can round-trip entries
without re-parsing the Markdown. Both files are written atomically.

Each entry tracks::

    {
      "date": "<YYYY-MM-DD HH:MM TZ aware>",
      "scenario_id": "...",
      "root_cause_id": "...",
      "fingerprint": "<sha256:16>",
      "action_id": "...",
      "verify_result": "accepted" | "rejected" | "postponed" | "unknown",
      "symptom": "<short text>",
      "target": "<target group>",
      "learning": "<short note>",
      "confidence": 0.0,
      "outcome_label": "<human readable>"
    }

Constraints
-----------
- Free-text fields are scrubbed through :func:`redact_text` before being
  committed to disk so no API keys, tokens, raw URLs or proxy passwords leak.
- ``fingerprint`` is a sha256 16-hex string. We never store raw IPs or host
  names; callers must hash to a fingerprint first.
- All writes go under ``base_dir``; defaults to ``JOURNAL_DIR``; tests can pass
  ``tmp_path``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from netfix.constants import JOURNAL_DIR
from netfix.redaction import redact_text
from netfix.utils import ensure_dir, ensure_private_dir, secure_write_text


MEMORY_DIR_NAME = "memory"
MARKDOWN_FILE_NAME = "MEMORY.md"
JSONL_FILE_NAME = "entries.jsonl"
SCHEMA_VERSION = "netfix_memory_store.v1"

_VALID_VERIFY_RESULTS = {"accepted", "rejected", "postponed", "unknown", "verified"}
_OUTCOME_LABELS = {
    "accepted": "接受，已验证",
    "rejected": "拒绝",
    "postponed": "暂缓",
    "unknown": "未确认",
    "verified": "已验证",
}

_HEADING_RE = re.compile(r"^#\s+(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})\s*[·:]\s*(.+?)\s*$")
_FINGERPRINT_LINE_RE = re.compile(r"^\s*网络指纹:\s*(?:<([^>]+)>|([0-9a-f]{4,64}))\s*$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_date(value: Any) -> str:
    """Return a stable display date ``YYYY-MM-DD HH:MM`` plus full ISO timestamp."""
    if not value:
        value = _utc_now()
    text = str(value)
    naive_display = re.match(r"^(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})(?::\d{2})?$", text.strip())
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        try:
            parsed = datetime.fromisoformat(str(value)[:19])
        except Exception:
            return _utc_now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    display = naive_display.group(1) if naive_display else parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    return f"{display}|{parsed.astimezone(timezone.utc).isoformat()}"


def _normalize_fingerprint(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[0-9a-f]{2,64}", text) else ""


def _normalize_verify_result(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"ok", "pass", "succeeded", "verified", "accept", "accepted"}:
        return "accepted"
    if text in {"fail", "failed", "reject", "rejected", "declined"}:
        return "rejected"
    if text in {"postpone", "postponed", "later", "wait"}:
        return "postponed"
    return "unknown"


def _scrub(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    text = redact_text(text)
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def _format_heading(date_display: str, scenario_id: str) -> str:
    return f"# {date_display} · {scenario_id or 'unknown-scenario'}"


def _entry_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Project a JSONL row into the public entry shape."""
    return {
        "date": str(row.get("display_date") or row.get("iso_date") or ""),
        "scenario_id": str(row.get("scenario_id") or ""),
        "root_cause_id": str(row.get("root_cause_id") or ""),
        "fingerprint": str(row.get("fingerprint") or ""),
        "action_id": str(row.get("action_id") or ""),
        "verify_result": str(row.get("verify_result") or "unknown"),
        "symptom": str(row.get("symptom") or ""),
        "target": str(row.get("target") or ""),
        "learning": str(row.get("learning") or ""),
        "confidence": float(row.get("confidence") or 0.0),
        "outcome_label": str(row.get("outcome_label") or _OUTCOME_LABELS.get(str(row.get("verify_result") or ""), "未确认")),
    }


class MemoryStore:
    """Persistent MEMORY.md + sidecar JSONL store.

    Parameters
    ----------
    base_dir:
        Directory under which ``memory/`` will be created. Defaults to
        :data:`netfix.constants.JOURNAL_DIR` (== ``~/.netfix``). Tests pass
        ``tmp_path`` to keep the real install untouched.
    """

    def __init__(self, base_dir: Optional[Any] = None) -> None:
        if base_dir is None:
            base_dir = JOURNAL_DIR
        self._base_dir = Path(base_dir).expanduser()
        self._memory_dir: Optional[Path] = None
        self._lock_path: Optional[Path] = None

    @property
    def memory_dir(self) -> Path:
        if self._memory_dir is None:
            ensure_dir(self._base_dir)
            directory = self._base_dir / MEMORY_DIR_NAME
            ensure_dir(directory)
            ensure_private_dir(directory)
            self._memory_dir = directory
        return self._memory_dir

    @property
    def markdown_path(self) -> Path:
        return self.memory_dir / MARKDOWN_FILE_NAME

    @property
    def jsonl_path(self) -> Path:
        return self.memory_dir / JSONL_FILE_NAME

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    # -- public API --------------------------------------------------------

    def append_entry(
        self,
        date: Any = None,
        scenario_id: str = "",
        root_cause_id: str = "",
        fingerprint: str = "",
        action_id: str = "",
        verify_result: str = "unknown",
        *,
        symptom: str = "",
        target: str = "",
        learning: str = "",
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """Append a single entry to MEMORY.md and the JSONL sidecar.

        All free-text inputs are redacted before persistence. ``fingerprint``
        must already be a hex digest; non-hex content is dropped to keep the
        format safe.
        """
        combo = _normalize_date(date)
        display_date, iso_date = combo.split("|", 1)
        normalized_fingerprint = _normalize_fingerprint(fingerprint)
        normalized_verify = _normalize_verify_result(verify_result)
        outcome_label = _OUTCOME_LABELS.get(normalized_verify, "未确认")
        row = {
            "schema_version": SCHEMA_VERSION,
            "display_date": display_date,
            "iso_date": iso_date,
            "scenario_id": str(scenario_id or "unknown-scenario"),
            "root_cause_id": str(root_cause_id or "unknown-root-cause"),
            "fingerprint": normalized_fingerprint,
            "action_id": str(action_id or ""),
            "verify_result": normalized_verify,
            "symptom": _scrub(symptom),
            "target": _scrub(target, max_len=80),
            "learning": _scrub(learning),
            "confidence": float(confidence or 0.0),
            "outcome_label": outcome_label,
        }
        self._append_to_jsonl(row)
        self._append_to_markdown(row)
        return _entry_from_row(row)

    def find_recent(
        self,
        scenario_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return the most recent ``limit`` entries.

        ``scenario_id`` is optional; if supplied we filter to entries whose
        scenario matches. Newest entries are returned first (largest
        ``iso_date``).
        """
        rows = self._load_rows()
        if scenario_id:
            rows = [row for row in rows if str(row.get("scenario_id") or "") == str(scenario_id)]
        rows.sort(key=lambda row: str(row.get("iso_date") or ""), reverse=True)
        capped = max(1, int(limit))
        return [_entry_from_row(row) for row in rows[:capped]]

    def decay_older_than(self, days: int = 30) -> int:
        """Drop entries whose ``iso_date`` is older than ``days``.

        Returns the number of rows removed. ``days <= 0`` is treated as
        "decay everything".
        """
        days_value = int(days)
        rows = self._load_rows()
        if not rows:
            return 0
        if days_value <= 0:
            kept: List[Dict[str, Any]] = []
            removed = len(rows)
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_value)
            kept = []
            removed = 0
            for row in rows:
                iso = str(row.get("iso_date") or "")
                parsed: Optional[datetime] = None
                try:
                    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                except Exception:
                    parsed = None
                if parsed is None or parsed < cutoff:
                    removed += 1
                else:
                    kept.append(row)
        self._write_rows(kept)
        self._rewrite_markdown(kept)
        return removed

    def read_markdown(self) -> str:
        """Return the Markdown document as a single string."""
        path = self.markdown_path
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def clear_all(self) -> int:
        """Delete both the Markdown document and the JSONL sidecar.

        Returns the total number of files removed (0 or 2).
        """
        removed = 0
        for path in (self.markdown_path, self.jsonl_path):
            try:
                if path.exists():
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    # -- internal helpers --------------------------------------------------

    def _append_to_jsonl(self, row: Dict[str, Any]) -> None:
        path = self.jsonl_path
        ensure_dir(self.memory_dir)
        payload = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        try:
            with open(path, "rb") as existing:
                existing_bytes = existing.read()
        except FileNotFoundError:
            existing_bytes = b""
        combined = (existing_bytes or b"").rstrip(b"\n") + b"\n" + payload.encode("utf-8")
        # Use secure_write_text for the rewrite so permissions stay at 0o600.
        secure_write_text(path, combined.decode("utf-8"), mode=0o600)

    def _append_to_markdown(self, row: Dict[str, Any]) -> None:
        block = self._format_markdown_block(row)
        path = self.markdown_path
        existing = ""
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8")
            except Exception:
                existing = ""
        if not existing.strip():
            existing = "# Netfix MEMORY (auto-generated)\n\n"
        text = existing.rstrip() + "\n\n" + block
        secure_write_text(path, text, mode=0o600)

    def _rewrite_markdown(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            secure_write_text(self.markdown_path, "# Netfix MEMORY (auto-generated)\n\n", mode=0o600)
            return
        body = "\n\n".join(self._format_markdown_block(row) for row in rows).rstrip() + "\n"
        secure_write_text(self.markdown_path, f"# Netfix MEMORY (auto-generated)\n\n{body}", mode=0o600)

    @staticmethod
    def _format_markdown_block(row: Dict[str, Any]) -> str:
        display = str(row.get("display_date") or row.get("iso_date") or "")
        scenario = str(row.get("scenario_id") or "unknown-scenario")
        root_cause = str(row.get("root_cause_id") or "unknown-root-cause")
        verify = str(row.get("verify_result") or "unknown")
        action = str(row.get("action_id") or "")
        outcome = str(row.get("outcome_label") or _OUTCOME_LABELS.get(verify, "未确认"))
        symptom = str(row.get("symptom") or "")
        target = str(row.get("target") or "")
        learning = str(row.get("learning") or "")
        fingerprint = str(row.get("fingerprint") or "")
        confidence = float(row.get("confidence") or 0.0)
        heading = _format_heading(display, scenario)
        bits = [heading, ""]
        bits.append(f"- 症状: \"{symptom or '未记录'}\"，目标域名 `{target or 'unspecified'}`")
        bits.append(f"- 根因: `{root_cause}`（置信度 {confidence:.2f}）")
        if fingerprint:
            bits.append(f"- 网络指纹: `{fingerprint}`")
        elif verify != "unknown":
            bits.append(f"- 网络指纹: <无>")
        action_label = f"{action}（{outcome}）" if action else f"无（{outcome}）"
        bits.append(f"- 行动: {action_label}")
        if learning:
            bits.append(f"- 学习: {learning}")
        return "\n".join(bits)

    def _load_rows(self) -> List[Dict[str, Any]]:
        path = self.jsonl_path
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _write_rows(self, rows: Iterable[Dict[str, Any]]) -> None:
        body = "".join(
            json.dumps(dict(row), ensure_ascii=False, default=str) + "\n" for row in rows
        )
        secure_write_text(self.jsonl_path, body, mode=0o600)


__all__ = [
    "MemoryStore",
    "SCHEMA_VERSION",
    "MEMORY_DIR_NAME",
    "MARKDOWN_FILE_NAME",
    "JSONL_FILE_NAME",
]
