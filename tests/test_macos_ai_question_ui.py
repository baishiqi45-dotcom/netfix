from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "gui" / "macos" / "Sources" / "Views" / "DashboardView.swift"
SETTINGS = ROOT / "gui" / "macos" / "Sources" / "Views" / "SettingsView.swift"
API_CLIENT = ROOT / "gui" / "macos" / "Sources" / "APIClient.swift"
MODELS = ROOT / "gui" / "macos" / "Sources" / "Models" / "Report.swift"


def test_macos_dashboard_has_consent_gated_ai_question_sheet_with_image_picker():
    source = DASHBOARD.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")

    assert "AIQuestionSheet" in source
    assert "看不懂诊断？让 AI 解释一下" in source
    assert "aiAssistantSection" not in source
    assert ".buttonStyle(.borderless)" in source
    assert "下一步怎么处理？" in source
    assert "怎么看出来的？" in source
    assert "是不是代理没生效？" in source
    assert "为什么是这个根因？" not in source
    assert "NSOpenPanel()" in source
    assert "allowedContentTypes" in source
    assert ".heic" not in source
    assert ".tiff" not in source
    assert "只支持 PNG、JPEG、WebP 或 GIF" in source
    assert "留空也可以，Netfix 会直接解释当前诊断报告" in source
    assert "AI 设置" in source
    assert "showAISettings" in source
    assert "这只影响 AI 看报告，不影响诊断和代理部署" in source
    assert "选择供应商并粘贴 API Key" in source
    assert "4_500_000" in source
    assert "data:\\(mime);base64" in source
    assert "Toggle(isOn: $uploadConfirmed)" in source
    assert ".disabled(isWorking || !uploadConfirmed)" in source
    assert "imageDataURLs.isEmpty ? \"explain\" : \"image_question\"" in source
    assert "fallbackReasonLabel ?? result.fallbackReason" in source
    assert "fallbackReasonLabel" in models
    assert "AI 给出的解释" in source
    assert "Netfix 本地解释" in source
    assert "技术详情" in source
    assert "脱敏报告指纹" in source
    assert "备用链路：" not in source


def test_macos_dashboard_surfaces_proxy_deployment_without_ai_api_requirement():
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "proxyDeploySection" in source
    assert 'Label("让这台 Mac 用上你的代理", systemImage: "point.3.connected.trianglepath.dotted")' in source
    assert "AI 可不填" in source
    assert "复制整行，不要只复制出口 IP" in source
    assert 'Label("开始部署代理", systemImage: "square.and.arrow.down")' in source
    assert 'Button("我该复制什么？")' not in source
    assert "openProxySettings()" in source


def test_macos_api_client_sends_question_mode_images_and_feature_flag():
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "imageQuestionEnabled: Bool" in api_client
    assert '"image_question": imageQuestionEnabled' in api_client
    assert 'func explainWithLLM(question: String = "", mode: String = "explain", uploadConfirmed: Bool = false, images: [String] = [])' in api_client
    assert 'body["images"] = images' in api_client
    assert '"mode": mode' in api_client


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


def test_macos_privacy_settings_can_disable_persisted_proxy_identity_reports():
    settings = SETTINGS.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    api_client = API_CLIENT.read_text(encoding="utf-8")

    assert "@State private var persistProxyIdentityReport = false" in settings
    assert 'Toggle("保存完整代理身份报告", isOn: $persistProxyIdentityReport)' in settings
    assert "persistProxyIdentityReport = privacy.persistProxyIdentityReport" in settings
    assert "persistProxyIdentityReport: persistProxyIdentityReport" in settings
    assert "let persistProxyIdentityReport: Bool" in models
    assert 'case persistProxyIdentityReport = "persist_proxy_identity_report"' in models
    assert "persistProxyIdentityReport: Bool" in api_client
    assert '"persist_proxy_identity_report": persistProxyIdentityReport' in api_client
