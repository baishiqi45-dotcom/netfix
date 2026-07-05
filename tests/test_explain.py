"""Tests for netfix.explain."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict

from netfix import explain


def _sample_rules() -> Dict[str, Any]:
    return {
        "fixes": {
            "check-proxy-core": {
                "tier": 1,
                "description": "检查代理核心",
                "commands": ["echo ok"],
                "verify_diagnostic": "proxy_core_status",
            },
            "flush-dns-cache": {
                "tier": 1,
                "description": "刷新 DNS 缓存",
                "commands": ["echo flushed"],
                "verify_diagnostic": "dns_local",
            },
            "reset-system-proxy": {
                "tier": 2,
                "description": "重置系统代理",
                "commands": ["echo reset"],
            },
            "disable-auto-proxy": {
                "tier": 2,
                "description": "关闭自动代理",
                "commands": ["echo auto off"],
            },
            "disable-ipv6": {
                "tier": 2,
                "description": "关闭 IPv6",
                "commands": ["echo ipv6 off"],
            },
        }
    }


class TestExplainReport(unittest.TestCase):
    def test_healthy_report(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "wifi", "status": "ok"}],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertEqual(card["headline"], "网络看起来正常")
        self.assertEqual(card["severity"], "ok")
        self.assertEqual(card["primary_action"], None)
        self.assertEqual(card["actions"], [])
        self.assertNotIn("explanation", card["technical"])

    def test_proxy_down_primary_action(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "proxy_core_status", "status": "fail"}],
            "root_causes": [{"id": "proxy-down", "description": "代理客户端没有启动"}],
            "fixes": [{"id": "check-proxy-core"}],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertEqual(card["headline"], "代理客户端没有启动")
        self.assertEqual(card["severity"], "fail")
        self.assertEqual(card["primary_action"]["id"], "check-proxy-core")
        self.assertTrue(len(card["manual_steps"]) >= 1)

    def test_action_ordering_and_labels(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "proxy_http_test", "status": "fail"}],
            "root_causes": [{"id": "proxy-http-failed"}],
            "fixes": [
                {"id": "reset-system-proxy"},
                {"id": "check-proxy-core"},
            ],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        ids = [a["id"] for a in card["actions"]]
        # Primary action from template must come first.
        self.assertEqual(ids[0], "check-proxy-core")
        self.assertIn("reset-system-proxy", ids)
        # Confirm tier should be flagged.
        reset_action = next(a for a in card["actions"] if a["id"] == "reset-system-proxy")
        self.assertTrue(reset_action["needs_confirm"])

    def test_unknown_cause_falls_back(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "x", "status": "warn"}],
            "root_causes": [{"id": "weird-cause", "description": "神秘问题"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertEqual(card["headline"], "神秘问题")
        self.assertEqual(card["severity"], "warn")

    def test_mixed_proxy_pac_explanation(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "system_proxy_state", "status": "warn"}],
            "root_causes": [{"id": "mixed-proxy-pac"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertEqual(card["headline"], "系统里同时开了手动代理和自动代理")
        self.assertIn("手动代理", card["explanation"])
        self.assertIn("自动代理", card["explanation"])
        self.assertNotIn("PAC", card["explanation"])
        self.assertEqual(card["primary_action"]["id"], "disable-auto-proxy")
        self.assertTrue(card["primary_action"]["needs_confirm"])

    def test_ipv6_fallback_explanation_is_not_confirmed_leak(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "ipv6_leak", "status": "warn"}],
            "root_causes": [{"id": "ipv6-fallback-risk"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertEqual(card["headline"], "没有检测到 IPv6 泄漏")
        self.assertIn("没有检测到公网 IPv6", card["explanation"])
        self.assertEqual(card["primary_action"], None)
        self.assertEqual(card["actions"], [])
        self.assertNotIn("Tier", str(card))

    def test_no_circular_technical_snapshot(self):
        report: Dict[str, Any] = {
            "diagnostics": [],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        # Serializing the card (which embeds technical = report) must not
        # fail due to a circular reference.
        json.dumps(card, ensure_ascii=False, default=str)

    def test_manual_steps_deduplicated(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "dns", "status": "fail"}],
            "root_causes": [
                {
                    "id": "dns-cache-stale",
                    "description": "DNS 缓存污染",
                    "manual_steps": ["检查 DNS 设置"],
                }
            ],
            "fixes": [],
            "manual_steps": ["检查 DNS 设置", {"description": "检查 DNS 设置", "steps": ["a"]}],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        descriptions = [
            m if isinstance(m, str) else m["description"]
            for m in card["manual_steps"]
        ]
        self.assertEqual(len([d for d in descriptions if d == "检查 DNS 设置"]), 1)


if __name__ == "__main__":
    unittest.main()
