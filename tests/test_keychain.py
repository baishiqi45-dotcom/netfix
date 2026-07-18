import unittest
from unittest.mock import Mock, patch

from netfix import keychain


class TestKeychain(unittest.TestCase):
    def test_set_secret_uses_macos_security_password_prompt_without_argv_secret(self):
        proc = Mock(returncode=0, stderr="", stdout="")
        with patch("netfix.keychain.is_available", return_value=True), \
                patch("netfix.keychain.subprocess.run", return_value=proc) as run:
            result = keychain.set_secret(keychain.LLM_SERVICE, "deepseek", "sk-secret")

        self.assertTrue(result["ok"])
        args, kwargs = run.call_args
        cmd = args[0]
        self.assertEqual(cmd[-1], "-w")
        self.assertNotIn("sk-secret", cmd)
        self.assertEqual(kwargs["input"], "sk-secret\nsk-secret\n")
        self.assertTrue(kwargs["capture_output"])

    def test_set_secret_limits_keychain_item_to_trusted_app_when_available(self):
        proc = Mock(returncode=0, stderr="", stdout="")
        with patch("netfix.keychain.is_available", return_value=True), \
                patch.dict("os.environ", {"NETFIX_KEYCHAIN_TRUSTED_APP": "/Applications/Netfix.app/Contents/MacOS/netfix-backend"}, clear=True), \
                patch("netfix.keychain.os.path.exists", return_value=True), \
                patch("netfix.keychain.subprocess.run", return_value=proc) as run:
            result = keychain.set_secret(keychain.PROXY_SERVICE, "p1", "proxy-password")

        self.assertTrue(result["ok"])
        cmd = run.call_args.args[0]
        self.assertIn("-T", cmd)
        self.assertIn("/Applications/Netfix.app/Contents/MacOS/netfix-backend", cmd)
        self.assertNotIn("proxy-password", cmd)

    def test_llm_env_override_is_provider_scoped(self):
        with patch.dict(
            "os.environ",
            {
                "NETFIX_LLM_API_KEY": "generic",
                "NETFIX_LLM_API_KEY_DEEPSEEK": "deepseek-key",
            },
            clear=True,
        ):
            self.assertEqual(keychain.get_secret(keychain.LLM_SERVICE, "deepseek"), "deepseek-key")
            self.assertIsNone(keychain.get_secret(keychain.LLM_SERVICE, "qwen"))
            self.assertEqual(
                keychain.get_secret(keychain.LLM_SERVICE, "qwen", allow_generic_llm_override=True),
                "generic",
            )

    def test_has_secret_uses_provider_scoped_env_without_reading_keychain(self):
        with patch.dict("os.environ", {"NETFIX_LLM_API_KEY_QWEN": "qwen-key"}, clear=True), \
                patch("netfix.keychain.is_available", return_value=False):
            self.assertTrue(keychain.has_secret(keychain.LLM_SERVICE, "qwen"))
            self.assertFalse(keychain.has_secret(keychain.LLM_SERVICE, "deepseek"))

    def test_has_secret_checks_keychain_without_printing_secret(self):
        proc = Mock(returncode=0, stderr="", stdout="sk-secret\n")
        with patch.dict("os.environ", {}, clear=True), \
                patch("netfix.keychain.is_available", return_value=True), \
                patch("netfix.keychain.subprocess.run", return_value=proc) as run:
            self.assertTrue(keychain.has_secret(keychain.LLM_SERVICE, "deepseek"))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["security", "find-generic-password", "-a", "deepseek", "-s", keychain.LLM_SERVICE, "-w"])
        self.assertTrue(kwargs["capture_output"])

    def test_has_secret_rejects_empty_llm_keychain_item(self):
        proc = Mock(returncode=0, stderr="", stdout="\n")
        with patch.dict("os.environ", {}, clear=True), \
                patch("netfix.keychain.is_available", return_value=True), \
                patch("netfix.keychain.subprocess.run", return_value=proc):
            self.assertFalse(keychain.has_secret(keychain.LLM_SERVICE, "deepseek"))

    def test_delete_known_netfix_secrets_collects_llm_and_proxy_accounts(self):
        snapshot = {
            "llm": {"api_key_account": "deepseek", "provider": "deepseek"},
            "proxy_profiles": [
                {"id": "p1", "credential_ref": "keychain://netfix.proxy/p1"},
                {"id": "p2"},
            ],
        }
        calls = []

        def fake_delete(service, account, missing_ok=False):
            calls.append((service, account, missing_ok))
            return {"ok": True, "service": service, "account": account}

        with patch("netfix.keychain.delete_secret", side_effect=fake_delete):
            result = keychain.delete_known_netfix_secrets(snapshot)

        self.assertTrue(result["ok"])
        self.assertIn((keychain.LLM_SERVICE, "deepseek", True), calls)
        self.assertIn((keychain.PROXY_SERVICE, "p1", True), calls)
        self.assertIn((keychain.PROXY_SERVICE, "p2", True), calls)


if __name__ == "__main__":
    unittest.main()
