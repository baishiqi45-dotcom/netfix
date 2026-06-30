import json
import tempfile
import unittest
from pathlib import Path

from scripts import marketing_claims_check


RELEASE_GATE = Path(__file__).resolve().parents[1] / "scripts" / "release_gate.sh"


class TestMarketingClaimsCheck(unittest.TestCase):
    def test_current_repository_claims_pass(self):
        result = marketing_claims_check.run(Path(__file__).resolve().parents[1])

        self.assertTrue(result["ok"], result.get("findings"))

    def test_rejects_clean_residential_bypass_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "README.md"
            doc.write_text(
                "Netfix helps users bypass risk controls with clean residential IP deployment.",
                encoding="utf-8",
            )

            result = marketing_claims_check.run(root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["kind"], "residential_proxy_claim")

    def test_rejects_deepseek_vision_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "README.md"
            doc.write_text(
                "DeepSeek supports screenshot image question diagnosis for proxy errors.",
                encoding="utf-8",
            )

            result = marketing_claims_check.run(root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["kind"], "deepseek_vision_claim")

    def test_allows_safe_boundaries_for_proxy_and_deepseek(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "README.md"
            doc.write_text(
                "\n".join(
                    [
                        "Netfix does not claim clean residential IP and does not help bypass risk controls.",
                        "DeepSeek remains text-only; image question routes to Kimi/MiniMax/Qwen.",
                    ]
                ),
                encoding="utf-8",
            )

            result = marketing_claims_check.run(root)

        self.assertTrue(result["ok"], json.dumps(result.get("findings"), ensure_ascii=False))

    def test_release_gate_runs_marketing_claims_check(self):
        script = RELEASE_GATE.read_text(encoding="utf-8")

        self.assertIn("== Marketing claims ==", script)
        self.assertIn("scripts/marketing_claims_check.py", script)


if __name__ == "__main__":
    unittest.main()
