import unittest
import tempfile
import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

from netfix.cli import _build_report
from netfix.i18n import fmt, t
from netfix.report import Report


class TestI18n(unittest.TestCase):
    def test_get_existing_key(self):
        self.assertEqual(t("status.ok"), "正常")

    def test_get_missing_key_returns_key(self):
        self.assertEqual(t("missing.key.abc"), "missing.key.abc")

    def test_fmt_with_kwargs(self):
        # The key has no placeholder, so fmt falls back to the literal value.
        self.assertEqual(fmt("fix.tier", tier=13), "处理方式")


class TestReportSummary(unittest.TestCase):
    def test_build_report_adds_user_facing_diagnostic_display_names(self):
        data = _build_report(
            {},
            [{"name": "proxy_core_status", "status": "ok", "layer": "proxy"}],
            [],
        )

        self.assertEqual(data["diagnostics"][0]["name"], "proxy_core_status")
        self.assertEqual(data["diagnostics"][0]["display_name"], "代理软件状态")

    def test_healthy_summary(self):
        data = {
            "meta": {"version": "0.2.0", "timestamp": "now"},
            "environment": {},
            "diagnostics": [{"name": "gateway", "status": "ok"}],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        report = Report(data)
        summary = report.summary()
        self.assertIn("正常", summary["headline"])

    def test_to_human_includes_headline(self):
        data = {
            "meta": {"version": "0.2.0", "timestamp": "now"},
            "environment": {},
            "diagnostics": [{"name": "gateway", "status": "ok"}],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        text = Report(data).to_human()
        self.assertIn("结论", text)
        self.assertIn("【结论】", text)

    def test_save_respects_latest_report_privacy_toggle(self):
        data = {
            "meta": {"version": "0.2.0", "timestamp": "2026-06-24T00:00:00+00:00"},
            "environment": {},
            "diagnostics": [{"name": "gateway", "status": "ok"}],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "last_report.json"
            current_mac_report = root / "current_mac_report.json"
            current_mac_report.write_text("{}", encoding="utf-8")
            with patch("netfix.report.JOURNAL_DIR", root), \
                    patch("netfix.settings.get_privacy_settings", return_value={"save_latest_report": False}), \
                    patch("netfix.logs.EVENTS_FILE", root / "events.jsonl"), \
                    patch("netfix.logs.JOURNAL_DIR", root), \
                    patch("netfix.logs.LATEST_REPORT", report_path):
                saved = Report(data).save()
            self.assertEqual(saved, report_path)
            self.assertFalse(report_path.exists())
            self.assertFalse(current_mac_report.exists())
            self.assertTrue((root / "events.jsonl").exists())

    def test_full_current_mac_report_survives_later_subset_report(self):
        full = {
            "meta": {
                "version": "0.2.0",
                "timestamp": "2026-07-15T09:00:00+00:00",
                "origin": "doctor",
                "coverage": "current_mac_full",
                "route_signature": "route:v1:test",
            },
            "environment": {},
            "diagnostics": [{"name": "network_quality", "status": "ok", "details": {"base_rtt_ms": 42}}],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        subset = {
            "meta": {
                "version": "0.2.0",
                "timestamp": "2026-07-15T09:05:00+00:00",
                "origin": "codex",
                "coverage": "target_subset",
                "route_signature": "route:v1:test",
            },
            "environment": {},
            "diagnostics": [{"name": "openai_api", "status": "warn"}],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.jsonl"
            with patch("netfix.report.JOURNAL_DIR", root), \
                    patch("netfix.logs.EVENTS_FILE", events), \
                    patch("netfix.settings.get_privacy_settings", return_value={"save_latest_report": True}):
                Report(full).save()
                Report(subset).save()

            latest = json.loads((root / "last_report.json").read_text(encoding="utf-8"))
            current = json.loads((root / "current_mac_report.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["meta"]["origin"], "codex")
            self.assertEqual(current["meta"]["origin"], "doctor")
            self.assertEqual(current["diagnostics"][0]["name"], "network_quality")

    def test_save_redacts_proxy_credentials_and_uses_private_permissions(self):
        data = {
            "meta": {"version": "0.2.0", "timestamp": "2026-06-24T00:00:00+00:00"},
            "environment": {},
            "diagnostics": [
                {
                    "name": "codex_proxy",
                    "status": "fail",
                    "proxy_used": "http://user:real-pass@proxy.example.com:8000",
                }
            ],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "last_report.json"
            events_path = root / "events.jsonl"
            with patch("netfix.logs.EVENTS_FILE", events_path), \
                    patch("netfix.logs.JOURNAL_DIR", root), \
                    patch("netfix.logs.LATEST_REPORT", report_path):
                saved = Report(data).save(report_path)
            self.assertEqual(saved, report_path)
            text = report_path.read_text(encoding="utf-8")
            self.assertIn("user:***@", text)
            self.assertNotIn("real-pass", text)
            loaded = json.loads(text)
            self.assertEqual(loaded["diagnostics"][0]["proxy_used"], "http://user:***@proxy.example.com:8000")
            self.assertEqual(stat.S_IMODE(os.stat(report_path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(root).st_mode), 0o700)


class TestReportHumanOutput(unittest.TestCase):
    def _proxy_down_report(self, with_explanation=True):
        data = {
            "meta": {"version": "0.2.0", "timestamp": "now"},
            "environment": {},
            "diagnostics": [
                {"name": "proxy_core_status", "status": "fail", "display_name": "代理软件状态"}
            ],
            "root_causes": [
                {"id": "proxy-down", "description": "代理软件没有运行", "confidence": 0.9}
            ],
            "fixes": [
                {
                    "id": "check-proxy-core",
                    "tier": 1,
                    "description": "检测代理核心是否运行并监听 mixed 端口",
                    "command": "echo check",
                }
            ],
            "manual_steps": [],
        }
        if with_explanation:
            data["explanation"] = {
                "headline": "代理客户端没有启动",
                "explanation": "你的代理软件没开，流量没法通过代理出去。",
                "primary_action": {"id": "check-proxy-core", "label": "检查代理软件是否运行"},
                "actions": [],
                "manual_steps": [],
            }
        return data

    def test_summary_prefers_root_cause_over_env_guess(self):
        # gui_client 缺失且有 fail 时，旧逻辑会说“网络层就有问题”；
        # 有根因时必须优先用根因对应的人话结论。
        summary = Report(self._proxy_down_report()).summary()
        self.assertEqual(summary["headline"], "代理客户端没有启动")
        self.assertNotIn("Wi-Fi", summary["headline"])

    def test_summary_falls_back_to_root_cause_description(self):
        summary = Report(self._proxy_down_report(with_explanation=False)).summary()
        self.assertEqual(summary["headline"], "代理软件没有运行")

    def test_to_human_renders_explanation_card_on_top(self):
        text = Report(self._proxy_down_report()).to_human()
        self.assertIn("【结论】代理客户端没有启动", text)
        self.assertIn("【为什么】你的代理软件没开", text)
        self.assertIn("【下一步】检查代理软件是否运行：python3 netfix.py fix --issue check-proxy-core", text)

    def test_to_human_uses_display_name_for_diagnostics(self):
        text = Report(self._proxy_down_report()).to_human()
        self.assertIn("代理软件状态", text)
        self.assertNotIn("proxy_core_status", text)

    def test_to_human_falls_back_to_name_without_display_name(self):
        data = self._proxy_down_report()
        data["diagnostics"] = [{"name": "proxy_core_status", "status": "fail"}]
        text = Report(data).to_human()
        self.assertIn("proxy_core_status", text)

    def test_to_human_fix_section_has_copyable_cli_command(self):
        text = Report(self._proxy_down_report()).to_human()
        self.assertIn("python3 netfix.py fix --issue check-proxy-core", text)
        # 不再展示工程 id 冒号描述、也不再 dump 裸 shell 命令。
        self.assertNotIn("check-proxy-core: 检测代理核心", text)
        self.assertNotIn("echo check", text)

    def test_to_human_does_not_dump_raw_json(self):
        text = Report(self._proxy_down_report()).to_human()
        self.assertNotIn('"schema_version"', text)
        self.assertIn("python3 netfix.py report --json", text)


if __name__ == "__main__":
    unittest.main()
