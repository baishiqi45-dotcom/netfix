import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from netfix import residential_proxy
from netfix.residential_proxy import (
    BRIDGE_RECOVERY_CONFIRMATION,
    BRIDGE_RESTART_CONFIRMATION,
    PROXY_ROLLBACK_CONFIRMATION,
    SYSTEM_APPLY_CONFIRMATION,
    apply_dry_run,
    apply_proxy_profile,
    audit_proxy_identity,
    bridge_lifecycle,
    detect_stale_bridge,
    export_client_profile,
    parse_proxy_bundle,
    parse_proxy_input,
    recover_stale_bridge,
    replace_proxy_profile,
    restart_stale_bridge,
    rollback_last_proxy_apply,
    validate_proxy_profile,
    validation_target_profiles,
)


class TestResidentialProxy(unittest.TestCase):
    def test_parse_proxy_url_redacts_password(self):
        parsed = parse_proxy_input({"input": "socks5://user:p%40ss@proxy.example.com:1080"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["profile"]["protocol"], "socks5")
        self.assertEqual(parsed["profile"]["host"], "proxy.example.com")
        self.assertTrue(parsed["profile"]["password_set"])
        self.assertIn("user:***@", parsed["redacted_url"])
        self.assertNotIn("p@ss", parsed["redacted_url"])
        self.assertTrue(any("socks5://" in item for item in parsed["warnings"]))

    def test_parse_colon_tuple(self):
        parsed = parse_proxy_input({"input": "proxy.example.com:8000:user:pass"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["profile"]["protocol"], "http")
        self.assertEqual(parsed["profile"]["port"], 8000)
        self.assertEqual(parsed["profile"]["username"], "user")
        self.assertTrue(any("参数类型" in item for item in parsed["warnings"]))

    def test_parse_miyaip_like_colon_tuple_defaults_to_http_without_leaking_secret(self):
        parsed = parse_proxy_input({"input": "direct.miyaip.online:8001:demo-user:demo-password"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["profile"]["protocol"], "http")
        self.assertEqual(parsed["profile"]["host"], "direct.miyaip.online")
        self.assertEqual(parsed["profile"]["port"], 8001)
        self.assertEqual(parsed["profile"]["username"], "demo-user")
        self.assertTrue(parsed["profile"]["password_set"])
        self.assertIn("demo-user:***@", parsed["redacted_url"])
        self.assertNotIn("demo-password", parsed["redacted_url"])
        self.assertTrue(any("先按 HTTP" in item for item in parsed["warnings"]))
        self.assertEqual(parsed["deployment_decision"]["status"], "ready")
        self.assertIn("开始使用这台 Mac", parsed["deployment_decision"]["headline"])
        self.assertEqual(parsed["deployment_decision"]["system_apply"]["status"], "bridge_required")

    def test_parse_colon_tuple_can_be_forced_to_socks5h(self):
        parsed = parse_proxy_input({"input": "direct.example-proxy.test:8001:demo-user:demo-password", "protocol": "socks5h"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["profile"]["protocol"], "socks5h")
        self.assertFalse(any("先按 HTTP" in item for item in parsed["warnings"]))

    def test_parse_colon_tuple_preserves_colons_in_password(self):
        parsed = parse_proxy_input({"input": "proxy.example.com:8000:user:pa:ss"})
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["_secret"]["password"], "pa:ss")

    def test_parse_table_row_from_provider_paste(self):
        parsed = parse_proxy_input({"input": "proxy.example.com,8000,user,pa:ss"})

        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["profile"]["host"], "proxy.example.com")
        self.assertEqual(parsed["profile"]["port"], 8000)
        self.assertEqual(parsed["profile"]["username"], "user")
        self.assertTrue(parsed["profile"]["password_set"])
        self.assertEqual(parsed["_secret"]["password"], "pa:ss")

    def test_parse_proxy_bundle_redacts_multi_line_provider_paste(self):
        bundle = parse_proxy_bundle({
            "input": "\n".join([
                "host,port,user,password",
                "http://alpha:secret-one@alpha.example.com:8000",
                "beta.example.com:9000:beta:secret-two",
                "gamma.example.com,10000,gamma,secret-three",
                "bad-line",
            ]),
            "provider": "vendor-a",
        })

        self.assertTrue(bundle["ok"])
        self.assertEqual(bundle["schema_version"], "netfix_proxy_import_preview.v1")
        self.assertEqual(bundle["summary"]["valid_count"], 3)
        self.assertEqual(bundle["summary"]["invalid_count"], 1)
        self.assertEqual(bundle["recommendation"]["line_number"], 2)
        self.assertEqual(len(bundle["candidates"]), 4)
        self.assertEqual(bundle["candidates"][0]["line_number"], 2)
        self.assertTrue(bundle["candidates"][0]["ok"])
        self.assertEqual(bundle["candidates"][0]["profile"]["provider"], "vendor-a")
        self.assertFalse(bundle["candidates"][-1]["ok"])
        encoded = str(bundle)
        self.assertIn("alpha:***@", encoded)
        self.assertIn("beta:***@", encoded)
        self.assertNotIn("secret-one", encoded)
        self.assertNotIn("secret-two", encoded)
        self.assertNotIn("secret-three", encoded)

    def test_parse_provider_table_with_country_session_and_ttl_columns(self):
        bundle = parse_proxy_bundle({
            "input": "\n".join([
                "host,port,username,password,country,session,ttl",
                "gate.proxy.example.com,10001,user-us-session-abc,secret-us,US,abc,600",
                "gate.proxy.example.com 10002 user-uk-session-def secret-uk GB def 900",
            ]),
            "provider": "sanitized-provider",
            "expected_geo": {"country": "US"},
            "rotation": {"mode": "sticky", "ttl_seconds": 600},
        })

        self.assertTrue(bundle["ok"])
        self.assertEqual(bundle["summary"]["valid_count"], 2)
        first = bundle["candidates"][0]
        self.assertTrue(first["ok"])
        self.assertEqual(first["profile"]["host"], "gate.proxy.example.com")
        self.assertEqual(first["profile"]["port"], 10001)
        self.assertEqual(first["profile"]["username"], "user-us-session-abc")
        self.assertEqual(first["profile"]["provider"], "sanitized-provider")
        self.assertEqual(first["profile"]["expected_geo"], {"country": "US"})
        self.assertEqual(first["profile"]["rotation"], {"mode": "sticky", "ttl_seconds": 600})
        encoded = str(bundle)
        self.assertIn("user-us-session-abc:***@", encoded)
        self.assertNotIn("secret-us", encoded)
        self.assertNotIn("secret-uk", encoded)

    def test_parse_webshare_like_api_rows_with_protocol_column(self):
        bundle = parse_proxy_bundle({
            "input": "\n".join([
                "protocol,host,port,user,password",
                "socks5h api.proxy.example.com 12000 api-user api-secret",
                "http,api2.proxy.example.com,13000,api-user-2,api-secret-2",
            ]),
            "provider": "api-list",
        })

        self.assertTrue(bundle["ok"])
        self.assertEqual(bundle["summary"]["valid_count"], 2)
        first = bundle["candidates"][0]["profile"]
        second = bundle["candidates"][1]["profile"]
        self.assertEqual(first["protocol"], "socks5h")
        self.assertEqual(first["port"], 12000)
        self.assertEqual(second["protocol"], "http")
        self.assertEqual(second["port"], 13000)
        encoded = str(bundle)
        self.assertNotIn("api-secret", encoded)
        self.assertNotIn("api-secret-2", encoded)

    def test_parse_proxy_bundle_limits_large_pastes(self):
        text = "\n".join(f"proxy{i}.example.com:8000:user:pass{i}" for i in range(60))

        bundle = parse_proxy_bundle({"input": text, "limit": 5})

        self.assertTrue(bundle["ok"])
        self.assertEqual(bundle["summary"]["processed_count"], 5)
        self.assertTrue(bundle["truncated"])
        self.assertIn("只预检前 5 条", " ".join(bundle["warnings"]))

    def test_save_proxy_profile_invalid_input_never_returns_secret(self):
        result = residential_proxy.save_proxy_profile({
            "input": "proxy.example.com:not-a-port:user:super-secret-password",
        })

        self.assertFalse(result["ok"])
        encoded = str(result)
        self.assertNotIn("_secret", result)
        self.assertNotIn("super-secret-password", encoded)

    def test_validation_receipt_saves_exact_proxy_as_verified(self):
        payload = {"input": "http://user:pass@proxy.example.com:8000"}
        parsed = parse_proxy_input(payload)
        receipt = residential_proxy.issue_validation_receipt(
            parsed["profile"],
            password="pass",
        )["validation_receipt"]

        with patch("netfix.residential_proxy.get_proxy_profiles", return_value=[]), \
                patch("netfix.residential_proxy.upsert_proxy_profile", side_effect=lambda profile: profile), \
                patch("netfix.residential_proxy.keychain.set_secret", return_value={"ok": True}):
            result = residential_proxy.save_proxy_profile({**payload, "validation_receipt": receipt})

        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["verification_status"], "verified")
        self.assertTrue(result["profile"]["can_apply"])
        self.assertIn("validated_at", result["profile"])

    def test_legacy_save_without_receipt_is_unverified_and_cannot_system_apply(self):
        with patch("netfix.residential_proxy.get_proxy_profiles", return_value=[]), \
                patch("netfix.residential_proxy.upsert_proxy_profile", side_effect=lambda profile: profile):
            saved = residential_proxy.save_proxy_profile({"input": "http://proxy.example.com:8000"})

        self.assertTrue(saved["ok"])
        self.assertEqual(saved["profile"]["verification_status"], "unverified")
        self.assertFalse(saved["profile"]["can_apply"])
        with patch("netfix.residential_proxy.choose_network_service") as choose:
            applied = apply_proxy_profile(
                saved["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )
        self.assertFalse(applied["ok"])
        self.assertEqual(applied["reason_code"], "profile_not_verified")
        choose.assert_not_called()

    def test_validation_receipt_is_one_time_and_bound_to_the_exact_secret(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        receipt = residential_proxy.issue_validation_receipt(parsed["profile"], password="pass")["validation_receipt"]
        self.assertTrue(residential_proxy.consume_validation_receipt(receipt, parsed["profile"], password="pass")["ok"])
        reused = residential_proxy.consume_validation_receipt(receipt, parsed["profile"], password="pass")
        self.assertFalse(reused["ok"])
        self.assertEqual(reused["reason_code"], "validation_receipt_unknown")

        other = residential_proxy.issue_validation_receipt(parsed["profile"], password="pass")["validation_receipt"]
        mismatch = residential_proxy.consume_validation_receipt(other, parsed["profile"], password="different")
        self.assertFalse(mismatch["ok"])
        self.assertEqual(mismatch["reason_code"], "validation_receipt_mismatch")

    def test_replace_proxy_profile_preserves_id_and_rotates_keychain_secret(self):
        existing = {
            "id": "p1",
            "name": "旧住宅 IP",
            "protocol": "http",
            "host": "old.proxy.example.com",
            "port": 8000,
            "username": "old-user",
            "credential_ref": "keychain://netfix.proxy/p1",
            "provider": "provider-a",
            "expected_geo": {"country": "US"},
            "rotation": {"mode": "sticky", "ttl_seconds": 1800},
            "bypass_domains": ["localhost", "*.local"],
            "last_check": {"ok": False, "error": "auth_failed"},
        }

        with patch("netfix.residential_proxy.get_proxy_profiles", return_value=[existing]), \
                patch("netfix.residential_proxy.upsert_proxy_profile", side_effect=lambda profile: profile) as upsert, \
                patch("netfix.residential_proxy.keychain.set_secret", return_value={"ok": True}) as set_secret:
            result = replace_proxy_profile("p1", {"input": "socks5h://new-user:new-pass@new.proxy.example.com:1080"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["id"], "p1")
        self.assertEqual(result["profile"]["name"], "旧住宅 IP")
        self.assertEqual(result["profile"]["protocol"], "socks5h")
        self.assertEqual(result["profile"]["host"], "new.proxy.example.com")
        self.assertEqual(result["profile"]["port"], 1080)
        self.assertEqual(result["profile"]["username"], "new-user")
        self.assertEqual(result["profile"]["provider"], "provider-a")
        self.assertEqual(result["profile"]["expected_geo"], {"country": "US"})
        self.assertNotIn("last_check", result["profile"])
        self.assertEqual(result["profile"]["verification_status"], "unverified")
        self.assertFalse(result["profile"]["can_apply"])
        self.assertEqual(result["previous_endpoint"]["host"], "old.proxy.example.com")
        self.assertEqual(result["previous_endpoint"]["port"], 8000)
        self.assertEqual(result["new_endpoint"]["host"], "new.proxy.example.com")
        self.assertEqual(result["deployment_decision"]["status"], "ready")
        set_secret.assert_called_once_with("netfix.proxy", "p1", "new-pass")
        upsert.assert_called_once()

    def test_replace_proxy_profile_with_matching_receipt_remains_verified(self):
        existing = {
            "id": "p1",
            "name": "旧代理",
            "protocol": "http",
            "host": "old.proxy.example.com",
            "port": 8000,
        }
        replacement = "socks5h://new-user:new-pass@new.proxy.example.com:1080"
        parsed = parse_proxy_input({"input": replacement})
        receipt = residential_proxy.issue_validation_receipt(
            parsed["profile"],
            password="new-pass",
        )["validation_receipt"]
        with patch("netfix.residential_proxy.get_proxy_profiles", return_value=[existing]), \
                patch("netfix.residential_proxy.upsert_proxy_profile", side_effect=lambda profile: profile), \
                patch("netfix.residential_proxy.keychain.set_secret", return_value={"ok": True}):
            result = replace_proxy_profile(
                "p1",
                {"input": replacement, "validation_receipt": receipt},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["verification_status"], "verified")
        self.assertTrue(result["profile"]["can_apply"])
        self.assertEqual(result["profile"]["validation_source"], "preflight_receipt")

    def test_replace_proxy_profile_rejects_bad_receipt_before_keychain_or_save(self):
        existing = {"id": "p1", "protocol": "http", "host": "old.proxy.example.com", "port": 8000}
        with patch("netfix.residential_proxy.get_proxy_profiles", return_value=[existing]), \
                patch("netfix.residential_proxy.upsert_proxy_profile") as upsert, \
                patch("netfix.residential_proxy.keychain.set_secret") as set_secret:
            result = replace_proxy_profile(
                "p1",
                {
                    "input": "http://user:new-pass@new.proxy.example.com:8000",
                    "validation_receipt": "invalid",
                },
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["requires_validation"])
        upsert.assert_not_called()
        set_secret.assert_not_called()

    def test_parse_authenticated_http_returns_user_deployment_decision(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})

        self.assertTrue(parsed["ok"])
        decision = parsed["deployment_decision"]
        self.assertEqual(decision["schema_version"], "netfix_proxy_deployment_decision.v1")
        self.assertEqual(decision["status"], "ready")
        self.assertEqual(decision["system_apply"]["status"], "bridge_required")
        self.assertEqual(decision["system_apply"]["reason_code"], "authenticated_http_bridge_required")
        self.assertTrue(decision["system_apply"]["requires_netfix_running"])
        self.assertEqual(decision["client_export"]["status"], "available")
        self.assertEqual(decision["monitor"]["status"], "available_after_save")
        self.assertIn("保存到本机密码库", decision["next_steps"][0])

    def test_parse_authenticated_socks_returns_export_first_decision(self):
        parsed = parse_proxy_input({"input": "socks5://user:pass@proxy.example.com:1080"})

        self.assertTrue(parsed["ok"])
        decision = parsed["deployment_decision"]
        self.assertEqual(decision["status"], "ready")
        self.assertEqual(decision["system_apply"]["status"], "bridge_required")
        self.assertEqual(decision["system_apply"]["reason_code"], "authenticated_socks_bridge_required")
        self.assertTrue(decision["system_apply"]["requires_netfix_running"])
        self.assertEqual(decision["client_export"]["status"], "available")
        self.assertIn("本机转发", " ".join(decision["next_steps"]))

    def test_parse_unauthenticated_socks_returns_system_apply_decision(self):
        parsed = parse_proxy_input({"input": "socks5://proxy.example.com:1080"})

        self.assertTrue(parsed["ok"])
        decision = parsed["deployment_decision"]
        self.assertEqual(decision["status"], "ready")
        self.assertEqual(decision["system_apply"]["status"], "supported")
        self.assertEqual(decision["system_apply"]["reason_code"], "system_socks_supported_without_auth")
        self.assertFalse(decision["system_apply"]["requires_netfix_running"])

    def test_parse_invalid_url_port_returns_error(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:99999"})
        self.assertFalse(parsed["ok"])
        self.assertIn("port must be between 1 and 65535", parsed["errors"])
        self.assertEqual(parsed["deployment_decision"]["status"], "blocked")
        self.assertIn("port", parsed["deployment_decision"]["missing_fields"])

    def test_parse_password_without_username_is_rejected(self):
        parsed = parse_proxy_input({"host": "proxy.example.com", "port": 8000, "password": "pass"})
        self.assertFalse(parsed["ok"])
        self.assertIn("username is required when password is provided", parsed["errors"])
        self.assertEqual(parsed["deployment_decision"]["status"], "blocked")

    def test_apply_dry_run_requires_confirmation_for_system_mode(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        plan = apply_dry_run(parsed["profile"], mode="system")
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["requires_confirmation"])
        self.assertEqual(plan["status"], "dry_run")
        self.assertEqual(plan["deployment_decision"]["system_apply"]["status"], "bridge_required")
        self.assertTrue(any("IPv6" in step.get("label", "") for step in plan["steps"]))
        self.assertIn("本机密码库", " ".join(plan["warnings"]))

    def test_apply_app_env_returns_redacted_environment_without_secret(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        result = apply_proxy_profile(parsed["profile"], mode="app-env")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        encoded = str(result)
        self.assertIn("user:***@", encoded)
        self.assertNotIn("pass@proxy", encoded)

    def test_export_client_profile_returns_copyable_placeholders_without_secret(self):
        parsed = parse_proxy_input({"input": "socks5h://user:real-secret@proxy.example.com:1080"})
        exported = export_client_profile(parsed["profile"], fmt="all")
        self.assertTrue(exported["ok"])
        self.assertEqual(exported["profile_id"], parsed["profile"]["id"])
        self.assertIn("url", exported["snippets"])
        self.assertIn("env", exported["snippets"])
        self.assertIn("clash", exported["snippets"])
        self.assertIn("mihomo", exported["snippets"])
        self.assertIn("sing-box", exported["snippets"])
        encoded = str(exported)
        self.assertIn("<password>", encoded)
        self.assertIn("ALL_PROXY", exported["snippets"]["env"]["content"])
        self.assertEqual(exported["package"]["schema_version"], "netfix_proxy_client_package.v1")
        self.assertEqual(exported["package"]["recommended_format"], "mihomo")
        package_paths = {item["path"] for item in exported["package"]["files"]}
        self.assertIn("README.md", package_paths)
        self.assertTrue(any(path.endswith(".mihomo.yaml") for path in package_paths))
        self.assertTrue(any(path.endswith(".sing-box.json") for path in package_paths))
        self.assertTrue(any(item["secret_placeholder"] for item in exported["package"]["files"]))
        self.assertIn("远程 DNS", " ".join(exported["warnings"]))
        self.assertNotIn("real-secret", encoded)

    def test_export_single_format_returns_readme_and_selected_package_file(self):
        parsed = parse_proxy_input({"input": "http://user:real-secret@proxy.example.com:8000"})
        exported = export_client_profile(parsed["profile"], fmt="sing-box")
        encoded = str(exported)

        self.assertTrue(exported["ok"])
        self.assertNotIn("real-secret", encoded)
        self.assertEqual(set(exported["snippets"].keys()), {"sing-box"})
        self.assertEqual([item["format"] for item in exported["package"]["files"]], ["readme", "sing-box"])
        self.assertTrue(exported["package"]["secret_placeholder"])
        self.assertEqual(exported["package"]["file_count"], 2)

    def test_export_no_auth_socks_warns_about_dns_not_keychain_password(self):
        parsed = parse_proxy_input({"input": "socks5h://proxy.example.com:1080"})
        exported = export_client_profile(parsed["profile"], fmt="all")
        warnings = " ".join(exported["warnings"])

        self.assertTrue(exported["ok"])
        self.assertIn("远程 DNS", warnings)
        self.assertNotIn("本机密码库", warnings)
        self.assertFalse(exported["package"]["secret_placeholder"])
        self.assertNotIn("<password>", str(exported["package"]))

    def test_export_client_profile_rejects_unknown_format(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        exported = export_client_profile(parsed["profile"], fmt="shadowrocket")
        self.assertFalse(exported["ok"])
        self.assertIn("supported_formats", exported)

    def test_system_apply_requires_confirmation_phrase(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        result = apply_proxy_profile(parsed["profile"], mode="system", confirmed=True, confirmation="wrong")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "pending_confirmation")
        self.assertEqual(result["confirmation"], SYSTEM_APPLY_CONFIRMATION)

    def test_choose_network_service_prefers_default_route_device(self):
        services = {"stdout": "Wi-Fi\nEthernet\n"}
        hardware = {"stdout": "Hardware Port: Wi-Fi\nDevice: en0\n\nHardware Port: Ethernet\nDevice: en7\n"}
        route = Mock(returncode=0, stdout="interface: en7\n")
        with patch("netfix.residential_proxy.sys.platform", "darwin"), \
                patch("netfix.residential_proxy.subprocess.run", return_value=route), \
                patch("netfix.residential_proxy._run_networksetup", side_effect=[services, hardware]):
            self.assertEqual(residential_proxy.choose_network_service(), "Ethernet")

    def test_choose_network_service_falls_back_when_default_route_unknown(self):
        services = {"stdout": "Wi-Fi\nEthernet\n"}
        route = Mock(returncode=1, stdout="")
        with patch("netfix.residential_proxy.sys.platform", "darwin"), \
                patch("netfix.residential_proxy.subprocess.run", return_value=route), \
                patch("netfix.residential_proxy._run_networksetup", return_value=services):
            self.assertEqual(residential_proxy.choose_network_service(), "Wi-Fi")

    def test_system_apply_uses_bridge_for_authenticated_http_proxy(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        bridge = {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080}
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy.keychain.get_secret", return_value="pass") as get_secret, \
                patch("netfix.residential_proxy.proxy_bridge.start_http_bridge", return_value={"ok": True, "bridge": bridge}) as start_bridge, \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}) as networksetup, \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": True, "status": "ok"}), \
                patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": True, "proxy_check": {"status": "ok"}}) as validate, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["bridge"]["id"], "b1")
        self.assertEqual(result["applied"]["scope"], "loopback_bridge")
        get_secret.assert_called_once()
        start_bridge.assert_called_once()
        validate.assert_called_once()
        journal.assert_called()
        calls = [call.args[0] for call in networksetup.call_args_list]
        self.assertIn(["-setwebproxy", "Wi-Fi", "127.0.0.1", "19080"], calls)
        self.assertIn(["-setsecurewebproxy", "Wi-Fi", "127.0.0.1", "19080"], calls)

    def test_system_apply_uses_bridge_for_authenticated_socks_proxy(self):
        parsed = parse_proxy_input({"input": "socks5://user:pass@proxy.example.com:1080"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        bridge = {"id": "b-socks", "listen_host": "127.0.0.1", "listen_port": 19081}
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy.keychain.get_secret", return_value="pass") as get_secret, \
                patch("netfix.residential_proxy.proxy_bridge.start_http_bridge", return_value={"ok": True, "bridge": bridge}) as start_bridge, \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}) as networksetup, \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": True, "status": "ok"}), \
                patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": True, "proxy_check": {"status": "ok"}}) as validate, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["bridge"]["id"], "b-socks")
        self.assertEqual(result["applied"]["scope"], "loopback_bridge")
        get_secret.assert_called_once()
        start_bridge.assert_called_once()
        validate.assert_called_once()
        journal.assert_called()
        calls = [call.args[0] for call in networksetup.call_args_list]
        self.assertIn(["-setwebproxy", "Wi-Fi", "127.0.0.1", "19081"], calls)
        self.assertIn(["-setsecurewebproxy", "Wi-Fi", "127.0.0.1", "19081"], calls)
        self.assertNotIn(["-setsocksfirewallproxy", "Wi-Fi", "127.0.0.1", "19081"], calls)

    def test_system_apply_uses_networksetup_with_backup_and_verify(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi") as choose, \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup) as capture, \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}) as networksetup, \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": True, "status": "ok"}), \
                patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": True, "proxy_check": {"status": "ok"}}) as validate, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        choose.assert_called_once()
        capture.assert_called_once_with("Wi-Fi")
        validate.assert_called_once()
        journal.assert_called()
        applied_snapshot = journal.call_args_list[-1].args[0]["applied_snapshot"]
        self.assertTrue(applied_snapshot["web"]["enabled"])
        self.assertEqual(len(applied_snapshot["web"]["endpoint_hash"]), 16)
        self.assertNotIn("proxy.example.com", str(applied_snapshot))
        self.assertTrue(applied_snapshot["secure"]["enabled"])
        self.assertFalse(applied_snapshot["auto_proxy_url"]["enabled"])
        calls = [call.args[0] for call in networksetup.call_args_list]
        self.assertIn(["-setautoproxystate", "Wi-Fi", "off"], calls)
        self.assertIn(["-setwebproxy", "Wi-Fi", "proxy.example.com", "8000"], calls)
        self.assertIn(["-setsecurewebproxy", "Wi-Fi", "proxy.example.com", "8000"], calls)

    def test_system_apply_cannot_disable_verification_or_automatic_rollback(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}), \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": True, "status": "ok"}), \
                patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": False, "proxy_check": {"status": "fail"}}) as validate, \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True}) as restore, \
                patch("netfix.residential_proxy._write_apply_journal"):
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
                verify=False,
                rollback_on_verify_failure=False,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rolled_back_after_verify_failure")
        validate.assert_called_once()
        restore.assert_called_once_with(backup)

    def test_system_apply_disables_restorable_ipv6_and_records_state(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
            "ipv6": {"mode": "automatic", "enabled": True, "restorable": True},
        }
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}) as networksetup, \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": True, "status": "ok"}), \
                patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": True, "proxy_check": {"status": "ok"}}), \
                patch("netfix.residential_proxy._write_apply_journal"):
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["ipv6"], {"disabled_during_apply": True, "backup_mode": "automatic"})
        calls = [call.args[0] for call in networksetup.call_args_list]
        self.assertIn(["-setv6off", "Wi-Fi"], calls)

    def test_restore_system_proxy_backup_restores_ipv6_automatic(self):
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
            "ipv6": {"mode": "automatic", "restorable": True},
        }
        with patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}) as networksetup:
            result = residential_proxy._restore_system_proxy_backup(backup)

        self.assertTrue(result["ok"])
        calls = [call.args[0] for call in networksetup.call_args_list]
        self.assertIn(["-setv6automatic", "Wi-Fi"], calls)

    def test_restore_system_proxy_backup_returns_structured_partial_failure(self):
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        with patch(
            "netfix.residential_proxy._run_networksetup",
            side_effect=[{"ok": True}, RuntimeError("restore exploded")],
        ):
            result = residential_proxy._restore_system_proxy_backup(backup)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "partial_restore_failed")
        self.assertEqual(result["reason_code"], "networksetup_restore_failed")
        self.assertEqual(len(result["commands"]), 1)
        self.assertIn("restore exploded", result["error"])

    def test_system_apply_blocks_before_mutation_when_pac_backup_cannot_be_persisted(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {
                "enabled": True,
                "url": "",
                "restore_blocked_reason": "auto_proxy_url_not_stored_in_keychain",
            },
            "auto_discovery": {"enabled": False},
        }

        def prepared(entry):
            return {"last_apply": {**entry, "backup": backup}}

        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy._write_apply_journal", side_effect=prepared), \
                patch("netfix.residential_proxy._run_networksetup") as networksetup:
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason_code"], "auto_proxy_url_not_stored_in_keychain")
        networksetup.assert_not_called()

    def test_system_apply_readback_mismatch_rolls_back_before_endpoint_validation(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}), \
                patch("netfix.residential_proxy._write_apply_journal"), \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": False, "reason_code": "system_proxy_readback_mismatch", "error": "mismatch"}), \
                patch("netfix.residential_proxy.validate_proxy_profile") as validate, \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True}) as restore:
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rolled_back_after_verify_failure")
        self.assertEqual(result["verify"]["reason_code"], "system_proxy_readback_mismatch")
        validate.assert_not_called()
        restore.assert_called_once_with(backup)

    def test_verify_failure_reports_restore_failure_and_keeps_active_bridge(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        parsed["profile"].update({"verification_status": "verified", "can_apply": True})
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
        }
        bridge = {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080}
        with patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=backup), \
                patch("netfix.residential_proxy.keychain.get_secret", return_value="pass"), \
                patch("netfix.residential_proxy.proxy_bridge.start_http_bridge", return_value={"ok": True, "bridge": bridge}), \
                patch("netfix.residential_proxy.proxy_bridge.stop_bridge") as stop_bridge, \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}), \
                patch("netfix.residential_proxy._write_apply_journal"), \
                patch("netfix.residential_proxy._verify_applied_system_topology", return_value={"ok": True, "status": "ok"}), \
                patch("netfix.residential_proxy.validate_proxy_profile", return_value={"ok": False, "status": "fail"}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": False, "status": "partial_restore_failed"}):
            result = apply_proxy_profile(
                parsed["profile"],
                mode="system",
                confirmed=True,
                confirmation=SYSTEM_APPLY_CONFIRMATION,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "rollback_failed_after_verify_failure")
        self.assertEqual(result["reason_code"], "verify_failed_rollback_failed")
        stop_bridge.assert_not_called()

    def test_second_netfix_apply_keeps_original_rollback_backup(self):
        current = {"service": "Wi-Fi", "web": {"enabled": True, "server": "127.0.0.1", "port": 19080}}
        original = {"service": "Wi-Fi", "web": {"enabled": False, "authenticated": False}}
        previous = {
            "id": "apply-a",
            "backup": original,
            "applied_snapshot": {"service": "Wi-Fi", "web": {"enabled": True, "endpoint_hash": "abc"}},
        }
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": previous}), \
                patch("netfix.residential_proxy._system_proxy_matches_snapshot", return_value=True):
            backup, replaced_id = residential_proxy._rollback_backup_for_new_apply(current)

        self.assertEqual(backup, original)
        self.assertEqual(replaced_id, "apply-a")

    def test_apply_journal_redacts_auto_proxy_url_and_keeps_keychain_ref(self):
        entry = {
            "id": "journal-1",
            "backup": {
                "service": "Wi-Fi",
                "web": {"enabled": False, "raw": "web raw"},
                "secure": {"enabled": False, "raw": "secure raw"},
                "socks": {"enabled": False, "raw": "socks raw"},
                "auto_proxy_url": {
                    "enabled": True,
                    "url": "http://user:secret-password@pac.example.com/proxy.pac?token=raw-token",
                    "raw": "URL: http://user:secret-password@pac.example.com/proxy.pac?token=raw-token",
                },
                "auto_discovery": {"enabled": False, "raw": "auto raw"},
            },
        }
        with patch("netfix.residential_proxy.keychain.set_secret", return_value={"ok": True}) as set_secret, \
                patch("netfix.residential_proxy.secure_write_json") as write_json:
            payload = residential_proxy._write_apply_journal(entry)

        set_secret.assert_called_once()
        written = write_json.call_args.args[1]
        auto_url = written["last_apply"]["backup"]["auto_proxy_url"]
        self.assertEqual(auto_url["url"], "")
        self.assertEqual(auto_url["credential_ref"]["service"], "netfix.proxy")
        self.assertIn("url_hash", auto_url)
        self.assertNotIn("raw", auto_url)
        self.assertNotIn("raw", written["last_apply"]["backup"]["web"])
        encoded = str(payload)
        self.assertNotIn("secret-password", encoded)
        self.assertNotIn("raw-token", encoded)

    def test_restore_system_proxy_backup_reads_auto_proxy_url_from_keychain_ref(self):
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {
                "enabled": True,
                "url": "",
                "credential_ref": {"service": "netfix.proxy", "account": "journal:j1:auto_proxy_url"},
            },
            "auto_discovery": {"enabled": False},
        }
        with patch("netfix.residential_proxy.keychain.get_secret", return_value="http://pac.example.com/proxy.pac"), \
                patch("netfix.residential_proxy._run_networksetup", return_value={"ok": True}) as networksetup:
            result = residential_proxy._restore_system_proxy_backup(backup)

        self.assertTrue(result["ok"])
        calls = [call.args[0] for call in networksetup.call_args_list]
        self.assertIn(["-setautoproxyurl", "Wi-Fi", "http://pac.example.com/proxy.pac"], calls)

    def test_restore_system_proxy_backup_blocks_redacted_auto_proxy_without_keychain_ref(self):
        backup = {
            "service": "Wi-Fi",
            "web": {"enabled": False, "authenticated": False},
            "secure": {"enabled": False, "authenticated": False},
            "socks": {"enabled": False, "authenticated": False},
            "auto_proxy_url": {"enabled": True, "url": "http://user:***@pac.example.com/proxy.pac"},
            "auto_discovery": {"enabled": False},
        }
        result = residential_proxy._restore_system_proxy_backup(backup)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_code"], "auto_proxy_url_backup_not_restorable")

    def test_rollback_last_proxy_apply_requires_confirmation(self):
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": {"id": "j1", "profile_id": "p1", "network_service": "Wi-Fi"}}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup") as restore:
            result = rollback_last_proxy_apply(confirmed=True, confirmation="wrong")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "pending_confirmation")
        self.assertEqual(result["confirmation"], PROXY_ROLLBACK_CONFIRMATION)
        restore.assert_not_called()

    def test_rollback_last_proxy_apply_restores_backup(self):
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "backup": {"service": "Wi-Fi"},
        }
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True, "network_service": "Wi-Fi"}) as restore, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            result = rollback_last_proxy_apply(confirmed=True, confirmation=PROXY_ROLLBACK_CONFIRMATION)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "rolled_back")
        restore.assert_called_once_with({"service": "Wi-Fi"})
        journal.assert_called_once()

    def test_rollback_last_proxy_apply_stops_bridge_after_restore(self):
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "backup": {"service": "Wi-Fi"},
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True, "network_service": "Wi-Fi"}), \
                patch("netfix.residential_proxy.proxy_bridge.stop_bridge", return_value={"ok": True, "stopped": True, "bridge_id": "b1"}) as stop, \
                patch("netfix.residential_proxy._write_apply_journal"):
            result = rollback_last_proxy_apply(confirmed=True, confirmation=PROXY_ROLLBACK_CONFIRMATION)
        self.assertTrue(result["ok"])
        self.assertEqual(result["bridge_stop"]["bridge_id"], "b1")
        stop.assert_called_once_with("b1")

    def test_detect_stale_bridge_when_system_points_to_closed_bridge_port(self):
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "profile_name": "proxy",
            "network_service": "Wi-Fi",
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        current = {
            "service": "Wi-Fi",
            "web": {"enabled": True, "server": "127.0.0.1", "port": 19080},
            "secure": {"enabled": True, "server": "127.0.0.1", "port": 19080},
            "socks": {"enabled": False, "server": "", "port": 0},
        }
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=current), \
                patch("netfix.residential_proxy.proxy_bridge.status", return_value={"ok": True, "bridges": []}), \
                patch("netfix.residential_proxy._loopback_port_open", return_value=False):
            result = detect_stale_bridge()
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "stale_bridge")
        self.assertTrue(result["stale"])
        self.assertTrue(result["recovery_available"])
        self.assertEqual(result["confirmation"], BRIDGE_RECOVERY_CONFIRMATION)

    def test_detect_bridge_healthy_when_current_backend_owns_bridge(self):
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        current = {
            "service": "Wi-Fi",
            "web": {"enabled": True, "server": "127.0.0.1", "port": 19080},
            "secure": {"enabled": False, "server": "", "port": 0},
            "socks": {"enabled": False, "server": "", "port": 0},
        }
        bridge = {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080, "running": True}
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=current), \
                patch("netfix.residential_proxy.proxy_bridge.status", return_value={"ok": True, "bridges": [bridge]}):
            result = detect_stale_bridge()
        self.assertEqual(result["status"], "healthy")
        self.assertFalse(result["recovery_available"])

    def test_detect_direct_system_apply_as_netfix_owned_only_while_snapshot_matches(self):
        current = {
            "service": "Wi-Fi",
            "web": {"enabled": True, "server": "proxy.example.com", "port": 8000},
            "secure": {"enabled": True, "server": "proxy.example.com", "port": 8000},
            "socks": {"enabled": False, "server": "", "port": 0},
            "auto_proxy_url": {"enabled": False},
            "auto_discovery": {"enabled": False},
            "ipv6": {"mode": "off"},
        }
        entry = {
            "id": "j-direct",
            "profile_id": "p-direct",
            "network_service": "Wi-Fi",
            "bridge": None,
            "applied_snapshot": residential_proxy._proxy_topology_snapshot(current),
        }
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=current):
            owned = detect_stale_bridge()

        self.assertEqual(owned["status"], "healthy_system_apply")
        self.assertTrue(owned["system_points_to_netfix_apply"])
        self.assertFalse(owned["recovery_available"])

        changed = {**current, "web": {"enabled": True, "server": "other.example.com", "port": 8000}}
        with patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._capture_system_proxy_backup", return_value=changed):
            not_owned = detect_stale_bridge()

        self.assertEqual(not_owned["status"], "system_not_pointing_to_netfix_apply")
        self.assertFalse(not_owned["system_points_to_netfix_apply"])

    def test_direct_system_apply_lifecycle_is_running_without_backend_dependency(self):
        lifecycle = bridge_lifecycle(
            [],
            {
                "ok": True,
                "status": "healthy_system_apply",
                "system_points_to_netfix_apply": True,
                "profile_id": "p-direct",
                "network_service": "Wi-Fi",
            },
        )

        self.assertEqual(lifecycle["status"], "running_system")
        self.assertFalse(lifecycle["requires_netfix_running"])
        self.assertEqual(lifecycle["profile_id"], "p-direct")

    def test_recover_stale_bridge_requires_confirmation_then_restores_backup(self):
        stale = {"ok": True, "status": "stale_bridge", "stale": True, "recovery_available": True}
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "backup": {"service": "Wi-Fi"},
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        with patch("netfix.residential_proxy.detect_stale_bridge", return_value=stale), \
                patch("netfix.residential_proxy._restore_system_proxy_backup") as restore:
            pending = recover_stale_bridge(confirmed=True, confirmation="wrong")
        self.assertEqual(pending["status"], "pending_confirmation")
        restore.assert_not_called()

        with patch("netfix.residential_proxy.detect_stale_bridge", return_value=stale), \
                patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True, "network_service": "Wi-Fi"}) as restore, \
                patch("netfix.residential_proxy.proxy_bridge.stop_bridge", return_value={"ok": True, "missing": True}) as stop, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            recovered = recover_stale_bridge(confirmed=True, confirmation=BRIDGE_RECOVERY_CONFIRMATION)
        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["status"], "recovered")
        restore.assert_called_once_with({"service": "Wi-Fi"})
        stop.assert_called_once_with("b1")
        journal.assert_called_once()

    def test_confirmed_bridge_recovery_also_stops_a_healthy_netfix_owned_bridge(self):
        healthy = {
            "ok": True,
            "status": "healthy",
            "stale": False,
            "recovery_available": False,
            "system_points_to_bridge": True,
        }
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "backup": {"service": "Wi-Fi"},
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        with patch("netfix.residential_proxy.detect_stale_bridge", return_value=healthy), \
                patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True, "network_service": "Wi-Fi"}) as restore, \
                patch("netfix.residential_proxy.proxy_bridge.stop_bridge", return_value={"ok": True}) as stop, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            recovered = recover_stale_bridge(
                confirmed=True,
                confirmation=BRIDGE_RECOVERY_CONFIRMATION,
            )

        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["status"], "recovered")
        self.assertEqual(recovered["recovery_kind"], "stop_and_restore")
        restore.assert_called_once_with({"service": "Wi-Fi"})
        stop.assert_called_once_with("b1")
        journal.assert_called_once()

    def test_healthy_bridge_is_not_stopped_when_restore_fails(self):
        healthy = {
            "ok": True,
            "status": "healthy",
            "stale": False,
            "recovery_available": False,
            "system_points_to_bridge": True,
        }
        entry = {
            "id": "j1",
            "backup": {"service": "Wi-Fi"},
            "bridge": {"id": "b1"},
        }
        with patch("netfix.residential_proxy.detect_stale_bridge", return_value=healthy), \
                patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": False, "error": "restore failed"}), \
                patch("netfix.residential_proxy.proxy_bridge.stop_bridge") as stop, \
                patch("netfix.residential_proxy._write_apply_journal"):
            recovered = recover_stale_bridge(
                confirmed=True,
                confirmation=BRIDGE_RECOVERY_CONFIRMATION,
            )

        self.assertFalse(recovered["ok"])
        self.assertEqual(recovered["status"], "recovery_failed")
        stop.assert_not_called()

    def test_confirmed_recovery_restores_a_matching_direct_system_apply(self):
        owned = {
            "ok": True,
            "status": "healthy_system_apply",
            "stale": False,
            "recovery_available": False,
            "system_points_to_netfix_apply": True,
        }
        entry = {
            "id": "j-direct",
            "profile_id": "p-direct",
            "network_service": "Wi-Fi",
            "backup": {"service": "Wi-Fi"},
            "bridge": None,
        }
        with patch("netfix.residential_proxy.detect_stale_bridge", return_value=owned), \
                patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy._restore_system_proxy_backup", return_value={"ok": True}) as restore, \
                patch("netfix.residential_proxy.proxy_bridge.stop_bridge") as stop, \
                patch("netfix.residential_proxy._write_apply_journal"):
            recovered = recover_stale_bridge(
                confirmed=True,
                confirmation=BRIDGE_RECOVERY_CONFIRMATION,
            )

        self.assertEqual(recovered["status"], "recovered")
        self.assertEqual(recovered["recovery_kind"], "stop_and_restore")
        restore.assert_called_once_with({"service": "Wi-Fi"})
        stop.assert_not_called()

    def test_restart_stale_bridge_restarts_same_loopback_port_without_system_proxy_write(self):
        stale = {
            "ok": True,
            "status": "stale_bridge",
            "stale": True,
            "recovery_available": True,
            "system_points_to_bridge": True,
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "bridge": {"id": "old", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        healthy = {
            "ok": True,
            "status": "healthy",
            "stale": False,
            "recovery_available": False,
            "profile_id": "p1",
        }
        entry = {
            "id": "j1",
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "bridge": stale["bridge"],
        }
        profile = {
            "id": "p1",
            "protocol": "http",
            "host": "proxy.example.com",
            "port": 8000,
            "username": "user",
            "credential_ref": "keychain://netfix-proxy/p1",
        }
        new_bridge = {"id": "new", "listen_host": "127.0.0.1", "listen_port": 19080}
        with patch("netfix.residential_proxy.detect_stale_bridge", side_effect=[stale, healthy]), \
                patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": entry}), \
                patch("netfix.residential_proxy.get_proxy_profiles", return_value=[profile]), \
                patch("netfix.residential_proxy.keychain.get_secret", return_value="pass") as get_secret, \
                patch("netfix.residential_proxy.proxy_bridge.start_http_bridge", return_value={"ok": True, "bridge": new_bridge}) as start, \
                patch("netfix.residential_proxy._restore_system_proxy_backup") as restore, \
                patch("netfix.residential_proxy._run_networksetup") as networksetup, \
                patch("netfix.residential_proxy._write_apply_journal") as journal:
            result = restart_stale_bridge(
                confirmed=True,
                confirmation=BRIDGE_RESTART_CONFIRMATION,
                idle_timeout_s=30,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "restarted")
        self.assertFalse(result["system_proxy_changed"])
        get_secret.assert_called_once()
        start.assert_called_once_with(profile, password="pass", bind_host="127.0.0.1", bind_port=19080, idle_timeout_s=30.0)
        restore.assert_not_called()
        networksetup.assert_not_called()
        saved = journal.call_args.args[0]
        self.assertEqual(saved["bridge"]["id"], "new")
        self.assertEqual(saved["bridge_restart_previous_bridge"]["id"], "old")

    def test_restart_stale_bridge_restarts_authenticated_socks_profile(self):
        stale = {
            "ok": True,
            "status": "stale_bridge",
            "stale": True,
            "recovery_available": True,
            "system_points_to_bridge": True,
            "profile_id": "p1",
            "network_service": "Wi-Fi",
            "bridge": {"id": "old", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        healthy = {
            "ok": True,
            "status": "healthy",
            "stale": False,
            "recovery_available": False,
            "profile_id": "p1",
        }
        profile = {
            "id": "p1",
            "protocol": "socks5",
            "host": "proxy.example.com",
            "port": 1080,
            "username": "user",
            "credential_ref": "keychain://netfix-proxy/p1",
        }
        new_bridge = {"id": "new", "listen_host": "127.0.0.1", "listen_port": 19080}
        with patch("netfix.residential_proxy.detect_stale_bridge", side_effect=[stale, healthy]), \
                patch("netfix.residential_proxy._read_apply_journal", return_value={"last_apply": {"id": "j1", "profile_id": "p1", "bridge": stale["bridge"]}}), \
                patch("netfix.residential_proxy.get_proxy_profiles", return_value=[profile]), \
                patch("netfix.residential_proxy.keychain.get_secret", return_value="pass"), \
                patch("netfix.residential_proxy.proxy_bridge.start_http_bridge", return_value={"ok": True, "bridge": new_bridge}) as start, \
                patch("netfix.residential_proxy._write_apply_journal"):
            result = restart_stale_bridge(
                confirmed=True,
                confirmation=BRIDGE_RESTART_CONFIRMATION,
                idle_timeout_s=30,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "restarted")
        start.assert_called_once_with(profile, password="pass", bind_host="127.0.0.1", bind_port=19080, idle_timeout_s=30.0)

    def test_restart_stale_bridge_blocks_unknown_loopback_listener(self):
        stale = {
            "ok": True,
            "status": "unknown_loopback_listener",
            "stale": True,
            "recovery_available": True,
            "bridge": {"id": "old", "listen_host": "127.0.0.1", "listen_port": 19080},
        }
        with patch("netfix.residential_proxy.detect_stale_bridge", return_value=stale), \
                patch("netfix.residential_proxy.proxy_bridge.start_http_bridge") as start:
            result = restart_stale_bridge(confirmed=True, confirmation=BRIDGE_RESTART_CONFIRMATION)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason_code"], "loopback_port_owned_by_unknown_process")
        start.assert_not_called()

    def test_bridge_lifecycle_flags_recovery_required_for_stale_system_proxy(self):
        stale = {
            "ok": True,
            "status": "stale_bridge",
            "recovery_available": True,
            "system_points_to_bridge": True,
            "network_service": "Wi-Fi",
            "profile_id": "p1",
            "bridge": {"id": "b1", "listen_host": "127.0.0.1", "listen_port": 19080},
            "confirmation": BRIDGE_RECOVERY_CONFIRMATION,
            "port_open": False,
        }
        lifecycle = bridge_lifecycle([], stale)

        self.assertEqual(lifecycle["schema_version"], "netfix_proxy_bridge_lifecycle.v1")
        self.assertEqual(lifecycle["status"], "recovery_required")
        self.assertEqual(lifecycle["primary_action"], "recover_system_proxy")
        self.assertTrue(lifecycle["needs_attention"])
        self.assertTrue(lifecycle["recovery_available"])
        self.assertEqual(lifecycle["confirmation"], BRIDGE_RECOVERY_CONFIRMATION)

    def test_bridge_lifecycle_summarizes_running_system_bridge_audit(self):
        bridge = {
            "id": "b1",
            "listen_host": "127.0.0.1",
            "listen_port": 19080,
            "request_count": 3,
            "active_connections": 1,
            "recent_clients": [{"host": "127.0.0.1", "count": 3}],
        }
        stale = {
            "ok": True,
            "status": "healthy",
            "recovery_available": False,
            "system_points_to_bridge": True,
            "active_bridge": bridge,
        }
        lifecycle = bridge_lifecycle([bridge], stale)

        self.assertEqual(lifecycle["status"], "running_system")
        self.assertEqual(lifecycle["primary_action"], "keep_running_or_rollback")
        self.assertTrue(lifecycle["requires_netfix_running"])
        self.assertEqual(lifecycle["audit"]["request_count"], 3)
        self.assertEqual(lifecycle["audit"]["recent_client_count"], 1)

    def test_bridge_lifecycle_reports_stopped_without_journal(self):
        lifecycle = bridge_lifecycle([], {"ok": True, "status": "no_journal", "recovery_available": False})

        self.assertEqual(lifecycle["status"], "stopped")
        self.assertEqual(lifecycle["primary_action"], "none")
        self.assertFalse(lifecycle["needs_attention"])

    def test_validate_http_proxy_success(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        fake_sock = Mock()
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", return_value=(204, b"", 123.4)) as request:
            result = validate_proxy_profile(parsed["profile"], password="pass")

        self.assertTrue(result["ok"])
        self.assertEqual(result["proxy_check"]["status"], "ok")
        self.assertEqual(result["proxy_check"]["tcp"], "ok")
        self.assertEqual(result["proxy_check"]["http_code"], 204)
        self.assertIn("user:***@", result["proxy_check"]["checked_via"])
        fake_sock.close.assert_called_once()
        request.assert_called_once()

    def test_validate_proxy_can_include_exit_identity_report(self):
        parsed = parse_proxy_input({
            "input": "http://user:pass@proxy.example.com:8000",
            "expected_geo": {"country_code": "US"},
        })
        fake_sock = Mock()
        responses = [
            (204, b"", 12.0),
            (200, b'{"ip":"203.0.113.10"}', 22.0),
            (204, b"", 31.0),
            (204, b"", 32.0),
            (200, b"Success", 33.0),
        ]
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", side_effect=responses) as request, \
                patch("netfix.residential_proxy.ip_intel.get_ip_info", return_value={
                    "ip": "203.0.113.10",
                    "country": "United States",
                    "country_code": "US",
                    "asn": "AS64500 Example ISP",
                    "isp": "Example ISP",
                    "ip_type": "residential",
                    "status": "ok",
                }) as ip_info:
            result = validate_proxy_profile(parsed["profile"], password="pass", include_identity=True)

        self.assertTrue(result["ok"])
        report = result["identity_report"]
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["exit_ip"], "203.0.113.10")
        self.assertEqual(report["target_profile"], "baseline")
        self.assertEqual(report["expected_geo"]["status"], "ok")
        self.assertEqual(len(report["targets"]), 3)
        self.assertTrue(all(item["status"] == "ok" for item in report["targets"]))
        self.assertEqual(request.call_count, 5)
        ip_info.assert_called_once_with("203.0.113.10", timeout=10)

    def test_validation_target_profiles_expose_allowlisted_ai_dev_matrix(self):
        profiles = validation_target_profiles()

        self.assertTrue(profiles["ok"])
        self.assertEqual(profiles["schema_version"], "netfix_proxy_validation_targets.v1")
        self.assertEqual(profiles["default_profile"], "baseline")
        ids = {profile["id"] for profile in profiles["profiles"]}
        self.assertEqual(ids, {"baseline", "ai_dev"})
        self.assertIn("api.deepseek.com", profiles["allowed_hosts"])
        ai_dev = next(profile for profile in profiles["profiles"] if profile["id"] == "ai_dev")
        probe_ids = {probe["id"] for probe in ai_dev["probes"]}
        self.assertIn("github_api", probe_ids)
        self.assertIn("openai_api", probe_ids)
        self.assertIn("deepseek_api", probe_ids)
        self.assertIn("kimi_api", probe_ids)
        self.assertIn("minimax_api", probe_ids)
        self.assertIn("api.minimaxi.com", profiles["allowed_hosts"])

    def test_validate_proxy_passes_selected_target_profile_to_identity_audit(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        fake_sock = Mock()
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", return_value=(204, b"", 12.0)), \
                patch("netfix.residential_proxy.audit_proxy_identity", return_value={
                    "status": "ok",
                    "target_profile": "ai_dev",
                    "targets": [],
                }) as audit:
            result = validate_proxy_profile(
                parsed["profile"],
                password="pass",
                include_identity=True,
                target_profile="ai_dev",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["identity_report"]["target_profile"], "ai_dev")
        self.assertEqual(audit.call_args.kwargs["target_profile"], "ai_dev")

    def test_non_baseline_target_profile_runs_matrix_even_without_identity_flag(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        fake_sock = Mock()
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", return_value=(204, b"", 12.0)), \
                patch("netfix.residential_proxy.audit_proxy_identity", return_value={
                    "status": "ok",
                    "target_profile": "ai_dev",
                    "targets": [],
                }) as audit:
            result = validate_proxy_profile(
                parsed["profile"],
                password="pass",
                include_identity=False,
                target_profile="ai_dev",
            )

        self.assertTrue(result["ok"])
        self.assertIn("identity_report", result)
        self.assertEqual(audit.call_args.kwargs["target_profile"], "ai_dev")

    def test_identity_matrix_failure_fails_proxy_validation(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        fake_sock = Mock()
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", return_value=(204, b"", 12.0)), \
                patch("netfix.residential_proxy.audit_proxy_identity", return_value={
                    "status": "fail",
                    "target_matrix_status": "fail",
                    "target_profile": "ai_dev",
                    "targets": [{"id": "deepseek_api", "status": "fail"}],
                }):
            result = validate_proxy_profile(
                parsed["profile"],
                password="pass",
                include_identity=True,
                target_profile="ai_dev",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["status"], "fail")
        self.assertEqual(result["proxy_check"]["error"], "identity_validation_failed")

    def test_non_baseline_matrix_warning_fails_proxy_validation(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        fake_sock = Mock()
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", return_value=(204, b"", 12.0)), \
                patch("netfix.residential_proxy.audit_proxy_identity", return_value={
                    "status": "warn",
                    "target_matrix_status": "warn",
                    "target_profile": "ai_dev",
                    "targets": [{"id": "openai_api", "status": "warn", "http_code": 503}],
                }):
            result = validate_proxy_profile(
                parsed["profile"],
                password="pass",
                include_identity=True,
                target_profile="ai_dev",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["status"], "fail")
        self.assertEqual(result["proxy_check"]["error"], "target_matrix_not_fully_validated")

    def test_validate_proxy_rejects_unknown_target_profile_before_network(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        with patch("netfix.residential_proxy.socket.create_connection") as connect:
            result = validate_proxy_profile(parsed["profile"], target_profile="private_scan")

        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["error"], "target_profile_not_allowed")
        self.assertEqual(result["proxy_check"]["supported_target_profiles"], ["ai_dev", "baseline"])
        connect.assert_not_called()

    def test_identity_audit_preserves_blocked_custom_target_in_report(self):
        parsed = parse_proxy_input({"input": "http://user:pass@proxy.example.com:8000"})
        blocked_target = "http://169.254.169.254/latest/meta-data"
        responses = [
            (200, b'{"ip":"203.0.113.10"}', 20.0),
            (204, b"", 21.0),
            (204, b"", 22.0),
            (200, b"Success", 23.0),
        ]
        with patch("netfix.residential_proxy.codex._request_http_proxy", side_effect=responses), \
                patch("netfix.residential_proxy.ip_intel.get_ip_info", return_value={
                    "ip": "203.0.113.10",
                    "ip_type": "residential",
                    "status": "ok",
                }):
            report = audit_proxy_identity(parsed["profile"], password="pass", target_urls=[blocked_target])

        blocked = next(item for item in report["targets"] if item.get("error") == "target_url_not_allowed")
        self.assertEqual(blocked["target"], blocked_target)
        self.assertEqual(report["target_matrix_status"], "fail")

    def test_audit_proxy_identity_marks_socks5_dns_risk_without_claiming_ipv6_result(self):
        parsed = parse_proxy_input({"input": "socks5://user:pass@proxy.example.com:1080"})
        responses = [
            (200, b'{"ip":"198.51.100.20"}', 20.0),
            (204, b"", 21.0),
            (204, b"", 22.0),
            (200, b"Success", 23.0),
        ]
        with patch("netfix.residential_proxy.codex._request_socks5_proxy", side_effect=responses), \
                patch("netfix.residential_proxy.ip_intel.get_ip_info", return_value={
                    "ip": "198.51.100.20",
                    "ip_type": "unknown",
                    "status": "ok",
                }):
            report = audit_proxy_identity(parsed["profile"], password="pass")

        self.assertEqual(report["exit_ip"], "198.51.100.20")
        self.assertEqual(report["dns_leak"]["status"], "warn")
        self.assertIn(report["ipv6_leak"]["status"], {"unknown", "ok", "warn"})
        self.assertIn("无法可靠判断", " ".join(report["warnings"]))

    def test_ipv6_leak_assessment_checks_macos_ipv6_enabled_state(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        getinfo = "IPv6: Automatic\nIPv6 IP address: 2001:db8::1\nIPv6 Router: 2001:db8::ff\n"
        with patch("netfix.residential_proxy.sys.platform", "darwin"), \
                patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._run_networksetup", return_value={"stdout": getinfo}):
            result = residential_proxy._ipv6_leak_assessment(parsed["profile"])
        self.assertEqual(result["status"], "warn")
        self.assertTrue(result["system_ipv6_enabled"])
        self.assertEqual(result["network_service"], "Wi-Fi")

    def test_ipv6_leak_assessment_marks_disabled_macos_ipv6_ok(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        getinfo = "IPv6: Off\n"
        with patch("netfix.residential_proxy.sys.platform", "darwin"), \
                patch("netfix.residential_proxy.choose_network_service", return_value="Wi-Fi"), \
                patch("netfix.residential_proxy._run_networksetup", return_value={"stdout": getinfo}):
            result = residential_proxy._ipv6_leak_assessment(parsed["profile"])
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["system_ipv6_enabled"])

    def test_validate_proxy_tcp_timeout(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        with patch("netfix.residential_proxy.socket.create_connection", side_effect=TimeoutError("timed out")):
            result = validate_proxy_profile(parsed["profile"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["error"], "timeout")

    def test_validate_proxy_dns_failure(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        with patch("netfix.residential_proxy.socket.create_connection", side_effect=OSError("[Errno 8] nodename nor servname provided, or not known")):
            result = validate_proxy_profile(parsed["profile"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["error"], "dns_failed")

    def test_validate_proxy_rejects_unapproved_target_url(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        with patch("netfix.residential_proxy.socket.create_connection") as connect:
            result = validate_proxy_profile(parsed["profile"], target_url="http://169.254.169.254/latest/meta-data")
        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["error"], "target_url_not_allowed")
        connect.assert_not_called()

    def test_validate_proxy_auth_required(self):
        parsed = parse_proxy_input({"input": "http://proxy.example.com:8000"})
        err = HTTPError("https://www.gstatic.com/generate_204", 407, "Proxy Auth", {}, None)
        fake_sock = Mock()
        with patch("netfix.residential_proxy.socket.create_connection", return_value=fake_sock), \
                patch("netfix.residential_proxy.codex._request_http_proxy", side_effect=err):
            result = validate_proxy_profile(parsed["profile"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["proxy_check"]["http_code"], 407)
        self.assertEqual(result["proxy_check"]["auth"], "failed")
        self.assertEqual(result["proxy_check"]["error"], "proxy_auth_required")


if __name__ == "__main__":
    unittest.main()
