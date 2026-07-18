"""Tests for netfix.agent_session — 会话持久化 + 决策记忆 + 跨会话 fingerprint。"""
from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from netfix import agent_session, api, memory
from netfix.agent_session import AgentSessionStore
from netfix.memory import MemoryStore


class _TmpJournal:
    """把 JOURNAL_DIR 重定向到 tmp，避免污染真实文件。"""

    def __init__(self, base: Path):
        self.base = base

    def __enter__(self):
        self._orig = agent_session.JOURNAL_DIR
        agent_session.JOURNAL_DIR = self.base
        self.base.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, exc_type, exc, tb):
        agent_session.JOURNAL_DIR = self._orig


class TestFingerprint(unittest.TestCase):
    def test_fingerprint_is_symmetric(self):
        parts = {"scenario_id": "dns", "root_cause_id": "dns-cache-stale", "network_fingerprint": "abc"}
        first = agent_session.compute_fingerprint(parts)
        second = agent_session.compute_fingerprint(dict(parts))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)

    def test_fingerprint_changes_when_scenario_changes(self):
        a = agent_session.compute_fingerprint({"scenario_id": "dns", "root_cause_id": "dns-cache-stale"})
        b = agent_session.compute_fingerprint({"scenario_id": "dns", "root_cause_id": "dns-leak"})
        self.assertNotEqual(a, b)

    def test_fingerprint_empty_when_no_keys(self):
        self.assertEqual("", agent_session.compute_fingerprint({}))


class TestAgentSessionPersistence(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self._ctx = _TmpJournal(self.tmp)
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_create_session_persists_to_disk(self):
        s = agent_session.create_session(scenario_id="dns-abnormal")
        path = self.tmp / "chat" / f"{s['session_id']}.json"
        self.assertTrue(path.exists())
        self.assertEqual(s["state"]["scenario_id"], "dns-abnormal")

    def test_append_turn_and_load(self):
        s = agent_session.create_session()
        agent_session.append_turn(
            s["session_id"],
            role="user",
            question="为什么 ChatGPT 打不开？",
        )
        agent_session.append_turn(
            s["session_id"],
            role="assistant",
            answer={"headline": "代理节点超时", "explanation": "试试切节点", "actions": []},
        )
        loaded = agent_session.load_session(s["session_id"])
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["turns"]), 2)
        self.assertEqual(loaded["turns"][0]["question"], "为什么 ChatGPT 打不开？")

    def test_conclusion_updates_state(self):
        s = agent_session.create_session()
        agent_session.append_turn(
            s["session_id"],
            role="tool_result",
            conclusion={"scenario_id": "dns", "cause_id": "dns-cache-stale", "confidence": 0.88},
        )
        loaded = agent_session.load_session(s["session_id"])
        self.assertEqual(loaded["state"]["root_cause_id"], "dns-cache-stale")
        self.assertAlmostEqual(loaded["state"]["confidence"], 0.88)

    def test_list_sessions_returns_summaries(self):
        s1 = agent_session.create_session(scenario_id="dns")
        s2 = agent_session.create_session(scenario_id="proxy")
        summaries = agent_session.list_sessions()
        ids = {s["session_id"] for s in summaries}
        self.assertIn(s1["session_id"], ids)
        self.assertIn(s2["session_id"], ids)

    def test_delete_session(self):
        s = agent_session.create_session()
        ok = agent_session.delete_session(s["session_id"])
        self.assertTrue(ok)
        self.assertIsNone(agent_session.load_session(s["session_id"]))

    def test_proactive_alerts_are_recorded(self):
        s = agent_session.create_session()
        agent_session.append_proactive_alert(
            s["session_id"],
            alert={"alert_id": "abc", "type": "exit_ip_type_change", "severity": "warn"},
        )
        loaded = agent_session.load_session(s["session_id"])
        self.assertEqual(len(loaded["proactive_alerts"]), 1)


class TestDecisionMemory(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self._ctx = _TmpJournal(self.tmp)
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_record_decision_and_check_declined(self):
        s = agent_session.create_session()
        agent_session.record_decision(
            s["session_id"],
            action_id="switch-node",
            outcome="declined",
            reason_code="work_session",
        )
        loaded = agent_session.load_session(s["session_id"])
        self.assertTrue(agent_session.is_action_declined(loaded["state"]["decisions"], "switch-node"))

    def test_accepted_decision_is_not_declined(self):
        s = agent_session.create_session()
        agent_session.record_decision(s["session_id"], action_id="flush-dns-cache", outcome="accepted")
        loaded = agent_session.load_session(s["session_id"])
        self.assertFalse(agent_session.is_action_declined(loaded["state"]["decisions"], "flush-dns-cache"))

    def test_expired_decision_is_ignored(self):
        s = agent_session.create_session()
        # inject expired decision
        loaded = agent_session.load_session(s["session_id"])
        loaded["state"]["decisions"] = [
            {"action_id": "switch-node", "outcome": "declined", "at": "2020-01-01T00:00:00Z", "expires_at": "2020-02-01T00:00:00Z"}
        ]
        from netfix.agent_session import _atomic_write
        _atomic_write(self.tmp / "chat" / f"{s['session_id']}.json", loaded)
        reloaded = agent_session.load_session(s["session_id"])
        self.assertFalse(agent_session.is_action_declined(reloaded["state"]["decisions"], "switch-node"))


class TestConceptMemory(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self._ctx = _TmpJournal(self.tmp)
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_concept_marked_and_readable(self):
        s = agent_session.create_session()
        agent_session.record_concept_explained(s["session_id"], "dns_leak")
        loaded = agent_session.load_session(s["session_id"])
        self.assertIn("dns_leak", loaded["state"]["concepts_explained"])


class TestSimilarSessions(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self._ctx = _TmpJournal(self.tmp)
        self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_find_similar_by_fingerprint(self):
        fingerprint = agent_session.compute_fingerprint(
            {"scenario_id": "dns-abnormal", "root_cause_id": "dns-cache-stale"}
        )
        s = agent_session.create_session()
        agent_session.attach_anchor(
            s["session_id"],
            report_id="r1",
            proxy_profile_id="default",
        )
        agent_session.attach_fingerprint(s["session_id"], fingerprint)
        agent_session.append_turn(
            s["session_id"], role="assistant",
            answer={"headline": "DNS 缓存过期", "actions": [{"id": "flush-dns-cache"}]},
        )
        similar = agent_session.find_similar_sessions(fingerprint=fingerprint, limit=5)
        self.assertTrue(len(similar) >= 1)
        self.assertEqual(similar[0]["session_id"], s["session_id"])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Class-based AgentSessionStore — netfix.agent_session.AgentSessionStore
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Find an unused TCP port without consuming the kernel-assigned one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _make_store(tmp_path: Path) -> AgentSessionStore:
    return AgentSessionStore(base_dir=tmp_path)


def _make_memory(tmp_path: Path) -> MemoryStore:
    return MemoryStore(base_dir=tmp_path)


class TestAgentSessionStoreLifecycle:
    """Cover the P0 class-based AgentSessionStore required by ``/chat/sessions``.

    pytest-style functions so we can use the ``tmp_path`` fixture directly.
    """

    def test_create_returns_id_and_persists_file(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(
            scenario_id="dns-cache-stale",
            root_cause_id="dns-cache-stale",
            symptom_text="DNS_PROBE",
            fingerprint="aabbccddeeff0011",
        )
        assert sid
        path = store.sessions_dir / f"{sid}.json"
        assert path.exists(), f"expected {path} to exist"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["scenario_id"] == "dns-cache-stale"
        assert payload["root_cause_id"] == "dns-cache-stale"
        assert payload["fingerprint"] == "aabbccddeeff0011"
        assert payload["status"] == "active"
        assert payload["turns"] == []
        assert payload["decisions"] == []

    def test_duplicate_session_id_raises(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="x")
        try:
            store.create(scenario_id="x", session_id=sid)
        except FileExistsError:
            pass
        else:
            raise AssertionError("expected FileExistsError for duplicate session_id")

    def test_get_and_list_summaries_round_trip(self, tmp_path):
        store = _make_store(tmp_path)
        s1 = store.create(scenario_id="a", root_cause_id="rca-a", fingerprint="fp-aaaa")
        s2 = store.create(scenario_id="b", root_cause_id="rca-b", fingerprint="fp-bbbb")
        full = store.get(s1)
        assert full is not None
        assert full["scenario_id"] == "a"
        summaries = store.list_summaries()
        ids = {row["session_id"] for row in summaries}
        assert s1 in ids
        assert s2 in ids
        assert summaries[0]["session_id"] == s2

    def test_get_unknown_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get("does-not-exist") is None

    def test_append_turn_persists_with_required_fields(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="dns-cache-stale", fingerprint="fp-1")
        turn = store.append_turn(sid, {
            "role": "user",
            "question": "why is chat.openai.com failing?",
            "plan": [{"tool": "netfix_dns_resolve", "why": "resolve target"}],
            "tool_calls": [{"tool": "netfix_dns_resolve", "result": {"ok": True}}],
            "observations": [{"fact": "DNS A record returned 0.0.0.0"}],
            "conclusion": "DNS_PROBE error suggests stale cache",
            "answer": "Try flushing DNS cache",
            "confirmation_request": None,
        })
        for field in (
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
        ):
            assert field in turn, f"missing field {field}"
        assert turn["index"] == 0
        assert turn["role"] == "user"

        session = store.get(sid)
        assert len(session["turns"]) == 1
        assert session["turns"][0]["question"] == "why is chat.openai.com failing?"
        assert session["status"] == "active"

    def test_append_turn_increments_index(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="x")
        first = store.append_turn(sid, {"role": "user", "question": "one"})
        second = store.append_turn(sid, {"role": "assistant", "answer": "two"})
        third = store.append_turn(sid, {"role": "user", "question": "three"})
        assert first["index"] == 0
        assert second["index"] == 1
        assert third["index"] == 2

    def test_record_decision_updates_status(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="x")
        decision = store.record_decision(sid, {
            "category": "manual_ack",
            "outcome": "accepted",
            "action_id": "flush-dns-cache",
            "confirmation": "FLUSH_DNS_CACHE",
            "note": "user said yes",
        })
        assert decision["outcome"] == "accepted"
        assert decision["action_id"] == "flush-dns-cache"
        session = store.get(sid)
        assert session["decisions"][0]["decision_id"] == decision["decision_id"]
        assert session["status"] == "completed"

        # rejected → canceled
        sid2 = store.create(scenario_id="y")
        store.record_decision(sid2, {"category": "manual_ack", "outcome": "rejected"})
        assert store.get(sid2)["status"] == "canceled"

        # postponed → awaiting_user_input
        sid3 = store.create(scenario_id="z")
        store.record_decision(sid3, {"category": "manual_ack", "outcome": "postponed"})
        assert store.get(sid3)["status"] == "awaiting_user_input"

    def test_record_decision_rejects_invalid_outcome(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="x")
        try:
            store.record_decision(sid, {"category": "manual_ack", "outcome": "lolwat"})
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for invalid outcome")

    def test_mark_concept_explained_is_idempotent(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="x")
        first = store.mark_concept_explained(sid, "dns-basics")
        assert first == ["dns-basics"]
        again = store.mark_concept_explained(sid, "dns-basics")
        assert again == ["dns-basics"]
        store.mark_concept_explained(sid, "ipv6-leak")
        session = store.get(sid)
        assert session["explained_concepts"] == ["dns-basics", "ipv6-leak"]

    def test_mark_concept_explained_unknown_session_raises(self, tmp_path):
        store = _make_store(tmp_path)
        try:
            store.mark_concept_explained("missing", "dns-basics")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError for missing session")

    def test_delete_removes_file(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="x")
        path = store.sessions_dir / f"{sid}.json"
        assert path.exists()
        assert store.delete(sid)
        assert not path.exists(), "file must be gone after delete"
        assert store.get(sid) is None
        assert not store.delete(sid)


class TestAgentSessionStoreFingerprint:
    def test_fingerprint_match_returns_session(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="dns-cache-stale", fingerprint="abc123")
        matches = store.find_similar("abc123")
        assert [m["session_id"] for m in matches] == [sid]

    def test_fingerprint_match_history(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.create(scenario_id="dns", fingerprint="old-fp")
        # Mutate the cache + on-disk fingerprint to simulate history rotation.
        session = store.get(sid)
        session["fingerprint"] = "new-fp"
        session["fingerprint_history"].append("new-fp")
        store._cache[sid] = session
        store._atomic_write_locked(session)

        assert [m["session_id"] for m in store.find_similar("old-fp")] == [sid]
        assert [m["session_id"] for m in store.find_similar("new-fp")] == [sid]

    def test_fingerprint_no_match(self, tmp_path):
        store = _make_store(tmp_path)
        store.create(scenario_id="dns", fingerprint="abc")
        assert store.find_similar("zzz") == []
        assert store.find_similar("") == []


# ---------------------------------------------------------------------------
# MemoryStore — netfix.memory.MemoryStore
# ---------------------------------------------------------------------------


class TestMemoryStore:
    def test_append_entry_persists_to_markdown_and_jsonl(self, tmp_path):
        store = _make_memory(tmp_path)
        entry = store.append_entry(
            date="2026-07-18 14:23",
            scenario_id="dns-cache-stale",
            root_cause_id="dns-cache-stale",
            fingerprint="deadbeefcafe1234",
            action_id="flush-dns-cache",
            verify_result="accepted",
            symptom="DNS_PROBE on chat.openai.com",
            target="chat.openai.com",
            learning="此 Mac 在 Wi-Fi 切换后大概率命中此根因",
            confidence=0.88,
        )
        assert entry["scenario_id"] == "dns-cache-stale"
        assert entry["verify_result"] == "accepted"
        assert store.markdown_path.exists()
        assert store.jsonl_path.exists()
        md = store.read_markdown()
        assert "# 2026-07-18 14:23 · dns-cache-stale" in md
        assert "flush-dns-cache" in md
        assert "接受" in md
        assert "`deadbeefcafe1234`" in md

    def test_find_recent_newest_first(self, tmp_path):
        store = _make_memory(tmp_path)
        store.append_entry(date="2026-07-15 10:00", scenario_id="dns-cache-stale",
                           root_cause_id="dns-cache-stale", fingerprint="aa",
                           action_id="flush-dns-cache", verify_result="accepted")
        store.append_entry(date="2026-07-18 14:23", scenario_id="dns-cache-stale",
                           root_cause_id="dns-cache-stale", fingerprint="bb",
                           action_id="flush-dns-cache", verify_result="accepted")
        store.append_entry(date="2026-07-18 15:00", scenario_id="ipv6-leak",
                           root_cause_id="ipv6-leak", fingerprint="cc",
                           action_id="disable-ipv6", verify_result="accepted")
        recent = store.find_recent(limit=10)
        assert len(recent) == 3
        assert recent[0]["fingerprint"] == "cc"
        assert recent[0]["scenario_id"] == "ipv6-leak"

    def test_find_recent_filters_by_scenario(self, tmp_path):
        store = _make_memory(tmp_path)
        store.append_entry(date="2026-07-18 14:23", scenario_id="dns-cache-stale",
                           root_cause_id="dns-cache-stale", fingerprint="aa",
                           action_id="flush-dns-cache", verify_result="accepted")
        store.append_entry(date="2026-07-18 15:00", scenario_id="ipv6-leak",
                           root_cause_id="ipv6-leak", fingerprint="bb",
                           action_id="disable-ipv6", verify_result="accepted")
        recent = store.find_recent(scenario_id="dns-cache-stale", limit=10)
        assert len(recent) == 1
        assert recent[0]["scenario_id"] == "dns-cache-stale"

    def test_decay_older_than_removes_old(self, tmp_path):
        store = _make_memory(tmp_path)
        store.append_entry(date="2020-01-01T00:00:00+00:00", scenario_id="old",
                           root_cause_id="old", fingerprint="aa",
                           action_id="x", verify_result="accepted")
        store.append_entry(date="2030-01-01T00:00:00+00:00", scenario_id="new",
                           root_cause_id="new", fingerprint="bb",
                           action_id="y", verify_result="accepted")
        removed = store.decay_older_than(days=30)
        assert removed == 1
        recent = store.find_recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["scenario_id"] == "new"
        md = store.read_markdown()
        assert "new" in md
        assert "`old`" not in md

    def test_decay_zero_days_removes_all(self, tmp_path):
        store = _make_memory(tmp_path)
        store.append_entry(date="2020-01-01T00:00:00+00:00", scenario_id="old",
                           root_cause_id="old", fingerprint="aa",
                           action_id="x", verify_result="accepted")
        assert store.decay_older_than(days=0) == 1
        assert store.find_recent() == []

    def test_clear_all_removes_files(self, tmp_path):
        store = _make_memory(tmp_path)
        store.append_entry(date="2026-07-18 14:23", scenario_id="dns",
                           root_cause_id="dns", fingerprint="aa",
                           action_id="x", verify_result="accepted")
        assert store.markdown_path.exists()
        assert store.jsonl_path.exists()
        removed = store.clear_all()
        assert removed == 2
        assert not store.markdown_path.exists()
        assert not store.jsonl_path.exists()
        assert store.find_recent() == []

    def test_memory_redacts_secrets(self, tmp_path):
        store = _make_memory(tmp_path)
        store.append_entry(
            date="2026-07-18 14:23",
            scenario_id="ip-test",
            root_cause_id="ip-reputation-risk",
            fingerprint="deadbeef",
            action_id="switch-node",
            verify_result="accepted",
            symptom="联系 alice@example.com 报告 203.0.113.10",
            target="openai.com",
        )
        md = store.read_markdown()
        assert "alice@example.com" not in md
        assert "203.0.113.10" not in md
        assert "[redacted_email]" in md


# ---------------------------------------------------------------------------
# HTTP smoke tests — patching the process-wide singletons in netfix.api
# ---------------------------------------------------------------------------


class _ApiTestBase(unittest.TestCase):
    """Shared HTTP server boot for the chat-session and memory smoke tests."""

    @classmethod
    def setUpClass(cls):
        cls.server: HTTPServer = api.create_server(host="127.0.0.1", port=_free_port(), timeout=5)
        cls.server.timeout = 1
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self._session_store = AgentSessionStore(base_dir=self._tmp)
        self._memory_store = MemoryStore(base_dir=self._tmp)
        # Patch the process-wide singletons so /chat/sessions/* and /memory
        # actually hit our isolated tmp dirs.
        self._patches = [
            patch.object(api, "_SESSION_STORE", self._session_store),
            patch.object(api, "_MEMORY_STORE", self._memory_store),
        ]
        for p in self._patches:
            p.start()
        api._SESSION_STORE = self._session_store
        api._MEMORY_STORE = self._memory_store

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _req(self, method: str, path: str, body: Any = None, expect_error: int = None):
        headers = {"X-Netfix-Token": api._API_TOKEN}
        data: Any = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(f"{self.base}{path}", data=data, headers=headers, method=method)
        if expect_error:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, expect_error)
            return json.loads(ctx.exception.read().decode("utf-8"))
        with urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.headers.get("Content-Type"), "application/json")
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str):
        return self._req("GET", path)

    def _post(self, path: str, body: Any = None):
        return self._req("POST", path, body=body)

    def _delete(self, path: str):
        return self._req("DELETE", path)


class TestChatSessionsHttp(_ApiTestBase):
    def test_create_session(self):
        data = self._post("/chat/sessions", {
            "scenario_id": "dns-cache-stale",
            "root_cause_id": "dns-cache-stale",
            "fingerprint": "deadbeefcafe1234",
            "symptom_text": "DNS_PROBE on chat.openai.com",
        })
        self.assertTrue(data["ok"])
        self.assertIn("session_id", data)
        sid = data["session_id"]

    def test_create_session_duplicate_id_conflicts(self):
        sid = self._session_store.create(scenario_id="x", session_id="chat-fixed-id")
        data = self._req("POST", "/chat/sessions", body={"session_id": sid, "scenario_id": "x"}, expect_error=409)
        self.assertFalse(data["ok"])
        self.assertEqual(data.get("reason_code"), "session_id_conflict")

    def test_list_and_get_session(self):
        sid = self._session_store.create(scenario_id="dns", root_cause_id="dns")
        listed = self._get("/chat/sessions")
        self.assertTrue(listed["ok"])
        ids = [row["session_id"] for row in listed["sessions"]]
        self.assertIn(sid, ids)

        single = self._get(f"/chat/sessions/{sid}")
        self.assertTrue(single["ok"])
        self.assertEqual(single["session"]["scenario_id"], "dns")

    def test_get_unknown_session_404(self):
        self._req("GET", "/chat/sessions/does-not-exist", expect_error=404)

    def test_append_turn_via_http(self):
        sid = self._session_store.create(scenario_id="dns", fingerprint="fp-1")
        data = self._post(f"/chat/sessions/{sid}/turns", {
            "role": "user",
            "question": "why?",
            "plan": [{"tool": "netfix_dns_resolve"}],
        })
        self.assertTrue(data["ok"])
        self.assertEqual(data["turn"]["role"], "user")
        loaded = self._session_store.get(sid)
        self.assertEqual(len(loaded["turns"]), 1)

    def test_decisions_endpoint(self):
        sid = self._session_store.create(scenario_id="dns")
        data = self._post(f"/chat/sessions/{sid}/decisions", {
            "category": "manual_ack",
            "outcome": "accepted",
            "action_id": "flush-dns-cache",
        })
        self.assertTrue(data["ok"])
        self.assertEqual(data["decision"]["action_id"], "flush-dns-cache")

    def test_confirm_endpoint_transitions_status(self):
        sid = self._session_store.create(scenario_id="dns")
        data = self._post(f"/chat/sessions/{sid}/confirm", {
            "outcome": "accepted",
            "category": "manual_ack",
            "action_id": "flush-dns-cache",
        })
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "completed")

    def test_concepts_endpoint(self):
        sid = self._session_store.create(scenario_id="dns")
        data = self._post(f"/chat/sessions/{sid}/concepts/dns-basics", {})
        self.assertTrue(data["ok"])
        self.assertEqual(data["explained_concepts"], ["dns-basics"])

    def test_delete_session(self):
        sid = self._session_store.create(scenario_id="dns")
        path = self._session_store.sessions_dir / f"{sid}.json"
        self.assertTrue(path.exists())
        data = self._delete(f"/chat/sessions/{sid}")
        self.assertTrue(data["ok"])
        self.assertFalse(path.exists())

    def test_delete_unknown_session_404(self):
        self._req("DELETE", "/chat/sessions/missing", expect_error=404)


class TestMemoryHttp(_ApiTestBase):
    def test_memory_recent_empty(self):
        data = self._get("/memory/recent")
        self.assertTrue(data["ok"])
        self.assertEqual(data["entries"], [])

    def test_memory_recent_with_entries(self):
        self._post("/memory/append", {
            "scenario_id": "dns-cache-stale",
            "root_cause_id": "dns-cache-stale",
            "fingerprint": "deadbeef",
            "action_id": "flush-dns-cache",
            "verify_result": "accepted",
            "symptom": "DNS_PROBE on chat.openai.com",
            "target": "chat.openai.com",
        })
        data = self._get("/memory/recent?scenario_id=dns-cache-stale&limit=5")
        self.assertTrue(data["ok"])
        self.assertEqual(data["scenario_id"], "dns-cache-stale")
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["scenario_id"], "dns-cache-stale")

    def test_memory_append_returns_entry(self):
        data = self._post("/memory/append", {
            "scenario_id": "ipv6-leak",
            "root_cause_id": "ipv6-leak",
            "fingerprint": "abcd",
            "action_id": "disable-ipv6",
            "verify_result": "accepted",
        })
        self.assertTrue(data["ok"])
        self.assertEqual(data["entry"]["scenario_id"], "ipv6-leak")

    def test_memory_decay_endpoint(self):
        self._post("/memory/append", {
            "scenario_id": "old",
            "root_cause_id": "old",
            "fingerprint": "a",
            "action_id": "x",
            "verify_result": "accepted",
        })
        data = self._post("/memory/decay?days=0", {})
        self.assertTrue(data["ok"])
        self.assertEqual(data["removed"], 1)
        self.assertEqual(data["days"], 0)
        self.assertEqual(self._get("/memory/recent")["entries"], [])

    def test_memory_delete(self):
        self._post("/memory/append", {
            "scenario_id": "x",
            "root_cause_id": "y",
            "fingerprint": "ab",
            "action_id": "z",
            "verify_result": "accepted",
        })
        data = self._delete("/memory")
        self.assertTrue(data["ok"])
        self.assertEqual(data["removed"], 2)


class TestExplainLlmSessionIntegration(_ApiTestBase):
    """Ensure ``/explain_llm`` accepts ``session_id`` and persists two turns."""

    def test_explain_llm_with_session_id_appends_two_turns(self):
        sid = self._session_store.create(scenario_id="dns", fingerprint="fp-x")
        with patch("netfix.api.llm_explain.explain_with_llm", return_value={
            "schema_version": "llm_explanation.v1",
            "headline": "test headline",
            "severity": "ok",
            "explanation": "test explanation",
            "actions": [],
            "manual_steps": [],
        }) as explain_mock, \
            patch("netfix.api._load_current_mac_report", return_value=(200, {"diagnostics": []})):
            data = self._post("/explain_llm", {
                "question": "why is chat.openai.com failing?",
                "session_id": sid,
            })
        self.assertTrue(data["ok"])
        self.assertEqual(data["session_persisted"]["session_id"], sid)
        self.assertEqual(data["session_persisted"]["turns_appended"], 2)
        explain_mock.assert_called_once()
        session = self._session_store.get(sid)
        self.assertEqual(len(session["turns"]), 2)
        self.assertEqual(session["turns"][0]["role"], "user")
        self.assertEqual(session["turns"][1]["role"], "assistant")

    def test_explain_llm_without_session_id_is_unchanged(self):
        with patch("netfix.api.llm_explain.explain_with_llm", return_value={
            "schema_version": "llm_explanation.v1",
            "headline": "h",
            "severity": "ok",
            "explanation": "e",
            "actions": [],
            "manual_steps": [],
        }), patch("netfix.api._load_current_mac_report", return_value=(200, {"diagnostics": []})):
            data = self._post("/explain_llm", {"question": "hi"})
        self.assertTrue(data["ok"])
        self.assertNotIn("session_persisted", data)
        self.assertNotIn("session_error", data)

    def test_explain_llm_with_unknown_session_id_returns_error(self):
        with patch("netfix.api.llm_explain.explain_with_llm", return_value={
            "schema_version": "llm_explanation.v1",
            "headline": "h",
            "severity": "ok",
            "explanation": "e",
            "actions": [],
            "manual_steps": [],
        }), patch("netfix.api._load_current_mac_report", return_value=(200, {"diagnostics": []})):
            data = self._post("/explain_llm", {"question": "hi", "session_id": "missing-session-id"})
        self.assertTrue(data["ok"])
        self.assertIn("session_error", data)
        self.assertIn("not found", data["session_error"])
