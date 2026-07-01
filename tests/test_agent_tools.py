from unittest.mock import patch

from netfix import agent_tools


def test_agent_tools_redact_command_errors_before_returning_to_mcp():
    secret_url = "http://user:demo-password@proxy.example.com:8000"
    with patch("netfix.agent_tools.detect_system_proxy", return_value={"https": secret_url}), \
            patch(
                "netfix.agent_tools.run_command",
                return_value={
                    "ok": False,
                    "stdout": "",
                    "stderr": f"curl failed {secret_url} sk-live-secret-token-1234567890abc",
                    "returncode": 56,
                },
            ):
        result = agent_tools.test_proxy_for_url("https://example.com")

    encoded = str(result)
    assert "user:***@" in encoded
    assert "demo-password" not in encoded
    assert "sk-live-secret-token" not in encoded
