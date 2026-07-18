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
        self.assertEqual(card["headline"], "没有检测到公网 IPv6")
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


class TestNewCauseExplanations(unittest.TestCase):
    """P0-A.6：补全 4 场景缺失的 cause 模板，避免 fallback 到技术 description。"""

    def test_proxy_auth_failure_wrong_password_template(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "proxy_core_status", "status": "fail"}],
            "root_causes": [{"id": "wrong-password", "description": "代理凭据错误"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        # 必须有明确 headline，不能直接回退到 description
        self.assertNotEqual(card["headline"], "代理凭据错误")
        self.assertIn("用户名", card["explanation"] + card["headline"])
        self.assertTrue(len(card["manual_steps"]) >= 1)

    def test_ssl_self_signed_certificate_template(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "codex_api_direct", "status": "fail"}],
            "root_causes": [{"id": "self-signed-cert", "description": "自签证书"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "自签证书")
        self.assertIn("证书", card["explanation"] + card["headline"])
        # 不允许建议关闭校验
        self.assertNotIn("-k", card["explanation"])

    def test_mtu_too_high_template(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "mtu_probe", "status": "fail"}],
            "root_causes": [{"id": "mtu-too-high", "description": "MTU 太高"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "MTU 太高")
        self.assertIn("数据包", card["explanation"] + card["headline"])

    def test_dns_hijack_template(self):
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "dns_local", "status": "fail"}],
            "root_causes": [{"id": "dns-hijack", "description": "DNS 解析被劫持"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "DNS 解析被劫持")
        # 必须以"疑似"措辞，避免直接断言攻击
        self.assertTrue("疑似" in card["explanation"] or "疑似" in card["headline"])

    def test_cli_no_proxy_template(self):
        """P0-B.8: 浏览器能开，Codex CLI 连不上"""
        report: Dict[str, Any] = {
            "diagnostics": [
                {"name": "codex_api_via_proxy", "status": "fail"},
                {"name": "proxy_core_status", "status": "ok"},
            ],
            "root_causes": [{"id": "cli-no-env-proxy", "description": "CLI 没读到代理环境变量"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        # headline 必须明确归因，不能回退到技术描述
        self.assertNotEqual(card["headline"], "CLI 没读到代理环境变量")
        self.assertNotIn("AI", card["explanation"] + card["headline"])
        self.assertNotIn("综上所述", card["explanation"] + card["headline"])
        # 必须给出可操作的 manual_step（例如 export 变量）
        self.assertTrue(len(card["manual_steps"]) >= 1)
        manual_text = " ".join(
            m["description"] if isinstance(m, dict) and "description" in m else str(m)
            for m in card["manual_steps"]
        )
        self.assertTrue(
            "ALL_PROXY" in manual_text or "export" in manual_text or "终端" in manual_text,
            f"manual_steps should mention export / terminal guidance, got: {manual_text!r}",
        )

    def test_network_switch_template(self):
        """P0-B.8: 从公司回家后代理全乱"""
        report: Dict[str, Any] = {
            "diagnostics": [
                {"name": "system_proxy_state", "status": "fail"},
                {"name": "gateway", "status": "warn"},
            ],
            "root_causes": [{"id": "network-baseline-drift", "description": "网络基线漂移"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "网络基线漂移")
        self.assertNotIn("综上所述", card["explanation"] + card["headline"])
        self.assertNotIn("AI", card["explanation"] + card["headline"])
        self.assertTrue(len(card["manual_steps"]) >= 1)
        manual_text = " ".join(
            m["description"] if isinstance(m, dict) and "description" in m else str(m)
            for m in card["manual_steps"]
        )
        # 必须提到手动重启核心/重置代理之类的具体动作
        self.assertTrue(
            "代理" in manual_text or "重启" in manual_text or "Wi-Fi" in manual_text or "IPv6" in manual_text,
            f"manual_steps should reference 重启代理/重置网络, got: {manual_text!r}",
        )

    def test_auth_scheme_unsupported_template(self):
        """P1.3: 代理认证方式客户端不支持（NTLM/SAML）"""
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "proxy_auth_check", "status": "fail"}],
            "root_causes": [{"id": "auth-scheme-unsupported", "description": "认证方式不支持"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "认证方式不支持")
        self.assertNotIn("AI", card["explanation"] + card["headline"])
        self.assertNotIn("综上所述", card["explanation"] + card["headline"])
        self.assertTrue(len(card["manual_steps"]) >= 1)
        manual_text = " ".join(
            m["description"] if isinstance(m, dict) and "description" in m else str(m)
            for m in card["manual_steps"]
        )
        self.assertTrue(
            "NTLM" in manual_text or "SAML" in manual_text or "Basic" in manual_text or "服务商" in manual_text,
            f"manual_steps should reference NTLM/SAML/Basic guidance, got: {manual_text!r}",
        )

    def test_cert_expired_not_mitm(self):
        """P1.3: 证书过期但不是中间人"""
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "ssl_cert_check", "status": "fail"}],
            "root_causes": [{"id": "cert-expired-not-mitm", "description": "证书过期"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "证书过期")
        self.assertNotIn("AI", card["explanation"] + card["headline"])
        self.assertNotIn("综上所述", card["explanation"] + card["headline"])
        # 模板文案里不应把这种情况误判为劫持
        self.assertNotIn("劫持", card["explanation"])
        self.assertNotIn("中间人", card["headline"])
        self.assertTrue(len(card["manual_steps"]) >= 1)

    def test_wifi_band_crowded_template(self):
        """P1.3: Wi-Fi 频段拥挤细分模板"""
        report: Dict[str, Any] = {
            "diagnostics": [{"name": "wifi_signal", "status": "warn"}],
            "root_causes": [{"id": "wifi-band-crowded", "description": "Wi-Fi 频段拥挤"}],
            "fixes": [],
            "manual_steps": [],
        }
        card = explain.explain_report(report, rules=_sample_rules())
        self.assertNotEqual(card["headline"], "Wi-Fi 频段拥挤")
        self.assertNotIn("AI", card["explanation"] + card["headline"])
        self.assertNotIn("综上所述", card["explanation"] + card["headline"])
        self.assertTrue(len(card["manual_steps"]) >= 1)
        manual_text = " ".join(
            m["description"] if isinstance(m, dict) and "description" in m else str(m)
            for m in card["manual_steps"]
        )
        self.assertTrue(
            "信道" in manual_text or "5GHz" in manual_text or "路由器" in manual_text,
            f"manual_steps should reference channel / 5GHz / 路由器, got: {manual_text!r}",
        )


if __name__ == "__main__":
    unittest.main()
