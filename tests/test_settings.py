import copy
from unittest import TestCase
from unittest.mock import patch

from netfix import settings


class TestSettings(TestCase):
    def test_delete_proxy_profile_removes_only_matching_profile(self):
        current = copy.deepcopy(settings.DEFAULT_SETTINGS)
        current["proxy_profiles"] = [
            {"id": "p1", "name": "one"},
            {"id": "p2", "name": "two"},
        ]
        with patch("netfix.settings.load_settings", return_value=current), \
                patch("netfix.settings.save_settings") as save:
            result = settings.delete_proxy_profile("p1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["id"], "p1")
        saved = save.call_args.args[0]
        self.assertEqual(saved["proxy_profiles"], [{"id": "p2", "name": "two"}])

    def test_delete_proxy_profile_reports_missing_profile(self):
        current = copy.deepcopy(settings.DEFAULT_SETTINGS)
        current["proxy_profiles"] = [{"id": "p1", "name": "one"}]
        with patch("netfix.settings.load_settings", return_value=current), \
                patch("netfix.settings.save_settings") as save:
            result = settings.delete_proxy_profile("missing")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "profile not found")
        save.assert_not_called()

    def test_disabling_llm_budget_persistence_clears_local_ledger(self):
        current = copy.deepcopy(settings.DEFAULT_SETTINGS)
        with patch("netfix.settings.load_settings", return_value=current), \
                patch("netfix.settings.save_settings"), \
                patch("netfix.settings.get_llm_settings", return_value={"ok": True}), \
                patch("netfix.llm_budget.clear_persistent_ledger", return_value={"ok": True, "removed": ["ledger"]}) as clear:
            settings.update_llm_settings({
                "budget": {
                    "enabled": True,
                    "persist_usage_ledger": False,
                    "max_requests_per_hour": 60,
                    "max_image_requests_per_hour": 12,
                }
            })

        clear.assert_called_once()

    def test_changing_llm_provider_without_account_syncs_keychain_account(self):
        current = copy.deepcopy(settings.DEFAULT_SETTINGS)
        current["llm"]["provider"] = "deepseek"
        current["llm"]["api_key_account"] = "deepseek"
        with patch("netfix.settings.load_settings", return_value=current), \
                patch("netfix.settings.save_settings") as save, \
                patch("netfix.settings.get_llm_settings", return_value={"ok": True}):
            settings.update_llm_settings({"provider": "minimax"})

        saved = save.call_args.args[0]
        self.assertEqual(saved["llm"]["provider"], "minimax")
        self.assertEqual(saved["llm"]["api_key_account"], "minimax")
