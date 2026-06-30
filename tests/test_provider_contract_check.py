import json
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock, patch

from netfix.llm_provider import LLMProviderError, OpenAICompatibleProvider, list_providers, parse_chat_completion_json_content
from scripts.provider_contract_check import run


class TestProviderContractCheck(unittest.TestCase):
    def test_provider_contract_check_passes(self):
        result = run()
        self.assertTrue(result["ok"], result.get("findings"))
        self.assertEqual(result["provider_ids"][:4], ["deepseek", "moonshot_kimi", "minimax", "qwen"])

    def test_domestic_provider_presets_record_official_doc_evidence(self):
        providers = {provider["id"]: provider for provider in list_providers()}
        for provider_id in ("deepseek", "moonshot_kimi", "minimax", "qwen"):
            with self.subTest(provider=provider_id):
                provider = providers[provider_id]
                self.assertEqual(provider["metadata_checked_at"], "2026-06-25")
                self.assertTrue(provider["official_docs"])
                self.assertTrue(all(url.startswith("https://") for url in provider["official_docs"]))

    def test_minimax_payload_uses_current_completion_token_field(self):
        provider = OpenAICompatibleProvider("https://api.minimaxi.com/v1", "k", "MiniMax-M3", provider_id="minimax")
        payload = provider._build_payload([{"role": "user", "content": "{}"}], 256, 1.0)
        self.assertEqual(payload["max_completion_tokens"], 256)
        self.assertNotIn("max_tokens", payload)

    def test_provider_contract_rejects_non_product_capability_names(self):
        provider = {
            "id": "bad",
            "label": "Bad",
            "base_url": "https://api.example.com/v1",
            "model": "bad-model",
            "market": "domestic",
            "openai_compatible": True,
            "supports_json_mode": True,
            "supports_vision": False,
            "capabilities": ["text", "tool_call"],
            "text_priority": 99,
            "system_prompt": "Return JSON.",
            "default_max_tokens": 128,
        }

        from scripts.provider_contract_check import check_provider

        findings = check_provider(provider)
        self.assertIn("capabilities", {item["kind"] for item in findings})

    def test_parse_chat_completion_json_content(self):
        raw = json.dumps({
            "choices": [
                {"message": {"content": json.dumps({"headline": "ok"})}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "nested": {"ignored": True}},
        })
        parsed = parse_chat_completion_json_content(raw)
        self.assertEqual(parsed["headline"], "ok")
        self.assertEqual(parsed["__netfix_usage"], {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13})

    def test_parse_chat_completion_accepts_fenced_json(self):
        raw = json.dumps({
            "choices": [
                {"message": {"content": "```json\n{\"headline\":\"ok\"}\n```"}}
            ]
        })
        self.assertEqual(parse_chat_completion_json_content(raw)["headline"], "ok")

    def test_parse_chat_completion_accepts_embedded_json(self):
        raw = json.dumps({
            "choices": [
                {"message": {"content": "好的，结果如下：\n{\"headline\":\"ok\"}\n请查收。"}}
            ]
        })
        self.assertEqual(parse_chat_completion_json_content(raw)["headline"], "ok")

    def test_parse_chat_completion_rejects_non_json_content(self):
        raw = json.dumps({"choices": [{"message": {"content": "plain text"}}]})
        with self.assertRaises(LLMProviderError) as ctx:
            parse_chat_completion_json_content(raw)
        self.assertEqual(ctx.exception.reason_code, "invalid_json_response")

    def test_provider_error_classifies_rate_limit(self):
        response = Mock()
        response.read.return_value = b'{"error":{"message":"rate limit"}}'
        err = HTTPError("https://api.example.com/chat/completions", 429, "Too Many Requests", {}, response)
        with patch("netfix.llm_provider.urllib.request.urlopen", side_effect=err):
            provider = OpenAICompatibleProvider("https://api.deepseek.com", "k", "m", provider_id="deepseek")
            with self.assertRaises(LLMProviderError) as ctx:
                provider.complete_json([{"role": "user", "content": "{}"}])
        self.assertEqual(ctx.exception.reason_code, "rate_limited")
        self.assertEqual(ctx.exception.http_status, 429)

    def test_provider_error_classifies_domestic_chinese_error_messages(self):
        cases = [
            (400, "请求过于频繁，请稍后重试", "rate_limited"),
            (400, "账户余额不足，请充值后继续使用", "quota_or_billing"),
            (400, "鉴权失败，API Key 无效", "auth_failed"),
            (400, "模型不存在或无访问权限", "model_not_found"),
        ]
        for status, message, reason in cases:
            with self.subTest(message=message):
                response = Mock()
                response.read.return_value = json.dumps({"error": {"message": message}}).encode("utf-8")
                err = HTTPError("https://api.example.com/chat/completions", status, "Bad Request", {}, response)
                with patch("netfix.llm_provider.urllib.request.urlopen", side_effect=err):
                    provider = OpenAICompatibleProvider("https://api.deepseek.com", "k", "m", provider_id="deepseek")
                    with self.assertRaises(LLMProviderError) as ctx:
                        provider.complete_json([{"role": "user", "content": "{}"}])
                self.assertEqual(ctx.exception.reason_code, reason)

    def test_provider_error_message_redacts_tokens_and_image_payloads(self):
        response = Mock()
        response.read.return_value = json.dumps({
            "error": {
                "message": "bad request",
                "api_key": "sk-" + "a" * 48,
                "image": "data:image/png;base64," + "A" * 80,
                "email": "owner@example.com",
            }
        }).encode("utf-8")
        err = HTTPError("https://api.example.com/chat/completions", 400, "Bad Request", {}, response)
        with patch("netfix.llm_provider.urllib.request.urlopen", side_effect=err):
            provider = OpenAICompatibleProvider("https://api.deepseek.com", "sk-" + "b" * 48, "m", provider_id="deepseek")
            with self.assertRaises(LLMProviderError) as ctx:
                provider.complete_json([{"role": "user", "content": "{}"}])
        message = str(ctx.exception)
        self.assertNotIn("sk-" + "a" * 48, message)
        self.assertNotIn("data:image/png;base64," + "A" * 80, message)
        self.assertNotIn("owner@example.com", message)
        self.assertIn("[redacted_email]", message)


if __name__ == "__main__":
    unittest.main()
