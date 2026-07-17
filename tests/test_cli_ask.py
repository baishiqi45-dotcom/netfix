import contextlib
import io
import json
import unittest
from unittest.mock import patch

from netfix import cli
from netfix.report import Report


_SAMPLE_REPORT = {
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

_SAMPLE_CARD = {
    "schema_version": "llm_explanation.v1",
    "source": "fallback",
    "headline": "代理客户端没有启动",
    "severity": "fail",
    "explanation": "你的代理软件没开，流量没法通过代理出去。",
    "actions": [
        {
            "id": "check-proxy-core",
            "label": "检查代理软件是否运行",
            "tier": 1,
            "needs_confirm": False,
        }
    ],
    "manual_steps": [{"id": "", "description": "打开你的代理软件", "steps": []}],
}


class TestUnknownCommandIntercept(unittest.TestCase):
    def test_natural_language_first_arg_gets_human_guidance(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(["我网速很慢"])
        self.assertEqual(rc, 2)
        text = err.getvalue()
        self.assertIn("看不懂这个命令", text)
        self.assertIn('python3 netfix.py ask "你的网络问题"', text)
        self.assertIn("python3 netfix.py doctor", text)
        self.assertNotIn("invalid choice", text)

    def test_known_command_passes_intercept_to_argparse(self):
        # kb 缺少必填的 --query，应该走 argparse 自己的错误，而不是人话引导。
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cli.main(["kb"])
        self.assertNotIn("看不懂这个命令", err.getvalue())


class TestAskCommand(unittest.TestCase):
    def test_ask_uses_latest_report_and_renders_card(self):
        with patch("netfix.cli.Report.load", return_value=Report(_SAMPLE_REPORT)), \
                patch(
                    "netfix.cli.llm_explain.explain_with_llm",
                    return_value=dict(_SAMPLE_CARD),
                ) as mocked:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["ask", "我网速很慢"])
        self.assertEqual(rc, 0)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.kwargs.get("question"), "我网速很慢")
        text = out.getvalue()
        self.assertIn("【结论】代理客户端没有启动", text)
        self.assertIn("【为什么】", text)
        self.assertIn("【建议操作】", text)
        self.assertIn("python3 netfix.py fix --issue check-proxy-core", text)
        self.assertIn("打开你的代理软件", text)

    def test_ask_without_report_runs_triage_first(self):
        with patch("netfix.cli.Report.load", side_effect=FileNotFoundError), \
                patch(
                    "netfix.cli._triage_report",
                    return_value=Report(_SAMPLE_REPORT),
                ) as triage, \
                patch(
                    "netfix.cli.llm_explain.explain_with_llm",
                    return_value=dict(_SAMPLE_CARD),
                ):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["ask", "我网速很慢"])
        self.assertEqual(rc, 0)
        triage.assert_called_once()

    def test_ask_json_outputs_raw_card(self):
        with patch("netfix.cli.Report.load", return_value=Report(_SAMPLE_REPORT)), \
                patch(
                    "netfix.cli.llm_explain.explain_with_llm",
                    return_value=dict(_SAMPLE_CARD),
                ):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["ask", "我网速很慢", "--json"])
        self.assertEqual(rc, 0)
        card = json.loads(out.getvalue())
        self.assertEqual(card["schema_version"], "llm_explanation.v1")
        self.assertEqual(card["headline"], "代理客户端没有启动")


class TestExplainCommandHumanOutput(unittest.TestCase):
    def test_explain_renders_plain_language_sections(self):
        card = {
            "headline": "代理客户端没有启动",
            "explanation": "你的代理软件没开。",
            "primary_action": {"id": "check-proxy-core", "label": "检查代理软件是否运行"},
            "actions": [{"id": "check-proxy-core", "label": "检查代理软件是否运行", "tier": 1}],
            "manual_steps": [],
        }
        with patch("netfix.cli.Report.load", return_value=Report(_SAMPLE_REPORT)), \
                patch("netfix.cli.explain.explain_report", return_value=card):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cli.main(["explain"])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("【结论】代理客户端没有启动", text)
        self.assertIn("【为什么】你的代理软件没开。", text)
        self.assertIn("【建议操作】", text)
        self.assertIn("python3 netfix.py fix --issue check-proxy-core", text)


class TestCliEpilog(unittest.TestCase):
    def test_epilog_lists_real_commands(self):
        epilog = cli.build_parser().epilog
        self.assertIn('ask "我网速很慢"', epilog)
        self.assertIn("python3 netfix.py doctor", epilog)
        self.assertIn("python3 netfix.py explain", epilog)
        self.assertNotIn("AI 解释子命令", epilog)


if __name__ == "__main__":
    unittest.main()
