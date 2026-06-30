from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
NETFIX_APP = ROOT / "gui" / "macos" / "Sources" / "NetfixApp.swift"
WELCOME_VIEW = ROOT / "gui" / "macos" / "Sources" / "Views" / "WelcomeView.swift"
PROXY_SETUP_VIEW = ROOT / "gui" / "macos" / "Sources" / "Views" / "ProxySetupView.swift"
PRIVACY_VIEW = ROOT / "gui" / "macos" / "Sources" / "Views" / "PrivacyDisclosureView.swift"
DASHBOARD_VIEW = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
SETTINGS_VIEW = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"


def test_welcome_skip_still_shows_privacy_disclosure_before_completion():
    app = NETFIX_APP.read_text(encoding="utf-8")
    welcome = WELCOME_VIEW.read_text(encoding="utf-8")
    welcome_branch = re.search(r"case \.welcome:(.*?)case \.privacy:", app, re.S)

    assert 'Button("跳过介绍")' in welcome
    assert welcome_branch is not None
    assert "onSkip: { onboardingStep = .privacy }" in welcome_branch.group(1)
    assert "onSkip: { completeOnboarding() }" not in welcome_branch.group(1)


def test_proxy_setup_does_not_claim_client_detected_when_environment_has_no_client():
    proxy_setup = PROXY_SETUP_VIEW.read_text(encoding="utf-8")

    assert 'Text("添加代理参数")' in proxy_setup
    assert 'if let client = env.guiClient, !client.isEmpty {' in proxy_setup
    assert 'client: client,' in proxy_setup
    assert '"已识别代理客户端"' not in proxy_setup


def test_proxy_setup_exposes_one_paste_proxy_onboarding_path():
    proxy_setup = PROXY_SETUP_VIEW.read_text(encoding="utf-8")

    assert "有供应商给你的代理参数？直接粘贴" in proxy_setup
    assert "TextEditor(text: $proxyInput)" in proxy_setup
    assert 'Button("预检")' in proxy_setup
    assert 'Button("保存到这台 Mac")' in proxy_setup
    assert "importProxyPreview(input: proxyInput" in proxy_setup
    assert "saveProxyProfile(input: proxyInput, startMonitor: true" in proxy_setup
    assert "密码保存到本机密码库" in proxy_setup
    assert "代理服务商后台复制整行 HTTP/SOCKS 连接参数" in proxy_setup
    assert "不是只复制出口 IP" in proxy_setup
    assert "还没影响浏览器" in proxy_setup
    assert "去部署到这台 Mac" in proxy_setup
    save_fn = proxy_setup.split("private func saveProxyInput() async", 1)[1].split("private func bindClient()", 1)[0]
    assert "onContinue()" not in save_fn


def test_macos_primary_ui_does_not_expose_tier_language():
    visible_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PRIVACY_VIEW, DASHBOARD_VIEW, SETTINGS_VIEW)
    )

    assert "自动修复 Tier" not in visible_sources
    assert "Tier 1" not in visible_sources
    assert "Tier 2" not in visible_sources
    assert "低风险问题" in visible_sources
    assert "修改网络设置" in visible_sources
