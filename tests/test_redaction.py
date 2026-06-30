import json
import unittest

from netfix.redaction import redact_report


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


if __name__ == "__main__":
    unittest.main()
