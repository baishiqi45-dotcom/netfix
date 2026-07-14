import json
import unittest

from netfix.redaction import redact_report, redact_text


class TestRedaction(unittest.TestCase):
    def test_redacts_secrets_ips_profiles_and_raw_output(self):
        report = {
            "meta": {"hostname": "alice-mac"},
            "environment": {
                "active_profile": {"address": "proxy.example.com", "port": 8000},
                "profiles": [{"address": "10.0.0.5", "remarks": "home"}],
                "system_proxy": {"http": "http://user:secret-pass@203.0.113.10:8000?token=abcdef1234567890abcdef123456"},
            },
            "diagnostics": [
                {
                    "name": "proxy_auth_check",
                    "status": "fail",
                    "stdout": "password=secret-pass",
                    "stderr": "token abcdef1234567890abcdef123456",
                }
            ],
            "explanation": {"technical": {"command": "curl http://user:secret-pass@host"}},
        }
        redacted = redact_report(report)
        encoded = json.dumps(redacted, ensure_ascii=False)
        self.assertNotIn("secret-pass", encoded)
        self.assertNotIn("alice-mac", encoded)
        self.assertNotIn("proxy.example.com", encoded)
        self.assertNotIn("203.0.113.10", encoded)
        self.assertNotIn("stdout", encoded)
        self.assertGreater(redacted["redaction_audit"].get("secret", 0), 0)

    def test_redacts_secret_like_words_in_free_text(self):
        text = "代理认证失败 demo-password；bad API key sk-live-secret-token-1234567890"
        redacted = redact_text(text)
        self.assertNotIn("demo-password", redacted)
        self.assertNotIn("sk-live-secret-token", redacted)
        self.assertIn("[redacted_secret]", redacted)

    def test_keeps_non_secret_token_field_names_readable(self):
        text = "max_tokens_field uses max_completion_tokens"
        redacted = redact_text(text)
        self.assertIn("max_tokens_field", redacted)
        self.assertIn("max_completion_tokens", redacted)

    def test_keeps_non_secret_route_signature_stable(self):
        signature = "route:v1:0123456789abcdef"
        redacted = redact_report({"meta": {"route_signature": signature}})

        self.assertEqual(
            redacted["redacted_report"]["meta"]["route_signature"],
            signature,
        )


if __name__ == "__main__":
    unittest.main()
