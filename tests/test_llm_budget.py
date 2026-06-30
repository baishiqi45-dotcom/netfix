import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from netfix import llm_budget


class TestLLMBudget(TestCase):
    def test_persistent_ledger_survives_backend_memory_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "llm-budget.json"
            budget = {
                "enabled": True,
                "persist_usage_ledger": True,
                "window_seconds": 3600,
                "max_requests_per_hour": 2,
                "max_image_requests_per_hour": 1,
                "cooldown_seconds_after_rate_limit": 300,
            }
            with patch("netfix.llm_budget.LLM_BUDGET_JOURNAL", ledger):
                llm_budget.reset_state()
                llm_budget.record_request("deepseek", "explain", budget, now=1_000)
                llm_budget.record_provider_result("deepseek", "rate_limited", budget, now=1_000)

                llm_budget.reset_state()
                status = llm_budget.status(budget, now=1_010)
                allowance = llm_budget.check_request("deepseek", "explain", budget, now=1_010)

        self.assertEqual(status["used_requests"], 1)
        self.assertEqual(status["remaining_requests"], 1)
        self.assertEqual(status["used_image_requests"], 0)
        self.assertEqual(status["remaining_image_requests"], 1)
        self.assertEqual(status["cooldowns"]["deepseek"]["retry_after_s"], 290)
        self.assertFalse(allowance["ok"])
        self.assertEqual(allowance["reason_code"], "provider_cooldown")

    def test_status_prunes_old_entries_and_exposes_only_safe_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "llm-budget.json"
            budget = {
                "enabled": True,
                "persist_usage_ledger": True,
                "window_seconds": 60,
                "max_requests_per_hour": 3,
                "max_image_requests_per_hour": 2,
            }
            with patch("netfix.llm_budget.LLM_BUDGET_JOURNAL", ledger):
                llm_budget.reset_state()
                llm_budget.record_request("deepseek", "explain", budget, now=1_000)
                llm_budget.record_request("minimax", "image_question", budget, now=1_100)
                status = llm_budget.status(budget, now=1_100)

        self.assertEqual(status["used_requests"], 1)
        self.assertEqual(status["used_image_requests"], 1)
        self.assertEqual(status["by_provider"]["minimax"]["requests"], 1)
        self.assertNotIn("api_key", str(status).lower())
        self.assertNotIn("prompt", str(status).lower())
        self.assertNotIn("image_url", str(status).lower())

    def test_empty_status_does_not_create_persistent_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "llm-budget.json"
            budget = {"enabled": True, "persist_usage_ledger": True}
            with patch("netfix.llm_budget.LLM_BUDGET_JOURNAL", ledger):
                llm_budget.reset_state()
                status = llm_budget.status(budget, now=1_000)
                self.assertEqual(status["used_requests"], 0)
                self.assertFalse(ledger.exists())

    def test_clear_persistent_ledger_removes_local_usage_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "llm-budget.json"
            ledger.write_text('{"requests":[]}', encoding="utf-8")
            with patch("netfix.llm_budget.LLM_BUDGET_JOURNAL", ledger):
                result = llm_budget.clear_persistent_ledger()

            self.assertTrue(result["ok"])
            self.assertEqual(result["removed"], [str(ledger)])
            self.assertFalse(ledger.exists())
