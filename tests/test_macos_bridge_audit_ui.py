from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"
APP_DELEGATE = ROOT / "gui" / "macos" / "Sources" / "AppDelegate.swift"
DASHBOARD_STATE = ROOT / "gui" / "macos" / "Sources" / "Models" / "DashboardState.swift"
HEALTH_MONITOR = ROOT / "gui" / "macos" / "Sources" / "Monitoring" / "HealthMonitor.swift"


def test_macos_bridge_status_surfaces_local_access_audit():
    settings = SETTINGS.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    app_delegate = APP_DELEGATE.read_text(encoding="utf-8")

    assert "requestCount" in models
    assert "recentClients" in models
    assert "ProxyBridgeClient" in models
    assert "ProxyBridgeLifecycle" in models
    assert "ProxyBridgeStartupCheck" in models
    assert "ProxyBridgeSettings" in models
    assert "ProxyBridgeRestartResult" in models
    assert 'case schemaVersion = "schema_version"' in models
    assert 'case startupCheck = "startup_check"' in models
    assert 'case autoRestart = "auto_restart"' in models
    assert 'case autoRestartEnabled = "auto_restart_enabled"' in models
    assert 'case eventAppended = "event_appended"' in models
    assert 'case primaryAction = "primary_action"' in models
    assert 'case bridgeStop = "bridge_stop"' in models
    assert "ProxyBridgeStop" in models
    assert 'case requestCount = "request_count"' in models
    assert 'case recentClients = "recent_clients"' in models
    assert "state.lifecycle" in settings
    assert "state.startupCheck" in settings
    assert "proxyBridgeAutoRestartEnabled" in settings
    assert "启动时检查上次代理连接" in settings
    assert "必须由你点击恢复并确认" in settings
    assert "saveProxyBridgeSettings" in settings
    assert "启动时代理检查" in settings
    assert "启动时已自动恢复代理连接" not in settings
    assert "bridgeStopLabel" in settings
    assert ".onChange(of: backend.state)" in settings
    assert "请保持 Netfix 打开" in settings
    assert "恢复原来的网络设置" in settings
    assert "当前代理需要 Netfix 保持打开" in settings
    assert "bridgeStatusMenuItem" in app_delegate
    assert "bridgeStatusOverride" in app_delegate
    assert "bridgeStatusTimer" in app_delegate
    assert "menuNeedsUpdate" in app_delegate
    assert "refreshBridgeMenuStatus" in app_delegate
    assert "refreshBridgeAttentionStatus" in app_delegate
    assert "startBridgeStatusPolling" in app_delegate
    assert "scheduledTimer(withTimeInterval: 45" in app_delegate
    assert "applyBridgeState(state, notify: false)" in app_delegate
    assert "applyBridgeState(state, notify: notify)" in app_delegate
    assert "bridgeAttention(for: state)" in app_delegate
    assert "bridgeStatusOverride ?? healthStatus" in app_delegate
    assert "notifyBridgeAttention" in app_delegate
    assert 'UserDefaults.standard.bool(forKey: "netfix.notificationsEnabled")' in app_delegate
    assert "需要恢复网络设置" in app_delegate
    assert "DashboardStateStore" in app_delegate
    assert "已自动恢复代理连接" not in app_delegate
    assert "bridgeMenuTitle" in app_delegate
    assert "网络状态：" in app_delegate
    assert "Netfix 代理使用中" in app_delegate


def test_macos_notifications_respect_user_toggle_for_health_and_bridge():
    app_delegate = APP_DELEGATE.read_text(encoding="utf-8")
    health_monitor = HEALTH_MONITOR.read_text(encoding="utf-8")

    assert 'UserDefaults.standard.bool(forKey: "netfix.notificationsEnabled")' in app_delegate
    assert 'UserDefaults.standard.bool(forKey: "netfix.notificationsEnabled")' in health_monitor
    assert "guard notificationsEnabled else { return }" in health_monitor
    assert "if notificationsEnabled" in health_monitor
    assert "requestNotificationAuthorization()" in health_monitor


def test_external_proxy_never_gets_netfix_restore_or_quit_prompt():
    app_delegate = APP_DELEGATE.read_text(encoding="utf-8")
    dashboard_state = DASHBOARD_STATE.read_text(encoding="utf-8")

    assert "state.canOfferNetfixRestore" in app_delegate
    assert "var canOfferNetfixRestore: Bool" in dashboard_state
    assert 'decision?.effectiveRoute == "external_system_proxy"' in dashboard_state
    assert 'proxy?.applied?.owner == "external"' in dashboard_state
