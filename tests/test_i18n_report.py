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
        self.assertEqual(fmt("fix.tier", tier=13), "等级")


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
            with patch("netfix.report.JOURNAL_DIR", root), \
                    patch("netfix.settings.get_privacy_settings", return_value={"save_latest_report": False}), \
                    patch("netfix.logs.EVENTS_FILE", root / "events.jsonl"), \
                    patch("netfix.logs.JOURNAL_DIR", root), \
                    patch("netfix.logs.LATEST_REPORT", report_path):
                saved = Report(data).save()
            self.assertEqual(saved, report_path)
            self.assertFalse(report_path.exists())
            self.assertTrue((root / "events.jsonl").exists())

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


if __name__ == "__main__":
    unittest.main()
