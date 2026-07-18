from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
AI_CHAT = ROOT / "gui" / "macos" / "Sources" / "Views" / "AIChatView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"
HEALTH_MONITOR = ROOT / "gui" / "macos" / "Sources" / "Monitoring" / "HealthMonitor.swift"


def test_macos_dashboard_uses_cancellable_async_jobs_for_read_only_checks():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "activeJobID" in dashboard
    assert "cancelActiveJob" in dashboard
    assert 'Label("取消", systemImage: "xmark.circle")' in dashboard
    assert "runReadOnlyReportJob" in dashboard
    assert 'command: ["doctor"]' in dashboard
    assert 'command: ["services", "--group", group]' in dashboard
    assert "awaitReportJob" in dashboard
    assert "client.startRunJob" in dashboard
    assert "client.jobStatus" in dashboard
    assert "client.cancelJob" in dashboard
    assert '"async": true' in api_client
    assert 'path: "jobs/\\(jobID)"' in api_client
    assert 'path: "jobs/\\(jobID)/cancel"' in api_client
    assert "struct APIJobResponse" in models
    assert 'case startedAt = "started_at"' in models
    assert 'case finishedAt = "finished_at"' in models


def test_macos_mutating_fix_paths_still_use_confirmed_synchronous_calls():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    chat = AI_CHAT.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "func executeAction(_ action: Action) async" in dashboard
    assert "func recoverStaleBridge() async" in dashboard
    assert "client.fix(timeout: 90)" not in dashboard
    assert 'viewModel.recommendedAction' in dashboard
    assert 'Button("处理建议")' in dashboard
    assert "confirmed: confirmed" in dashboard
    assert "client.recoverProxyBridge(confirmed: true)" in dashboard
    assert "client.rollbackProxyProfile(confirmed: true)" not in dashboard
    assert "client.rollback(timeout: 30)" not in dashboard
    assert "no_recovery_needed" in dashboard
    assert 'body: ["command": ["fix", "--all", "--yes", "--report"], "timeout": timeout]' not in api_client
    assert 'path: "fixes/execute"' in api_client
    assert 'path: "proxy/profiles/rollback"' in api_client
    assert 'path: "proxy/bridge/recover"' in api_client
    assert 'body["confirmation"] = "APPLY_SYSTEM_FIX"' in api_client
    assert '"confirmation"] = "ROLLBACK_PROXY_PROFILE"' in api_client
    assert "让 Netfix 处理这个问题？" in dashboard
    # 常驻「问 AI」对话区（AIChatView）会把 AI 回答里的 manual_steps 渲染为只读步骤列表（不执行），
    # 修复执行仍全部走上面的 confirmed 同步路径。
    assert "手动步骤" in chat


def test_proxy_save_uses_decoding_client_error_for_human_format_errors():
    api_client = API_CLIENT.read_text(encoding="utf-8")

    start = api_client.index("func saveProxyProfile")
    end = api_client.index("func replaceProxyProfile")
    body = api_client[start:end]
    assert "postDecodingClientError" in body
    assert 'path: "proxy/profiles"' in body


def test_api_client_prefers_specific_errors_over_generic_failed_text():
    api_client = API_CLIENT.read_text(encoding="utf-8")

    start = api_client.index("private static func errorDetail")
    end = api_client.index("private static func friendlyReasonCode")
    body = api_client[start:end]
    assert "let errorValue" in body
    assert '["failed", "fail", "error"].contains(value.lowercased())' in body
    assert 'dict["errors"] as? [String]' in body
    assert body.index('dict["errors"] as? [String]') < body.index('if let value = errorValue, !value.isEmpty {')


def test_macos_toolbar_splits_primary_and_secondary_actions():
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert "private var actionToolbar: some View" in dashboard
    assert "private var primaryActionToolbar: some View" not in dashboard
    assert "private var secondaryActionToolbar: some View" in dashboard
    assert 'Button("代理")' in dashboard
    assert 'Button("设置")' in dashboard
    assert 'Menu("更多")' in dashboard
    toolbar = dashboard[
        dashboard.index("private var secondaryActionToolbar"):
        dashboard.index('Menu("更多")')
    ]
    assert 'Label("问 AI", systemImage: "sparkles")' in toolbar
    assert 'Button("日志")' not in toolbar


def test_health_monitor_auto_fix_uses_explicit_tier1_action_only():
    health_monitor = HEALTH_MONITOR.read_text(encoding="utf-8")

    assert "client.fix()" not in health_monitor
    assert "autoFixAction" in health_monitor
    assert "action.tier == 1" in health_monitor
    assert "!action.needsConfirm" in health_monitor
    assert "client.executeFix(fixId: action.id" in health_monitor
