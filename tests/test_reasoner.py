"""Tests for netfix root-cause reasoning."""
from __future__ import annotations

import unittest

from netfix import reasoner


class TestReasoner(unittest.TestCase):
    def test_mixed_proxy_pac_root_cause(self):
        diagnostics = [
            {
                "name": "system_proxy_state",
                "status": "warn",
                "details": {"mixed_auto_and_manual": True},
            }
        ]

        causes = reasoner.reason({}, diagnostics)

        self.assertEqual(causes[0]["id"], "mixed-proxy-pac")
        self.assertIn("PAC", causes[0]["description"])
        self.assertIn("disable-auto-proxy", causes[0]["fixes"])

    def test_ipv6_fallback_risk_not_reported_as_exposed(self):
        diagnostics = [
            {
                "name": "ipv6_leak",
                "status": "warn",
                "details": {
                    "leak_confirmed": False,
                    "fallback_risk": True,
                },
            }
        ]

        causes = reasoner.reason({}, diagnostics)
        ids = [cause["id"] for cause in causes]

        self.assertIn("ipv6-fallback-risk", ids)
        self.assertNotIn("ipv6-exposed", ids)
        fallback = next(cause for cause in causes if cause["id"] == "ipv6-fallback-risk")
        self.assertEqual(fallback.get("fixes", []), [])

    def test_confirmed_ipv6_leak_is_reported_as_exposed(self):
        diagnostics = [
            {
                "name": "ipv6_leak",
                "status": "warn",
                "details": {
                    "leak_confirmed": True,
                    "fallback_risk": False,
                },
            }
        ]

        causes = reasoner.reason({}, diagnostics)

        self.assertEqual(causes[0]["id"], "ipv6-exposed")
        self.assertIn("disable-ipv6", causes[0]["fixes"])


if __name__ == "__main__":
    unittest.main()
