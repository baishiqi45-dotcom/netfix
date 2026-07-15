from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
README = ROOT / "README.md"
README_EN = ROOT / "README.en.md"
DEVELOPER_INTERFACES = ROOT / "docs" / "developer" / "interfaces.md"


def test_macos_settings_has_app_bundle_mcp_copy_tab():
    source = SETTINGS.read_text(encoding="utf-8")

    assert "private var agentTab: some View" in source
    # MCP 属于高级层；普通用户的“AI 解释”有独立设置层。
    assert "aiLayerView" in source
    assert 'case "ai":' in source
    assert "advancedIntroSection\n            agentTab" in source
    assert "把 Netfix 接进 AI 编程助手" in source
    assert "已下载 App 的用户不用找仓库脚本" in source
    assert 'appendingPathComponent("netfix/mcp_server.py")' in source
    assert "codex mcp add netfix -- python3" in source
    assert "复制 Kimi/通用配置" in source
    assert "command: python3" in source
    assert "NSPasteboard.general.setString" in source
    assert "MCP 不保存 AI 密钥或代理密码" in source


def test_developer_docs_explain_app_mcp_copy_path_and_source_script():
    readme = README.read_text(encoding="utf-8")
    readme_en = README_EN.read_text(encoding="utf-8")
    interfaces = DEVELOPER_INTERFACES.read_text(encoding="utf-8")

    assert "./scripts/install_mcp.sh --all" not in readme
    assert "./scripts/install_mcp.sh --all" not in readme_en
    assert "Settings -> Advanced &" in interfaces
    assert "Copy for Codex" in interfaces
    assert "Copy Kimi /" in interfaces
    assert "./scripts/install_mcp.sh --all --dry-run" in interfaces
