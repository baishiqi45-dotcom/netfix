"""Tests for netfix.agent_memory."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from netfix import agent_memory


class _TempHome(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._old_home = os.environ.get("HOME", "")
        os.environ["HOME"] = self._tmpdir
        agent_memory._memory_dir().__class__  # touch

    def tearDown(self):
        os.environ["HOME"] = self._old_home


class TestAppendEntry(unittest.TestCase):
    def test_append_creates_section(self):
        result = agent_memory.append_entry({
            "scenario_id": "dns-abnormal",
            "root_cause": "dns-cache-stale",
            "fix_executed": "flush-dns-cache",
            "outcome": "verified",
            "summary": "DNS 刷新后恢复",
        })
        self.assertTrue(result["ok"])
        text = agent_memory._atomic_read_text(agent_memory._memory_file())
        self.assertIn("## entries", text)
        self.assertIn("dns-abnormal", text)
        self.assertIn("flush-dns-cache", text)

    def test_append_redacts_secrets(self):
        result = agent_memory.append_entry({
            "scenario_id": "ip-test",
            "root_cause": "ip-reputation-risk",
            "fix_executed": "switch-node",
            "outcome": "verified",
            "summary": "联系 alice@example.com 报告 203.0.113.10",
        })
        text = agent_memory._atomic_read_text(agent_memory._memory_file())
        self.assertNotIn("alice@example.com", text)
        self.assertNotIn("203.0.113.10", text)
        self.assertIn("[redacted_email]", text)


class TestLookupSimilar(unittest.TestCase):
    def test_lookup_finds_matching_entry(self):
        agent_memory.append_entry({
            "scenario_id": "dns-abnormal",
            "root_cause": "dns-cache-stale",
            "fix_executed": "flush-dns-cache",
            "outcome": "verified",
            "summary": "刷新后恢复",
        })
        results = agent_memory.lookup_similar("dns")
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("dns-cache-stale", results[0].format_markdown())


class TestRetention(unittest.TestCase):
    def test_apply_retention_keeps_recent(self):
        agent_memory.append_entry({
            "scenario_id": "fresh",
            "root_cause": "dns-cache-stale",
            "fix_executed": "flush-dns-cache",
            "outcome": "verified",
            "summary": "new",
        })
        result = agent_memory.apply_retention(days=30)
        self.assertTrue(result["ok"])
        self.assertEqual(result["removed"], 0)


if __name__ == "__main__":
    unittest.main()
