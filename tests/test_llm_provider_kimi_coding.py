import json
import threading
import time
import unittest
from http.server import HTTPServer
from unittest.mock import patch
from urllib.request import Request, urlopen

from netfix import api
from netfix.llm_provider import OpenAICompatibleProvider, get_provider, list_providers, provider_candidates


FAKE_KIMI_CODING_KEY = "sk-kimi-test-placeholder-key"


class TestKimiCodingPreset(unittest.TestCase):
    def test_kimi_coding_preset_contract(self):
        preset = get_provider("kimi_coding")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["label"], "Kimi 编程版")
        self.assertEqual(preset["base_url"], "https://api.kimi.com/coding/v1")
        self.assertEqual(preset["model"], "kimi-for-coding")
        self.assertTrue(preset["openai_compatible"])
        self.assertTrue(preset["supports_json_mode"])
        self.assertFalse(preset["supports_vision"])
        self.assertEqual(preset["temperature_policy"], "omit")
        self.assertIsNone(preset["default_temperature"])
        self.assertNotIn("extra_payload", preset)
        self.assertEqual(preset["market"], "domestic")
        self.assertGreaterEqual(preset["text_priority"], 50)
        self.assertEqual(preset["metadata_checked_at"], "2026-06-25")
        self.assertTrue(preset["official_docs"])
        self.assertTrue(all(url.startswith("https://") for url in preset["official_docs"]))
        self.assertIn("sk-kimi-", preset["notes"])
        self.assertIn("不通用", preset["notes"])

    def test_kimi_coding_is_fifth_preset_after_qwen(self):
        ids = [item["id"] for item in list_providers()]
        self.assertEqual(ids[:5], ["deepseek", "moonshot_kimi", "minimax", "qwen", "kimi_coding"])

    def test_kimi_coding_payload_omits_temperature_and_uses_json_mode(self):
        client = OpenAICompatibleProvider("https://api.kimi.com/coding/v1", "k", "kimi-for-coding", provider_id="kimi_coding")
        payload = client._build_payload([{"role": "user", "content": "{}"}], 64, 0)
        self.assertNotIn("temperature", payload)
        self.assertIn("response_format", payload)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_tokens"], 64)
        self.assertNotIn("store", payload)
        self.assertNotIn("thinking", payload)
        self.assertEqual(client._chat_completions_url(), "https://api.kimi.com/coding/v1/chat/completions")

    def test_kimi_coding_stays_out_of_top_text_candidates(self):
        text_ids = [item["id"] for item in provider_candidates(mode="explain")]
        self.assertEqual(text_ids[:4], ["deepseek", "moonshot_kimi", "minimax", "qwen"])
        self.assertIn("kimi_coding", text_ids)


class TestKimiCodingKeyPrefixWarning(unittest.TestCase):
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

    def _save_llm_settings(self, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base}/settings/llm",
            data=data,
            headers={"Content-Type": "application/json", "X-Netfix-Token": api._API_TOKEN},
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_sk_kimi_key_with_moonshot_provider_returns_non_blocking_warning(self):
        with patch("netfix.api.keychain.set_secret", return_value={"ok": True}) as set_secret, \
                patch("netfix.api.settings.update_llm_settings", return_value={}):
            data = self._save_llm_settings({
                "provider": "moonshot_kimi",
                "api_key": FAKE_KIMI_CODING_KEY,
            })
        self.assertTrue(data["ok"])
        set_secret.assert_called_once()
        self.assertIn("warning", data)
        self.assertIn("Kimi 编程版", data["warning"])
        self.assertIn("sk-kimi-", data["warning"])

    def test_sk_kimi_key_with_kimi_coding_provider_has_no_warning(self):
        with patch("netfix.api.keychain.set_secret", return_value={"ok": True}), \
                patch("netfix.api.settings.update_llm_settings", return_value={}):
            data = self._save_llm_settings({
                "provider": "kimi_coding",
                "api_key": FAKE_KIMI_CODING_KEY,
            })
        self.assertTrue(data["ok"])
        self.assertNotIn("warning", data)


if __name__ == "__main__":
    unittest.main()
