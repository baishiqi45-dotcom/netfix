from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODEL = ROOT / "gui" / "macos" / "Sources" / "Models" / "DashboardInsights.swift"
APP_DELEGATE = ROOT / "gui" / "macos" / "Sources" / "AppDelegate.swift"


def test_dashboard_exposes_plain_language_network_insights():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")

    assert "struct DashboardInsightsResponse" in model
    assert "struct DashboardPrimaryInsight" in model
    assert 'case primaryInsight = "primary_insight"' in model
    assert "struct NetworkActivitySummary" in model
    assert "struct ProxyHealthTrend" in model
    assert "func dashboardInsights() async throws -> DashboardInsightsResponse" in api_client
    assert 'path: "dashboard/insights"' in api_client

    assert "DashboardHomePresentation" in dashboard
    assert "currentStatusSection" in dashboard
    assert "connectionQualitySection" in dashboard
    assert "diagnosticEvidenceSection" in dashboard
    current_status = dashboard[
        dashboard.index("private var currentStatusSection") : dashboard.index("private func compactIdentityItem")
    ]
    assert "connectionQualitySection" in current_status
    assert dashboard.index("private var connectionQualitySection") < dashboard.index("private var diagnosticEvidenceSection")
    assert 'Text("网络体感")' in dashboard
    assert 'connectionQualityMetric(title: "速度"' in dashboard
    assert 'connectionQualityMetric(title: "延迟"' in dashboard
    assert 'connectionQualityMetric(title: "稳定性"' in dashboard
    assert 'connectionQualityMetric(title: "后台占用"' in dashboard
    assert 'DisclosureGroup(isExpanded: $isEvidenceExpanded)' in dashboard
    assert 'Label("检查详情", systemImage: "doc.text.magnifyingglass")' in dashboard
    assert 'responsivenessMetric(label: "速度"' in dashboard
    assert 'Label("后台网络活动", systemImage: "arrow.up.arrow.down.circle")' not in dashboard
    assert 'Label("近期网络事件", systemImage: "clock.arrow.circlepath")' not in dashboard
    assert 'Label("代理近 10 次", systemImage: "waveform.path.ecg")' not in dashboard
    assert 'Text("后台网络活动")' in dashboard
    assert 'Text("近期网络事件")' in dashboard
    assert 'Text("代理近 10 次")' in dashboard
    assert 'Button("这次不提醒")' in dashboard
    assert "检测到上行流量较高" in dashboard
    assert "当前只是活动记录，不代表异常。" in dashboard
    assert "还没有速度、延迟和后台占用数据" not in dashboard
    assert "本次未采集速度和延迟数据" in dashboard
    assert "没有 base_rtt 数据" not in dashboard
    assert "响应性 \\(rpm)" not in dashboard
    assert "基础延迟 \\(rtt)ms" not in dashboard
    assert "network_quality / bandwidth_hog" not in dashboard
    assert "network_quality 诊断结果" not in dashboard
    assert "现在最该看的问题" not in dashboard
    assert "下一步：" not in dashboard
    assert "谁在占用网络" not in dashboard
    assert "最近卡顿" not in dashboard
    assert "未测出" not in dashboard
    assert "速度/延迟检测没有拿到有效数据" not in dashboard
    assert "先别把它当正常" not in dashboard
    assert "很卡" not in dashboard
    assert "偶尔卡" not in dashboard
    assert "挤满" not in dashboard
    assert "占满" not in dashboard
    assert "疑似" not in dashboard
    assert "几乎不可用" not in dashboard


def test_dashboard_and_menu_do_not_guess_green_or_expose_route_jargon():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    app_delegate = APP_DELEGATE.read_text(encoding="utf-8")
    current_status = dashboard[
        dashboard.index("private var currentStatusSection") : dashboard.index("private func compactIdentityItem")
    ]

    assert 'case "external_system_proxy": return "由其他 App 管理"' in dashboard
    assert 'contentSize = NSSize(width: 460, height: 500)' in app_delegate
    assert '.frame(minWidth: 420, idealWidth: 460, minHeight: 440)' in dashboard
    assert 'case .unknown:\n            color = .systemGray' in app_delegate
    assert "backend.isReady ? .systemGreen : .systemYellow" not in app_delegate
    assert 'label == "低"' in dashboard
    assert 'label.contains("低")' not in dashboard
    assert 'hasPrefix("public_ipv4_hash:")' in dashboard
    assert 'return "联网身份已确认"' in dashboard
    assert 'ScrollView(.horizontal, showsIndicators: false)' not in current_status
    assert 'return "刚刚更新"' in dashboard
    diagnose = dashboard[dashboard.index("func diagnose() async"):dashboard.index("func fix() async")]
    assert "refreshProxyUsage" not in diagnose
    assert "refreshDashboardInsights" not in diagnose
    assert 'if isSectionVisible("connection_quality")' in dashboard
    assert '"\\(state.interfaceLabel) · \\(state.localIPLabel)"' not in current_status
    assert 'case "unavailable": return "本次没有采到速度、延迟或稳定性数据。"' in dashboard
    assert 'return "网络提供方 · \\(isp)"' not in dashboard
    assert 'label.contains("较高") || label.contains("不稳") {\n            return .orange' in dashboard


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
