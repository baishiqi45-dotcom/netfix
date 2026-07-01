import json
import stat
import tempfile
import threading
import time
import unittest
from io import BytesIO
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from netfix import api


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server: HTTPServer = api.create_server(host="127.0.0.1", port=0, timeout=5)
        cls.server.timeout = 1
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        deadline = time.time() + 5
        while not cls.server.server_address[1] and time.time() < deadline:
            time.sleep(0.01)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _get(self, path):
        headers = {}
        if path != "/health":
            headers["X-Netfix-Token"] = api._API_TOKEN
        req = Request(f"{self.base}{path}", headers=headers)
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.headers.get("Content-Type"), "application/json")
            return json.loads(resp.read().decode("utf-8"))

    def _get_error(self, path, expected_status, headers=None):
        req = Request(f"{self.base}{path}", headers=headers or {})
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, expected_status)
        return json.loads(ctx.exception.read().decode("utf-8"))

    def _post_json(self, path, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", "X-Netfix-Token": api._API_TOKEN},
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            self.assertEqual(resp.headers.get("Content-Type"), "application/json")
            return json.loads(resp.read().decode("utf-8"))

    def _post_json_error(self, path, body, expected_status):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", "X-Netfix-Token": api._API_TOKEN},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=20)
        self.assertEqual(ctx.exception.code, expected_status)
        return json.loads(ctx.exception.read().decode("utf-8"))

    def _post_json_error_with_headers(self, path, body, headers, expected_status):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=20)
        self.assertEqual(ctx.exception.code, expected_status)
        return json.loads(ctx.exception.read().decode("utf-8"))

    def _post_json_with_headers(self, path, body, headers):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}{path}",
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            self.assertEqual(resp.headers.get("Content-Type"), "application/json")
            return json.loads(resp.read().decode("utf-8"))

    def _get_raw(self, path):
        req = Request(f"{self.base}{path}")
        with urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")

    def test_health(self):
        data = self._get("/health")
        self.assertTrue(data["ok"])
        self.assertIn("version", data)

    def test_session_endpoint_removed(self):
        data = self._get_error("/session", 403)
        self.assertFalse(data["ok"])
        data = self._get_error("/session", 410, {"X-Netfix-Token": api._API_TOKEN})
        self.assertFalse(data["ok"])
        self.assertIn("removed", data["error"])

    def test_web_shell_uses_httponly_cookie_not_inline_token(self):
        status, headers, html = self._get_raw("/")
        self.assertEqual(status, 200)
        cookie = headers.get("Set-Cookie", "")
        self.assertIn("netfix_token=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertNotIn(api._API_TOKEN, html)
        self.assertNotIn("__NETFIX_API_TOKEN__", html)
        self.assertNotIn("X-Netfix-Token", html)

    def test_same_origin_browser_post_accepts_httponly_cookie(self):
        _status, headers, _html = self._get_raw("/")
        cookie = headers.get("Set-Cookie", "").split(";", 1)[0]
        data = self._post_json_with_headers(
            "/proxy/parse",
            {"input": "proxy.example.com:8000"},
            {"Origin": self.base, "Cookie": cookie},
        )
        self.assertTrue(data["ok"])

    def test_sensitive_get_requires_token(self):
        data = self._get_error("/logs", 403)
        self.assertFalse(data["ok"])
        self.assertIn("token", data["error"])

    def test_api_token_file_is_private_and_chmod_failure_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "api-token.txt"
            with patch("netfix.api._API_TOKEN_FILE", token_file), \
                    patch("netfix.api._API_TOKEN", "test-token"):
                written = api._write_api_token_file()
            self.assertEqual(written, token_file)
            self.assertEqual(token_file.read_text(encoding="utf-8"), "test-token\n")
            self.assertEqual(stat.S_IMODE(token_file.stat().st_mode), 0o600)

        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "api-token.txt"
            with patch("netfix.api._API_TOKEN_FILE", token_file), \
                    patch("netfix.api.os.chmod", side_effect=OSError("denied")):
                with self.assertRaises(RuntimeError):
                    api._write_api_token_file()

    def test_capabilities(self):
        data = self._get("/capabilities")
        self.assertIn("commands", data)
        self.assertIn("codex", data["commands"])
        self.assertIn("service_groups", data)

    def test_llm_providers_prioritize_domestic_models(self):
        data = self._get("/llm/providers")
        self.assertTrue(data["ok"])
        ids = [item["id"] for item in data["providers"][:4]]
        self.assertEqual(ids, ["deepseek", "moonshot_kimi", "minimax", "qwen"])
        self.assertIn("api_key_set", data["providers"][0])
        self.assertIn("text_explain_ready", data["providers"][0])
        self.assertIn("image_question_ready", data["providers"][0])
        self.assertFalse(data["providers"][0]["image_question_provider_supported"])
        self.assertEqual(data["providers"][0]["metadata_checked_at"], "2026-06-25")
        self.assertTrue(data["providers"][0]["official_docs"][0].startswith("https://"))
        self.assertEqual(data["providers"][1]["base_url"], "https://api.moonshot.cn/v1")
        self.assertTrue(data["providers"][1]["image_question_adapter_ready"])
        self.assertEqual(data["providers"][2]["base_url"], "https://api.minimaxi.com/v1")
        self.assertEqual(data["providers"][2]["max_tokens_field"], "max_completion_tokens")
        self.assertTrue(data["providers"][2]["image_question_adapter_ready"])

    def test_llm_providers_report_provider_key_status(self):
        with patch.dict("os.environ", {"NETFIX_LLM_API_KEY_QWEN": "qwen-key"}, clear=True), \
                patch("netfix.keychain.is_available", return_value=False):
            data = self._get("/llm/providers")
        keyed = {item["id"]: item["api_key_set"] for item in data["providers"]}
        self.assertTrue(keyed["qwen"])
        self.assertFalse(keyed["moonshot_kimi"])

    def test_llm_providers_show_active_provider_runtime_settings(self):
        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = True
        configured["llm"]["provider"] = "deepseek"
        configured["llm"]["model"] = "deepseek-v4-pro"
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.has_secret", return_value=True):
            data = self._get("/llm/providers")

        deepseek = next(item for item in data["providers"] if item["id"] == "deepseek")
        self.assertEqual(deepseek["model"], "deepseek-v4-pro")

    def test_llm_chain_readiness_reports_text_and_vision_provider_gaps(self):
        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = True
        configured["llm"]["features"]["image_question"] = True
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.has_secret", side_effect=lambda _service, account, **_kw: account in {"deepseek", "minimax"}), \
                patch("netfix.api.llm_budget.status", return_value={
                    "enabled": True,
                    "window_s": 3600,
                    "used_requests": 7,
                    "remaining_requests": 53,
                    "used_image_requests": 2,
                    "remaining_image_requests": 10,
                    "cooldowns": {},
                    "persisted": True,
                }) as budget_status:
            data = self._get("/llm/chain-readiness")

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_llm_chain_readiness.v1")
        self.assertEqual(data["budget"]["used_requests"], 7)
        self.assertEqual(data["budget"]["remaining_image_requests"], 10)
        self.assertTrue(data["budget"]["persisted"])
        budget_status.assert_called_once()
        chains = {chain["id"]: chain for chain in data["chains"]}
        self.assertEqual(chains["text"]["status"], "ready")
        self.assertEqual(chains["image_question"]["status"], "ready")
        text_steps = {step["provider"]: step for step in chains["text"]["providers"]}
        image_steps = {step["provider"]: step for step in chains["image_question"]["providers"]}
        self.assertTrue(text_steps["deepseek"]["ready"])
        self.assertEqual(text_steps["deepseek"]["metadata_checked_at"], "2026-06-25")
        self.assertIn("https://api-docs.deepseek.com/", text_steps["deepseek"]["official_docs"])
        self.assertTrue(image_steps["minimax"]["ready"])
        self.assertEqual(image_steps["minimax"]["max_tokens_field"], "max_completion_tokens")
        self.assertIn("https://platform.minimaxi.com/docs/api-reference/text-chat-openai", image_steps["minimax"]["official_docs"])
        self.assertEqual(image_steps["moonshot_kimi"]["status"], "missing_key")
        self.assertIn("qwen", chains["image_question"]["missing_key_providers"])

    def test_llm_chain_test_requires_confirmation(self):
        data = self._post_json("/llm/chain-test", {})

        self.assertFalse(data["ok"])
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["confirmation"], "TEST_LLM_CHAIN")

    def test_import_deepseek_sidecar_key_requires_confirmation(self):
        data = self._post_json("/llm/import-deepseek-sidecar-key", {})

        self.assertFalse(data["ok"])
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["confirmation"], "IMPORT_DEEPSEEK_SIDECAR_KEY")

    def test_import_deepseek_sidecar_key_returns_sanitized_status(self):
        with patch("netfix.api.deepseek_sidecar.import_sidecar_key", return_value={
            "ok": True,
            "schema_version": "netfix_deepseek_sidecar_import.v1",
            "provider": "deepseek",
            "api_key_account": "deepseek",
            "key_name": "DS_API_KEY",
            "env_path": "/Users/alice/Desktop/mess/.env",
            "model": "deepseek-v4-pro",
            "llm_enabled": True,
            "api_key_set": True,
            "settings": {"api_key": "********"},
        }) as importer:
            data = self._post_json(
                "/llm/import-deepseek-sidecar-key",
                {"confirmation": "IMPORT_DEEPSEEK_SIDECAR_KEY"},
            )

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_deepseek_sidecar_import.v1")
        self.assertEqual(data["model"], "deepseek-v4-pro")
        self.assertNotIn("sk-", json.dumps(data))
        importer.assert_called_once_with(account="deepseek", enable_llm=True)

    def test_llm_chain_test_does_not_call_providers_when_llm_disabled(self):
        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = False
        configured["llm"]["features"]["image_question"] = True
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.get_secret", return_value="key"), \
                patch("netfix.api.llm_provider.OpenAICompatibleProvider.complete_json") as complete:
            data = self._post_json("/llm/chain-test", {"confirmation": "TEST_LLM_CHAIN", "mode": "all"})

        self.assertFalse(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_llm_chain_test.v1")
        self.assertEqual(data["reason_code"], "llm_disabled")
        self.assertEqual(data["tested_count"], 0)
        complete.assert_not_called()

    def test_llm_chain_test_rejects_unknown_mode_without_provider_call(self):
        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = True
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.get_secret", return_value="key"), \
                patch("netfix.api.llm_provider.OpenAICompatibleProvider.complete_json") as complete:
            data = self._post_json_error(
                "/llm/chain-test",
                {"confirmation": "TEST_LLM_CHAIN", "mode": "surprise"},
                400,
            )

        self.assertFalse(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_llm_chain_test.v1")
        self.assertEqual(data["reason_code"], "invalid_mode")
        self.assertIn("mode", data["error"])
        self.assertEqual(data["tested_count"], 0)
        complete.assert_not_called()

    def test_llm_chain_test_calls_only_configured_provider_keys(self):
        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = True
        configured["llm"]["features"]["image_question"] = True
        provider_response = {
            "schema_version": "llm_explanation.v1",
            "headline": "provider chain test ok",
            "severity": "ok",
            "explanation": "ok",
            "actions": [],
            "manual_steps": [],
        }
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.get_secret", side_effect=lambda _service, account, **_kw: "key" if account in {"deepseek", "minimax"} else ""), \
                patch("netfix.api.llm_budget.check_request", return_value={"ok": True}), \
                patch("netfix.api.llm_budget.record_request"), \
                patch("netfix.api.llm_provider.OpenAICompatibleProvider.complete_json", return_value=dict(provider_response)) as complete:
            data = self._post_json("/llm/chain-test", {"confirmation": "TEST_LLM_CHAIN", "mode": "all"})

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_llm_chain_test.v1")
        self.assertEqual(data["tested_count"], 3)
        self.assertEqual(complete.call_count, 3)
        chains = {chain["id"]: chain for chain in data["chains"]}
        self.assertEqual(chains["text"]["status"], "ok")
        self.assertEqual(chains["image_question"]["status"], "ok")
        text_steps = {step["provider"]: step for step in chains["text"]["providers"]}
        self.assertEqual(text_steps["deepseek"]["status"], "ok")
        self.assertEqual(text_steps["minimax"]["status"], "ok")
        self.assertEqual(text_steps["moonshot_kimi"]["status"], "skipped")
        self.assertEqual(text_steps["moonshot_kimi"]["reason_code"], "missing_api_key")
        image_steps = {step["provider"]: step for step in chains["image_question"]["providers"]}
        self.assertEqual(image_steps["minimax"]["status"], "ok")
        self.assertEqual(image_steps["moonshot_kimi"]["status"], "skipped")
        self.assertEqual(image_steps["moonshot_kimi"]["reason_code"], "missing_api_key")

    def test_llm_provider_test_requires_confirmation_and_enabled_setting(self):
        data = self._post_json("/llm/test", {})
        self.assertFalse(data["ok"])
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["confirmation"], "TEST_LLM_PROVIDER")

        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = False
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.get_secret", return_value="key"), \
                patch("netfix.api.llm_provider.OpenAICompatibleProvider.complete_json") as complete:
            disabled = self._post_json_error("/llm/test", {"confirmation": "TEST_LLM_PROVIDER"}, 400)
        self.assertFalse(disabled["ok"])
        self.assertEqual(disabled["reason_code"], "llm_disabled")
        complete.assert_not_called()

    def test_llm_provider_test_uses_strict_json_prompt(self):
        configured = json.loads(json.dumps(api.settings.DEFAULT_SETTINGS))
        configured["llm"]["enabled"] = True
        configured["llm"]["model"] = "deepseek-v4-pro"
        provider_response = {
            "schema_version": "llm_explanation.v1",
            "headline": "provider test ok",
            "severity": "ok",
            "explanation": "ok",
            "actions": [],
            "manual_steps": [],
        }
        with patch("netfix.api.settings.load_settings", return_value=configured), \
                patch("netfix.api.keychain.get_secret", return_value="key"), \
                patch("netfix.api.llm_provider.OpenAICompatibleProvider.complete_json", return_value=dict(provider_response)) as complete:
            data = self._post_json("/llm/test", {"confirmation": "TEST_LLM_PROVIDER"})

        self.assertTrue(data["ok"])
        self.assertEqual(data["provider_used"], "deepseek")
        messages = complete.call_args.args[0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("JSON API", messages[0]["content"])
        self.assertIn("llm_explanation.v1", messages[1]["content"])
        self.assertIn("expected_json", messages[1]["content"])
        self.assertEqual(complete.call_args.kwargs["max_tokens"], 256)

    def test_run_sync(self):
        data = self._post_json("/run", {"command": ["codex"], "timeout": 5})
        self.assertIn("ok", data)
        if data.get("ok"):
            self.assertIn("result", data)
        else:
            self.assertIn("error", data)

    def test_json_body_limit_supports_image_question_payloads_and_reports_oversize(self):
        self.assertGreaterEqual(api.MAX_JSON_BODY_BYTES, 20 * 1024 * 1024)
        handler = object.__new__(api.APIRequestHandler)
        handler.headers = {"Content-Length": str(api.MAX_JSON_BODY_BYTES + 1)}
        handler.rfile = BytesIO(b"")
        self.assertIsNone(handler._read_body())
        self.assertIn("too large", handler._body_error_message())

    def test_run_rejects_unknown_command(self):
        data = self._post_json_error("/run", {"command": ["server"]}, 403)
        self.assertFalse(data["ok"])
        self.assertIn("not allowed", data["error"])

    def test_run_rejects_cross_origin_browser_post(self):
        data = self._post_json_error_with_headers(
            "/run",
            {"command": ["codex"], "timeout": 5},
            {"Origin": "https://evil.example"},
            403,
        )
        self.assertFalse(data["ok"])
        self.assertIn("cross-origin", data["error"])

    def test_same_origin_browser_post_requires_token(self):
        data = self._post_json_error_with_headers(
            "/proxy/parse",
            {"input": "proxy.example.com:8000"},
            {"Origin": self.base},
            403,
        )
        self.assertFalse(data["ok"])
        self.assertIn("token", data["error"])

    def test_same_origin_browser_post_accepts_token(self):
        data = self._post_json_with_headers(
            "/proxy/parse",
            {"input": "proxy.example.com:8000"},
            {"Origin": self.base, "X-Netfix-Token": api._API_TOKEN},
        )
        self.assertTrue(data["ok"])

    def test_run_rejects_tier2_fix_execution(self):
        data = self._post_json_error(
            "/run",
            {"command": ["fix", "--issue", "disable-ipv6", "--yes", "--report"]},
            403,
        )
        self.assertFalse(data["ok"])
        self.assertIn("Tier 2", data["error"])

    def test_confirmed_fix_endpoint_requires_phrase_for_tier2(self):
        data = self._post_json_error(
            "/fixes/execute",
            {"fix_id": "disable-ipv6", "confirmed": True},
            409,
        )
        self.assertFalse(data["ok"])
        self.assertTrue(data["requires_confirmation"])
        self.assertEqual(data["confirmation"], api.SYSTEM_FIX_CONFIRMATION)

    def test_confirmed_fix_endpoint_allows_tier2_dry_run_without_phrase(self):
        with patch("netfix.api.detect_environment", return_value={"ok": True}), \
                patch("netfix.api.get_core", return_value=None), \
                patch("netfix.api.FixEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.execute.return_value = {"ok": True, "status": "dry-run", "preview": ["sudo bash bin/disable_ipv6.sh"]}
            data = self._post_json(
                "/fixes/execute",
                {"fix_id": "disable-ipv6", "dry_run": True},
            )

        self.assertEqual(data["status"], "dry-run")
        engine.execute.assert_called_once()
        self.assertTrue(engine.execute.call_args.kwargs["dry_run"])
        self.assertFalse(engine.execute.call_args.kwargs["confirmed"])

    def test_confirmed_fix_endpoint_executes_tier2_after_app_confirmation(self):
        report = {
            "diagnostics": [],
            "root_causes": [],
            "fixes": [],
            "manual_steps": [],
            "explanation": {"headline": "网络看起来正常"},
        }
        with patch("netfix.api.detect_environment", return_value={"ok": True}) as detect, \
                patch("netfix.api.get_core", return_value=None) as get_core, \
                patch("netfix.api.FixEngine") as engine_cls, \
                patch("netfix.api.run_cli", return_value={"ok": True, "result": report}) as run:
            engine = engine_cls.return_value
            engine.execute.return_value = {"ok": True, "status": "ok"}
            data = self._post_json(
                "/fixes/execute",
                {
                    "fix_id": "disable-ipv6",
                    "confirmed": True,
                    "confirmation": api.SYSTEM_FIX_CONFIRMATION,
                    "timeout": 9,
                },
            )

        self.assertEqual(data["explanation"]["headline"], "网络看起来正常")
        detect.assert_called_once()
        get_core.assert_called_once()
        engine.execute.assert_called_once()
        kwargs = engine.execute.call_args.kwargs
        self.assertEqual(kwargs["confirmed"], True)
        self.assertEqual(kwargs["auto_confirm"], False)
        self.assertEqual(kwargs["env"], {"ok": True})
        run.assert_called_once_with(["codex", "--json", "--timeout", "9"], timeout=9)

    def test_confirmed_fix_endpoint_explains_verification_failure(self):
        failed_result = {
            "ok": False,
            "status": "failed",
            "fix_id": "disable-ipv6",
            "verification_failed": True,
            "verify_diagnostic": {
                "name": "ipv6_leak",
                "display_name": "IPv6 泄漏检查",
                "status": "warn",
                "details": {
                    "reason": "proxy active and IPv6 default route present; no public IPv6 observed",
                },
            },
        }
        with patch("netfix.api.detect_environment", return_value={"ok": True}), \
                patch("netfix.api.get_core", return_value=None), \
                patch("netfix.api.FixEngine") as engine_cls:
            engine = engine_cls.return_value
            engine.execute.return_value = failed_result
            data = self._post_json_error(
                "/fixes/execute",
                {
                    "fix_id": "disable-ipv6",
                    "confirmed": True,
                    "confirmation": api.SYSTEM_FIX_CONFIRMATION,
                    "timeout": 9,
                },
                400,
            )

        self.assertEqual(data["reason_code"], "fix_verification_failed")
        self.assertIn("修复命令已执行", data["error"])
        self.assertIn("IPv6 泄漏检查", data["error"])
        self.assertNotEqual(data["error"], "failed")

    def test_run_allows_plain_rollback(self):
        with patch("netfix.api.run_cli", return_value={"ok": True, "result": {"diagnostics": [], "root_causes": [], "fixes": [], "manual_steps": []}}) as run:
            data = self._post_json("/run", {"command": ["rollback"], "timeout": 5})
        self.assertTrue(data["ok"])
        run.assert_called_once()

    def test_explain_llm_falls_back_without_cloud_call(self):
        report = {
            "diagnostics": [{"name": "proxy_auth_check", "status": "fail"}],
            "root_causes": [{"id": "proxy-auth", "description": "代理认证失败"}],
            "explanation": {"headline": "代理认证失败", "explanation": "本地解释"},
        }
        with patch("netfix.api._load_latest_report", return_value=(200, report)), \
                patch("netfix.llm_explain.load_settings", return_value={"llm": {"enabled": False}}):
            data = self._post_json("/explain_llm", {})
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["source"], "fallback")

    def test_explain_llm_requires_upload_confirmation_when_ask_each_time(self):
        report = {
            "diagnostics": [{"name": "proxy_auth_check", "status": "fail"}],
            "root_causes": [{"id": "proxy-auth", "description": "代理认证失败"}],
            "explanation": {"headline": "代理认证失败", "explanation": "本地解释"},
        }
        with patch(
            "netfix.llm_explain.load_settings",
            return_value={"llm": {"enabled": True, "provider": "deepseek", "upload_consent": "ask_each_time"}},
        ), patch("netfix.api._load_latest_report", return_value=(200, report)), \
                patch("netfix.llm_explain.OpenAICompatibleProvider.complete_json") as complete:
            data = self._post_json("/explain_llm", {})
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["fallback_reason"], "upload_consent_required")
        complete.assert_not_called()

    def test_explain_llm_uses_latest_report_not_client_supplied_report(self):
        latest = {
            "diagnostics": [{"name": "latest", "status": "fail"}],
            "root_causes": [{"id": "latest-root", "description": "最新报告"}],
            "explanation": {"headline": "最新报告", "explanation": "本地解释"},
        }
        client_supplied = {
            "diagnostics": [{"name": "client", "status": "ok"}],
            "root_causes": [],
            "explanation": {"headline": "客户端传入", "explanation": "不应使用"},
        }
        with patch("netfix.api._load_latest_report", return_value=(200, latest)), \
                patch("netfix.llm_explain.load_settings", return_value={"llm": {"enabled": False}}):
            data = self._post_json("/explain_llm", {"report": client_supplied})
        self.assertTrue(data["ok"])
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn("最新报告", encoded)
        self.assertNotIn("客户端传入", encoded)

    def test_explain_llm_passes_image_inputs_to_llm_layer(self):
        latest = {
            "diagnostics": [{"name": "latest", "status": "fail"}],
            "root_causes": [{"id": "latest-root", "description": "最新报告"}],
            "explanation": {"headline": "最新报告", "explanation": "本地解释"},
        }

        def fake_explain(**kwargs):
            self.assertEqual(kwargs["mode"], "image_question")
            self.assertEqual(kwargs["image_inputs"], ["data:image/png;base64,AAAA"])
            return {"source": "fallback", "fallback_reason": "image_question_disabled"}

        with patch("netfix.api._load_latest_report", return_value=(200, latest)), \
                patch("netfix.api.llm_explain.explain_with_llm", side_effect=fake_explain) as explain:
            data = self._post_json(
                "/explain_llm",
                {"mode": "image_question", "images": ["data:image/png;base64,AAAA"], "upload_confirmed": True},
            )
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["fallback_reason"], "image_question_disabled")
        explain.assert_called_once()

    def test_proxy_parse_redacts_credentials(self):
        data = self._post_json("/proxy/parse", {"input": "http://user:pass@proxy.example.com:8000"})
        self.assertTrue(data["ok"])
        self.assertIn("user:***@", data["redacted_url"])
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("pass@proxy", encoded)

    def test_proxy_parse_colon_tuple_defaults_to_http_without_returning_secret(self):
        data = self._post_json("/proxy/parse", {"input": "direct.miyaip.online:8001:demo-user:demo-password"})

        self.assertTrue(data["ok"])
        self.assertEqual(data["profile"]["protocol"], "http")
        self.assertEqual(data["profile"]["host"], "direct.miyaip.online")
        self.assertEqual(data["profile"]["port"], 8001)
        self.assertEqual(data["profile"]["username"], "demo-user")
        self.assertTrue(data["profile"]["password_set"])
        self.assertEqual(data["deployment_decision"]["status"], "ready")
        self.assertEqual(data["deployment_decision"]["system_apply"]["status"], "bridge_required")
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn("demo-user:***@", encoded)
        self.assertIn("开始使用这台 Mac", encoded)
        self.assertIn("先按 HTTP", encoded)
        self.assertNotIn("demo-password", encoded)
        self.assertNotIn("_secret", encoded)

    def test_proxy_import_preview_accepts_single_host_port_user_password_line(self):
        data = self._post_json(
            "/proxy/import-preview",
            {"input": "direct.miyaip.online:8001:demo-user:demo-password"},
        )

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_proxy_import_preview.v1")
        self.assertEqual(data["summary"]["valid_count"], 1)
        self.assertEqual(data["summary"]["ready_count"], 1)
        self.assertEqual(data["recommendation"]["line_number"], 1)
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn("direct.miyaip.online", encoded)
        self.assertIn("demo-user:***@", encoded)
        self.assertIn("开始使用这台 Mac", encoded)
        self.assertNotIn("demo-password", encoded)
        self.assertNotIn("_secret", encoded)

    def test_proxy_import_preview_redacts_bulk_credentials(self):
        data = self._post_json(
            "/proxy/import-preview",
            {
                "input": "\n".join([
                    "host,port,user,password",
                    "http://alpha:secret-one@alpha.example.com:8000",
                    "beta.example.com,9000,beta,secret-two",
                    "bad-line",
                ]),
            },
        )

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_proxy_import_preview.v1")
        self.assertEqual(data["summary"]["valid_count"], 2)
        self.assertEqual(data["summary"]["invalid_count"], 1)
        self.assertEqual(data["recommendation"]["line_number"], 2)
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn("alpha:***@", encoded)
        self.assertIn("beta:***@", encoded)
        self.assertNotIn("secret-one", encoded)
        self.assertNotIn("secret-two", encoded)
        self.assertNotIn("_secret", encoded)

    def test_proxy_validate_uses_safe_validator(self):
        check = {
            "profile_id": "p1",
            "status": "ok",
            "auth": "ok",
            "tcp": "ok",
            "target": "https://www.gstatic.com/generate_204",
            "http_code": 204,
            "latency_ms": 120,
            "error": None,
            "checked_via": "http://user:***@proxy.example.com:8000",
        }
        with patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": True, "proxy_check": check}):
            data = self._post_json("/proxy/validate", {"input": "http://user:pass@proxy.example.com:8000"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["proxy_check"]["status"], "ok")
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("pass@proxy", encoded)

    def test_proxy_validation_targets_endpoint_returns_allowlisted_profiles(self):
        data = self._get("/proxy/validation-targets")

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_proxy_validation_targets.v1")
        self.assertEqual(data["default_profile"], "baseline")
        self.assertIn("api.deepseek.com", data["allowed_hosts"])
        self.assertIn("api.minimaxi.com", data["allowed_hosts"])
        self.assertEqual({profile["id"] for profile in data["profiles"]}, {"baseline", "ai_dev"})
        ai_dev = next(profile for profile in data["profiles"] if profile["id"] == "ai_dev")
        self.assertIn("minimax_api", {probe["id"] for probe in ai_dev["probes"]})

    def test_proxy_validate_can_request_identity_report(self):
        check = {
            "profile_id": "p1",
            "status": "ok",
            "auth": "ok",
            "tcp": "ok",
            "target": "https://www.gstatic.com/generate_204",
            "http_code": 204,
            "latency_ms": 120,
            "error": None,
            "checked_via": "http://user:***@proxy.example.com:8000",
        }
        identity = {
            "status": "ok",
            "exit_ip": "203.0.113.10",
            "identity": {"ip_type": "residential", "country_code": "US"},
            "targets": [],
        }
        with patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": True, "proxy_check": check, "identity_report": identity}) as validate:
            data = self._post_json(
                "/proxy/validate",
                {"input": "http://user:pass@proxy.example.com:8000", "include_identity": True, "target_profile": "ai_dev"},
            )
        self.assertTrue(data["ok"])
        self.assertEqual(data["identity_report"]["exit_ip"], "203.0.113.10")
        kwargs = validate.call_args.kwargs
        self.assertTrue(kwargs["include_identity"])
        self.assertEqual(kwargs["password"], "pass")
        self.assertEqual(kwargs["target_profile"], "ai_dev")

    def test_saved_proxy_validate_does_not_persist_full_identity_report_by_default(self):
        profile = {
            "id": "p1",
            "name": "proxy",
            "protocol": "http",
            "host": "proxy.example.com",
            "port": 8000,
            "username": "user",
            "credential_ref": "keychain://netfix.proxy/p1",
        }
        result = {
            "ok": True,
            "proxy_check": {"status": "ok", "latency_ms": 120},
            "identity_report": {
                "status": "ok",
                "exit_ip": "203.0.113.10",
                "identity": {"country_code": "US", "city": "New York", "isp": "Residential ISP", "asn": "AS64500", "ip_type": "residential"},
                "dns_leak": {"status": "unknown"},
                "ipv6_leak": {"status": "unknown"},
                "targets": [{"id": "google_204", "status": "ok"}],
                "warnings": ["sample"],
            },
        }
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[profile]), \
                patch("netfix.api.settings.get_privacy_settings", return_value={"persist_proxy_identity_report": False}), \
                patch("netfix.api.residential_proxy.validate_saved_profile", return_value=result) as validate_saved, \
                patch("netfix.api.settings.upsert_proxy_profile") as upsert:
            data = self._post_json("/proxy/profiles/p1/validate", {"timeout": 10, "include_identity": True, "target_profile": "ai_dev"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["identity_report"]["exit_ip"], "203.0.113.10")
        self.assertEqual(validate_saved.call_args.kwargs["target_profile"], "ai_dev")
        self.assertIn("profile", data)
        saved = upsert.call_args.args[0]
        self.assertNotIn("last_identity_report", saved)
        self.assertIn("last_identity_summary", saved)
        self.assertEqual(saved["last_identity_summary"]["status"], "ok")
        self.assertEqual(saved["last_identity_summary"]["ip_type"], "residential")
        self.assertNotIn("exit_ip", saved["last_identity_summary"])

    def test_saved_proxy_validate_can_persist_full_identity_report_when_user_allows(self):
        profile = {"id": "p1", "protocol": "http", "host": "proxy.example.com", "port": 8000}
        result = {
            "ok": True,
            "proxy_check": {"status": "ok"},
            "identity_report": {"status": "ok", "exit_ip": "203.0.113.10", "identity": {"ip_type": "residential"}},
        }
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[profile]), \
                patch("netfix.api.settings.get_privacy_settings", return_value={"persist_proxy_identity_report": True}), \
                patch("netfix.api.residential_proxy.validate_saved_profile", return_value=result), \
                patch("netfix.api.settings.upsert_proxy_profile") as upsert:
            data = self._post_json("/proxy/profiles/p1/validate", {"timeout": 10, "include_identity": True})
        self.assertTrue(data["ok"])
        saved = upsert.call_args.args[0]
        self.assertEqual(saved["last_identity_report"]["exit_ip"], "203.0.113.10")

    def test_proxy_validate_rejects_unapproved_target_url(self):
        data = self._post_json_error(
            "/proxy/validate",
            {"input": "http://proxy.example.com:8000", "target_url": "http://169.254.169.254/latest/meta-data"},
            400,
        )
        self.assertFalse(data["ok"])
        self.assertEqual(data["proxy_check"]["error"], "target_url_not_allowed")

    def test_proxy_monitor_status_and_controls(self):
        status = self._get("/proxy/monitor")
        self.assertTrue(status["ok"])
        self.assertIn("monitor", status)
        with patch("netfix.api.proxy_monitor_service.start", return_value={"ok": True, "monitor": {"running": True, "profile_id": "p1"}}) as start:
            data = self._post_json("/proxy/monitor/start", {"profile_id": "p1", "interval": 60, "timeout": 5, "target_profile": "ai_dev"})
        self.assertTrue(data["ok"])
        start.assert_called_once()
        self.assertEqual(start.call_args.kwargs["target_profile"], "ai_dev")
        with patch("netfix.api.proxy_monitor_service.stop", return_value={"ok": True, "monitor": {"running": False}}) as stop:
            stopped = self._post_json("/proxy/monitor/stop", {})
        self.assertTrue(stopped["ok"])
        stop.assert_called_once()

    def test_proxy_profile_save_can_start_monitor_without_system_apply(self):
        saved = {
            "ok": True,
            "profile": {"id": "p1", "name": "proxy.example.com:8000"},
            "deployment_decision": {"status": "ready"},
        }
        monitor = {"ok": True, "monitor": {"running": True, "profile_id": "p1", "target_profile": "ai_dev"}}
        with patch("netfix.api.residential_proxy.save_proxy_profile", return_value=saved) as save, \
                patch("netfix.api.proxy_monitor_service.start", return_value=monitor) as start:
            data = self._post_json("/proxy/profiles", {
                "input": "http://user:pass@proxy.example.com:8000",
                "start_monitor": True,
                "target_profile": "ai_dev",
                "monitor_interval": 120,
                "timeout": 7,
            })

        self.assertTrue(data["ok"])
        self.assertTrue(data["monitor"]["ok"])
        save.assert_called_once()
        start.assert_called_once()
        self.assertEqual(start.call_args.kwargs["profile_id"], "p1")
        self.assertEqual(start.call_args.kwargs["target_profile"], "ai_dev")
        self.assertEqual(start.call_args.kwargs["interval"], 120)
        self.assertEqual(start.call_args.kwargs["timeout"], 7)

    def test_proxy_profile_save_failure_does_not_start_monitor(self):
        with patch("netfix.api.residential_proxy.save_proxy_profile", return_value={"ok": False, "error": "bad proxy"}) as save, \
                patch("netfix.api.proxy_monitor_service.start") as start:
            data = self._post_json_error("/proxy/profiles", {
                "input": "bad",
                "start_monitor": True,
            }, 400)

        self.assertFalse(data["ok"])
        save.assert_called_once()
        start.assert_not_called()

    def test_proxy_profile_save_failure_strips_internal_secret_payload(self):
        failure = {
            "ok": False,
            "error": "bad proxy",
            "_secret": {"password": "super-secret"},
            "errors": ["格式不完整"],
        }
        with patch("netfix.api.residential_proxy.save_proxy_profile", return_value=failure):
            data = self._post_json_error("/proxy/profiles", {
                "input": "proxy.example.com:8000:user:super-secret",
            }, 400)

        encoded = json.dumps(data, ensure_ascii=False)
        self.assertFalse(data["ok"])
        self.assertNotIn("_secret", data)
        self.assertNotIn("super-secret", encoded)

    def test_proxy_profile_replace_can_restart_matching_monitor_without_system_apply(self):
        replaced = {
            "ok": True,
            "profile": {"id": "p1", "name": "住宅 IP"},
            "deployment_decision": {"status": "ready"},
            "previous_endpoint": {"host": "old.proxy.example.com", "port": 8000},
            "new_endpoint": {"host": "new.proxy.example.com", "port": 9000},
        }
        monitor_state = {"ok": True, "monitor": {"running": True, "profile_id": "p1", "target_profile": "ai_dev", "interval": 60, "timeout": 5}}
        monitor = {"ok": True, "monitor": {"running": True, "profile_id": "p1", "target_profile": "ai_dev"}}
        with patch("netfix.api.proxy_monitor_service.status", return_value=monitor_state) as status, \
                patch("netfix.api.residential_proxy.replace_proxy_profile", return_value=replaced) as replace, \
                patch("netfix.api.proxy_monitor_service.start", return_value=monitor) as start:
            data = self._post_json("/proxy/profiles/p1/replace", {
                "input": "http://new-user:new-pass@new.proxy.example.com:9000",
                "start_monitor": True,
                "target_profile": "ai_dev",
                "timeout": 7,
            })

        self.assertTrue(data["ok"])
        self.assertTrue(data["monitor"]["ok"])
        self.assertEqual(data["profile"]["id"], "p1")
        self.assertEqual(data["new_endpoint"]["host"], "new.proxy.example.com")
        status.assert_called_once()
        replace.assert_called_once()
        self.assertEqual(replace.call_args.args[0], "p1")
        self.assertEqual(replace.call_args.args[1]["input"], "http://new-user:new-pass@new.proxy.example.com:9000")
        start.assert_called_once()
        self.assertEqual(start.call_args.kwargs["profile_id"], "p1")
        self.assertEqual(start.call_args.kwargs["target_profile"], "ai_dev")
        self.assertEqual(start.call_args.kwargs["interval"], 60)
        self.assertEqual(start.call_args.kwargs["timeout"], 7)

    def test_proxy_profile_replace_missing_profile_returns_404_and_does_not_restart_monitor(self):
        with patch("netfix.api.proxy_monitor_service.status", return_value={"ok": True, "monitor": {"running": False}}) as status, \
                patch("netfix.api.residential_proxy.replace_proxy_profile", return_value={"ok": False, "error": "profile not found"}) as replace, \
                patch("netfix.api.proxy_monitor_service.start") as start:
            data = self._post_json_error("/proxy/profiles/missing/replace", {
                "input": "http://new-user:new-pass@new.proxy.example.com:9000",
                "start_monitor": True,
            }, 404)

        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "profile not found")
        status.assert_called_once()
        replace.assert_called_once()
        start.assert_not_called()

    def test_proxy_profile_delete_stops_matching_monitor_and_deletes_keychain_secret(self):
        monitor_state = {"ok": True, "monitor": {"running": True, "profile_id": "p1"}}
        deleted = {
            "ok": True,
            "profile": {"id": "p1", "credential_ref": "keychain://netfix.proxy/p1"},
            "keychain": {"ok": True, "service": "netfix.proxy", "account": "p1"},
        }
        with patch("netfix.api.proxy_monitor_service.status", return_value=monitor_state) as status, \
                patch("netfix.api.proxy_monitor_service.stop", return_value={"ok": True, "monitor": {"running": False}}) as stop, \
                patch("netfix.api.residential_proxy.delete_proxy_profile", return_value=deleted) as delete:
            data = self._post_json("/proxy/profiles/p1/delete", {})

        self.assertTrue(data["ok"])
        self.assertTrue(data["monitor_stopped"])
        self.assertEqual(data["profile"]["id"], "p1")
        status.assert_called_once()
        stop.assert_called_once()
        delete.assert_called_once_with("p1")

    def test_proxy_profile_delete_clears_matching_persisted_monitor_without_running_thread(self):
        monitor_state = {
            "ok": True,
            "monitor": {
                "running": False,
                "profile_id": "",
                "persisted": {"enabled": True, "profile_id": "p1"},
            },
        }
        deleted = {
            "ok": True,
            "profile": {"id": "p1", "credential_ref": "keychain://netfix.proxy/p1"},
            "keychain": {"ok": True, "service": "netfix.proxy", "account": "p1"},
        }
        with patch("netfix.api.proxy_monitor_service.status", return_value=monitor_state) as status, \
                patch("netfix.api.proxy_monitor_service.stop", return_value={"ok": True, "monitor": {"running": False}}) as stop, \
                patch("netfix.api.residential_proxy.delete_proxy_profile", return_value=deleted) as delete:
            data = self._post_json("/proxy/profiles/p1/delete", {})

        self.assertTrue(data["ok"])
        self.assertFalse(data["monitor_stopped"])
        self.assertTrue(data["monitor_persisted_cleared"])
        status.assert_called_once()
        stop.assert_called_once()
        delete.assert_called_once_with("p1")

    def test_proxy_profile_delete_missing_profile_returns_404(self):
        with patch("netfix.api.proxy_monitor_service.status", return_value={"ok": True, "monitor": {"running": False}}), \
                patch("netfix.api.proxy_monitor_service.stop") as stop, \
                patch("netfix.api.residential_proxy.delete_proxy_profile", return_value={"ok": False, "error": "profile not found"}) as delete:
            data = self._post_json_error("/proxy/profiles/missing/delete", {}, 404)

        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "profile not found")
        stop.assert_not_called()
        delete.assert_called_once_with("missing")

    def test_proxy_bridge_status_requires_token_and_returns_bridges(self):
        data = self._get_error("/proxy/bridge", 403)
        self.assertFalse(data["ok"])
        api._STARTUP_BRIDGE_CHECK = {}
        with patch("netfix.api.proxy_bridge.status", return_value={"ok": True, "bridges": [{"id": "b1"}]}) as status, \
                patch("netfix.api.residential_proxy.detect_stale_bridge", return_value={"ok": True, "status": "no_journal"}) as stale, \
                patch("netfix.api.residential_proxy.bridge_lifecycle", return_value={
                    "schema_version": "netfix_proxy_bridge_lifecycle.v1",
                    "status": "stopped",
                    "primary_action": "none",
                    "needs_attention": False,
                }) as lifecycle:
            bridge = self._get("/proxy/bridge")
        self.assertTrue(bridge["ok"])
        self.assertEqual(bridge["bridges"][0]["id"], "b1")
        self.assertEqual(bridge["stale_check"]["status"], "no_journal")
        self.assertEqual(bridge["lifecycle"]["schema_version"], "netfix_proxy_bridge_lifecycle.v1")
        self.assertEqual(bridge["lifecycle"]["status"], "stopped")
        status.assert_called_once()
        stale.assert_called_once()
        lifecycle.assert_called_once_with([{"id": "b1"}], {"ok": True, "status": "no_journal"})

    def test_startup_bridge_check_records_attention_event_and_is_exposed(self):
        api._STARTUP_BRIDGE_CHECK = {}
        stale = {
            "ok": True,
            "status": "stale_bridge",
            "recovery_available": True,
            "network_service": "Wi-Fi",
        }
        lifecycle = {
            "schema_version": "netfix_proxy_bridge_lifecycle.v1",
            "status": "recovery_required",
            "severity": "warning",
            "headline": "需要恢复系统代理",
            "detail": "系统代理指向已停止的 Netfix 桥接端口。",
            "needs_attention": True,
            "recovery_available": True,
            "network_service": "Wi-Fi",
        }
        with patch("netfix.api.proxy_bridge.status", return_value={"ok": True, "bridges": []}), \
                patch("netfix.api.residential_proxy.detect_stale_bridge", return_value=stale), \
                patch("netfix.api.residential_proxy.bridge_lifecycle", return_value=lifecycle), \
                patch("netfix.api.logs.append_event", return_value={"ok": True}) as append_event:
            startup = api._record_startup_bridge_check()

        self.assertTrue(startup["ok"])
        self.assertEqual(startup["schema_version"], "netfix_proxy_bridge_startup_check.v1")
        self.assertEqual(startup["lifecycle"]["status"], "recovery_required")
        self.assertTrue(startup["event_appended"])
        event = append_event.call_args.args[0]
        self.assertEqual(event["type"], "proxy_bridge_startup")
        self.assertEqual(event["status"], "warn")
        self.assertTrue(event["recovery_available"])

        with patch("netfix.api.proxy_bridge.status", return_value={"ok": True, "bridges": []}), \
                patch("netfix.api.residential_proxy.detect_stale_bridge", return_value={"ok": True, "status": "no_journal"}), \
                patch("netfix.api.residential_proxy.bridge_lifecycle", return_value={
                    "schema_version": "netfix_proxy_bridge_lifecycle.v1",
                    "status": "stopped",
                    "needs_attention": False,
                }):
            bridge = self._get("/proxy/bridge")

        self.assertEqual(bridge["startup_check"]["schema_version"], "netfix_proxy_bridge_startup_check.v1")
        self.assertEqual(bridge["startup_check"]["lifecycle"]["status"], "recovery_required")
        api._STARTUP_BRIDGE_CHECK = {}

    def test_proxy_bridge_settings_endpoint_persists_auto_restart_preference(self):
        with patch("netfix.api.settings.get_proxy_bridge_settings", return_value={
            "auto_restart_enabled": False,
            "idle_timeout": 0,
            "updated_at": "",
        }) as get_settings:
            data = self._get("/settings/proxy-bridge")
        self.assertTrue(data["ok"])
        self.assertFalse(data["settings"]["auto_restart_enabled"])
        get_settings.assert_called_once()

        with patch("netfix.api.settings.update_proxy_bridge_settings", return_value={
            "auto_restart_enabled": True,
            "idle_timeout": 30,
            "updated_at": "",
        }) as update_settings:
            saved = self._post_json("/settings/proxy-bridge", {"auto_restart_enabled": True, "idle_timeout": 30})
        self.assertTrue(saved["ok"])
        self.assertTrue(saved["settings"]["auto_restart_enabled"])
        update_settings.assert_called_once_with({"auto_restart_enabled": True, "idle_timeout": 30})

    def test_startup_bridge_check_attempts_restart_only_when_opted_in(self):
        api._STARTUP_BRIDGE_CHECK = {}
        restart = {
            "ok": True,
            "status": "restarted",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "bridge": {"id": "new", "listen_host": "127.0.0.1", "listen_port": 19080},
            "system_proxy_changed": False,
        }
        lifecycle = {
            "schema_version": "netfix_proxy_bridge_lifecycle.v1",
            "status": "running_system",
            "needs_attention": False,
        }
        with patch("netfix.api.settings.get_proxy_bridge_settings", return_value={
            "auto_restart_enabled": True,
            "idle_timeout": 30,
            "updated_at": "",
        }), \
                patch("netfix.api.residential_proxy.restart_stale_bridge", return_value=restart) as restart_bridge, \
                patch("netfix.api.proxy_bridge.status", return_value={"ok": True, "bridges": [restart["bridge"]]}), \
                patch("netfix.api.residential_proxy.detect_stale_bridge", return_value={"ok": True, "status": "healthy"}), \
                patch("netfix.api.residential_proxy.bridge_lifecycle", return_value=lifecycle), \
                patch("netfix.api.logs.append_event", return_value={"ok": True}) as append_event:
            startup = api._record_startup_bridge_check()

        self.assertEqual(startup["auto_restart"]["status"], "restarted")
        self.assertFalse(startup["auto_restart"]["system_proxy_changed"])
        self.assertTrue(startup["auto_restart_event_appended"])
        restart_bridge.assert_called_once_with(
            confirmed=True,
            confirmation="RESTART_STALE_PROXY_BRIDGE",
            idle_timeout_s=30.0,
        )
        self.assertEqual(append_event.call_args.args[0]["status"], "ok")
        api._STARTUP_BRIDGE_CHECK = {}

    def test_proxy_bridge_recover_requires_token_and_confirmation(self):
        pending = {
            "ok": True,
            "status": "pending_confirmation",
            "requires_confirmation": True,
            "confirmation": "RESTORE_STALE_PROXY_BRIDGE",
        }
        with patch("netfix.api.residential_proxy.recover_stale_bridge", return_value=pending) as recover:
            data = self._post_json("/proxy/bridge/recover", {"confirmed": True, "confirmation": "wrong"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["confirmation"], "RESTORE_STALE_PROXY_BRIDGE")
        recover.assert_called_once()

    def test_proxy_apply_app_env_is_token_protected_and_redacted(self):
        profile = {
            "id": "p1",
            "name": "proxy",
            "protocol": "http",
            "host": "proxy.example.com",
            "port": 8000,
            "username": "user",
            "credential_ref": "keychain://netfix.proxy/p1",
        }
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[profile]):
            data = self._post_json("/proxy/profiles/p1/apply", {"mode": "app-env"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "applied")
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn("user:***@", encoded)
        self.assertNotIn("pass", encoded)

    def test_proxy_apply_system_confirmation_pending_without_phrase(self):
        profile = {
            "id": "p1",
            "name": "proxy",
            "protocol": "http",
            "host": "proxy.example.com",
            "port": 8000,
            "username": "",
            "credential_ref": "",
        }
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[profile]):
            data = self._post_json("/proxy/profiles/p1/apply", {"mode": "system", "confirmed": True, "confirmation": "wrong"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "pending_confirmation")
        self.assertEqual(data["confirmation"], "APPLY_PROXY_PROFILE")

    def test_proxy_apply_system_uses_bridge_for_authenticated_profile(self):
        profile = {
            "id": "p1",
            "name": "proxy",
            "protocol": "http",
            "host": "proxy.example.com",
            "port": 8000,
            "username": "user",
            "credential_ref": "keychain://netfix.proxy/p1",
        }
        applied = {
            "ok": True,
            "status": "applied",
            "mode": "system",
            "profile_id": "p1",
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
            "applied": {"scope": "loopback_bridge"},
        }
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[profile]), \
                patch("netfix.api.residential_proxy.apply_proxy_profile", return_value=applied) as apply:
            data = self._post_json(
                "/proxy/profiles/p1/apply",
                {"mode": "system", "confirmed": True, "confirmation": "APPLY_PROXY_PROFILE", "target_profile": "ai_dev"},
            )
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "applied")
        self.assertEqual(data["bridge"]["listen_host"], "127.0.0.1")
        apply.assert_called_once()
        self.assertEqual(apply.call_args.kwargs["target_profile"], "ai_dev")

    def test_proxy_export_profile_is_token_protected_and_uses_secret_placeholders(self):
        profile = {
            "id": "p1",
            "name": "proxy",
            "protocol": "socks5h",
            "host": "proxy.example.com",
            "port": 1080,
            "username": "user",
            "credential_ref": "keychain://netfix.proxy/p1",
        }
        missing_token = self._post_json_error_with_headers("/proxy/profiles/p1/export", {"format": "all"}, {}, 403)
        self.assertFalse(missing_token["ok"])
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[profile]):
            data = self._post_json("/proxy/profiles/p1/export", {"format": "all"})
        self.assertTrue(data["ok"])
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn("<password>", encoded)
        self.assertIn("ALL_PROXY", data["snippets"]["env"]["content"])
        self.assertIn("sing-box", data["snippets"])
        self.assertEqual(data["package"]["schema_version"], "netfix_proxy_client_package.v1")
        self.assertEqual(data["package"]["recommended_format"], "mihomo")
        self.assertTrue(any(item["path"] == "README.md" for item in data["package"]["files"]))
        self.assertTrue(any(item["path"].endswith(".sing-box.json") for item in data["package"]["files"]))
        self.assertNotIn("real-secret", encoded)

    def test_proxy_apply_profile_not_found(self):
        with patch("netfix.api.settings.get_proxy_profiles", return_value=[]):
            data = self._post_json_error("/proxy/profiles/missing/apply", {"mode": "app-env"}, 404)
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["error"])

    def test_proxy_rollback_requires_confirmation(self):
        with patch(
            "netfix.api.residential_proxy.rollback_last_proxy_apply",
            return_value={
                "ok": True,
                "status": "pending_confirmation",
                "requires_confirmation": True,
                "confirmation": "ROLLBACK_PROXY_PROFILE",
            },
        ) as rollback:
            data = self._post_json("/proxy/profiles/rollback", {"confirmed": True, "confirmation": "wrong"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "pending_confirmation")
        rollback.assert_called_once()

    def test_proxy_rollback_no_journal_returns_404(self):
        with patch(
            "netfix.api.residential_proxy.rollback_last_proxy_apply",
            return_value={"ok": False, "status": "no_journal", "error": "no proxy apply journal found"},
        ):
            data = self._post_json_error(
                "/proxy/profiles/rollback",
                {"confirmed": True, "confirmation": "ROLLBACK_PROXY_PROFILE"},
                404,
            )
        self.assertFalse(data["ok"])
        self.assertEqual(data["status"], "no_journal")

    def test_run_async_and_get_job(self):
        data = self._post_json(
            "/run", {"command": ["codex"], "timeout": 5, "async": True}
        )
        self.assertTrue(data.get("ok"))
        job_id = data["job_id"]
        self.assertIsInstance(job_id, str)

        deadline = time.time() + 30
        while time.time() < deadline:
            job = self._get(f"/jobs/{job_id}")
            self.assertIn("status", job)
            if job["status"] == "done":
                self.assertIn("result", job)
                return
            time.sleep(0.2)
        self.fail("async job did not finish in time")

    def test_run_async_job_can_be_cancelled(self):
        with patch("netfix.api.start_job", return_value="cancel-me") as start, \
                patch("netfix.api.cancel_job", return_value={
                    "status": "cancelled",
                    "ok": False,
                    "error": "job cancelled",
                    "finished_at": "2026-01-01T00:00:00+00:00",
                }) as cancel:
            started = self._post_json("/run", {"command": ["codex"], "timeout": 30, "async": True})
            missing_token = self._post_json_error_with_headers("/jobs/cancel-me/cancel", {}, {}, 403)
            cancelled = self._post_json("/jobs/cancel-me/cancel", {})

        self.assertTrue(started["ok"])
        self.assertEqual(started["job_id"], "cancel-me")
        self.assertFalse(missing_token["ok"])
        self.assertTrue(cancelled["ok"])
        self.assertEqual(cancelled["status"], "cancelled")
        start.assert_called_once()
        cancel.assert_called_once_with("cancel-me")

    def test_report_latest_404_when_missing(self):
        # Ensure the report file is absent for this test.
        report_path = Path.home() / ".netfix" / "last_report.json"
        existed = report_path.exists()
        if existed:
            backup = report_path.read_bytes()
            report_path.unlink()
        try:
            with self.assertRaises(HTTPError) as ctx:
                self._get("/report/latest")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            if existed:
                report_path.write_bytes(backup)

    def test_logs_clear_removes_local_report_and_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "last_report.json"
            events = root / "events.jsonl"
            report.write_text("{}", encoding="utf-8")
            events.write_text('{"timestamp":"2026-06-24T00:00:00+00:00"}\n', encoding="utf-8")
            with patch("netfix.logs.JOURNAL_DIR", root), \
                    patch("netfix.logs.LATEST_REPORT", report), \
                    patch("netfix.logs.EVENTS_FILE", events):
                data = self._post_json("/logs/clear", {"latest_report": True, "events": True})
            self.assertTrue(data["ok"])
            self.assertFalse(report.exists())
            self.assertFalse(events.exists())

    def test_logs_endpoint_returns_renderable_empty_state_without_report_or_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "last_report.json"
            events = root / "events.jsonl"
            with patch("netfix.logs.JOURNAL_DIR", root), \
                    patch("netfix.logs.LATEST_REPORT", report), \
                    patch("netfix.logs.EVENTS_FILE", events):
                data = self._get("/logs")

        self.assertTrue(data["ok"])
        self.assertEqual(data["journal_dir"], str(root))
        self.assertFalse(data["latest_report_exists"])
        self.assertFalse(data["events_exists"])
        self.assertEqual(data["latest_report_summary"], {})
        self.assertEqual(data["events"], [])

    def test_support_bundle_requires_token_and_redacts_report_and_events(self):
        missing_token = self._get_error("/support/bundle", 403)
        self.assertFalse(missing_token["ok"])

        report = {
            "meta": {"timestamp": "2026-07-01T00:00:00+00:00", "hostname": "author-mac"},
            "environment": {
                "system_proxy": "http://demo-user:demo-password@proxy.example.com:8000",
                "active_profile": {"name": "work", "host": "proxy.example.com", "password": "demo-password"},
                "profiles": [{"name": "work", "host": "proxy.example.com"}],
            },
            "diagnostics": [
                {"name": "proxy", "error": "failed with sk-live-secret-token-1234567890"},
            ],
            "root_causes": [{"id": "proxy-auth", "description": "代理认证失败 demo-password"}],
            "explanation": {"headline": "代理认证失败"},
            "fixes": [{"id": "replace_proxy_credentials", "tier": 2}],
        }
        events = {
            "events": [
                {
                    "timestamp": "2026-07-01T00:01:00+00:00",
                    "headline": "重试失败 demo-password",
                    "root_cause": "bad API key sk-live-secret-token-1234567890",
                }
            ]
        }
        with patch("netfix.api._load_latest_report", return_value=(200, report)), \
                patch("netfix.api.logs.load_events", return_value=events), \
                patch("netfix.api.logs.load_logs", return_value={
                    "ok": True,
                    "latest_report_exists": True,
                    "events_exists": True,
                    "latest_report_path": "/Users/someone/.netfix/last_report.json",
                    "events_path": "/Users/someone/.netfix/events.jsonl",
                    "journal_dir": "/Users/someone/.netfix",
                    "privacy": {"log_retention_days": 7},
                }), \
                patch("netfix.api._environment_summary", return_value={
                    "ok": True,
                    "system_proxy": "socks5://demo-user:demo-password@proxy.example.com:1080",
                }):
            data = self._get("/support/bundle")

        self.assertTrue(data["ok"])
        self.assertEqual(data["schema_version"], "netfix_support_bundle.v1")
        self.assertTrue(data["latest_report"]["exists"])
        self.assertIn("redacted_report_hash", data["latest_report"])
        self.assertEqual(data["events"]["count"], 1)
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("demo-password", encoded)
        self.assertNotIn("sk-live-secret-token", encoded)
        self.assertNotIn("/Users/someone", encoded)
        self.assertIn("support_text", data)
        self.assertIn("代理认证失败", data["support_text"])

    def test_logs_prune_removes_expired_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.jsonl"
            events.write_text(
                "\n".join([
                    '{"timestamp":"2020-01-01T00:00:00+00:00","status":"fail"}',
                    '{"timestamp":"2999-01-01T00:00:00+00:00","status":"ok"}',
                ]) + "\n",
                encoding="utf-8",
            )
            with patch("netfix.logs.JOURNAL_DIR", root), \
                    patch("netfix.logs.EVENTS_FILE", events):
                data = self._post_json("/logs/prune", {"retention_days": 7})
            self.assertTrue(data["ok"])
            self.assertEqual(data["removed"], 1)
            self.assertEqual(data["kept"], 1)
            self.assertIn("2999", events.read_text(encoding="utf-8"))

    def test_privacy_settings_endpoint_applies_retention(self):
        with patch("netfix.api.settings.update_privacy_settings", return_value={"log_retention_days": 3, "persist_proxy_identity_report": False}), \
                patch("netfix.api.logs.apply_retention_policy", return_value={"ok": True, "removed": 0}) as prune:
            data = self._post_json("/settings/privacy", {"log_retention_days": 3, "persist_proxy_identity_report": False})
        self.assertTrue(data["ok"])
        self.assertEqual(data["settings"]["log_retention_days"], 3)
        self.assertFalse(data["settings"]["persist_proxy_identity_report"])
        prune.assert_called_once()

    def test_data_clear_requires_confirmation_phrase(self):
        data = self._post_json_error("/data/clear", {"confirm": "wrong"}, 400)
        self.assertFalse(data["ok"])
        self.assertIn("DELETE_NETFIX_LOCAL_DATA", data["error"])

    def test_data_clear_removes_logs_settings_and_known_keychain_items(self):
        with patch("netfix.api.settings.load_settings", return_value={"llm": {"api_key_account": "deepseek"}, "proxy_profiles": []}) as load, \
                patch("netfix.api.logs.clear_logs", return_value={"ok": True, "removed": ["report"], "errors": {}}) as clear_logs, \
                patch("netfix.api.settings.clear_settings", return_value={"ok": True, "removed": ["settings"]}) as clear_settings, \
                patch("netfix.api.keychain.delete_known_netfix_secrets", return_value={"ok": True, "deleted": [], "missing": [], "errors": {}}) as clear_keychain, \
                patch("netfix.api.llm_budget.clear_persistent_ledger", return_value={"ok": True, "removed": ["llm_budget_journal"]}) as clear_budget:
            data = self._post_json("/data/clear", {"confirm": "DELETE_NETFIX_LOCAL_DATA"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["llm_budget"]["removed"], ["llm_budget_journal"])
        load.assert_called_once()
        clear_logs.assert_called_once()
        clear_settings.assert_called_once()
        clear_keychain.assert_called_once()
        clear_budget.assert_called_once()


if __name__ == "__main__":
    unittest.main()
