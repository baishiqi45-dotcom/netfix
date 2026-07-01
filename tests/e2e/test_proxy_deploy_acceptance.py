import os
import sys

import pytest

from netfix.residential_proxy import (
    PROXY_ROLLBACK_CONFIRMATION,
    SYSTEM_APPLY_CONFIRMATION,
    apply_proxy_profile,
    parse_proxy_input,
    rollback_last_proxy_apply,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("NETFIX_ENABLE_NETWORKSETUP_E2E") != "1",
    reason="real networksetup e2e is opt-in; set NETFIX_ENABLE_NETWORKSETUP_E2E=1",
)


def test_proxy_deploy_apply_then_rollback_real_network_service():
    if sys.platform != "darwin":
        pytest.skip("networksetup e2e only runs on macOS")
    service = os.environ.get("NETFIX_E2E_NETWORK_SERVICE", "").strip()
    proxy_input = os.environ.get("NETFIX_E2E_PROXY_INPUT", "").strip()
    if not service or not proxy_input:
        pytest.skip("set NETFIX_E2E_NETWORK_SERVICE and NETFIX_E2E_PROXY_INPUT to run this test")

    parsed = parse_proxy_input({"input": proxy_input})
    assert parsed["ok"], parsed.get("errors")
    profile = parsed["profile"]

    apply_result = None
    try:
        apply_result = apply_proxy_profile(
            profile,
            mode="system",
            confirmed=True,
            confirmation=SYSTEM_APPLY_CONFIRMATION,
            network_service=service,
            verify=False,
            rollback_on_verify_failure=True,
        )
        assert apply_result["ok"], apply_result
        assert apply_result["status"] == "applied"
        assert apply_result["network_service"] == service
        assert apply_result["rollback_available"] is True
    finally:
        rollback = rollback_last_proxy_apply(
            confirmed=True,
            confirmation=PROXY_ROLLBACK_CONFIRMATION,
        )
        if apply_result and apply_result.get("ok"):
            assert rollback["ok"], rollback
            assert rollback["status"] == "rolled_back"
