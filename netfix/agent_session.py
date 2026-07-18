"""Netfix Agent 会话持久化：把多轮 AI 对话落到 JOURNAL_DIR/chat/。

设计目标
--------
1. 不破坏现有 P0 合同：所有落到磁盘的事实先经过 redact_report。
2. 跨会话引用：相同 fingerprint 时复用上次的根因/fix 经验，文案「这和上次同类问题」。
3. 用户决策记忆：避免重复催促用户已经拒绝过的 fix。
4. 不引入新依赖：只用 stdlib + 现有 redaction。

Schema
------
session_id: UUID4
turns: list of {turn_id, index, role, question, plan, tool_calls, observations, conclusion, answer}
state: {status, scenario_id, root_cause_id, confidence, decisions[], concepts_explained[]}
anchor: {report_id, network_fingerprint, proxy_profile_id}
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from netfix.constants import JOURNAL_DIR
from netfix.redaction import redact_report

AGENT_SCHEMA_VERSION = "netfix_agent_session.v1"
CHAT_DIR_NAME = "chat"
# New class-based persistence stores files under a sibling directory so the
# legacy module-level functions and ``AgentSessionStore`` never share filenames
# even when the user keeps both on disk. Tests override ``base_dir`` entirely.
SESSIONS_DIR_NAME = "agent_sessions"

_SCENARIO_KEYS = ("scenario_id", "root_cause_id", "network_fingerprint", "proxy_profile_id", "target_group", "exit_ip_class")


def _chat_dir() -> Path:
    path = JOURNAL_DIR / CHAT_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_timestamp() -> float:
    return time.time()


def compute_fingerprint(parts: Dict[str, Any]) -> str:
    """Symmetric fingerprint for cross-session similarity lookup."""
    normalized: List[str] = []
    for key in _SCENARIO_KEYS:
        value = parts.get(key)
        if value is None or value == "":
            continue
        normalized.append(f"{key}={value}")
    raw = "\n".join(normalized).strip()
    if not raw:
        return ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def network_fingerprint(global_state: Dict[str, Any]) -> str:
    """Stable hash of the current network without saving SSID/labels."""
    keys = ("gateway_ip_hash", "resolver_id_hash", "interface_kind", "network_location")
    blob = "|".join(f"{key}={global_state.get(key, '')}" for key in keys)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def new_session_id() -> str:
    return uuid.uuid4().hex


def _safe_read(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write(path: Path, data: Dict[str, Any]) -> bool:
    """Atomic write to avoid corrupting sessions on crash."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, default=str)
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            encoding="utf-8",
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False


def create_session(
    *,
    anchor: Optional[Dict[str, Any]] = None,
    scenario_id: Optional[str] = None,
) -> Dict[str, Any]:
    session_id = new_session_id()
    session = {
        "schema_version": AGENT_SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "anchor": {
            "report_id": (anchor or {}).get("report_id"),
            "network_fingerprint": (anchor or {}).get("network_fingerprint") or "",
            "proxy_profile_id": (anchor or {}).get("proxy_profile_id"),
        },
        "state": {
            "status": "active",
            "scenario_id": scenario_id,
            "root_cause_id": None,
            "confidence": 0.0,
            "decisions": [],
            "concepts_explained": [],
            "fingerprint": "",
        },
        "turns": [],
        "proactive_alerts": [],
    }
    _atomic_write(_chat_dir() / f"{session_id}.json", session)
    return session


def _decisions_summary(decisions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Return latest decision per action_id, not counting superseded ones."""
    latest: Dict[str, Dict[str, Any]] = {}
    for item in decisions:
        action_id = item.get("action_id")
        if not action_id:
            continue
        if item.get("superseded_by"):
            continue
        if item.get("expires_at"):
            try:
                expires = datetime.strptime(item["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    continue
            except Exception:
                pass
        previous = latest.get(action_id)
        if previous:
            try:
                prev_at = datetime.strptime(previous.get("at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                cur_at = datetime.strptime(item.get("at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if prev_at > cur_at:
                    continue
            except Exception:
                pass
        latest[action_id] = item
    return latest


def is_action_declined(decisions: List[Dict[str, Any]], action_id: str) -> bool:
    summary = _decisions_summary(decisions)
    item = summary.get(action_id)
    return bool(item and item.get("outcome") == "declined")


def append_turn(
    session_id: str,
    *,
    role: str = "user",
    question: Optional[str] = None,
    plan: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    observations: Optional[List[Dict[str, Any]]] = None,
    conclusion: Optional[Dict[str, Any]] = None,
    answer: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return None
    turns = list(session.get("turns") or [])
    turn_index = len(turns) + 1
    turn = {
        "turn_id": uuid.uuid4().hex,
        "index": turn_index,
        "role": role,
        "created_at": _now_iso(),
    }
    if question is not None:
        turn["question"] = question
    if plan is not None:
        turn["plan"] = plan
    if tool_calls is not None:
        turn["tool_calls"] = list(tool_calls)
    if observations is not None:
        turn["observations"] = list(observations)
    if conclusion is not None:
        turn["conclusion"] = conclusion
        state = session.setdefault("state", {})
        state["scenario_id"] = conclusion.get("scenario_id") or state.get("scenario_id")
        state["root_cause_id"] = conclusion.get("cause_id") or state.get("root_cause_id")
        try:
            state["confidence"] = float(conclusion.get("confidence") or state.get("confidence") or 0)
        except (TypeError, ValueError):
            state["confidence"] = state.get("confidence") or 0
    if answer is not None:
        # answer may contain actions; persist those that look safe
        turn["answer"] = _sanitize_answer(answer)
    turns.append(turn)
    session["turns"] = turns
    session["updated_at"] = _now_iso()
    _atomic_write(path, session)
    return turn


def _sanitize_answer(answer: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key in ("headline", "explanation", "severity", "provider_used", "fallback_reason"):
        if key in answer:
            safe[key] = answer[key]
    if isinstance(answer.get("actions"), list):
        safe["actions"] = [
            {"id": a.get("id"), "label": a.get("label"), "tier": a.get("tier")}
            for a in answer["actions"]
            if isinstance(a, dict) and a.get("id")
        ]
    return safe


def record_decision(
    session_id: str,
    *,
    action_id: str,
    outcome: str,
    reason_code: str = "user_choice",
    ttl_seconds: int = 30 * 24 * 3600,
    superseded_by: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return None
    state = session.setdefault("state", {})
    decisions = list(state.get("decisions") or [])
    # 之前的同 action_id 决策标记为 superseded
    if not superseded_by:
        for item in decisions:
            if item.get("action_id") == action_id and not item.get("superseded_by"):
                item["superseded_by"] = _now_iso()
    decision = {
        "action_id": action_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "at": _now_iso(),
    }
    if ttl_seconds > 0:
        decision["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    decisions.append(decision)
    state["decisions"] = decisions
    session["updated_at"] = _now_iso()
    _atomic_write(path, session)
    return decision


def record_concept_explained(session_id: str, concept_id: str) -> bool:
    """Track concepts that have already been explained in this session."""
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return False
    state = session.setdefault("state", {})
    concepts = list(state.get("concepts_explained") or [])
    if concept_id not in concepts:
        concepts.append(concept_id)
    state["concepts_explained"] = concepts
    session["updated_at"] = _now_iso()
    _atomic_write(path, session)
    return True


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    return _safe_read(_chat_dir() / f"{session_id}.json")


def list_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    """List lightweight session metadata, with descrption redacted."""
    path = _chat_dir()
    if not path.exists():
        return []
    files = sorted(path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    summaries: List[Dict[str, Any]] = []
    for file_path in files[: max(1, limit)]:
        data = _safe_read(file_path)
        if not data:
            continue
        first_question = ""
        for turn in data.get("turns") or []:
            if turn.get("role") == "user" and turn.get("question"):
                first_question = str(turn["question"])
                break
        redacted = redact_report({"first_question": first_question}, level="balanced").get(
            "redacted_report", {}
        )
        summaries.append(
            {
                "session_id": data.get("session_id"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "scenario_id": (data.get("state") or {}).get("scenario_id"),
                "root_cause_id": (data.get("state") or {}).get("root_cause_id"),
                "status": (data.get("state") or {}).get("status"),
                "first_question_preview": redacted.get("first_question", ""),
                "turn_count": len(data.get("turns") or []),
            }
        )
    return summaries


def delete_session(session_id: str) -> bool:
    """Clear a single session; returns True when the file existed."""
    path = _chat_dir() / f"{session_id}.json"
    try:
        if path.exists():
            path.unlink()
            return True
    except Exception:
        return False
    return False


def clear_all_sessions() -> int:
    """Wipe every local chat session; returns number of files removed."""
    removed = 0
    path = _chat_dir()
    if not path.exists():
        return 0
    for file_path in path.glob("*.json"):
        try:
            file_path.unlink()
            removed += 1
        except Exception:
            continue
    return removed


def _session_matches_fingerprint(session: Dict[str, Any], fingerprint: str) -> bool:
    state = session.get("state") or {}
    if state.get("fingerprint") and state.get("fingerprint") == fingerprint:
        return True
    anchor = session.get("anchor") or {}
    return bool(anchor.get("network_fingerprint")) and anchor.get("network_fingerprint") == fingerprint


def find_similar_sessions(
    fingerprint: str,
    *,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    if not fingerprint:
        return []
    matches: List[Dict[str, Any]] = []
    path = _chat_dir()
    if not path.exists():
        return []
    for file_path in sorted(path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        session = _safe_read(file_path)
        if not session or not _session_matches_fingerprint(session, fingerprint):
            continue
        turns = session.get("turns") or []
        # 倒序找到第一个含有 conclusion 的回合
        appended = False
        for turn in reversed(turns):
            conclusion = turn.get("conclusion") or {}
            if conclusion.get("cause_id") and conclusion.get("scenario_id"):
                matches.append(
                    {
                        "session_id": session.get("session_id"),
                        "scenario_id": conclusion.get("scenario_id"),
                        "cause_id": conclusion.get("cause_id"),
                        "confidence": conclusion.get("confidence"),
                        "updated_at": session.get("updated_at"),
                    }
                )
                appended = True
                break
        if not appended:
            state = session.get("state") or {}
            matches.append(
                {
                    "session_id": session.get("session_id"),
                    "scenario_id": state.get("scenario_id"),
                    "cause_id": state.get("root_cause_id"),
                    "confidence": state.get("confidence"),
                    "updated_at": session.get("updated_at"),
                }
            )
        if len(matches) >= limit:
            break
    return matches


def attach_fingerprint(session_id: str, fingerprint: str) -> bool:
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return False
    state = session.setdefault("state", {})
    state["fingerprint"] = fingerprint
    session["updated_at"] = _now_iso()
    return _atomic_write(path, session)


def attach_anchor(session_id: str, *, report_id: Optional[str], proxy_profile_id: Optional[str]) -> bool:
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return False
    anchor = session.setdefault("anchor", {})
    if report_id is not None:
        anchor["report_id"] = report_id
    if proxy_profile_id is not None:
        anchor["proxy_profile_id"] = proxy_profile_id
    session["updated_at"] = _now_iso()
    return _atomic_write(path, session)


def append_proactive_alert(session_id: str, alert: Dict[str, Any]) -> bool:
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return False
    alerts = list(session.get("proactive_alerts") or [])
    alerts.append(alert)
    session["proactive_alerts"] = alerts
    session["updated_at"] = _now_iso()
    return _atomic_write(path, session)


def mark_completed(session_id: str, status: str = "completed") -> bool:
    path = _chat_dir() / f"{session_id}.json"
    session = _safe_read(path)
    if not session:
        return False
    state = session.setdefault("state", {})
    state["status"] = status
    session["updated_at"] = _now_iso()
    return _atomic_write(path, session)


# ---------------------------------------------------------------------------
# Class-based AgentSessionStore
# ---------------------------------------------------------------------------
#
# The functions above are kept for back-compat with proactive_alerts and
# agent_memory. ``AgentSessionStore`` is the P0-A.3 conversational session
# store: HTTP ``/chat/sessions/*`` endpoints and ``netfix_chat`` should use
# this class. It writes to ``<base_dir>/agent_sessions/<session_id>.json``
# instead of ``<base_dir>/chat`` so the two layouts never collide on a real
# install. ``base_dir`` defaults to ``JOURNAL_DIR`` (== ~/.netfix) so passing
# a ``tmp_path`` from tests isolates the store cleanly.
#
# Sessions persist the full conversation, including a normalized turn schema
# (turn_id / index / role / created_at / question / plan / tool_calls /
# observations / conclusion / answer / confirmation_request). All free-text
# bodies are passed through ``redact_report`` before they reach disk.


import re as _re_class  # noqa: E402
import threading as _threading_class  # noqa: E402
import uuid as _uuid_class  # noqa: E402
from datetime import datetime as _dt_class, timezone as _tz_class  # noqa: E402
from typing import Any as _Any, Dict as _Dict, Iterable as _Iterable, List as _List, Optional as _Opt  # noqa: E402

from netfix.utils import ensure_dir as _ensure_dir_class, ensure_private_dir as _ensure_private_dir_class, secure_write_text as _secure_write_text_class  # noqa: E402


SESSION_SCHEMA_VERSION = "netfix_agent_session_store.v1"
_VALID_STATUSES = {
    "active",
    "awaiting_confirmation",
    "awaiting_user_input",
    "completed",
    "failed",
    "canceled",
}
_VALID_ROLES = {"user", "assistant", "system", "tool"}
_VALID_DECISION_OUTCOMES = {"accepted", "rejected", "postponed"}
_VALID_DECISION_CATEGORIES = {
    "upload_redacted_report",
    "upload_image",
    "change_system_setting",
    "switch_proxy_node",
    "flush_dns",
    "renew_dhcp",
    "disable_ipv6",
    "reset_system_proxy",
    "manual_ack",
    "user_cancel",
}
_TURN_FIELDS = (
    "turn_id",
    "index",
    "role",
    "created_at",
    "question",
    "plan",
    "tool_calls",
    "observations",
    "conclusion",
    "answer",
    "confirmation_request",
)
_MAX_TURNS = 200
_MAX_DECISIONS = 100
_MAX_CONCEPTS = 64


def _class_now_iso() -> str:
    return _dt_class.now(_tz_class.utc).isoformat()


def _class_safe_id(value: _Opt[str], *, field: str = "id") -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if not _re_class.fullmatch(r"[A-Za-z0-9._:\-]{1,128}", text):
        raise ValueError(f"{field} contains unsupported characters: {value!r}")
    return text


def _class_redact(value: _Any) -> _Any:
    if value is None:
        return None
    try:
        out = redact_report({"value": value}, level="balanced").get("redacted_report", {})
        return out.get("value", value)
    except Exception:
        return value


def _class_normalize_turn(turn: _Any, index: int) -> _Dict[str, _Any]:
    if not isinstance(turn, dict):
        turn = {}
    role = str(turn.get("role") or "user").strip().lower()
    if role not in _VALID_ROLES:
        role = "user"
    body = {
        "question": turn.get("question"),
        "plan": turn.get("plan"),
        "tool_calls": turn.get("tool_calls"),
        "observations": turn.get("observations"),
        "conclusion": turn.get("conclusion"),
        "answer": turn.get("answer"),
        "confirmation_request": turn.get("confirmation_request"),
    }
    safe_body = _class_redact(body)
    if not isinstance(safe_body, dict):
        safe_body = {}
    return {
        "turn_id": str(turn.get("turn_id") or f"turn-{int(time.time() * 1000)}-{index}"),
        "index": int(index),
        "role": role,
        "created_at": str(turn.get("created_at") or _class_now_iso()),
        "question": safe_body.get("question", ""),
        "plan": safe_body.get("plan", []),
        "tool_calls": safe_body.get("tool_calls", []),
        "observations": safe_body.get("observations", []),
        "conclusion": safe_body.get("conclusion", ""),
        "answer": safe_body.get("answer", ""),
        "confirmation_request": safe_body.get("confirmation_request"),
    }


class AgentSessionStore:
    """Persistent store for conversational AI triage sessions.

    ``base_dir`` defaults to :data:`netfix.constants.JOURNAL_DIR` so production
    callers can simply instantiate ``AgentSessionStore()`` and get the canonical
    location. Tests should pass ``tmp_path`` via the ``base_dir`` argument so
    they run isolated against the real filesystem.

    Layout::

        <base_dir>/agent_sessions/<session_id>.json

    Each session file is a JSON document with the shape::

        {
            "schema_version": "netfix_agent_session_store.v1",
            "session_id": "<id>",
            "created_at": "<iso8601>",
            "updated_at": "<iso8601>",
            "status": "active" | ...,
            "scenario_id": "...",
            "root_cause_id": "...",
            "symptom_text": "<redacted>",
            "fingerprint": "<sha256:16>",
            "fingerprint_history": ["<sha256:16>", ...],
            "metadata": {...},
            "turns": [ ... ],
            "decisions": [ ... ],
            "explained_concepts": ["..."]
        }

    Free-text bodies are passed through ``redact_report`` so persisted JSON
    never leaks proxies / tokens / raw IPs. ``fingerprint`` is a 16-hex sha256
    digest — never a raw URL or IP.
    """

    def __init__(self, base_dir: _Opt[_Any] = None) -> None:
        if base_dir is None:
            base_dir = JOURNAL_DIR
        self._base_dir = Path(base_dir).expanduser()
        self._sessions_dir: _Opt[Path] = None
        self._lock = _threading_class.Lock()
        self._index_lock = _threading_class.Lock()
        self._cache: _Dict[str, _Dict[str, _Any]] = {}

    @property
    def sessions_dir(self) -> Path:
        """Return (and lazily create) the directory holding session files."""
        if self._sessions_dir is None:
            _ensure_dir_class(self._base_dir)
            directory = self._base_dir / SESSIONS_DIR_NAME
            _ensure_dir_class(directory)
            _ensure_private_dir_class(directory)
            self._sessions_dir = directory
        return self._sessions_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    # -- public API --------------------------------------------------------

    def create(
        self,
        *,
        scenario_id: str = "",
        root_cause_id: str = "",
        symptom_text: str = "",
        fingerprint: str = "",
        status: str = "active",
        session_id: _Opt[str] = None,
        metadata: _Opt[_Dict[str, _Any]] = None,
    ) -> str:
        """Create a new session and return its id.

        ``session_id`` may be supplied by the caller; otherwise we mint one.
        A duplicate id raises :class:`FileExistsError` so callers can detect
        collisions (the test contract forbids reusing the same id).
        """
        with self._index_lock:
            self._ensure_index_locked()
            new_id = session_id or f"chat-{int(time.time() * 1000)}-{_uuid_class.uuid4().hex[:8]}"
            new_id = _class_safe_id(new_id, field="session_id")
            if new_id in self._cache:
                raise FileExistsError(f"session_id already exists: {new_id}")
            now = _class_now_iso()
            normalized_status = str(status or "active").strip().lower()
            if normalized_status not in _VALID_STATUSES:
                normalized_status = "active"
            redacted_symptom = _class_redact({"text": symptom_text}).get("text") if symptom_text else ""
            if not isinstance(redacted_symptom, str):
                redacted_symptom = ""
            safe_metadata = _class_redact(metadata) if isinstance(metadata, dict) and metadata else {}
            if not isinstance(safe_metadata, dict):
                safe_metadata = {}
            session: _Dict[str, _Any] = {
                "schema_version": SESSION_SCHEMA_VERSION,
                "session_id": new_id,
                "created_at": now,
                "updated_at": now,
                "status": normalized_status,
                "scenario_id": str(scenario_id or ""),
                "root_cause_id": str(root_cause_id or ""),
                "symptom_text": redacted_symptom,
                "fingerprint": str(fingerprint or ""),
                "metadata": safe_metadata,
                "turns": [],
                "decisions": [],
                "explained_concepts": [],
                "fingerprint_history": [str(fingerprint)] if fingerprint else [],
            }
            self._atomic_write_locked(session)
            self._cache[new_id] = session
            return new_id

    def list_summaries(self) -> _List[_Dict[str, _Any]]:
        """Return one lightweight summary dict per session, newest first."""
        with self._index_lock:
            self._ensure_index_locked()
            items = [self._summary(session) for session in self._cache.values()]
        items.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
        return items

    def get(self, session_id: str) -> _Opt[_Dict[str, _Any]]:
        """Return a deep copy of the session, or ``None`` if it does not exist."""
        session_id = _class_safe_id(session_id, field="session_id")
        with self._index_lock:
            self._ensure_index_locked()
            session = self._cache.get(session_id)
            if session is None:
                return None
            return json.loads(json.dumps(session, ensure_ascii=False, default=str))

    def append_turn(self, session_id: str, turn: _Any) -> _Dict[str, _Any]:
        """Append ``turn`` to ``session_id``; return the normalized turn."""
        session_id = _class_safe_id(session_id, field="session_id")
        with self._index_lock:
            self._ensure_index_locked()
            with self._lock:
                session = self._cache.get(session_id)
                if session is None:
                    raise FileNotFoundError(f"session not found: {session_id}")
                turns = list(session.get("turns") or [])
                if len(turns) >= _MAX_TURNS:
                    # Match the in-memory index when we drop the oldest.
                    turns = turns[1:]
                normalized = _class_normalize_turn(turn, len(turns))
                turns.append(normalized)
                session["turns"] = turns
                session["updated_at"] = _class_now_iso()
                self._atomic_write_locked(session)
                return normalized

    def record_decision(self, session_id: str, decision: _Any) -> _Dict[str, _Any]:
        """Append a user decision to ``session_id`` and update session status."""
        if not isinstance(decision, dict):
            raise ValueError("decision must be a dict")
        session_id = _class_safe_id(session_id, field="session_id")
        category = str(decision.get("category") or "").strip()
        if category not in _VALID_DECISION_CATEGORIES:
            raise ValueError(f"unknown decision category: {category}")
        outcome = str(decision.get("outcome") or "").strip().lower()
        if outcome not in _VALID_DECISION_OUTCOMES:
            raise ValueError("decision.outcome must be accepted, rejected, or postponed")
        with self._index_lock:
            self._ensure_index_locked()
            with self._lock:
                session = self._cache.get(session_id)
                if session is None:
                    raise FileNotFoundError(f"session not found: {session_id}")
                decisions = list(session.get("decisions") or [])
                if len(decisions) >= _MAX_DECISIONS:
                    decisions = decisions[1:]
                payload = _class_redact(decision) if isinstance(decision, dict) else {}
                if not isinstance(payload, dict):
                    payload = {}
                entry = {
                    "decision_id": str(decision.get("decision_id") or f"dec-{int(time.time() * 1000)}-{_uuid_class.uuid4().hex[:8]}"),
                    "created_at": _class_now_iso(),
                    "category": category,
                    "outcome": outcome,
                    "action_id": str(decision.get("action_id") or ""),
                    "confirmation": str(decision.get("confirmation") or ""),
                    "note": str(payload.get("note") or ""),
                }
                decisions.append(entry)
                session["decisions"] = decisions
                if outcome == "accepted" and category != "user_cancel":
                    session["status"] = "completed"
                elif outcome == "rejected" or category == "user_cancel":
                    session["status"] = "canceled"
                else:
                    session["status"] = "awaiting_user_input"
                session["updated_at"] = _class_now_iso()
                self._atomic_write_locked(session)
                return entry

    def mark_concept_explained(self, session_id: str, concept_id: str) -> _List[str]:
        """Idempotently add ``concept_id`` to the session's explained list."""
        session_id = _class_safe_id(session_id, field="session_id")
        concept_id = _class_safe_id(concept_id, field="concept_id")
        with self._index_lock:
            self._ensure_index_locked()
            with self._lock:
                session = self._cache.get(session_id)
                if session is None:
                    raise FileNotFoundError(f"session not found: {session_id}")
                explained = list(session.get("explained_concepts") or [])
                if concept_id not in explained:
                    explained.append(concept_id)
                if len(explained) > _MAX_CONCEPTS:
                    explained = explained[-_MAX_CONCEPTS:]
                session["explained_concepts"] = explained
                session["updated_at"] = _class_now_iso()
                self._atomic_write_locked(session)
                return explained

    def find_similar(self, fingerprint: str) -> _List[_Dict[str, _Any]]:
        """Return session summaries whose fingerprint matches (current or history)."""
        target = str(fingerprint or "").strip().lower()
        if not target:
            return []
        with self._index_lock:
            self._ensure_index_locked()
            matches: _List[_Dict[str, _Any]] = []
            for session in self._cache.values():
                history = session.get("fingerprint_history") or []
                if not isinstance(history, list):
                    history = []
                current_fp = str(session.get("fingerprint") or "").strip().lower()
                history_lookup = {str(item).strip().lower() for item in history if isinstance(item, str)}
                if target == current_fp or target in history_lookup:
                    matches.append(self._summary(session))
        matches.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
        return matches

    def delete(self, session_id: str) -> bool:
        """Delete the session file. Returns ``True`` when a file was removed."""
        session_id = _class_safe_id(session_id, field="session_id")
        with self._index_lock:
            self._ensure_index_locked()
            with self._lock:
                path = self.sessions_dir / f"{session_id}.json"
                removed = False
                if path.exists():
                    try:
                        path.unlink()
                        removed = True
                    except OSError:
                        removed = False
                self._cache.pop(session_id, None)
                return removed

    # -- internals ---------------------------------------------------------

    def _ensure_index_locked(self) -> None:
        if self._cache:
            return
        sessions_dir = self.sessions_dir
        for path in sorted(sessions_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            session_id = str(data.get("session_id") or path.stem)
            self._cache[session_id] = data

    def _atomic_write_locked(self, session: _Dict[str, _Any]) -> None:
        sessions_dir = self.sessions_dir
        session_id = str(session.get("session_id") or "")
        if not session_id:
            raise ValueError("session.session_id is required")
        path = sessions_dir / f"{session_id}.json"
        safe_session = json.loads(json.dumps(session, ensure_ascii=False, default=str))
        payload = json.dumps(safe_session, ensure_ascii=False, default=str, indent=2)
        _ensure_private_dir_class(sessions_dir)
        _secure_write_text_class(path, payload, mode=0o600)

    @staticmethod
    def _summary(session: _Dict[str, _Any]) -> _Dict[str, _Any]:
        turns = session.get("turns") if isinstance(session.get("turns"), list) else []
        decisions = session.get("decisions") if isinstance(session.get("decisions"), list) else []
        concepts = session.get("explained_concepts") if isinstance(session.get("explained_concepts"), list) else []
        status = str(session.get("status") or "active").strip().lower()
        if status not in _VALID_STATUSES:
            status = "active"
        return {
            "session_id": str(session.get("session_id") or ""),
            "status": status,
            "created_at": str(session.get("created_at") or ""),
            "updated_at": str(session.get("updated_at") or ""),
            "scenario_id": str(session.get("scenario_id") or ""),
            "root_cause_id": str(session.get("root_cause_id") or ""),
            "fingerprint": str(session.get("fingerprint") or ""),
            "turn_count": len(turns),
            "decision_count": len(decisions),
            "explained_concepts": list(concepts),
            "last_turn_role": str(turns[-1].get("role") or "") if turns else "",
        }


__all__ = [
    "AGENT_SCHEMA_VERSION",
    "CHAT_DIR_NAME",
    "compute_fingerprint",
    "network_fingerprint",
    "new_session_id",
    "create_session",
    "append_turn",
    "record_decision",
    "record_concept_explained",
    "load_session",
    "list_sessions",
    "delete_session",
    "clear_all_sessions",
    "find_similar_sessions",
    "attach_fingerprint",
    "attach_anchor",
    "append_proactive_alert",
    "mark_completed",
    "is_action_declined",
    "AgentSessionStore",
    "SESSION_SCHEMA_VERSION",
]  # noqa: E501
