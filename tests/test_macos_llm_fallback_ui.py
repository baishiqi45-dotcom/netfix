from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_VIEW = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"
APP_DELEGATE = ROOT / "gui" / "macos" / "Sources" / "AppDelegate.swift"
MENTIONED_DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"


def test_macos_ai_settings_exposes_domestic_fallback_chain():
    view = SETTINGS_VIEW.read_text(encoding="utf-8")
    client = API_CLIENT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "llmFallbackEnabled" in view
    assert "启用国内备用链路" in view
    assert "DeepSeek -> Kimi -> MiniMax -> Qwen" in view
    assert "图片问诊链路：MiniMax -> Kimi" in view
    assert "llmChainReadinessBlock" in view
    assert "链路就绪度" in view
    assert "providerAdapterEvidenceText" in view
    assert "官方文档核验" in view
    assert "请求字段" in view
    assert "showLLMChainTestConfirmation" in view
    assert "showLLMProviderTestConfirmation" in view
    assert "testLLMChain" in view
    assert "testLLMConnection" in view
    assert "importDeepSeekSidecarKey" in view
    assert 'Button("导入 DeepSeek 侧车 Key")' in view
    assert "不会显示或记录密钥" in view
    assert 'Button("测试链路")' in view
    assert 'Button("测试连接")' in view
    assert "会真实调用已配置的供应商" in view
    assert "llmChainTestSummary" in view
    assert "selectLLMProviderForKey" in view
    assert 'Button("配置 Key")' in view
    assert "正在配置" in view
    assert "func llmChainReadiness() async throws -> LLMChainReadinessResponse" in client
    assert "func importDeepSeekSidecarKey() async throws -> DeepSeekSidecarImportResponse" in client
    assert "func testLLMChain(timeout: Int = 60) async throws -> LLMChainTestResponse" in client
    assert "func testLLM(timeout: Int = 30) async throws -> LLMTestResponse" in client
    assert '"llm/chain-readiness"' in client
    assert '"llm/import-deepseek-sidecar-key"' in client
    assert '"llm/chain-test"' in client
    assert '"IMPORT_DEEPSEEK_SIDECAR_KEY"' in client
    assert '"TEST_LLM_CHAIN"' in client
    assert '"TEST_LLM_PROVIDER"' in client
    assert "struct LLMChainReadinessResponse" in models
    assert "struct LLMChainReadiness" in models
    assert "struct LLMChainProviderReadiness" in models
    assert "metadataCheckedAt" in models
    assert "officialDocs" in models
    assert "maxTokensField" in models
    assert "struct LLMChainTestResponse" in models
    assert "struct DeepSeekSidecarImportResponse" in models
    assert 'case apiKeyAccount = "api_key_account"' in models
    assert "struct LLMChainTest" in models
    assert "struct LLMChainTestProvider" in models
    assert 'case schemaVersion = "schema_version"' in models
    assert 'case readyCount = "ready_count"' in models
    assert "fallbackEnabled: llmFallbackEnabled" in view
    assert "fallbackEnabled: Bool" in client
    assert '"fallback": [' in client
    assert '"chain": ["deepseek", "moonshot_kimi", "minimax", "qwen"]' in client
    assert '"vision_chain": ["minimax", "moonshot_kimi", "qwen"]' in client


def test_macos_ai_settings_exposes_llm_budget_controls():
    view = SETTINGS_VIEW.read_text(encoding="utf-8")
    client = API_CLIENT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "llmBudgetEnabled" in view
    assert "每小时云端请求上限" in view
    assert "每小时图片问诊上限" in view
    assert "LLMChainBudgetStatus" in models
    assert "budgetStatusText" in view
    assert "llmBudgetPersistLedger" in view
    assert "persistUsageLedger" in models
    assert "persistUsageLedger: llmBudgetPersistLedger" in view
    assert "persistUsageLedger: Bool" in client
    assert '"persist_usage_ledger": persistUsageLedger' in client
    assert "记住我的使用次数" in view
    assert "remainingRequests" in models
    assert "remainingImageRequests" in models
    assert "budgetEnabled: llmBudgetEnabled" in view
    assert "budgetEnabled: Bool" in client
    assert '"budget": [' in client
    assert '"max_requests_per_hour": maxRequestsPerHour' in client
    assert '"max_image_requests_per_hour": maxImageRequestsPerHour' in client
    assert "struct LLMSettingsBudget" in models
    assert 'case maxRequestsPerHour = "max_requests_per_hour"' in models


def test_macos_ai_settings_has_plain_minimax_setup_path():
    view = SETTINGS_VIEW.read_text(encoding="utf-8")
    delegate = APP_DELEGATE.read_text(encoding="utf-8")
    dashboard = MENTIONED_DASHBOARD.read_text(encoding="utf-8")

    assert '@AppStorage("netfix.settings.selectedTab")' in view
    assert 'TabView(selection: $selectedSettingsTab)' in view
    assert '.tag("ai")' in view
    assert "让 AI 解释诊断结果" in view
    assert "这是可选的 AI 看报告功能" in view
    assert "没有 API Key 也能诊断、部署代理和处理 IPv6" in view
    assert "用 MiniMax 配置" in view
    assert "prepareRecommendedLLMProvider(\"minimax\")" in view
    assert "可选：AI 密钥（只用于 AI 看报告）" in view
    assert "密钥只保存在本机密码库" in view
    assert "保存并测试" in view
    assert "saveAndTestLLMSettings" in view
    assert "高级：模型地址、备用模型和预算" in view
    assert "showAISettings" in delegate
    assert 'UserDefaults.standard.set("ai", forKey: "netfix.settings.selectedTab")' in delegate
    assert "#selector(AppDelegate.showAISettings)" in dashboard
    assert "showProxySettings" in delegate
    assert 'UserDefaults.standard.set("proxy", forKey: "netfix.settings.selectedTab")' in delegate
    assert 'NSMenuItem(title: "部署代理…", action: #selector(showProxySettings)' in delegate
    assert "#selector(AppDelegate.showProxySettings)" in dashboard
