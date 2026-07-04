"""Tests for netfix.fix_engine."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netfix import diagnose
from netfix.constants import REPO_ROOT
from netfix.fix_engine import FixEngine


def _make_engine(tmpdir: Path, target: Path, tier: int = 1) -> FixEngine:
    engine = FixEngine(journal_dir=tmpdir)
    engine.rules = {
        "symptoms": [],
        "fixes": {
            "test-append": {
                "tier": tier,
                "description": "append marker",
                "commands": [
                    f"python3 -c \"open('{target}', 'a').write('modified')\""
                ],
                "backup_paths": [str(target)],
            }
        },
    }
    return engine


def _make_engine_with_command(tmpdir: Path, command: str, tier: int = 2) -> FixEngine:
    engine = FixEngine(journal_dir=tmpdir)
    engine.rules = {
        "symptoms": [],
        "fixes": {
            "test-command": {
                "tier": tier,
                "description": "run command",
                "commands": [command],
            }
        },
    }
    return engine


class TestFixEngine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_dry_run_does_not_modify(self):
        target = self.root / "config.txt"
        target.write_text("original", encoding="utf-8")
        engine = _make_engine(self.root, target)
        result = engine.execute("test-append", dry_run=True)
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_execute_writes_file_and_rollback_restores(self):
        target = self.root / "config.txt"
        target.write_text("original", encoding="utf-8")
        # Tier 2 creates a backup so rollback can restore.
        engine = _make_engine(self.root, target, tier=2)
        with patch("netfix.fix_engine.confirm", return_value=True):
            result = engine.execute("test-append")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(target.read_text(encoding="utf-8"), "originalmodified")
        self.assertIn("backups", result)

        rollback = engine.rollback()
        self.assertTrue(rollback["ok"])
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_tier2_requires_confirm(self):
        target = self.root / "system.conf"
        target.write_text("original", encoding="utf-8")
        engine = _make_engine(self.root, target, tier=2)

        # User declines.
        with patch("netfix.fix_engine.confirm", return_value=False):
            result = engine.execute("test-append")
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

        # User confirms.
        with patch("netfix.fix_engine.confirm", return_value=True):
            result = engine.execute("test-append")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(target.read_text(encoding="utf-8"), "originalmodified")

        rollback = engine.rollback()
        self.assertTrue(rollback["ok"])
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_unknown_fix(self):
        engine = FixEngine(journal_dir=self.root)
        result = engine.execute("no-such-fix")
        self.assertFalse(result["ok"])

    def test_auto_confirm_does_not_bypass_tier2_prompt(self):
        target = self.root / "system.conf"
        target.write_text("original", encoding="utf-8")
        engine = _make_engine(self.root, target, tier=2)
        with patch("netfix.fix_engine.confirm", return_value=False) as mock_confirm:
            result = engine.execute("test-append", auto_confirm=True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        mock_confirm.assert_called_once()

    def test_app_confirmed_tier2_bypasses_cli_prompt(self):
        target = self.root / "system.conf"
        target.write_text("original", encoding="utf-8")
        engine = _make_engine(self.root, target, tier=2)
        with patch("netfix.fix_engine.confirm") as mock_confirm:
            result = engine.execute("test-append", confirmed=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(target.read_text(encoding="utf-8"), "originalmodified")
        mock_confirm.assert_not_called()

    def test_repo_relative_bin_paths_resolve_for_app_launch_cwd(self):
        resolved = FixEngine._resolve_repo_relative_paths("sudo bash bin/disable_ipv6.sh")
        self.assertIn(str(REPO_ROOT / "bin" / "disable_ipv6.sh"), resolved)
        self.assertNotIn(" bin/disable_ipv6.sh", resolved)

    def test_tier2_networksetup_runs_directly_after_confirmation(self):
        engine = _make_engine_with_command(
            self.root,
            "networksetup -setproxyautodiscovery Wi-Fi off",
            tier=2,
        )

        with patch("netfix.fix_engine.confirm", return_value=True), \
                patch("netfix.fix_engine.os.geteuid", return_value=501), \
                patch("netfix.fix_engine.run_command", return_value={
                    "ok": True,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                }) as mock_run:
            result = engine.execute("test-command")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(mock_run.call_args.args[0], [
            "networksetup",
            "-setproxyautodiscovery",
            "Wi-Fi",
            "off",
        ])

    def test_verify_diagnostic_is_run(self):
        target = self.root / "dns.txt"
        target.write_text("original", encoding="utf-8")
        engine = _make_engine(self.root, target, tier=1)
        engine.rules["fixes"]["test-append"]["verify_diagnostic"] = "dns_local"

        with patch.object(diagnose, "run_diagnostic", return_value={
            "name": "dns_local",
            "status": "ok",
        }) as mock_diag:
            result = engine.execute("test-append", env={"foo": "bar"}, core=None)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["verified"])
        self.assertEqual(result["verify_diagnostic"]["name"], "dns_local")
        mock_diag.assert_called_once()
        call_args = mock_diag.call_args
        self.assertEqual(call_args.kwargs.get("timeout"), 20)

    def test_verify_failure_marks_result_failed(self):
        engine = _make_engine_with_command(self.root, "echo fixed", tier=1)
        engine.rules["fixes"]["test-command"]["verify"] = "echo still-broken"

        with patch("netfix.fix_engine.run_command", side_effect=[
            {"ok": True, "returncode": 0, "stdout": "", "stderr": ""},
            {"ok": False, "returncode": 1, "stdout": "", "stderr": "still broken"},
        ]):
            result = engine.execute("test-command")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["verified"])
        self.assertTrue(result["verification_failed"])

    def test_ipv6_fallback_risk_after_disable_is_a_warning_not_failure(self):
        engine = _make_engine_with_command(self.root, "echo fixed", tier=1)
        engine.rules["fixes"]["disable-ipv6"] = engine.rules["fixes"].pop("test-command")
        engine.rules["fixes"]["disable-ipv6"]["verify_diagnostic"] = "ipv6_leak"

        with patch.object(diagnose, "run_diagnostic", return_value={
            "name": "ipv6_leak",
            "status": "warn",
            "details": {
                "public_ipv6": None,
                "ipv6_default_route": True,
                "proxy_active": True,
                "leak_confirmed": False,
                "fallback_risk": True,
                "reason": "proxy active and IPv6 default route present; no public IPv6 observed",
            },
        }):
            result = engine.execute("disable-ipv6")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["verified"])
        self.assertFalse(result["verification_failed"])
        self.assertEqual(result["verification_warning"]["code"], "ipv6_fallback_risk")

    def test_rollback_skips_dangerous_reverse_command(self):
        engine = FixEngine(journal_dir=self.root)
        engine._write_journal({
            "timestamp": "2026-06-24T00:00:00+00:00",
            "fix_id": "bad-fix",
            "tier": 2,
            "commands": [],
            "backups": {},
            "reverse": ["sudo rm -rf /"],
        })

        with patch("netfix.fix_engine.run_command") as mock_run:
            result = engine.rollback()

        self.assertFalse(result["ok"])
        self.assertEqual(result["commands_reversed"][0]["status"], "skipped")
        self.assertEqual(result["commands_reversed"][0]["reason"], "dangerous pattern")
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
