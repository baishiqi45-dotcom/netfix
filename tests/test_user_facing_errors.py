"""Tests for the unified user-facing error map and dashboard state resolver.

These tests cover the five scenarios the original request demanded:
1. account / password wrong (proxy_auth_failed)
2. proxy server unreachable (proxy_unreachable)
3. DNS failure (dns_failed)
4. IPv6 fallback not-confirmed-leak (ipv6_fallback_risk)
5. backend / app error (backend_unreachable)
"""
from __future__ import annotations

import pytest

from netfix import dashboard_state, user_facing_errors


REQUIRED_CODES = {
    "proxy_auth_failed",
    "proxy_unreachable",
    "dns_failed",
    "ipv6_leak_confirmed",
    "ipv6_fallback_risk",
    "ipv6_leak_confirmed",
    "system_proxy_not_set",
    "fix_command_failed",
    "fix_verification_failed",
    "fix_cancelled",
    "backend_unreachable",
    "decode_failed",
    "unsupported_input_format",
    "missing_required_field",
    "llm_disabled",
    "missing_api_key",
}


def test_all_required_codes_present():
    codes = {entry["code"] for entry in user_facing_errors.all_codes()}
    missing = REQUIRED_CODES - codes
    assert not missing, f"missing user-facing codes: {sorted(missing)}"


def test_every_entry_has_three_layer_structure():
    for entry in user_facing_errors.all_codes():
        assert "code" in entry
        assert "headline" in entry and entry["headline"]
        assert "next_step" in entry and entry["next_step"]
        # technical is allowed to be empty
        assert "technical" in entry


def test_classify_account_password_wrong():
    card = user_facing_errors.classify_text("HTTP 407 Proxy authentication failed")
    assert card["code"] == "proxy_auth_failed"
    assert "账号" in card["headline"] or "密码" in card["headline"]
    assert "服务商" in card["next_step"]


def test_classify_proxy_unreachable():
    card = user_facing_errors.classify_text("Connection refused by upstream")
    assert card["code"] == "proxy_unreachable"
    assert "代理" in card["headline"]
    assert "地址" in card["next_step"] or "端口" in card["next_step"]


def test_classify_dns_failure():
    card = user_facing_errors.classify_text("nodename nor servname provided, or name not known")
    assert card["code"] == "dns_failed"
    assert "DNS" in card["headline"] or "解析" in card["headline"]


def test_classify_ipv6_fallback_not_confirmed_leak():
    card = user_facing_errors.classify_text("proxy active and ipv6 default route present no public ipv6 observed")
    assert card["code"] == "ipv6_fallback_risk"
    assert "IPv6" in card["headline"] or "公网" in card["headline"]
    # must not tell user to keep pressing fix buttons
    assert "不用反复" in card["next_step"] or "一般可以继续" in card["next_step"]


def test_classify_backend_error():
    card = user_facing_errors.classify_text("connection refused: app 没有连上后端")
    assert card["code"] in {"proxy_unreachable", "backend_unreachable"}
    assert card["headline"]


def test_classify_timeout():
    card = user_facing_errors.classify_text("Request timed out after 10s")
    assert card["code"] == "timeout"


def test_classify_unsupported_format():
    card = user_facing_errors.classify_text("ss://YWJjZGU@127.0.0.1:8388 not supported")
    assert card["code"] == "unsupported_input_format"


def test_render_error_prefers_code():
    card = user_facing_errors.render_error(code="proxy_auth_failed", message="totally different text")
    assert card["code"] == "proxy_auth_failed"
    assert "source" in card and card["source"] == "code"


def test_render_error_falls_back_to_message():
    card = user_facing_errors.render_error(message="connect timeout while dialing")
    assert card["code"] in {"proxy_unreachable", "timeout"}
    assert card["source"] == "message"


def test_render_error_falls_back_to_http_status():
    card = user_facing_errors.render_error(http_status=502)
    assert card["code"] == "http_502"
    assert card["source"] == "http_status"


def test_http_status_table_known_and_unknown():
    known = user_facing_errors.lookup_http_status(409)
    assert known["code"] == "http_409"
    unknown = user_facing_errors.lookup_http_status(418)
    assert unknown["code"] == "http_418"
    assert unknown["headline"]


def test_scrub_internal_phrases():
    text = "ipv6_leak default route: tier 2 fix required"
    out = user_facing_errors.scrub_internal_phrases(text)
    assert "ipv6_leak" not in out
    assert "IPv6 旁路" in out
    assert "默认路由" in out
    assert "tier 2" not in out


# ---- dashboard_state -------------------------------------------------------

def test_dashboard_state_no_proxy():
    payload = dashboard_state.resolve(saved_profile_count=0)
    assert payload["state"] == "no_proxy"
    assert "粘贴" in payload["next_step"]
    assert payload["bridge_in_use"] is False
    assert payload["bridge_needs_recovery"] is False


def test_dashboard_state_proxy_saved():
    payload = dashboard_state.resolve(saved_profile_count=1, bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}})
    assert payload["state"] == "proxy_saved"
    assert "开始使用" in payload["headline"]


def test_dashboard_state_proxy_in_use():
    payload = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
    )
    assert payload["state"] == "proxy_in_use"
    assert payload["bridge_in_use"] is True


def test_dashboard_state_network_recovery():
    payload = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "recovery_required", "needs_attention": True}, "stale_check": {"recovery_available": True}},
    )
    assert payload["state"] == "network_recovery"
    assert "恢复" in payload["next_step"]


def test_dashboard_state_proxy_degraded_when_running_but_check_failed():
    payload = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
        last_diagnostic_status="fail",
    )
    assert payload["state"] == "proxy_degraded"


@pytest.mark.parametrize(
    "code",
    sorted(REQUIRED_CODES),
)
def test_each_required_code_resolves_to_headline(code):
    card = user_facing_errors.lookup_code(code)
    assert card is not None, f"missing code {code}"
    assert card["headline"], f"empty headline for {code}"
    assert card["next_step"], f"empty next step for {code}"
