import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netfix import deepseek_sidecar


class TestDeepSeekSidecarImport(unittest.TestCase):
    def test_parse_env_file_handles_export_quotes_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "export DS_API_KEY='sk-test-secret' # local key",
                        "DS_DEFAULT_MODEL=deepseek-v4-pro",
                    ]
                ),
                encoding="utf-8",
            )

            values = deepseek_sidecar.parse_env_file(env_path)

        self.assertEqual(values["DS_API_KEY"], "sk-test-secret")
        self.assertEqual(values["DS_DEFAULT_MODEL"], "deepseek-v4-pro")

    def test_import_sidecar_key_stores_secret_without_returning_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "DS_API_KEY=sk-test-secret\nDS_DEFAULT_MODEL=deepseek-v4-pro\n",
                encoding="utf-8",
            )
            with patch("netfix.deepseek_sidecar.keychain.set_secret", return_value={"ok": True}) as set_secret, \
                    patch(
                        "netfix.deepseek_sidecar.settings.update_llm_settings",
                        return_value={
                            "enabled": True,
                            "provider": "deepseek",
                            "api_key_account": "deepseek",
                            "api_key_set": True,
                            "model": "deepseek-v4-pro",
                        },
                    ) as update_settings:
                result = deepseek_sidecar.import_sidecar_key(env_path=env_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema_version"], "netfix_deepseek_sidecar_import.v1")
        self.assertEqual(result["model"], "deepseek-v4-pro")
        self.assertEqual(result["key_name"], "DS_API_KEY")
        self.assertNotIn("sk-test-secret", str(result))
        set_secret.assert_called_once_with("netfix.llm", "deepseek", "sk-test-secret")
        update_settings.assert_called_once()
        saved = update_settings.call_args.args[0]
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["provider"], "deepseek")
        self.assertEqual(saved["api_key_account"], "deepseek")
        self.assertEqual(saved["model"], "deepseek-v4-pro")

    def test_import_reports_missing_sidecar_key_without_writing_keychain(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("DS_DEFAULT_MODEL=deepseek-v4-pro\n", encoding="utf-8")
            with patch("netfix.deepseek_sidecar.keychain.set_secret") as set_secret:
                result = deepseek_sidecar.import_sidecar_key(env_path=env_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_code"], "sidecar_key_missing")
        set_secret.assert_not_called()


if __name__ == "__main__":
    unittest.main()
