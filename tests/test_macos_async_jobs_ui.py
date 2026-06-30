from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"


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
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "func fix() async" in dashboard
    assert "func executeAction(_ action: Action) async" in dashboard
    assert "func rollback() async" in dashboard
    assert "client.fix(timeout: 90)" in dashboard
    assert "client.executeFix(fixId: action.id, timeout: 60)" in dashboard
    assert "client.rollback(timeout: 30)" in dashboard
    assert 'path: "fixes/execute"' in api_client
    assert '"confirmation": "APPLY_SYSTEM_FIX"' in api_client
    assert "让 Netfix 处理这个问题？" in dashboard
    assert "你需要做的事" in dashboard
    assert "手动步骤" not in dashboard
