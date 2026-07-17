from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"
APP_DELEGATE = ROOT / "gui" / "macos" / "Sources" / "AppDelegate.swift"


def test_macos_dashboard_has_consent_gated_ai_question_sheet_with_image_picker():
    source = DASHBOARD.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "AIQuestionSheet" in source
    assert "问 AI 解释这次检查" in source
    assert "看不懂结果？让 AI 解释一下" not in source
    assert "aiAssistantSection" not in source
    assert ".buttonStyle(.borderless)" in source
    assert "下一步怎么处理？" in source
    assert "怎么看出来的？" in source
    assert "是不是代理没生效？" in source
    assert "这个代理能用吗？" in source
    assert "粘贴格式对吗？" in source
    assert "为什么代理检查失败？" in source
    assert "AIQuestionContext" in source
    assert "为什么是这个根因？" not in source
    assert "NSOpenPanel()" in source
    assert "allowedContentTypes" in source
    assert ".heic" not in source
    assert ".tiff" not in source
    assert "只支持 PNG、JPEG、WebP 或 GIF" in source
    assert "留空也可以，Netfix 会直接解释当前诊断报告" in source
    assert "AI 设置" in source
    assert "showAISettings" in source
    assert "这只影响 AI 看报告，不影响检查网络、使用代理或恢复网络设置" in source
    assert "选择供应商并填写 AI 密钥" in source
    assert "4_500_000" in source
    assert "data:\\(mime);base64" in source
    assert "Toggle(isOn: $uploadConfirmed)" in source
    assert "requiresUploadConfirmation" in source
    assert ".disabled(isWorking || sendDisabled)" in source
    assert "imageDataURLs.isEmpty ? \"explain\" : \"image_question\"" in source
    assert "fallbackReasonLabel ?? result.fallbackReason" in source
    assert "fallbackReasonLabel" in models
    assert "AI 解释" in source
    assert "Netfix 本地解释" in source
    assert "技术详情" in source
    assert "脱敏报告指纹" in source
    assert "备用链路：" not in source


def test_macos_dashboard_ai_flow_is_visible_contextual_and_keeps_answer_in_sheet():
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "canOfferAIExplanation" in source
    assert 'Label("问 AI 解释这次检查", systemImage: "sparkles")' in source
    assert "result: viewModel.llmExplanation" in source
    assert "errorMessage: viewModel.llmError" in source
    assert "isAIWorking" in source
    assert "onCancelRequest" in source
    assert 'Button("生成简明说明")' not in source
    assert 'Button("代理说明")' not in source
    assert "headline = response.result.headline ?? headline" not in source
    assert '.accessibilityLabel("还想问什么")' in source
    assert '.accessibilityLabel("关闭 AI 解释")' in source
    assert "LazyVGrid" in source


def test_macos_dashboard_surfaces_proxy_deployment_without_ai_api_requirement():
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "currentStatusSection" in source
    assert "DashboardHomePresentation" in source
    assert "proxyDeploySection" not in source
    assert "case .proxySetup" in source
    assert "state.primaryActionLabel" in source
    assert "粘贴代理参数" in source
    assert "不需要 API Key 也能用" not in source
    assert "外部系统代理" not in source
    assert "从服务商后台复制一整行" not in source
    assert "openAIExplanation()" in source
    assert 'Button("我该复制什么？")' not in source
    assert "openProxySettings()" in source


def test_macos_api_client_sends_question_mode_images_and_feature_flag():
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "imageQuestionEnabled: Bool" in api_client
    assert '"image_question": imageQuestionEnabled' in api_client
    assert 'func explainWithLLM(question: String = "", mode: String = "explain", uploadConfirmed: Bool = false, images: [String] = [], history: [[String: String]] = [])' in api_client
    assert 'body["images"] = images' in api_client
    assert '"mode": mode' in api_client


def test_macos_ai_question_sheet_is_true_multi_turn_with_history():
    source = DASHBOARD.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")

    # sheet 维护 QA 轮次对话流，答案不再互相覆盖
    assert "struct AIChatTurn: Identifiable" in models
    assert "@Published var aiConversation: [AIChatTurn]" in source
    assert "conversation: viewModel.aiConversation" in source
    assert "private var conversationSection: some View" in source
    assert "ForEach(conversation) { turn in" in source
    assert "conversation.isEmpty ? \"发送并解释\" : \"继续追问\"" in source
    assert "llmExplanation = nil" not in source.split("func explainWithAI")[1].split("func cancelAIExplanation")[0]
    # 发送时按契约装 history：已回答轮次展开为 user/assistant，最多 20 条、每条 2000 字
    assert "private static func historyPayload(from conversation: [AIChatTurn]) -> [[String: String]]" in source
    assert '"role": "user"' in source
    assert '"role": "assistant"' in source
    assert ".prefix(2_000)" in source
    assert ".suffix(20)" in source
    assert 'body["history"] = history' in api_client


def test_macos_ai_answer_renders_actions_and_manual_steps():
    source = DASHBOARD.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    # LLMExplainResult 解码 actions / manual_steps
    assert "let actions: [Action]?" in models
    assert "let manualSteps: [ManualStep]?" in models
    assert 'case manualSteps = "manual_steps"' in models
    assert "let reason: String?" in models
    # actions 渲染成按钮，走主界面同一执行路径；Tier>=2 只展示说明
    assert "private func actionButtons(for result: LLMExplainResult) -> some View" in source
    assert "onRunAction(action)" in source
    assert "action.tier >= 2" in source
    assert "会更改系统网络设置，请回到主界面确认后执行。" in source
    assert "requestAction(action)" in source
    # manual_steps 渲染为步骤列表
    assert "private func manualStepsList(for result: LLMExplainResult) -> some View" in source
    assert "手动步骤" in source


def test_macos_ai_entry_available_without_fresh_report():
    source = DASHBOARD.read_text(encoding="utf-8")
    delegate = APP_DELEGATE.read_text(encoding="utf-8")

    # 门控放宽：后端就绪即可问 AI；新鲜报告只决定是否结合报告回答
    assert "private var hasFreshReportForAI: Bool" in source
    assert "hasCurrentReport: hasFreshReportForAI" in source
    assert "先描述问题，或先检查网络让 AI 结合报告回答。" in source
    assert "还没有可解释的当前检查" not in source
    # 菜单栏新增「问 AI…」入口
    assert 'NSMenuItem(title: "问 AI…", action: #selector(showAIQuestion)' in delegate
    assert "func showAIQuestion()" in delegate
    assert "netfixShowAIQuestion" in delegate
    assert ".netfixShowAIQuestion" in source


def test_macos_settings_can_enable_image_question_feature_flag():
    settings = SETTINGS.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "@State private var llmImageQuestionEnabled = false" in settings
    assert "llmImageQuestionEnabled = settings.features?.imageQuestion ?? false" in settings
    assert "imageQuestionEnabled: llmImageQuestionEnabled" in settings
    assert "struct LLMSettingsFeatures" in models
    assert 'case imageQuestion = "image_question"' in models
    assert "imageQuestionAdapterReady" in models
    assert 'Toggle("允许带截图问 AI", isOn: $llmImageQuestionEnabled)' in settings
    assert "PNG、JPEG、WebP 或 GIF 截图" in settings
    assert "provider.imageQuestionProviderSupported == true && provider.imageQuestionAdapterReady != true" in settings


def test_macos_ai_settings_are_a_first_class_settings_layer_not_mcp_or_advanced():
    settings = SETTINGS.read_text(encoding="utf-8")

    assert 'case "ai":' in settings
    assert 'Text("AI").tag("ai")' in settings
    assert "private var aiLayerView: some View" in settings
    assert "advancedIntroSection\n            agentTab" in settings
    assert "advancedIntroSection\n            aiLayerView" not in settings


def test_macos_privacy_settings_can_disable_persisted_proxy_identity_reports():
    settings = SETTINGS.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "@State private var persistProxyIdentityReport = false" in settings
    assert 'Toggle("保存完整出口检测报告", isOn: $persistProxyIdentityReport)' in settings
    assert "persistProxyIdentityReport = privacy.persistProxyIdentityReport" in settings
    assert "persistProxyIdentityReport: persistProxyIdentityReport" in settings
    assert "let persistProxyIdentityReport: Bool" in models
    assert 'case persistProxyIdentityReport = "persist_proxy_identity_report"' in models
    assert "persistProxyIdentityReport: Bool" in api_client
    assert '"persist_proxy_identity_report": persistProxyIdentityReport' in api_client
