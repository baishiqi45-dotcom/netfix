from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
README = ROOT / "README.md"
README_EN = ROOT / "README.en.md"


def test_macos_settings_has_app_bundle_mcp_copy_tab():
    source = SETTINGS.read_text(encoding="utf-8")

    assert "private var agentTab: some View" in source
    assert 'Label("AI 编程助手", systemImage: "terminal")' in source
    assert "把 Netfix 接进 AI 编程助手" in source
    assert "已下载 App 的用户不用找仓库脚本" in source
    assert 'appendingPathComponent("netfix/mcp_server.py")' in source
    assert "codex mcp add netfix -- python3" in source
    assert "复制 Kimi/通用配置" in source
    assert "command: python3" in source
    assert "NSPasteboard.general.setString" in source
    assert "MCP 不保存 API Key 或代理密码" in source


def test_readmes_explain_app_mcp_copy_path_before_source_script():
    readme = README.read_text(encoding="utf-8")
    readme_en = README_EN.read_text(encoding="utf-8")

    assert "设置 → AI 编程助手 → 复制给 Codex" in readme
    assert "复制 Kimi/通用配置" in readme
    assert readme.index("设置 → AI 编程助手") < readme.index("./scripts/install_mcp.sh --all")
    assert "Settings -> AI Coding Assistant -> Copy for Codex" in readme_en
    assert "Copy Kimi / generic config" in readme_en
