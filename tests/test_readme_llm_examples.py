from pathlib import Path


README = Path(__file__).resolve().parents[1] / "README.md"
DEVELOPER_INTERFACES = Path(__file__).resolve().parents[1] / "docs" / "developer" / "interfaces.md"


def test_developer_docs_llm_curl_examples_use_canonical_endpoints_and_consent():
    text = DEVELOPER_INTERFACES.read_text(encoding="utf-8")

    assert '"enabled":true' in text
    assert '"api_key"' in text
    assert '"fallback":{"enabled":true' in text
    assert '"chain":["deepseek","moonshot_kimi","minimax","qwen"]' in text
    assert '"vision_chain":["minimax","moonshot_kimi","qwen"]' in text
    assert '"persist_usage_ledger":true' in text
    assert '"upload_confirmed":true' in text
    assert "NETFIX_LLM_API_KEY_DEEPSEEK" in text
    assert "/settings/llm" in text
    assert "/explain_llm" in text
    assert "/llm/explain" not in text


def test_developer_docs_mcp_domestic_llm_image_gate():
    text = DEVELOPER_INTERFACES.read_text(encoding="utf-8")

    assert "netfix_llm_providers" in text
    assert "netfix_explain_llm" in text
    assert 'mode: "image_question"' in text
    assert "upload_confirmed: true" in text
    assert "data:image/png;base64,..." in text
    assert "DeepSeek is the default text-explanation route" in text
    assert "no MCP tool can save an AI key or a" in text


def test_root_readme_keeps_optional_ai_interfaces_out_of_the_user_path():
    text = README.read_text(encoding="utf-8")

    assert "netfix_llm_providers" not in text
    assert "/settings/llm" not in text
    assert "NETFIX_LLM_API_KEY_DEEPSEEK" not in text


def test_readme_documents_authenticated_socks_bridge_support():
    text = README.read_text(encoding="utf-8")

    assert "有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发" in text
    assert "开始使用代理" in text
    assert "认证 SOCKS 不承诺一键系统应用" not in text
