from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_open_source_license_security_and_mcp_installer_exist():
    assert (ROOT / "LICENSE").exists()
    assert (ROOT / "SECURITY.md").exists()
    assert (ROOT / "CONTRIBUTING.md").exists()
    assert (ROOT / "CODE_OF_CONDUCT.md").exists()
    assert (ROOT / ".github" / "repository.yml").exists()
    assert (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "support_question.md").exists()
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "safe_diagnostic_report.md").exists()
    installer = ROOT / "scripts" / "install_mcp.sh"
    codex_installer = ROOT / "scripts" / "install_codex_mcp_from_github.sh"
    mac_installer = ROOT / "scripts" / "install_mac_app_from_github.sh"
    assert installer.exists()
    assert codex_installer.exists()
    assert mac_installer.exists()
    text = installer.read_text(encoding="utf-8")
    codex_text = codex_installer.read_text(encoding="utf-8")
    mac_text = mac_installer.read_text(encoding="utf-8")
    assert "codex mcp add netfix" in text
    assert "Automatic Kimi MCP registration is not enabled" in text
    assert "netfix/mcp_server.py" in text
    assert "--dry-run" in text
    assert "cd /tmp" in text
    assert "raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_codex_mcp_from_github.sh" in codex_text
    assert "codex mcp add netfix -- python3" in codex_text
    assert "NETFIX_ARCHIVE_URL" in codex_text
    assert 'REF="${NETFIX_REF:-main}"' in codex_text
    assert 'REF_KIND="${NETFIX_REF_KIND:-heads}"' in codex_text
    assert "NETFIX_REF_KIND" in codex_text
    assert "--dry-run" in codex_text
    assert "--uninstall" in codex_text
    assert "Will not read or send proxy passwords" in codex_text
    assert "zipfile.ZipFile" in codex_text
    assert "need_cmd unzip" not in codex_text
    assert "releases/download/${RELEASE_TAG}/Netfix-" in mac_text
    assert "raw.githubusercontent.com/baishiqi45-dotcom/netfix/main/scripts/install_mac_app_from_github.sh" in mac_text
    assert "v${VERSION}-qa.1" in mac_text
    assert "DEFAULT_DMG_SHA256" in mac_text
    assert "82815efd5888e60b914a1da303e2d42835a03b6b588f87d515346426eb57183b" in mac_text
    assert "hdiutil attach" in mac_text
    assert "ditto" in mac_text
    assert "NETFIX_DMG_URL" in mac_text
    assert "--dry-run" in mac_text
    assert "--uninstall" in mac_text
    assert "Will not read or send proxy passwords" in mac_text
    assert "codex mcp add netfix -- python3" in mac_text
    assert "Bundled Netfix MCP smoke check passed" in mac_text
    assert "MiniMax-compatible" in mac_text
    assert "mcpServers" in mac_text
    assert "设置 → 代理" in mac_text


def test_github_readme_has_bilingual_visual_assets_and_metadata():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    repository = (ROOT / ".github" / "repository.yml").read_text(encoding="utf-8")

    for rel in [
        "assets/github/hero.zh.svg",
        "assets/github/hero.zh.png",
        "assets/github/hero.en.svg",
        "assets/github/hero.en.png",
        "assets/github/workflow.zh.svg",
        "assets/github/workflow.zh.png",
        "assets/github/workflow.en.svg",
        "assets/github/workflow.en.png",
        "assets/github/social-preview.zh.svg",
        "assets/github/social-preview.zh.png",
        "assets/github/social-preview.en.svg",
        "assets/github/social-preview.en.png",
        "docs/github/STAR_GUIDE.md",
        "docs/github/SCREENSHOTS.md",
        "docs/github/RELEASE_NOTES_V0.2.0.md",
    ]:
        assert (ROOT / rel).exists()

    assert "assets/github/hero.zh.png" in readme
    assert "assets/github/workflow.zh.png" in readme
    assert "assets/github/hero.en.png" in readme_en
    assert "assets/github/workflow.en.png" in readme_en
    assert "<repo>" not in readme
    assert "<repo>" not in readme_en
    assert "network-diagnostics" in repository
    assert "mcp-server" in repository


def test_public_docs_do_not_use_author_local_paths_or_pipx_claim():
    public_files = [
        ROOT / "README.md",
        ROOT / "README.en.md",
        ROOT / "AGENTS.md",
        ROOT / "OPEN_SOURCE.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in public_files)

    assert "/Users/local-author" not in text
    assert "Desktop/private-project" not in text
    assert "pipx install ." not in text
    assert "scripts/install_mcp.sh" in text
    assert "install_codex_mcp_from_github.sh" in text
    assert "install_mac_app_from_github.sh" in text
    assert "scripts/release_preflight.py" in text


def test_public_templates_warn_against_posting_credentials():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "SECURITY.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "support_question.md",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "safe_diagnostic_report.md",
        ]
    )
    assert "proxy passwords" in text
    assert "API keys" in text
    assert "raw reports" in text
    assert "<password>" in text


def test_open_source_docs_explain_tracked_release_artifact_gate():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [ROOT / "README.md", ROOT / "OPEN_SOURCE.md", ROOT / "CONTRIBUTING.md"]
    )
    assert "tracked-release-artifact" in text
    assert "git ls-files 'Netfix-*.dmg' 'Netfix-*.zip'" in text
    assert "git rm --cached Netfix-0.2.0.dmg Netfix-0.2.0-macos.zip" in text
    assert "python3 scripts/release_preflight.py --with-dmg-smoke" in text
    assert "--write-record gui/macos/.build/release-export/Netfix-0.2.0-macos/download-qa-preflight.json" in text
    assert "python3 verify-download.py --require-recorded-preflight" in text


def test_ci_workspace_release_audit_is_a_hard_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python3 scripts/release_audit.py --scope workspace --root ." in workflow
    assert "python3 scripts/release_audit.py --scope workspace --root . --warn-only" not in workflow


def test_docs_and_cases_do_not_contain_author_paths_or_live_proxy_hosts():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in [ROOT / "docs", ROOT / "cases"]
        for path in folder.glob("*.md")
    )
    assert "/Users/local-author" not in text
    assert "Desktop/private-project" not in text
    assert "direct.miyaip" not in text
    assert "miyaip" not in text
    assert "api.llmapi.pro" not in text
