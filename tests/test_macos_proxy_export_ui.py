from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"


def test_macos_proxy_profile_export_is_visible_and_secret_safe():
    settings = SETTINGS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "func exportProxyProfile(profileID: String, format: String = \"all\")" in api_client
    assert "proxy/profiles/\\(profileID)/export" in api_client
    assert "struct ProxyClientExportResponse" in models
    assert "struct ProxyClientPackage" in models
    assert "struct ProxyClientPackageFile" in models
    assert "struct ProxyClientSnippet" in models
    assert 'case recommendedFormat = "recommended_format"' in models
    assert 'case secretPlaceholder = "secret_placeholder"' in models
    assert "@State private var proxyExportResult: ProxyClientExportResponse?" in settings
    assert 'Button("导出配置包")' in settings
    assert "await exportProxyProfile(profile)" in settings
    assert "proxyExportBlock" in settings
    assert "配置包：" in settings
    assert "package.files" in settings
    assert "不会显示已保存的代理密码" in settings
    assert "<password>" in settings
    assert ".textSelection(.enabled)" in settings
    assert "复制这一段" in settings
    assert "NSPasteboard.general" in settings


def test_macos_proxy_deployment_decision_is_decoded_and_rendered():
    settings = SETTINGS.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "struct ProxyDeploymentDecision" in models
    assert 'case deploymentDecision = "deployment_decision"' in models
    assert 'case systemApply = "system_apply"' in models
    assert 'case clientExport = "client_export"' in models
    assert 'case reasonCode = "reason_code"' in models
    assert 'case requiresNetfixRunning = "requires_netfix_running"' in models
    assert "let deploymentDecision: ProxyDeploymentDecision?" in models
    assert "proxyDeploymentDecisionBlock" in settings
    assert "authenticated_socks_bridge_required" in settings
    assert "这个代理需要账号密码" in settings
    assert "系统会先连本机，再由 Netfix 转发到供应商代理" in settings
    assert "已让这台 Mac 使用该代理" in settings
    assert "MiniMax -> Kimi -> Qwen" in settings


def test_macos_proxy_validation_target_matrix_is_selectable_and_applied():
    settings = SETTINGS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "struct ProxyValidationTargetsResponse" in models
    assert "struct ProxyValidationTargetProfile" in models
    assert "struct ProxyValidationTargetProbe" in models
    assert 'case targetProfile = "target_profile"' in models
    assert 'case targetProfileLabel = "target_profile_label"' in models
    assert "func proxyValidationTargets() async throws -> ProxyValidationTargetsResponse" in api_client
    assert "func validateProxyProfile(profileID: String, timeout: Int = 10, includeIdentity: Bool = true, targetProfile: String = \"baseline\")" in api_client
    assert "func applyProxyDryRun(profileID: String, mode: String = \"system\")" in api_client
    assert '"proxy/profiles/\\(profileID)/apply-dry-run"' in api_client
    assert "func applyProxyProfile(profileID: String, mode: String, confirmed: Bool = false, targetProfile: String = \"baseline\")" in api_client
    assert "func startProxyMonitor(profileID: String, interval: Int = 60, timeout: Int = 10, targetProfile: String = \"baseline\")" in api_client
    assert "func deleteProxyProfile(profileID: String)" in api_client
    assert "func replaceProxyProfile(profileID: String, input: String, startMonitor: Bool = true" in api_client
    assert '"proxy/validation-targets"' in api_client
    assert '"proxy/profiles/\\(profileID)/delete"' in api_client
    assert '"proxy/profiles/\\(profileID)/replace"' in api_client
    assert '"target_profile": targetProfile' in api_client
    assert "@State private var proxyValidationTargets" in settings
    assert "@State private var proxyTargetProfile = \"baseline\"" in settings
    assert 'Picker("检测目标", selection: $proxyTargetProfile)' in settings
    assert "try await client.proxyValidationTargets()" in settings
    assert "targetProfile: proxyTargetProfile" in settings
    assert "await validateSavedProxyProfile(profile)" in settings
    assert "await deleteProxyProfile(profile)" in settings
    assert "await replaceProxyProfile(profile)" in settings
    assert "monitorPersistedCleared" in models
    assert 'case monitorPersistedCleared = "monitor_persisted_cleared"' in models
    assert "清理重启自动恢复配置" in settings
    assert 'Button("删除", role: .destructive)' in settings
    assert 'Button("更新参数")' in settings
    assert "粘贴新的代理连接参数" in settings
    assert "验证通过：" in settings
    assert "验证有风险：" in settings
    assert "monitor.targetProfile" in settings
    assert "proxyRepairActionsBlock" in settings
    assert "handleProxyRepairAction" in settings
    assert "replace_profile_credentials" in settings
    assert "export_profile" in settings
    assert "repairActions" in settings
    assert "let targetProfile: String?" in models
    assert "struct ProxyRepairAction" in models
    assert "struct ProxyRepairUIAction" in models
    assert 'case repairActions = "repair_actions"' in models
    assert 'case uiAction = "ui_action"' in models


def test_macos_proxy_tab_prioritizes_plain_one_paste_wizard():
    settings = SETTINGS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "让这台 Mac 用代理上网" in settings
    assert "粘贴整行参数" in settings
    assert "去哪里复制？" in settings
    assert "复制包含地址、端口、用户名、密码的整行" in settings
    assert "proxy.example.com:8001:username:password" in settings
    assert 'Picker("服务商写的类型", selection: $proxyProtocolHint)' in settings
    assert "自动判断" in settings
    assert "如果服务商明确写 SOCKS5" in settings
    assert "保存不会改网络" in settings
    assert "还没有影响浏览器" in settings
    assert "开始使用代理" in settings
    assert "不要只复制出口 IP" in settings
    assert 'Label("只检查，不保存", systemImage: "checklist")' in settings
    assert 'Label("检查并保存到这台 Mac", systemImage: "tray.and.arrow.down")' in settings
    assert 'Button("我没有代理服务商参数")' in settings
    assert "proxyDeploymentConfirmationText" in settings
    assert "friendlyProxyApplyStep" in settings
    assert "prepareProxyDeployment" in settings
    assert "applyProxyDryRun" in api_client
    assert "proxyProtocolBody(input: String, protocolHint: String = \"auto\")" in api_client
    assert "健康维护" in settings
    assert "已保存的代理" in settings
    assert "更多操作" in settings
    assert "proxyProfileRow" in settings
    assert "proxyCheckSummary" in settings
    assert "friendlyProxyError" in settings
    assert "系统会先连本机，再由 Netfix 转发到供应商代理" in settings
    assert 'Label("开始使用代理", systemImage: "play.circle.fill")' in settings
    assert 'Button("导出配置包")' in settings
    assert 'Button("给终端工具使用")' in settings
