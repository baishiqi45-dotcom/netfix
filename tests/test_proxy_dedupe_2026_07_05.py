"""Tests for proxy profile de-duplication (P0-A, 2026-07-05)."""
from __future__ import annotations

import json
import sys
import unittest
import unittest.mock as mock
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from netfix import keychain, residential_proxy, settings


def _stub_keychain() -> None:
    """Avoid touching the real macOS Keychain in CI."""

    def _set_secret(service, account, secret):
        return {"ok": True, "service": service, "account": account, "stub": True}

    def _get_secret(service, account, **kwargs):
        return ""

    def _delete_secret(service, account, **kwargs):
        return {"ok": True, "service": service, "account": account, "skipped": True}

    keychain.set_secret = _set_secret
    keychain.get_secret = _get_secret
    keychain.delete_secret = _delete_secret


def _patch_settings_to_tmp(testcase: unittest.TestCase) -> Path:
    """Redirect settings.load_settings/save_settings to a temp file.

    ``settings.load_settings`` captures ``SETTINGS_PATH`` as a default arg, so
    we monkeypatch both the function default and the module constant to make
    the test isolated from any real ~/.netfix/settings.json on disk.
    """
    tmp = TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    settings_path = Path(tmp.name) / "settings.json"

    def _load(path: Path = settings_path):
        if not path.exists():
            import copy
            from netfix.settings import DEFAULT_SETTINGS
            return copy.deepcopy(DEFAULT_SETTINGS)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            import copy
            from netfix.settings import DEFAULT_SETTINGS
            return copy.deepcopy(DEFAULT_SETTINGS)

    def _save(payload, path: Path = settings_path):
        from netfix.utils import secure_write_json
        path.parent.mkdir(parents=True, exist_ok=True)
        secure_write_json(path, payload, sort_keys=True)
        return path

    testcase._orig_load = settings.load_settings
    testcase._orig_save = settings.save_settings
    settings.load_settings = _load
    settings.save_settings = _save
    testcase.addCleanup(lambda: setattr(settings, "load_settings", testcase._orig_load))
    testcase.addCleanup(lambda: setattr(settings, "save_settings", testcase._orig_save))
    return settings_path


class TestEndpointFingerprint(unittest.TestCase):
    def test_fingerprint_is_stable(self):
        a = residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8001, "alice")
        b = residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8001, "alice")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("v1:"))

    def test_fingerprint_ignores_password(self):
        a = residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8001, "alice")
        # Password is intentionally not part of the payload.
        self.assertEqual(a, residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8001, "alice"))

    def test_fingerprint_differs_by_endpoint(self):
        a = residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8001, "alice")
        b = residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8002, "alice")
        c = residential_proxy.endpoint_fingerprint("socks5h", "proxy.example.com", 8001, "bob")
        d = residential_proxy.endpoint_fingerprint("http", "proxy.example.com", 8001, "alice")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)


class TestProfileDedupe(unittest.TestCase):
    def setUp(self):
        _patch_settings_to_tmp(self)
        _stub_keychain()

    def test_ten_saves_with_changing_password_keep_one_profile(self):
        for i in range(10):
            residential_proxy.save_proxy_profile({
                "input": f"proxy.example.com:8001:alice:pw{i}",
                "target_profile": "baseline",
            })
        profiles = settings.get_proxy_profiles()
        self.assertEqual(len(profiles), 1, f"expected 1 profile, got {len(profiles)}")
        self.assertTrue(profiles[0].get("endpoint_fingerprint"))

    def test_password_change_reuses_id(self):
        first = residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:8001:alice:oldpass",
            "target_profile": "baseline",
        })
        self.assertTrue(first["ok"])
        profile_id = first["profile"]["id"]
        second = residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:8001:alice:newpass",
            "target_profile": "baseline",
        })
        self.assertTrue(second["ok"])
        self.assertEqual(second["profile"]["id"], profile_id)
        self.assertTrue(second.get("deduplicated"))
        self.assertEqual(len(settings.get_proxy_profiles()), 1)

    def test_different_endpoint_creates_new_profile(self):
        residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:8001:alice:pw",
            "target_profile": "baseline",
        })
        residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:8002:bob:pw",
            "target_profile": "baseline",
        })
        self.assertEqual(len(settings.get_proxy_profiles()), 2)

    def test_grouped_view_and_cleanup(self):
        residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:9001:alice:pw-new",
            "target_profile": "baseline",
        })
        # Inject two synthetic "legacy" duplicates directly to simulate the
        # screenshot scenario where 7-8 profiles share the same fingerprint.
        canonical = settings.get_proxy_profiles()[0]
        legacy1 = dict(canonical); legacy1["id"] = "legacy-a"; legacy1["name"] = "old A"
        legacy2 = dict(canonical); legacy2["id"] = "legacy-b"; legacy2["name"] = "old B"
        settings.upsert_proxy_profile(legacy1)
        settings.upsert_proxy_profile(legacy2)

        grouped = residential_proxy.group_proxy_profiles()
        self.assertGreaterEqual(grouped["duplicate_groups"], 1)
        self.assertEqual(grouped["total_profiles"], 3)
        self.assertIn("legacy-a", grouped["duplicate_profile_ids"])
        self.assertIn("legacy-b", grouped["duplicate_profile_ids"])

        result = residential_proxy.cleanup_duplicate_profiles()
        self.assertTrue(result["ok"])
        self.assertIn("legacy-a", result["removed_ids"])
        self.assertIn("legacy-b", result["removed_ids"])
        self.assertEqual(len(settings.get_proxy_profiles()), 1)

    def test_cleanup_keeps_active_bridge_profile(self):
        residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:9001:alice:pw-new",
            "target_profile": "baseline",
        })
        canonical = settings.get_proxy_profiles()[0]
        active_legacy = dict(canonical)
        active_legacy["id"] = "legacy-active"
        active_legacy["name"] = "old active"
        active_legacy["last_saved_at"] = "2000-01-01T00:00:00+00:00"
        settings.upsert_proxy_profile(active_legacy)

        with mock.patch.object(
            residential_proxy.proxy_bridge,
            "status",
            return_value={"bridges": [{"profile_id": "legacy-active", "running": True}]},
        ):
            grouped = residential_proxy.group_proxy_profiles()
            duplicate_group = next(group for group in grouped["groups"] if group["count"] > 1)
            self.assertEqual(duplicate_group["canonical_id"], "legacy-active")

            result = residential_proxy.cleanup_duplicate_profiles()

        self.assertTrue(result["ok"])
        remaining_ids = {profile["id"] for profile in settings.get_proxy_profiles()}
        self.assertEqual(remaining_ids, {"legacy-active"})


class TestRenameProxyProfile(unittest.TestCase):
    def setUp(self):
        _patch_settings_to_tmp(self)
        _stub_keychain()
        residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:9100:alice:pw",
            "target_profile": "baseline",
        })

    def test_rename_keeps_id(self):
        profile_id = settings.get_proxy_profiles()[0]["id"]
        result = settings.rename_proxy_profile(profile_id, "我的家用代理")
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["id"], profile_id)
        self.assertEqual(result["profile"]["name"], "我的家用代理")
        self.assertEqual(settings.get_proxy_profiles()[0]["name"], "我的家用代理")

    def test_rename_unknown_id_fails(self):
        result = settings.rename_proxy_profile("does-not-exist", "x")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
