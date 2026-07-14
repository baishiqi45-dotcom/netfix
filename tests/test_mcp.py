import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from netfix import mcp_server

ROOT = Path(__file__).resolve().parents[1]


class TestMCPServer(unittest.TestCase):
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

    def test_initialize_and_tools_list(self):
        init_id = 1
        list_id = 2
        responses = self._send_requests(
            [
                {
                    "jsonrpc": "2.0",
                    "id": init_id,
                    "method": "initialize",
                    "params": {},
                },
                {
                    "jsonrpc": "2.0",
                    "id": list_id,
                    "method": "tools/list",
                    "params": {},
                },
            ]
        )
        self.assertEqual(len(responses), 2)

        init_resp = responses[0]
        self.assertEqual(init_resp["id"], init_id)
        self.assertIn("result", init_resp)
        self.assertEqual(init_resp["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "netfix")
        self.assertIn("capabilities", init_resp["result"])

        list_resp = responses[1]
        self.assertEqual(list_resp["id"], list_id)
        self.assertIn("result", list_resp)
        tools = list_resp["result"]["tools"]
        names = {t["name"] for t in tools}
        for name in (
            "netfix_codex",
            "netfix_services",
            "netfix_triage",
            "netfix_doctor",
            "netfix_report",
            "netfix_kb_query",
            "netfix_fix_issue",
            "netfix_list_fixes",
            "netfix_dry_run_fix",
            "netfix_apply_fix",
            "netfix_sanitized_report",
            "netfix_evidence_chain",
            "netfix_rollback",
            "netfix_proxy_switch",
            "netfix_llm_providers",
            "netfix_explain_llm",
            "netfix_proxy_parse",
            "netfix_proxy_import_preview",
        ):
            self.assertIn(name, names)

        import_tool = next(t for t in tools if t["name"] == "netfix_proxy_import_preview")
        self.assertEqual(import_tool.get("annotations", {}).get("readOnlyHint"), True)
        self.assertNotIn("destructiveHint", import_tool.get("annotations", {}))
        self.assertIn("input", import_tool["inputSchema"]["properties"])
        self.assertIn("limit", import_tool["inputSchema"]["properties"])

        # Mutating tools must be visible as mutating/destructive to MCP hosts.
        for name in (
            "netfix_fix_issue",
            "netfix_apply_fix",
            "netfix_rollback",
            "netfix_proxy_switch",
            "netfix_flush_dns",
            "netfix_renew_dhcp",
            "netfix_disable_ipv6",
        ):
            tool = next(t for t in tools if t["name"] == name)
            annotations = tool.get("annotations", {})
            self.assertEqual(annotations.get("readOnlyHint"), False, name)
            self.assertEqual(annotations.get("destructiveHint"), True, name)

        for name in ("netfix_list_fixes", "netfix_dry_run_fix", "netfix_apply_fix", "netfix_sanitized_report", "netfix_evidence_chain"):
            tool = next(t for t in tools if t["name"] == name)
            self.assertIn("outputSchema", tool)

        apply_tool = next(t for t in tools if t["name"] == "netfix_apply_fix")
        self.assertIn("confirmation", apply_tool["inputSchema"]["properties"])
        self.assertIn("magic_word", apply_tool["inputSchema"]["properties"])

    def test_mcp_script_bootstraps_repo_root_when_started_from_other_cwd(self):
        script = ROOT / "netfix" / "mcp_server.py"
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=tmp,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = proc.communicate(
                input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n",
                timeout=30,
            )

        self.assertEqual(proc.returncode, 0, f"stderr: {stderr}")
        response = json.loads(stdout.splitlines()[0])
        self.assertEqual(response["result"]["serverInfo"]["name"], "netfix")

    def test_mutating_agent_tools_route_through_fix_engine_cli(self):
        with patch("netfix.mcp_server.run_cli", return_value={"ok": True}) as mock_run, \
                patch("netfix.agent_tools.flush_dns") as mock_flush:
            result = mcp_server._call_tool("netfix_flush_dns", {"timeout": 7})

        self.assertFalse(result.get("isError"))
        mock_flush.assert_not_called()
        mock_run.assert_called_once_with(
            ["fix", "--issue", "flush-dns-cache", "--dry-run", "--json", "--timeout", "7"],
            timeout=7,
        )

    def test_mcp_proxy_parse_does_not_return_secret(self):
        result = mcp_server._call_tool(
            "netfix_proxy_parse",
            {"input": "http://user:pass@proxy.example.com:8000"},
        )
        self.assertFalse(result.get("isError"))
        text = result["content"][0]["text"]
        self.assertIn("user:***@", text)
        self.assertNotIn("pass@proxy", text)

    def test_mcp_proxy_import_preview_redacts_bulk_credentials(self):
        result = mcp_server._call_tool(
            "netfix_proxy_import_preview",
            {
                "input": "\n".join([
                    "host,port,user,password",
                    "alpha.example.com,8000,alice,alpha-secret-001",
                    "http://bob:bob-secret-002@beta.example.com:9000",
                    "bad-line",
                ]),
                "limit": 10,
            },
        )

        self.assertFalse(result.get("isError"))
        text = result["content"][0]["text"]
        data = json.loads(text)
        self.assertEqual(data["schema_version"], "netfix_proxy_import_preview.v1")
        self.assertEqual(data["summary"]["valid_count"], 2)
        self.assertEqual(data["summary"]["invalid_count"], 1)
        self.assertIn("alice:***@", text)
        self.assertIn("bob:***@", text)
        self.assertNotIn("alpha-secret-001", text)
        self.assertNotIn("bob-secret-002", text)
        self.assertNotIn("_secret", text)

    def test_mcp_fix_issue_tier2_requires_confirmation_phrase(self):
        with patch("netfix.mcp_server.run_cli") as mock_run:
            result = mcp_server._call_tool(
                "netfix_fix_issue",
                {"issue": "disable-ipv6", "yes": True},
            )

        self.assertTrue(result.get("isError"))
        mock_run.assert_not_called()
        data = json.loads(result["content"][0]["text"])
        self.assertFalse(data["ok"])
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["confirmation"], "APPLY_SYSTEM_FIX")

    def test_mcp_fix_issue_tier2_dry_run_allowed_without_phrase(self):
        with patch("netfix.api.detect_environment", return_value={"ok": True}), \
                patch("netfix.api.get_core", return_value=None), \
                patch("netfix.api.FixEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.execute.return_value = {"ok": True, "status": "dry-run", "preview": ["sudo bash bin/disable_ipv6.sh"]}
            result = mcp_server._call_tool(
                "netfix_fix_issue",
                {"issue": "disable-ipv6", "dry_run": True},
            )

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["status"], "dry-run")
        kwargs = engine.execute.call_args.kwargs
        self.assertTrue(kwargs["dry_run"])
        self.assertFalse(kwargs["confirmed"])

    def test_mcp_list_fixes_returns_schema_and_confirmation_policy(self):
        result = mcp_server._call_tool("netfix_list_fixes", {"tier_filter": 2})

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["schema_version"], "netfix_mcp.v1")
        self.assertTrue(data["fixes"])
        self.assertTrue(all(item["tier"] == 2 for item in data["fixes"]))
        self.assertTrue(any(item["requires_confirmation"] for item in data["fixes"]))

    def test_mcp_dry_run_fix_uses_confirmed_api_without_mutating(self):
        with patch("netfix.api.detect_environment", return_value={"ok": True}), \
                patch("netfix.api.get_core", return_value=None), \
                patch("netfix.api.FixEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.execute.return_value = {"ok": True, "status": "dry-run", "preview": ["sudo bash bin/disable_ipv6.sh"]}
            result = mcp_server._call_tool("netfix_dry_run_fix", {"fix_id": "disable-ipv6"})

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["schema_version"], "netfix_mcp.v1")
        self.assertEqual(data["fix_id"], "disable-ipv6")
        self.assertEqual(data["preview"]["status"], "dry-run")
        self.assertTrue(engine.execute.call_args.kwargs["dry_run"])

    def test_mcp_apply_fix_tier2_requires_magic_word(self):
        result = mcp_server._call_tool("netfix_apply_fix", {"fix_id": "disable-ipv6", "confirmed": True, "magic_word": "WRONG"})

        self.assertTrue(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["schema_version"], "netfix_mcp.v1")
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["confirmation"], "APPLY_SYSTEM_FIX")

    def test_mcp_apply_fix_accepts_magic_word_alias(self):
        with patch("netfix.api._execute_confirmed_fix", return_value=(200, {"ok": True, "fix_id": "disable-ipv6"})) as execute:
            result = mcp_server._call_tool(
                "netfix_apply_fix",
                {"fix_id": "disable-ipv6", "confirmed": True, "magic_word": "APPLY_SYSTEM_FIX"},
            )

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertTrue(data["ok"])
        body = execute.call_args.args[0]
        self.assertTrue(body["confirmed"])
        self.assertEqual(body["confirmation"], "APPLY_SYSTEM_FIX")

    def test_mcp_sanitized_report_redacts_latest_report(self):
        report = Mock()
        report.as_dict.return_value = {
            "meta": {"timestamp": "now"},
            "diagnostics": [{"name": "proxy", "status": "fail", "error": "socks5://user:secret-pass@proxy.example.com:1080"}],
            "root_causes": [],
        }
        with patch("netfix.mcp_server.Report.load", return_value=report):
            result = mcp_server._call_tool("netfix_sanitized_report", {"level": "strict"})

        self.assertFalse(result.get("isError"))
        text = result["content"][0]["text"]
        data = json.loads(text)
        self.assertEqual(data["schema_version"], "netfix_mcp.v1")
        self.assertNotIn("secret-pass", text)
        self.assertIn("user:***@", text)
        self.assertIn("redacted_report_hash", data)

    def test_mcp_evidence_chain_binds_root_cause_to_diagnostics(self):
        report = Mock()
        report.as_dict.return_value = {
            "diagnostics": [
                {"name": "ipv6_leak", "display_name": "IPv6 泄漏检查", "status": "warn"},
                {"name": "dns", "display_name": "DNS 解析", "status": "ok"},
            ],
            "root_causes": [{"id": "ipv6-exposed", "description": "IPv6 直连", "confidence": 0.8}],
        }
        with patch("netfix.mcp_server.Report.load", return_value=report):
            result = mcp_server._call_tool("netfix_evidence_chain", {})

        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data["schema_version"], "netfix_mcp.v1")
        self.assertEqual(data["root_causes"][0]["evidence"][0]["diagnostic_id"], "ipv6_leak")

    def test_mcp_cli_result_strips_secret_carriers_and_redacts_command_output(self):
        secret_url = "http://user:demo-password@proxy.example.com:8000"
        with patch(
            "netfix.mcp_server.run_cli",
            return_value={
                "ok": False,
                "error": f"curl failed {secret_url} sk-live-secret-token-1234567890abc",
                "_secret": {"password": "demo-password"},
            },
        ):
            result = mcp_server._call_tool("netfix_codex", {})

        self.assertTrue(result.get("isError"))
        text = result["content"][0]["text"]
        self.assertNotIn('"_secret"', text)
        self.assertNotIn("demo-password", text)
        self.assertNotIn("sk-live-secret-token", text)
        self.assertIn("user:***@", text)

    def test_mcp_llm_providers_are_read_only_and_domestic_first(self):
        result = mcp_server._call_tool("netfix_llm_providers", {})
        self.assertFalse(result.get("isError"))
        data = json.loads(result["content"][0]["text"])
        ids = [item["id"] for item in data["providers"][:4]]
        self.assertEqual(ids, ["deepseek", "moonshot_kimi", "minimax", "qwen"])

    def test_mcp_llm_providers_include_local_readiness_status(self):
        with patch(
            "netfix.mcp_server.settings.load_settings",
            return_value={
                "llm": {
                    "provider": "deepseek",
                    "api_key_account": "deepseek-main",
                    "features": {"image_question": True},
                }
            },
        ), patch("netfix.mcp_server.keychain.has_secret", side_effect=lambda _service, account, **_kw: account in {"deepseek-main", "minimax"}):
            result = mcp_server._call_tool("netfix_llm_providers", {})

        self.assertFalse(result.get("isError"))
        providers = json.loads(result["content"][0]["text"])["providers"]
        deepseek = next(item for item in providers if item["id"] == "deepseek")
        minimax = next(item for item in providers if item["id"] == "minimax")
        self.assertEqual(deepseek["api_key_account"], "deepseek-main")
        self.assertTrue(deepseek["api_key_set"])
        self.assertTrue(deepseek["text_explain_ready"])
        self.assertFalse(deepseek["image_question_provider_supported"])
        self.assertTrue(minimax["api_key_set"])
        self.assertTrue(minimax["image_question_ready"])
        self.assertEqual(minimax["netfix_mode"], "text_and_image_question")

    def test_mcp_explain_llm_schema_exposes_image_question_safety_gate(self):
        tool = next(item for item in mcp_server._TOOLS if item["name"] == "netfix_explain_llm")
        props = tool["inputSchema"]["properties"]
        self.assertIn("mode", props)
        self.assertEqual(props["mode"]["enum"], ["explain", "image_question"])
        self.assertIn("upload_confirmed", props)
        self.assertIn("allow_fallback", props)
        self.assertIn("images", props)
        self.assertEqual(props["images"]["maxItems"], 3)

    def test_mcp_explain_llm_passes_image_question_arguments_to_safety_layer(self):
        report = Mock()
        report.as_dict.return_value = {"diagnostics": [], "fixes": []}
        image = {"data_url": "data:image/png;base64,AAAA"}
        with patch("netfix.mcp_server.Report.load", return_value=report), \
                patch(
                    "netfix.mcp_server.llm_explain.explain_with_llm",
                    return_value={"schema_version": "llm_explanation.v1", "source": "fallback"},
                ) as mock_explain:
            result = mcp_server._call_tool(
                "netfix_explain_llm",
                {
                    "question": "截图里有什么问题？",
                    "mode": "image_question",
                    "redaction_level": "strict",
                    "upload_confirmed": True,
                    "allow_fallback": False,
                    "images": [image],
                },
            )

        self.assertFalse(result.get("isError"))
        mock_explain.assert_called_once_with(
            {"diagnostics": [], "fixes": []},
            question="截图里有什么问题？",
            mode="image_question",
            redaction_level="strict",
            upload_confirmed=True,
            allow_fallback=False,
            image_inputs=[image],
        )


if __name__ == "__main__":
    unittest.main()
