from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"


def test_macos_proxy_import_preview_is_visible_and_secret_safe():
    settings = SETTINGS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "func importProxyPreview(input: String, limit: Int = 50, protocolHint: String = \"auto\")" in api_client
    assert 'path: "proxy/import-preview"' in api_client
    assert "struct ProxyImportPreviewResponse" in models
    assert "struct ProxyImportCandidate" in models
    assert 'case schemaVersion = "schema_version"' in models
    assert 'case lineNumber = "line_number"' in models
    assert 'case redactedURL = "redacted_url"' in models

    assert "@State private var proxyImportPreviewResult: ProxyImportPreviewResponse?" in settings
    assert "@State private var proxyStartMonitorOnSave = true" in settings
    assert 'Label("只检查，不保存", systemImage: "checklist")' in settings
    assert 'Toggle("保存后自动启动健康监控"' in settings
    assert "await importProxyPreview()" in settings
    assert "startMonitor: proxyStartMonitorOnSave" in settings
    assert "proxyImportPreviewBlock" in settings
    assert "useProxyImportCandidate" in settings
    assert "saveProxyImportCandidate" in settings
    assert "proxyInputLine" in settings
    assert "TextEditor(text: $proxyInput)" in settings
    assert "打开你的代理服务后台" in settings
    assert "复制包含地址、端口、用户名、密码的整行" in settings
    assert "proxy.example.com:8001:username:password" in settings
    assert 'Picker("参数类型", selection: $proxyProtocolHint)' in settings
    assert "自动判断" in settings
    assert "SOCKS5" in settings
    assert "不要只复制出口 IP" in settings
    assert "预检不会保存代理密码" in settings
    assert 'Label("检查并保存到这台 Mac", systemImage: "tray.and.arrow.down")' in settings
    assert "检查并保存只是把参数放到本机，暂不影响浏览器" in settings
    assert "下一步：开始使用代理" in settings
    assert "await saveProxyProfile(input: selected)" in settings
    assert "proxyStatus = \"正在保存并启动监控...\"" in settings
    assert "saveProxyProfile(input: String, startMonitor: Bool = true, targetProfile: String = \"baseline\", protocolHint: String = \"auto\")" in api_client
    assert "protocolHint: proxyProtocolHint" in settings
    assert 'body["start_monitor"] = startMonitor' in api_client
    assert "let monitor: ProxyMonitorState?" in models
