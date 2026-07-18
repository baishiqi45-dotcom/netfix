"""Netfix MEMORY.md 长期记忆：Claude Code Auto Memory 风格的跨会话经验沉淀。

每次成功 Tier 1/Tier 2 修复或失败诊断后，把
   "症状 → 根因 → fix → 验证 + 时间 + 网络指纹"
追加到 `~/.netfix/memory/MEMORY.md`，下次相似症状进来时优先 grep 命中。

约束
----
- 写文件前 redact_report
- 90 天清理（默认，可配）
- 显式 `clear()` 删整个目录
- 不会保存密码、Token、订阅 URL

入口
----
from netfix.agent_memory import (
    append_entry,            # 成功修复或诊断后追加
    lookup_similar,          # 拉取相似条目（最多 N 条）
    clear,                   # 一键清除
    list_recent,             # 列出最近 N 条（人类可读）
)
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from netfix import agent_session
from netfix.constants import JOURNAL_DIR
from netfix.redaction import redact_text


MEMORY_DIR_NAME = "memory"
MEMORY_FILE_NAME = "MEMORY.md"
DEFAULT_RETENTION_DAYS = 90


def _memory_dir() -> Path:
    d = JOURNAL_DIR / MEMORY_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _memory_file() -> Path:
    return _memory_dir() / MEMORY_FILE_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".memory-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def _atomic_read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _hash_short(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


@dataclass
class MemoryEntry:
    schema_version: str
    timestamp: str
    symptom: str
    scenario_id: str
    root_cause_id: str
    action_id: Optional[str]
    action_outcome: str  # 'succeeded' | 'failed' | 'declined' | 'unknown'
    fingerprint_hash: str
    notes: str

    def format_markdown(self) -> str:
        return _format_entry(self)


def _make_entry(
    *,
    symptom: str,
    scenario_id: str,
    root_cause_id: str,
    action_id: Optional[str],
    action_outcome: str,
    fingerprint: Dict[str, Any],
    notes: str = "",
) -> MemoryEntry:
    return MemoryEntry(
        schema_version="netfix_memory_entry.v1",
        timestamp=_now_iso(),
        symptom=redact_text(str(symptom or ""))[:200],
        scenario_id=str(scenario_id or ""),
        root_cause_id=str(root_cause_id or ""),
        action_id=str(action_id) if action_id else None,
        action_outcome=str(action_outcome or "unknown"),
        fingerprint_hash=agent_session.network_fingerprint(fingerprint),
        notes=redact_text(str(notes or ""))[:400],
    )


def _format_entry(entry: MemoryEntry) -> str:
    bits = [f"- {entry.timestamp[:19]}Z · {entry.scenario_id} → {entry.root_cause_id}"]
    if entry.action_id:
        bits.append(f" [{entry.action_outcome}] `{entry.action_id}`")
    if entry.symptom:
        bits.append(f"  症状: {entry.symptom}")
    if entry.notes:
        bits.append(f"  说明: {entry.notes}")
    bits.append(f"  fingerprint: `{entry.fingerprint_hash}`")
    return "\n".join(bits) + "\n"


def append_entry(
    entry: Optional[Dict[str, Any]] = None,
    *,
    symptom: str = "",
    scenario_id: str = "",
    root_cause_id: str = "",
    action_id: Optional[str] = None,
    action_outcome: str = "succeeded",
    fingerprint: Optional[Dict[str, Any]] = None,
    notes: str = "",
) -> Any:
    """追加一条 MEMORY 条目；不破坏现有文件内容（append-only）。"""
    return_dict = False
    if isinstance(entry, dict):
        return_dict = True
        symptom = str(entry.get("symptom") or entry.get("summary") or symptom or "")
        scenario_id = str(entry.get("scenario_id") or scenario_id or "")
        root_cause_id = str(entry.get("root_cause_id") or entry.get("root_cause") or root_cause_id or "")
        action_id = str(entry.get("action_id") or entry.get("fix_executed") or action_id or "") or None
        action_outcome = str(entry.get("action_outcome") or entry.get("outcome") or action_outcome or "unknown")
        if fingerprint is None:
            fingerprint_value = entry.get("fingerprint")
            fingerprint = fingerprint_value if isinstance(fingerprint_value, dict) else {}
        notes = str(entry.get("notes") or entry.get("summary") or notes or "")
    entry = _make_entry(
        symptom=symptom,
        scenario_id=scenario_id,
        root_cause_id=root_cause_id,
        action_id=action_id,
        action_outcome=action_outcome,
        fingerprint=fingerprint or {},
        notes=notes,
    )
    path = _memory_file()
    header_text = f"# Netfix MEMORY (auto-generated, do not edit by hand)\n\n"
    body = _atomic_read_text(path)
    if not body:
        body = header_text + "## entries\n\n"
    body = body.rstrip() + "\n\n" + _format_entry(entry)
    _atomic_write_text(path, body)
    if return_dict:
        return {"ok": True, "entry": asdict(entry)}
    return entry


def _parse_entries(text: str) -> List[MemoryEntry]:
    """把 Markdown 反解析为 MemoryEntry 列表（容忍格式错误）。"""
    out: List[MemoryEntry] = []
    current_ts = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("- ") and " · " in line:
            parts = line[2:].split(" · ", 1)
            ts_part = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            current_ts = ts_part + "Z" if not ts_part.endswith("Z") else ts_part
            scenario_part, _, cause_part = rest.partition(" → ")
            symptom = ""
            notes = ""
            action_id = None
            outcome = "unknown"
            fp_hash = ""
            symptom_line = next((l for l in text.splitlines() if l.strip().startswith("症状:")), "")
            notes_line = next((l for l in text.splitlines() if l.strip().startswith("说明:")), "")
            fp_line = next((l for l in text.splitlines() if l.strip().startswith("fingerprint:")), "")
            if symptom_line:
                symptom = symptom_line.split(":", 1)[1].strip()
            if notes_line:
                notes = notes_line.split(":", 1)[1].strip()
            if fp_line:
                fp_hash = fp_line.split("`")[1] if "`" in fp_line else fp_line.split(":", 1)[1].strip()
            if " [`" in rest and "`]" in rest:
                # extract [outcome] `action_id`
                a = rest.split(" [", 1)[1]
                outcome = a.split("] ", 1)[0]
                action_id = a.split("`", 1)[1].split("`", 1)[0]
            out.append(
                MemoryEntry(
                    schema_version="netfix_memory_entry.v1",
                    timestamp=current_ts,
                    symptom=symptom,
                    scenario_id=scenario_part.strip(),
                    root_cause_id=cause_part.strip().split(" ", 1)[0],
                    action_id=action_id,
                    action_outcome=outcome,
                    fingerprint_hash=fp_hash,
                    notes=notes,
                )
            )
            # reset per-entry traces
            symptom = ""
            notes = ""
            fp_hash = ""
    return out


def list_recent(limit: int = 20) -> List[MemoryEntry]:
    text = _atomic_read_text(_memory_file())
    entries = _parse_entries(text)
    # Reverse so newest first.
    entries.reverse()
    return entries[: max(1, int(limit))]


def lookup_similar(
    fingerprint: Any,
    *,
    scenario_id: str = "",
    root_cause_id: str = "",
    limit: int = 3,
) -> List[MemoryEntry]:
    """查找 fingerprint / scenario / root_cause 一致的最近条目。

    返回按时间倒序、过滤掉已 declined 的条目，最多 limit 条。
    """
    query = str(fingerprint or "") if not isinstance(fingerprint, dict) else ""
    target_fp = agent_session.network_fingerprint(fingerprint if isinstance(fingerprint, dict) else {})
    target_scenario = str(scenario_id or "")
    target_cause = str(root_cause_id or "")
    entries = list_recent(limit=200)
    matched: List[MemoryEntry] = []
    for e in entries:
        if e.action_outcome == "declined":
            continue
        same_fp = bool(target_fp) and e.fingerprint_hash == target_fp
        same_scenario = bool(target_scenario) and e.scenario_id == target_scenario
        same_cause = bool(target_cause) and e.root_cause_id == target_cause
        text_hit = bool(query) and query.lower() in _format_entry(e).lower()
        if same_fp or same_scenario or (same_scenario and same_cause) or text_hit:
            matched.append(e)
        if len(matched) >= max(1, int(limit)):
            break
    return matched


def clear() -> Dict[str, Any]:
    """一键清除 MEMORY 目录。"""
    d = _memory_dir()
    if not d.exists():
        return {"ok": True, "removed": []}
    removed: List[str] = []
    for p in d.glob("*"):
        try:
            p.unlink()
            removed.append(p.name)
        except Exception:
            pass
    return {"ok": True, "removed": removed}


def apply_retention(retention_days: Optional[int] = None, *, days: Optional[int] = None) -> Dict[str, Any]:
    """清理 retention_days 之前的条目。"""
    if days is not None:
        retention_days = days
    days = int(retention_days) if retention_days else DEFAULT_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    text = _atomic_read_text(_memory_file())
    if not text:
        return {"ok": True, "removed": 0, "kept": 0}
    keep_lines: List[str] = []
    removed = 0
    kept = 0
    block: List[str] = []
    def flush() -> None:
        nonlocal removed, kept
        # Find timestamp in block; if newer than cutoff, keep.
        keep = True
        ts = ""
        for ln in block:
            if ln.strip().startswith("- ") and " · " in ln:
                ts = ln.split(" · ", 1)[0].strip("- ")
                break
        if ts:
            try:
                iso = ts.replace("Z", "+00:00")
                t = datetime.fromisoformat(iso)
                if t < cutoff:
                    keep = False
            except Exception:
                pass
        if keep:
            keep_lines.extend(block)
            keep_lines.append("")
            kept += 1
        else:
            removed += 1
        block.clear()

    for ln in text.splitlines():
        if ln.strip().startswith("- ") and " · " in ln:
            if block:
                flush()
        block.append(ln)
    if block:
        flush()
    new_header = "# Netfix MEMORY (auto-generated, do not edit by hand)\n\n## entries\n\n"
    _atomic_write_text(_memory_file(), new_header + "\n".join(keep_lines))
    return {"ok": True, "removed": removed, "kept": kept, "retention_days": days}
