from pathlib import Path


README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_llm_curl_examples_enable_cloud_and_confirm_upload():
    text = README.read_text(encoding="utf-8")

    assert '"enabled":true' in text
    assert '"api_key":"$DEEPSEEK_API_KEY"' in text
    assert '"fallback":{"enabled":true' in text
    assert '"chain":["deepseek","moonshot_kimi","minimax","qwen"]' in text
    assert '"vision_chain":["minimax","moonshot_kimi","qwen"]' in text
    assert '"persist_usage_ledger":true' in text
    assert '"upload_confirmed":true' in text
    assert "NETFIX_LLM_API_KEY_DEEPSEEK" in text


def test_readme_documents_mcp_domestic_llm_image_gate():
    text = README.read_text(encoding="utf-8")

    assert "netfix_llm_providers" in text
    assert "netfix_explain_llm" in text
    assert 'mode: "image_question"' in text
    assert "upload_confirmed: true" in text
    assert "data:image/..." in text
    assert "DeepSeek 是默认文本解释主力" in text
    assert "不能保存 API Key 或代理密码" in text


def test_readme_documents_authenticated_socks_bridge_support():
    text = README.read_text(encoding="utf-8")

    assert "有账号密码的 HTTP/HTTPS/SOCKS 代理会由 Netfix 本机转发" in text
    assert "开始使用代理" in text
    assert "认证 SOCKS 不承诺一键系统应用" not in text
