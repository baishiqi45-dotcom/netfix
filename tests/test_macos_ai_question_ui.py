from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
AI_CHAT = ROOT / "gui" / "macos" / "Sources" / "Views" / "AIChatView.swift"
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"
APP_DELEGATE = ROOT / "gui" / "macos" / "Sources" / "AppDelegate.swift"


def test_macos_dashboard_has_inline_ai_chat_view_with_image_picker():
    source = DASHBOARD.read_text(encoding="utf-8")
    chat = AI_CHAT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    # 独立 sheet 已删除，可复用区块抽成常驻内联 AIChatView
    assert "AIQuestionSheet" not in source
    assert "showAIQuestionSheet" not in source
    assert "struct AIChatView: View" in chat
    assert "AIChatView(" in source
    assert "看不懂结果？让 AI 解释一下" not in source + chat
    assert "aiAssistantSection" not in source + chat
    assert ".buttonStyle(.borderless)" in source
    assert "下一步怎么处理？" in chat
    assert "怎么看出来的？" in chat
    assert "是不是代理没生效？" in chat
    # AIQuestionContext 只保留 diagnosis；proxy 死分支已删
    assert "AIQuestionContext" in chat
    assert "case proxy" not in chat
    assert "这个代理能用吗？" not in chat
    assert "粘贴格式对吗？" not in chat
    assert "为什么代理检查失败？" not in chat
    assert "为什么是这个根因？" not in source + chat
    assert "NSOpenPanel()" in chat
    assert "allowedContentTypes" in chat
    assert ".heic" not in chat
    assert ".tiff" not in chat
    assert "只支持 PNG、JPEG、WebP 或 GIF" in chat
    assert "留空也可以，Netfix 会直接解释当前诊断报告" in chat
    assert "AI 设置" in chat
    assert "showAISettings" in source
    assert "这只影响 AI 看报告，不影响检查网络、使用代理或恢复网络设置" in chat
    assert "选择供应商并填写 AI 密钥" in chat
    assert "4_500_000" in chat
    assert "data:\\(mime);base64" in chat
    assert ".disabled(isWorking || sendDisabled)" in chat
    assert "imageDataURLs.isEmpty ? \"explain\" : \"image_question\"" in source
    assert "fallbackReasonLabel ?? result.fallbackReason" in chat
    assert "fallbackReasonLabel" in models
    assert "AI 解释" in chat
    assert "Netfix 本地解释" in chat
    assert "技术详情" in chat
    assert "脱敏报告指纹" in chat
    assert "备用链路：" not in source + chat


def test_macos_ai_chat_inline_layout_fixed_list_prompts_and_paperclip():
    chat = AI_CHAT.read_text(encoding="utf-8")

    # 消息列表高度随内容自适应（160…380pt），内部滚动，对话为空时给快捷问题
    assert "private var messageList: some View" in chat
    assert "AIChatContentHeightKey" in chat
    assert "min(380, max(160, contentHeight))" in chat
    assert ".frame(height: messageListHeight)" in chat
    # 智能滚动：用户翻看历史时不强制拽回底部
    assert "isNearBottom" in chat
    # 回车发送（Shift+Return 换行）：NSEvent 本地监听在 composer 聚焦时拦截 Return
    assert "addLocalMonitorForEvents" in chat
    assert "if conversation.isEmpty {" in chat
    assert "private var promptGrid: some View" in chat
    assert "LazyVGrid" in chat
    # composer 旁保留回形针截图按钮
    assert "private var composerRow: some View" in chat
    assert 'Image(systemName: "paperclip")' in chat
    assert "pickImages()" in chat
    # 无新鲜报告时对话区顶部显示精简提示
    assert "private var noReportBanner: some View" in chat
    assert "还没有当前检查报告" in chat
    assert "先描述问题，或先检查网络让 AI 结合报告回答。" in chat


def test_macos_dashboard_ai_flow_is_inline_scrolls_and_focuses_composer():
    source = DASHBOARD.read_text(encoding="utf-8")
    chat = AI_CHAT.read_text(encoding="utf-8")

    assert "canOfferAIExplanation" in source
    # 单行入口换成常驻对话区，挂在主 ScrollView 并带锚点 id
    assert "private var aiChatSection: some View" in source
    assert '.id("aiChatSection")' in source
    assert "ScrollViewReader" in source
    assert "conversation: viewModel.aiConversation" in source
    assert "errorMessage: viewModel.llmError" in source
    assert "isAIWorking" in source
    assert "onCancelRequest" in source
    assert 'Button("生成简明说明")' not in source + chat
    assert 'Button("代理说明")' not in source + chat
    assert "headline = response.result.headline ?? headline" not in source
    assert '.accessibilityLabel("还想问什么")' in chat
    assert '.accessibilityLabel("关闭 AI 解释")' not in chat
    # 菜单栏通知/工具栏按钮统一：滚动到对话区 + FocusState 聚焦 composer
    assert "openAIExplanation()" in source
    assert "aiScrollRequest += 1" in source
    assert 'reader.scrollTo("aiChatSection"' in source
    assert "@FocusState private var aiComposerFocused: Bool" in source
    assert "aiComposerFocused = true" in source
    assert "composerFocused: $aiComposerFocused" in source
    assert "composerFocused: FocusState<Bool>.Binding" in chat
    assert ".focused(composerFocused)" in chat


def test_macos_ai_chat_confirms_upload_inline_and_resends():
    source = DASHBOARD.read_text(encoding="utf-8")
    chat = AI_CHAT.read_text(encoding="utf-8")

    # 后端回 needs_upload_confirmation 时在对话流里内联确认，替代发送前的 privacyNotice Toggle
    assert "needsUploadConfirmation == true" in chat
    assert "需要把脱敏后的报告发给 AI 供应商，确认发送？" in chat
    assert 'Button("确认发送")' in chat
    assert "confirmUpload" in chat
    # 确认后以 uploadConfirmed=true 重发同一问题
    assert "onSend(pending.question, pending.images, true)" in chat
    assert "uploadConfirmed: uploadConfirmed" in source
    # 「总是允许」且不带截图时直接带确认发送
    assert 'uploadConsent == "always"' in chat
    assert "Toggle(isOn: $uploadConfirmed)" not in chat
    assert "requiresUploadConfirmation" not in chat


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


def test_macos_ai_question_chat_is_true_multi_turn_with_history():
    source = DASHBOARD.read_text(encoding="utf-8")
    chat = AI_CHAT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")

    # 对话区维护 QA 轮次对话流，答案不再互相覆盖
    assert "struct AIChatTurn: Identifiable" in models
    assert "@Published var aiConversation: [AIChatTurn]" in source
    assert "conversation: viewModel.aiConversation" in source
    assert "private var conversationSection: some View" in chat
    assert "ForEach(conversation) { turn in" in chat
    assert "conversation.isEmpty ? \"发送并解释\" : \"继续追问\"" in chat
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
    chat = AI_CHAT.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    # LLMExplainResult 解码 actions / manual_steps
    assert "let actions: [Action]?" in models
    assert "let manualSteps: [ManualStep]?" in models
    assert 'case manualSteps = "manual_steps"' in models
    assert "let reason: String?" in models
    # actions 渲染成按钮，走主界面同一执行路径；会更改系统设置的只展示说明
    assert "private func actionButtons(for result: LLMExplainResult) -> some View" in chat
    assert "onRunAction(action)" in chat
    assert "action.tier >= 2" in chat
    assert "会更改系统网络设置，请在主界面确认后执行。" in chat
    assert "requestAction(action)" in source
    # manual_steps 渲染为步骤列表
    assert "private func manualStepsList(for result: LLMExplainResult) -> some View" in chat
    assert "手动步骤" in chat


def test_macos_ai_entry_available_without_fresh_report():
    source = DASHBOARD.read_text(encoding="utf-8")
    chat = AI_CHAT.read_text(encoding="utf-8")
    delegate = APP_DELEGATE.read_text(encoding="utf-8")

    # 门控放宽：后端就绪即可问 AI；新鲜报告只决定是否结合报告回答
    assert "private var hasFreshReportForAI: Bool" in source
    assert "hasCurrentReport: hasFreshReportForAI" in source
    assert "先描述问题，或先检查网络让 AI 结合报告回答。" in chat
    assert "还没有可解释的当前检查" not in source + chat
    # 菜单栏「问 AI…」入口：通知保留，行为改内联
    assert 'NSMenuItem(title: "问 AI…", action: #selector(showAIQuestion)' in delegate
    assert "func showAIQuestion()" in delegate
    assert "netfixShowAIQuestion" in delegate
    assert ".netfixShowAIQuestion" in source
    # popover 加高，容纳常驻对话区
    assert "NSSize(width: 460, height: 640)" in delegate


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
