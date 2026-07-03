"""User-experience hard constraints for the public installers and README.

These tests do not exercise the scripts. They check that the strings an
ordinary user actually sees still appear after future edits:

* QA / unsigned DMG warning is loud, in the installer's finished banner,
  not just hidden inside --help.
* The installer prints a one-line uninstall command and the App install
  path after a successful run.
* The Kimi / Claude / Cursor / MiniMax-compatible MCP installer gives the exact config file
  paths and a copy/paste JSON block.
* Chinese README first screen still leads with the paste-proxy value
  prop and warns that the current DMG is QA-only.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mac_installer_finished_banner_mentions_app_path_uninstall_and_qa():
    text = (ROOT / "scripts" / "install_mac_app_from_github.sh").read_text(encoding="utf-8")
    # New finished banner must be loud and contain all four signals.
    assert "Netfix 安装完成" in text
    assert "App 位置" in text
    assert "${APP_DEST}" in text
    assert "卸载命令" in text
    assert "未签名未公证" in text
    assert "v0.2.0-qa.1 预览版" in text
    # One-line app install must also leave local agents with usable MCP config.
    assert "Bundled Netfix MCP smoke check passed" in text
    assert "Kimi / Claude Desktop / Cursor / MiniMax-compatible" in text
    assert "mcpServers" in text
    assert '"command": "python3"' in text
    assert '"args": ["${MCP_SERVER}"]' in text
    assert "~/.kimi/mcp.json" in text
    assert "claude_desktop_config.json" in text
    assert ".cursor/mcp.json" in text
    # And it must say where a normal user pastes proxy credentials next.
    assert "设置 → 代理" in text
    assert "检查并保存到这台 Mac" in text
    assert "开始使用这台 Mac 上网" in text
    assert "当前出口 IP" in text
    assert "ss://" in text and "vmess://" in text
    assert "requires macOS 13 or newer" in text
    assert "--connect-timeout 10 --max-time 600 --retry 2" in text
    # Original safety assertions are still required.
    assert "Will not read or send proxy passwords" in text


def test_mcp_installer_gives_kimi_claude_cursor_paths_and_json_block():
    text = (ROOT / "scripts" / "install_mcp.sh").read_text(encoding="utf-8")
    # Existing string required by test_open_source_readiness.py must stay.
    assert "Automatic Kimi MCP registration is not enabled" in text
    # New UX constraints.
    assert "~/.kimi/mcp.json" in text
    assert "Library/Application Support/Claude/claude_desktop_config.json" in text
    assert ".cursor/mcp.json" in text
    assert "mcpServers" in text
    assert "command\": \"python3\"" in text
    assert "args\": [" in text
    assert "Netfix MCP 配置完成" in text


def test_chinese_readme_first_screen_states_paste_proxy_and_qa_warning():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    head = text.split("\n", 80)[:80]
    head_text = "\n".join(head)
    # First screen promise (KIMI audit §1.5 requirement).
    assert "粘贴" in head_text and "已有的代理" in head_text
    assert "当前出口 IP" in head_text
    assert "macOS 13" in head_text
    # Loud QA warning block.
    assert "未签名" in head_text or "未公证" in head_text
    assert "仍要打开" in head_text
    # Boundary copy still present so casual readers see Netfix is not a node seller.
    assert "不卖代理" in text
    # Uninstall command is reachable within the first 200 lines (above the fold for copy/paste).
    top = "\n".join(text.splitlines()[:200])
    assert "--uninstall" in top


def test_english_readme_first_screen_states_paste_proxy_and_qa_warning():
    text = (ROOT / "README.en.md").read_text(encoding="utf-8")
    head = "\n".join(text.splitlines()[:80])
    assert "paste" in head.lower()
    assert "unsigned" in head.lower() or "not notarized" in head.lower()
    assert "Open Anyway" in head or "open anyway" in head
    assert "no proxy selling" in text.lower() or "do not sell proxies" in text.lower()


def test_proxy_setup_view_has_placeholder_examples_and_unsupported_hint():
    text = (ROOT / "gui" / "macos" / "Sources" / "Views" / "ProxySetupView.swift").read_text(encoding="utf-8")
    # New placeholder must show a concrete example, supported formats, and unsupported schemes.
    assert "proxy.example.com:8001" in text
    assert "http://user:pass@host:port" in text or "socks5h://" in text
    assert "ss://" in text
    assert "vmess://" in text
    assert "subscript" in text.lower() or "订阅链接" in text


def test_issue_templates_warn_against_posting_credentials():
    base = ROOT / ".github" / "ISSUE_TEMPLATE"
    text = "\n".join(p.read_text(encoding="utf-8") for p in base.glob("*.md"))
    assert "proxy passwords" in text
    assert "API keys" in text
    assert "<password>" in text
