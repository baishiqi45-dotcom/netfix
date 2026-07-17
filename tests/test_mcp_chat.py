import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from netfix import mcp_server


class TestMCPChatTools(unittest.TestCase):
    def _send_requests(self, requests):
        proc = subprocess.Popen(
            [sys.executable, "-m", "netfix.mcp_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        lines = [json.dumps(req, ensure_ascii=False) for req in requests]
        stdout, stderr = proc.communicate(input="\n".join(lines) + "\n", timeout=30)
        self.assertEqual(proc.returncode, 0, f"stderr: {stderr}")
        return [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]

    def test_tools_list_includes_chat_and_symptom_intake(self):
        responses = self._send_requests(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
        )

        tools = responses[1]["result"]["tools"]
        by_name = {t["name"]: t for t in tools}
        for name in ("netfix_chat", "netfix_symptom_intake"):
            self.assertIn(name, by_name)
            annotations = by_name[name].get("annotations", {})
            self.assertEqual(annotations.get("readOnlyHint"), True, name)
            self.assertNotIn("destructiveHint", annotations, name)

        chat_tool = by_name["netfix_chat"]
        chat_props = chat_tool["inputSchema"]["properties"]
        self.assertEqual(chat_tool["inputSchema"]["required"], ["question"])
        self.assertIn("question", chat_props)
        self.assertIn("history", chat_props)
        self.assertEqual(chat_props["history"]["type"], "array")
        self.assertEqual(chat_props["history"]["maxItems"], 20)

        intake_tool = by_name["netfix_symptom_intake"]
        self.assertEqual(intake_tool["inputSchema"]["required"], ["text"])
        self.assertIn("text", intake_tool["inputSchema"]["properties"])

    def test_chat_passes_question_and_history_to_llm_explain(self):
        history = [
            {"role": "user", "content": "微信发不出去"},
            {"role": "assistant", "content": "先看系统代理是否生效"},
        ]
        with patch("netfix.mcp_server.Report.load", side_effect=FileNotFoundError("no report")), \
                patch(
                    "netfix.mcp_server.llm_explain.explain_with_llm",
                    return_value={"schema_version": "llm_explanation.v1", "source": "fallback"},
                ) as mock_explain:
            result = mcp_server._call_tool(
                "netfix_chat",
                {"question": "但网页能开，为什么？", "history": history},
            )

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_mcp.v1")
        self.assertIn("note", data)
        self.assertIn("history", data["note"])
        self.assertIn("20", data["note"])
        self.assertEqual(data["result"]["schema_version"], "llm_explanation.v1")
        self.assertEqual(mock_explain.call_args.kwargs["question"], "但网页能开，为什么？")
        self.assertEqual(mock_explain.call_args.kwargs["history"], history)
        self.assertIsNone(mock_explain.call_args.kwargs["report"])

    def test_chat_uses_latest_report_when_available(self):
        report = type("Report", (), {"as_dict": lambda self: {"diagnostics": [], "fixes": []}})()
        with patch("netfix.mcp_server.Report.load", return_value=report), \
                patch(
                    "netfix.mcp_server.llm_explain.explain_with_llm",
                    return_value={"schema_version": "llm_explanation.v1", "source": "fallback"},
                ) as mock_explain:
            result = mcp_server._call_tool("netfix_chat", {"question": "报告里哪层挂了？"})

        self.assertFalse(result.get("isError"))
        kwargs = mock_explain.call_args.kwargs
        self.assertEqual(kwargs["report"], {"diagnostics": [], "fixes": []})
        self.assertEqual(kwargs["history"], [])

    def test_chat_requires_question(self):
        result = mcp_server._call_tool("netfix_chat", {})

        data = json.loads(result["content"][0]["text"])
        self.assertFalse(data["ok"])
        self.assertIn("question", data["error"])

    def test_symptom_intake_matches_chinese_app_blocked_description(self):
        result = mcp_server._call_tool(
            "netfix_symptom_intake",
            {"text": "微信发不出去但网页能开"},
        )

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data["ok"])
        ids = [item["id"] for item in data["matched_symptoms"]]
        self.assertIn("system-proxy-not-effective", ids)
        for item in data["matched_symptoms"]:
            self.assertIn("name", item)
            self.assertGreater(item["score"], 0)
            self.assertGreater(item["confidence"], 0)
            self.assertLessEqual(item["confidence"], 1)
        self.assertTrue(data["suggested_tools"])
        for item in data["suggested_tools"]:
            self.assertTrue(item["tool"].startswith("netfix_"))
            self.assertIn("arguments", item)
            self.assertIn("why", item)

    def test_symptom_intake_matches_slow_network_description(self):
        result = mcp_server._call_tool(
            "netfix_symptom_intake",
            {"text": "网速很慢，视频一直转圈"},
        )

        data = json.loads(result["content"][0]["text"])
        ids = [item["id"] for item in data["matched_symptoms"]]
        self.assertTrue(ids)
        self.assertTrue(
            any(i in {"local-wifi-issue", "wifi-gateway-down", "mtu-mismatch"} for i in ids),
            f"unexpected matches: {ids}",
        )

    def test_symptom_intake_falls_back_to_triage_note_when_no_match(self):
        result = mcp_server._call_tool(
            "netfix_symptom_intake",
            {"text": "今天天气不错"},
        )

        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["matched_symptoms"], [])
        self.assertEqual(data["suggested_checks"], [])
        self.assertEqual(data["suggested_tools"], [])
        self.assertIn("netfix_triage", data["note"])


if __name__ == "__main__":
    unittest.main()
