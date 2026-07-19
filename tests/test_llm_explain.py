import unittest
import base64
import struct
import zlib
from unittest.mock import patch

from netfix import llm_explain as llm_explain_module
from netfix.llm_explain import explain_with_llm, sanitize_llm_response
from netfix.llm_provider import LLMProviderError, OpenAICompatibleProvider, list_providers, provider_candidates


SAMPLE_REPORT = {
    "meta": {"version": "0.2.0", "hostname": "alice-mac"},
    "diagnostics": [{"name": "proxy_auth_check", "status": "fail"}],
    "root_causes": [{"id": "proxy-auth", "description": "代理认证失败"}],
    "fixes": [{"id": "flush-dns-cache", "tier": 1}],
    "explanation": {
        "headline": "代理认证失败",
        "severity": "fail",
        "explanation": "本地规则解释",
        "actions": [{"id": "flush-dns-cache", "tier": 1, "needs_confirm": False}],
    },
}


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_data_url_with_text_metadata(secret: str) -> str:
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00")
        + _png_chunk(b"tEXt", f"comment={secret}".encode("utf-8"))
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + _png_chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def png_data_url() -> str:
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00")
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + _png_chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def malformed_png_data_url_with_text_metadata(secret: str) -> str:
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00")
        + _png_chunk(b"tEXt", f"comment={secret}".encode("utf-8"))
        + struct.pack(">I", 100)
        + b"IDAT"
        + b"too-short"
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _webp_chunk(kind: bytes, data: bytes) -> bytes:
    pad = b"\x00" if len(data) % 2 else b""
    return kind + struct.pack("<I", len(data)) + data + pad


def webp_data_url_with_exif_metadata(secret: str) -> str:
    chunks = (
        _webp_chunk(b"EXIF", f"proxy={secret}".encode("utf-8"))
        + _webp_chunk(b"VP8 ", b"\x00\x00\x00\x00\x00\x00\x00\x00")
    )
    webp = b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WEBP" + chunks
    return "data:image/webp;base64," + base64.b64encode(webp).decode("ascii")


def gif_data_url_with_comment_metadata(secret: str) -> str:
    comment = f"proxy={secret}".encode("utf-8")
    gif = (
        b"GIF89a"
        + b"\x01\x00\x01\x00\x00\x00\x00"
        + b"\x21\xfe"
        + bytes([len(comment)])
        + comment
        + b"\x00"
        + b"\x3b"
    )
    return "data:image/gif;base64," + base64.b64encode(gif).decode("ascii")


class TestLLMExplain(unittest.TestCase):
    def setUp(self):
        reset = getattr(llm_explain_module, "reset_llm_budget_state", None)
        if reset:
            reset()

    def test_domestic_providers_are_prioritized(self):
        providers = list_providers()
        ids = [item["id"] for item in providers[:4]]
        self.assertEqual(ids, ["deepseek", "moonshot_kimi", "minimax", "qwen"])
        self.assertFalse(providers[0]["supports_vision"])
        self.assertTrue(providers[1]["supports_vision"])
        self.assertEqual(providers[1]["base_url"], "https://api.moonshot.cn/v1")
        self.assertEqual(providers[1]["image_question_status"], "openai_compatible_image_url_ready")
        self.assertEqual(providers[2]["base_url"], "https://api.minimaxi.com/v1")
        self.assertEqual(providers[2]["image_question_status"], "openai_compatible_image_url_ready")
        self.assertIn("json", providers[0]["capabilities"])
        self.assertEqual(providers[0]["netfix_role"], "primary_text")
        self.assertEqual(providers[0]["image_question_status"], "unsupported_provider_no_vision")

    def test_chat_url_accepts_v1_or_plain_base_url(self):
        deepseek = OpenAICompatibleProvider("https://api.deepseek.com", "k", "m")
        kimi = OpenAICompatibleProvider("https://api.moonshot.ai/v1", "k", "m")
        self.assertEqual(deepseek._chat_completions_url(), "https://api.deepseek.com/chat/completions")
        self.assertEqual(kimi._chat_completions_url(), "https://api.moonshot.ai/v1/chat/completions")

    def test_provider_payload_uses_json_mode_when_supported(self):
        deepseek = OpenAICompatibleProvider("https://api.deepseek.com", "k", "m", provider_id="deepseek")
        kimi = OpenAICompatibleProvider("https://api.moonshot.cn/v1", "k", "m", provider_id="moonshot_kimi")
        openai = OpenAICompatibleProvider("https://api.openai.com/v1", "k", "m", provider_id="openai")
        deepseek_payload = deepseek._build_payload([{"role": "user", "content": "{}"}], 64, 0)
        kimi_payload = kimi._build_payload([{"role": "user", "content": "{}"}], 64, 0)
        openai_payload = openai._build_payload([{"role": "user", "content": "{}"}], 64, 0)
        self.assertNotIn("store", deepseek_payload)
        self.assertIn("response_format", deepseek_payload)
        self.assertIn("response_format", kimi_payload)
        self.assertNotIn("temperature", kimi_payload)
        self.assertEqual(openai_payload["store"], False)
        self.assertIn("response_format", openai_payload)

    def test_upload_consent_never_forces_local_fallback(self):
        settings = {"llm": {"enabled": True, "provider": "deepseek", "upload_consent": "never"}}
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "upload_consent_never")
        complete.assert_not_called()

    def test_saved_strict_redaction_cannot_be_downgraded_by_request(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "redaction_level": "strict",
                "fallback": {"enabled": False},
            }
        }
        report = dict(SAMPLE_REPORT)
        report["environment"] = {
            "profiles": [{"id": "private-profile", "host": "proxy.example.com"}],
            "active_profile": {"id": "private-profile"},
        }
        seen = {}

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen["messages"] = messages
            return {"headline": "ok", "severity": "ok", "explanation": "done", "actions": []}

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            explain_with_llm(
                report,
                redaction_level="balanced",
                upload_confirmed=True,
            )

        payload = seen["messages"][1]["content"]
        self.assertIn('"profiles": []', payload)
        self.assertIn('"active_profile": null', payload)
        self.assertNotIn("private-profile", payload)

    def test_question_text_is_redacted_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "fallback": {"enabled": False},
            }
        }
        seen = {}

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen["messages"] = messages
            return {"headline": "ok", "severity": "ok", "explanation": "done", "actions": []}

        question = "联系 alice@example.com，目标 203.0.113.10，token sk-live-secret-token-1234567890"
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            explain_with_llm(SAMPLE_REPORT, question=question, upload_confirmed=True)

        payload = seen["messages"][1]["content"]
        self.assertNotIn("alice@example.com", payload)
        self.assertNotIn("203.0.113.10", payload)
        self.assertNotIn("sk-live-secret-token", payload)
        self.assertIn("[redacted_email]", payload)

    def test_invalid_json_response_retries_once_with_doubled_max_tokens(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "fallback": {"enabled": False},
            }
        }
        seen_tokens = []

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen_tokens.append(max_tokens)
            if len(seen_tokens) == 1:
                raise LLMProviderError("truncated", reason_code="invalid_json_response")
            return {"headline": "ok", "severity": "ok", "explanation": "done", "actions": []}

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)

        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["provider_used"], "deepseek")
        self.assertEqual(seen_tokens, [900, 1800])

    def test_invalid_json_response_twice_falls_back_without_more_retries(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "fallback": {"enabled": False},
            }
        }
        seen_tokens = []

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen_tokens.append(max_tokens)
            raise LLMProviderError("truncated", reason_code="invalid_json_response")

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "provider_error: invalid_json_response")
        self.assertEqual(seen_tokens, [900, 1800])

    def test_other_provider_errors_do_not_retry(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "fallback": {"enabled": False},
            }
        }
        calls = []

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            calls.append(max_tokens)
            raise LLMProviderError("boom", reason_code="timeout")

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "provider_error: timeout")
        self.assertEqual(calls, [900])

    def test_provider_candidates_use_text_and_vision_priority(self):
        text_ids = [item["id"] for item in provider_candidates(mode="explain")]
        vision_ids = [item["id"] for item in provider_candidates(mode="image_question")]
        self.assertEqual(text_ids[:4], ["deepseek", "moonshot_kimi", "minimax", "qwen"])
        self.assertEqual(vision_ids[:3], ["minimax", "moonshot_kimi", "qwen"])

    def test_image_question_is_disabled_until_feature_flag_is_enabled(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "moonshot_kimi",
                "upload_consent": "always",
                "features": {"image_question": False},
            }
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=["data:image/png;base64,AAAA"],
            )
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "image_question_disabled")
        self.assertIn("启用图片问诊", result["fallback_reason_label"])
        self.assertIn("Qwen", result["fallback_reason_label"])
        complete.assert_not_called()

    def test_image_question_requires_explicit_confirmation_even_when_upload_always(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "moonshot_kimi",
                "upload_consent": "always",
                "features": {"image_question": True},
            }
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=False,
                image_inputs=[png_data_url()],
            )
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "upload_consent_required")
        self.assertTrue(result["needs_upload_confirmation"])
        complete.assert_not_called()

    def test_image_question_routes_deepseek_default_to_domestic_vision_fallback(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "ask_each_time",
                "features": {"image_question": True},
                "fallback": {
                    "enabled": True,
                    "domestic_only": True,
                    "vision_chain": ["minimax", "moonshot_kimi"],
                },
            }
        }
        payload = {
            "headline": "图片里的代理配置需要认证",
            "severity": "warn",
            "explanation": "done",
            "actions": [],
            "manual_steps": [],
        }
        seen = {}

        def fake_secret(_service, account, **_kwargs):
            return {"minimax": "vision-key"}.get(account)

        def fake_complete(self, messages, max_tokens=900, temperature=0.2):
            seen["provider"] = self.provider_id
            seen["messages"] = messages
            return payload

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", side_effect=fake_secret), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[{"data_url": png_data_url()}],
            )

        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["provider_used"], "minimax")
        self.assertEqual(seen["provider"], "minimax")
        user_content = seen["messages"][1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")

    def test_image_question_uses_qwen_vl_model_without_changing_text_model(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "ask_each_time",
                "features": {"image_question": True},
                "fallback": {
                    "enabled": True,
                    "domestic_only": True,
                    "vision_chain": ["qwen"],
                },
            }
        }
        seen = {}

        def fake_secret(_service, account, **_kwargs):
            return {"qwen": "vision-key"}.get(account)

        def fake_complete(self, messages, max_tokens=900, temperature=0.2):
            seen["provider"] = self.provider_id
            seen["model"] = self.model
            seen["messages"] = messages
            return {
                "headline": "Qwen image smoke ok",
                "severity": "ok",
                "explanation": "done",
                "actions": [],
                "manual_steps": [],
            }

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", side_effect=fake_secret), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[{"data_url": png_data_url()}],
            )

        qwen = next(item for item in list_providers() if item["id"] == "qwen")
        self.assertEqual(qwen["model"], "qwen-plus")
        self.assertEqual(qwen["vision_model"], "qwen-vl-plus")
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["provider_used"], "qwen")
        self.assertEqual(seen["provider"], "qwen")
        self.assertEqual(seen["model"], "qwen-vl-plus")
        user_content = seen["messages"][1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertTrue(user_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_image_question_strips_png_text_metadata_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "minimax",
                "base_url": "https://api.minimaxi.com/v1",
                "model": "MiniMax-M3",
                "api_key_account": "minimax",
                "upload_consent": "always",
                "features": {"image_question": True},
                "fallback": {"enabled": False},
            }
        }
        secret = "http://user:secret-pass@proxy.example.com:8000?token=abcdef1234567890abcdef"
        payload = {"headline": "ok", "severity": "ok", "explanation": "done", "actions": [], "manual_steps": []}
        seen = {}

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen["messages"] = messages
            return payload

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="vision-key"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[png_data_url_with_text_metadata(secret)],
            )

        encoded_messages = str(seen["messages"])
        self.assertNotIn("secret-pass", encoded_messages)
        self.assertNotIn("proxy.example.com", encoded_messages)
        provider_image_url = seen["messages"][1]["content"][1]["image_url"]["url"]
        provider_png = base64.b64decode(provider_image_url.split(",", 1)[1])
        self.assertNotIn(b"tEXt", provider_png)
        self.assertNotIn(b"secret-pass", provider_png)
        self.assertIn("image_redaction_audit", result)
        self.assertEqual(result["image_redaction_audit"]["images"], 1)
        self.assertGreaterEqual(result["image_redaction_audit"]["metadata_stripped"], 1)

    def test_image_question_uppercase_base64_still_strips_png_metadata_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "minimax",
                "base_url": "https://api.minimaxi.com/v1",
                "model": "MiniMax-M3",
                "api_key_account": "minimax",
                "upload_consent": "always",
                "features": {"image_question": True},
                "fallback": {"enabled": False},
            }
        }
        secret = "secret-pass"
        payload = {"headline": "ok", "severity": "ok", "explanation": "done", "actions": [], "manual_steps": []}
        seen = {}

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen["messages"] = messages
            return payload

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="vision-key"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[png_data_url_with_text_metadata(secret).replace(";base64,", ";BASE64,")],
            )

        provider_image_url = seen["messages"][1]["content"][1]["image_url"]["url"]
        self.assertTrue(provider_image_url.startswith("data:image/png;base64,"))
        provider_png = base64.b64decode(provider_image_url.split(",", 1)[1])
        self.assertNotIn(b"tEXt", provider_png)
        self.assertNotIn(secret.encode("utf-8"), provider_png)
        self.assertGreaterEqual(result["image_redaction_audit"]["metadata_stripped"], 1)

    def test_image_question_rejects_declared_mime_mismatch_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "minimax",
                "base_url": "https://api.minimaxi.com/v1",
                "model": "MiniMax-M3",
                "api_key_account": "minimax",
                "upload_consent": "always",
                "features": {"image_question": True},
                "fallback": {"enabled": False},
            }
        }
        disguised_png = png_data_url_with_text_metadata("secret-pass").replace("data:image/png", "data:image/gif", 1)
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="vision-key"), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[disguised_png],
            )
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "image_input_missing")
        complete.assert_not_called()

    def test_image_question_rejects_malformed_png_instead_of_resending_metadata(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "minimax",
                "base_url": "https://api.minimaxi.com/v1",
                "model": "MiniMax-M3",
                "api_key_account": "minimax",
                "upload_consent": "always",
                "features": {"image_question": True},
                "fallback": {"enabled": False},
            }
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="vision-key"), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[malformed_png_data_url_with_text_metadata("secret-pass")],
            )
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "image_input_missing")
        complete.assert_not_called()

    def test_image_question_strips_webp_and_gif_metadata_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "minimax",
                "base_url": "https://api.minimaxi.com/v1",
                "model": "MiniMax-M3",
                "api_key_account": "minimax",
                "upload_consent": "always",
                "features": {"image_question": True},
                "fallback": {"enabled": False},
            }
        }
        secret = "secret-pass"
        payload = {"headline": "ok", "severity": "ok", "explanation": "done", "actions": [], "manual_steps": []}
        seen = {}

        def fake_complete(_self, messages, max_tokens=900, temperature=0.2):
            seen["messages"] = messages
            return payload

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="vision-key"), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=[
                    webp_data_url_with_exif_metadata(secret),
                    gif_data_url_with_comment_metadata(secret),
                ],
            )

        image_parts = seen["messages"][1]["content"][1:]
        self.assertEqual(len(image_parts), 2)
        for part in image_parts:
            provider_image = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
            self.assertNotIn(secret.encode("utf-8"), provider_image)
        self.assertGreaterEqual(result["image_redaction_audit"]["metadata_stripped"], 2)

    def test_image_question_requires_inline_image_input(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "moonshot_kimi",
                "upload_consent": "always",
                "features": {"image_question": True},
            }
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(SAMPLE_REPORT, mode="image_question", upload_confirmed=True)
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "image_input_missing")
        complete.assert_not_called()

    def test_image_question_rejects_unsupported_image_mime_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "moonshot_kimi",
                "upload_consent": "always",
                "features": {"image_question": True},
            }
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="vision-key"), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(
                SAMPLE_REPORT,
                mode="image_question",
                upload_confirmed=True,
                image_inputs=["data:image/heic;base64,AAAA"],
            )
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "image_unsupported_format")
        self.assertIn("PNG、JPEG、WebP 或 GIF", result["fallback_reason_label"])
        complete.assert_not_called()

    def test_disabled_llm_falls_back_to_local_explain(self):
        with patch("netfix.llm_explain.load_settings", return_value={"llm": {"enabled": False}}):
            result = explain_with_llm(SAMPLE_REPORT)
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "llm_disabled")
        self.assertIn("redaction_audit", result)

    def test_ask_each_time_requires_explicit_upload_confirmation(self):
        settings = {"llm": {"enabled": True, "provider": "deepseek", "upload_consent": "ask_each_time"}}
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(SAMPLE_REPORT)
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "upload_consent_required")
        self.assertTrue(result["needs_upload_confirmation"])
        complete.assert_not_called()

    def test_confirmed_upload_uses_fallback_chain(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "ask_each_time",
                "fallback": {"enabled": True, "domestic_only": True, "chain": ["deepseek", "qwen"]},
            }
        }
        payload = {
            "headline": "ok",
            "severity": "ok",
            "explanation": "done",
            "actions": [],
            "manual_steps": [],
        }

        def fake_secret(_service, account, **_kwargs):
            return {"deepseek": "k1", "qwen": "k2"}.get(account)

        def fake_complete(self, messages, max_tokens=900, temperature=0.2):
            if self.provider_id == "deepseek":
                raise LLMProviderError("rate limited", reason_code="rate_limited", provider_id="deepseek")
            return payload

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", side_effect=fake_secret), \
                patch.object(OpenAICompatibleProvider, "complete_json", fake_complete):
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["provider_used"], "qwen")
        self.assertEqual([item["status"] for item in result["fallback_chain"]], ["failed", "ok"])
        self.assertEqual(result["fallback_chain"][0]["reason_code"], "rate_limited")

    def test_local_budget_blocks_cloud_request_before_provider_call(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "budget": {"enabled": True, "max_requests_per_hour": 0},
            }
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["fallback_reason"], "provider_error: local_budget_exceeded")
        self.assertEqual(result["fallback_chain"][0]["status"], "skipped")
        self.assertEqual(result["fallback_chain"][0]["reason_code"], "local_budget_exceeded")
        complete.assert_not_called()

    def test_rate_limited_provider_enters_local_cooldown(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
                "fallback": {"enabled": False},
                "budget": {"enabled": True, "cooldown_seconds_after_rate_limit": 300},
            }
        }

        def rate_limited(_self, messages, max_tokens=900, temperature=0.2):
            raise LLMProviderError("rate limited", reason_code="rate_limited", provider_id="deepseek")

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", rate_limited):
            first = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)
        self.assertEqual(first["fallback_chain"][0]["reason_code"], "rate_limited")

        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json") as complete:
            second = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)
        self.assertEqual(second["fallback_chain"][0]["status"], "skipped")
        self.assertEqual(second["fallback_chain"][0]["reason_code"], "provider_cooldown")
        complete.assert_not_called()

    def test_provider_usage_summary_is_returned_without_raw_payload(self):
        settings = {
            "llm": {
                "enabled": True,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "upload_consent": "always",
            }
        }
        payload = {
            "headline": "ok",
            "severity": "ok",
            "explanation": "done",
            "actions": [],
            "manual_steps": [],
            "__netfix_usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125, "details": {"ignored": True}},
        }
        with patch("netfix.llm_explain.load_settings", return_value=settings), \
                patch("netfix.llm_explain.keychain.get_secret", return_value="k"), \
                patch.object(OpenAICompatibleProvider, "complete_json", return_value=payload):
            result = explain_with_llm(SAMPLE_REPORT, upload_confirmed=True)
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["provider_usage"], {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125})
        self.assertEqual(result["fallback_chain"][-1]["usage"], result["provider_usage"])
        self.assertNotIn("__netfix_usage", str(result))

    def test_sanitize_drops_unknown_actions_and_commands(self):
        raw = {
            "severity": "fail",
            "headline": "h",
            "explanation": "e",
            "actions": [
                {"id": "flush-dns-cache", "tier": 1, "needs_confirm": False},
                {"id": "rm-rf", "tier": 1, "needs_confirm": False},
            ],
            "command": "rm -rf /",
        }
        result = sanitize_llm_response(raw, SAMPLE_REPORT)
        self.assertEqual([a["id"] for a in result["actions"]], ["flush-dns-cache"])
        self.assertNotIn("command", result)

    def test_sanitize_uses_local_action_tier_not_llm_claim(self):
        report = {
            "fixes": [{"id": "reset-system-proxy", "label": "重置系统代理", "tier": 2, "needs_confirm": True}],
            "explanation": {"actions": []},
        }
        raw = {
            "severity": "warn",
            "headline": "h",
            "explanation": "e",
            "actions": [{"id": "reset-system-proxy", "label": "一键修复", "tier": 1, "needs_confirm": False}],
        }
        result = sanitize_llm_response(raw, report)
        self.assertEqual(result["actions"][0]["tier"], 2)
        self.assertTrue(result["actions"][0]["needs_confirm"])
        self.assertEqual(result["actions"][0]["label"], "重置系统代理")

    def test_sanitize_redacts_provider_output(self):
        raw = {
            "severity": "warn",
            "headline": "proxy 203.0.113.10",
            "explanation": "see http://user:secret-pass@203.0.113.10:8000?token=abcdef1234567890abcdef123456",
            "evidence": [{"why": "email alice@example.com token abcdef1234567890abcdef123456"}],
            "manual_steps": [{"steps": ["connect to 203.0.113.10"]}],
            "actions": [],
        }
        result = sanitize_llm_response(raw, SAMPLE_REPORT)
        encoded = str(result)
        self.assertNotIn("203.0.113.10", encoded)
        self.assertNotIn("secret-pass", encoded)
        self.assertNotIn("alice@example.com", encoded)


if __name__ == "__main__":
    unittest.main()
