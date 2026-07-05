from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODEL = ROOT / "gui" / "macos" / "Sources" / "Models" / "DashboardInsights.swift"


def test_dashboard_exposes_plain_language_network_insights():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")

    assert "struct DashboardInsightsResponse" in model
    assert "struct NetworkActivitySummary" in model
    assert "struct ProxyHealthTrend" in model
    assert "func dashboardInsights() async throws -> DashboardInsightsResponse" in api_client
    assert 'path: "dashboard/insights"' in api_client

    assert 'Label("谁在占用网络", systemImage: "arrow.up.arrow.down.circle")' in dashboard
    assert 'Label("最近卡顿", systemImage: "clock.arrow.circlepath")' in dashboard
    assert 'Label("代理近 10 次", systemImage: "waveform.path.ecg")' in dashboard
    assert 'Button("别再提醒这个 App")' in dashboard
    assert "后台上传疑似挤满网络" in dashboard
    assert "还没有速度、延迟和后台占用数据" in dashboard
    assert "network_quality / bandwidth_hog" not in dashboard
    assert "network_quality 诊断结果" not in dashboard


def test_settings_exposes_privacy_safe_activity_monitor_controls():
    settings = SETTINGS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")

    assert "NetworkActivityIgnoreRule" in model
    assert "func networkActivitySettings() async throws -> NetworkActivitySettingsResponse" in api_client
    assert "func saveNetworkActivitySettings(" in api_client
    assert 'path: "settings/network-activity"' in api_client

    assert 'Section("卡顿检测与隐私")' in settings
    assert 'Toggle("显示哪个 App 正在大量上传或下载"' in settings
    assert "只记录 App 名称、上传/下载方向和粗略速度" in settings
    assert "不看网址、远端 IP、聊天内容，也不抓包" in settings
    assert "哪些 App 不提醒我" in settings
    assert 'Button("保存卡顿检测设置")' in settings
    assert "saveNetworkActivitySettings()" in settings


def test_proxy_and_ai_labels_stay_plain_language():
    settings = SETTINGS.read_text(encoding="utf-8")

    assert 'Picker("服务商写的类型", selection: $proxyProtocolHint)' in settings
    assert 'Picker("参数类型", selection: $proxyProtocolHint)' not in settings
    assert "让 AI 帮我看诊断报告" in settings
    assert "让云端 AI 解释诊断报告" not in settings
    assert "发送给 AI 前" in settings
