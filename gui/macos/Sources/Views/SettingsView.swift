import SwiftUI
import UserNotifications
import ServiceManagement
import AppKit

/// 设置 / 偏好设置窗口内容。
struct SettingsView: View {
    @ObservedObject var backend: Backend
    @AppStorage("netfix.launchAtLogin") private var launchAtLogin = false
    @AppStorage("netfix.notificationsEnabled") private var notificationsEnabled = false
    @AppStorage("netfix.iconStyle") private var iconStyle = 0
    @AppStorage("netfix.autoFixTier1") private var autoFixTier1 = false
    @AppStorage("netfix.settings.selectedTab") private var selectedSettingsTab = "general"
    @State private var showAdvancedAISettings = false
    @State private var showAdvancedProxyControls = false

    @State private var serviceGroups: [ServiceGroup] = []
    @State private var llmProviders: [LLMProviderInfo] = []
    @State private var llmChainReadiness: LLMChainReadinessResponse?
    @State private var llmEnabled = false
    @State private var llmProvider = "deepseek"
    @State private var llmBaseURL = "https://api.deepseek.com"
    @State private var llmModel = "deepseek-v4-flash"
    @State private var llmAPIKeyAccount = "deepseek"
    @State private var llmAPIKey = ""
    @State private var llmAPIKeySet = false
    @State private var redactionLevel = "balanced"
    @State private var uploadConsent = "ask_each_time"
    @State private var llmFallbackEnabled = true
    @State private var llmBudgetEnabled = true
    @State private var llmBudgetPersistLedger = true
    @State private var llmMaxRequestsPerHour = 60
    @State private var llmMaxImageRequestsPerHour = 12
    @State private var llmImageQuestionEnabled = false
    @State private var aiStatus: String?
    @State private var mcpStatus: String?
    @State private var showLLMProviderTestConfirmation = false
    @State private var showLLMChainTestConfirmation = false
    @State private var proxyProfiles: [ProxyProfile] = []
    @State private var proxyValidationTargets: [ProxyValidationTargetProfile] = [
        ProxyValidationTargetProfile(id: "baseline", label: "通用连通性", description: nil, probes: nil),
        ProxyValidationTargetProfile(id: "ai_dev", label: "AI / 开发工具", description: nil, probes: nil),
    ]
    @State private var proxyTargetProfile = "baseline"
    @State private var proxyProtocolHint = "auto"
    @State private var proxyStartMonitorOnSave = true
    @State private var proxyInput = ""
    @State private var proxyParseResult: ProxyParseResponse?
    @State private var proxyImportPreviewResult: ProxyImportPreviewResponse?
    @State private var proxyValidateResult: ProxyValidateResponse?
    @State private var proxyExportResult: ProxyClientExportResponse?
    @State private var proxyMonitorState: ProxyMonitorState?
    @State private var proxyBridgeState: ProxyBridgeResponse?
    @State private var proxyBridgeAutoRestartEnabled = false
    @State private var proxyStatus: String?
    @State private var pendingSystemProxyProfile: ProxyProfile?
    @State private var pendingSystemProxyPlan: ProxyApplyPlan?
    @State private var pendingDeleteProxyProfile: ProxyProfile?
    @State private var lastSavedProxyProfile: ProxyProfile?
    @State private var showSystemProxyConfirmation = false
    @State private var showDeleteProxyProfileConfirmation = false
    @State private var showProxyRollbackConfirmation = false
    @State private var showBridgeRecoveryConfirmation = false
    @State private var logRetentionEnabled = true
    @State private var logRetentionDays = 7
    @State private var saveLatestReport = true
    @State private var persistProxyIdentityReport = false
    @State private var privacyStatus: String?
    @State private var notificationStatus = UNAuthorizationStatus.notDetermined
    @State private var loadError: String?
    @State private var loginItemError: String?
    @State private var showClearAllDataConfirmation = false

    var body: some View {
        TabView(selection: $selectedSettingsTab) {
            generalTab
                .tabItem {
                    Label("通用", systemImage: "gear")
                }
                .tag("general")

            proxyTab
                .tabItem {
                    Label("部署代理", systemImage: "point.3.connected.trianglepath.dotted")
                }
                .tag("proxy")

            agentTab
                .tabItem {
                    Label("AI 编程助手", systemImage: "terminal")
                }
                .tag("agent")

            aiTab
                .tabItem {
                    Label("AI", systemImage: "sparkles")
                }
                .tag("ai")

            permissionsTab
                .tabItem {
                    Label("权限", systemImage: "lock.shield")
                }
                .tag("permissions")

            aboutTab
                .tabItem {
                    Label("关于", systemImage: "info.circle")
                }
                .tag("about")
        }
        .frame(width: 720, height: 620)
        .task {
            await refreshNotificationStatus()
            await loadServiceGroups()
            await loadCloudAndProxySettings()
        }
        .onChange(of: backend.state) { newState in
            if case .ready = newState {
                Task { await loadCloudAndProxySettings() }
            }
        }
        .alert("登录项设置失败", isPresented: .constant(loginItemError != nil)) {
            Button("确定") { loginItemError = nil }
        } message: {
            Text(loginItemError ?? "")
        }
        .confirmationDialog("删除全部 Netfix 本地数据？", isPresented: $showClearAllDataConfirmation, titleVisibility: .visible) {
            Button("删除日志、设置、AI 预算账本和已保存密钥", role: .destructive) {
                Task { await clearAllLocalData() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会删除 Netfix 最近报告、事件日志、AI 本地预算账本、非敏感设置，以及已保存的 AI 密钥和代理密码。不会删除 App 本体或系统网络配置。")
        }
        .confirmationDialog("开始使用这台 Mac 上网？", isPresented: $showSystemProxyConfirmation, titleVisibility: .visible) {
            Button("确认开始使用", role: .none) {
                if let profile = pendingSystemProxyProfile {
                    Task { await applyProxyProfile(profile, mode: "system", confirmed: true) }
                }
            }
            Button("取消", role: .cancel) {
                pendingSystemProxyProfile = nil
                pendingSystemProxyPlan = nil
            }
        } message: {
            Text(proxyDeploymentConfirmationText())
        }
        .confirmationDialog("删除代理配置？", isPresented: $showDeleteProxyProfileConfirmation, titleVisibility: .visible) {
            Button("删除配置", role: .destructive) {
                if let profile = pendingDeleteProxyProfile {
                    Task { await deleteProxyProfile(profile) }
                }
            }
            Button("取消", role: .cancel) {
                pendingDeleteProxyProfile = nil
            }
        } message: {
            Text("这会删除本地代理配置和对应密码；不会修改当前网络代理设置。")
        }
        .confirmationDialog("恢复原来的网络设置？", isPresented: $showProxyRollbackConfirmation, titleVisibility: .visible) {
            Button("恢复原来的网络设置", role: .destructive) {
                Task { await rollbackProxyProfile() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会恢复上次部署代理前备份的 macOS 网络代理设置。")
        }
        .confirmationDialog("修复失效的代理部署？", isPresented: $showBridgeRecoveryConfirmation, titleVisibility: .visible) {
            Button("恢复原来的网络设置", role: .destructive) {
                Task { await recoverProxyBridge() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("系统还在使用上次 Netfix 部署的代理，但转发服务可能已经不在运行。恢复后会回到部署前的网络代理设置。")
        }
        .confirmationDialog("测试国内模型链路？", isPresented: $showLLMChainTestConfirmation, titleVisibility: .visible) {
            Button("确认测试链路", role: .destructive) {
                Task { await testLLMChain() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会真实调用已配置的供应商，可能计入 DeepSeek、Kimi、MiniMax、Qwen 等供应商用量或账单。不会读取或显示 API Key。")
        }
        .confirmationDialog("测试当前模型连接？", isPresented: $showLLMProviderTestConfirmation, titleVisibility: .visible) {
            Button("确认测试连接", role: .destructive) {
                Task { await testLLMConnection() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会真实调用当前已配置的供应商，并可能计入供应商用量或账单。不会读取或显示 API Key。")
        }
    }

    // MARK: - General

    private var generalTab: some View {
        Form {
            Section {
                Toggle("登录时启动 netfix", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { newValue in
                        setLoginItem(enabled: newValue)
                    }

                Toggle("启用通知", isOn: $notificationsEnabled)
                    .onChange(of: notificationsEnabled) { newValue in
                        if newValue {
                            requestNotificationAuthorization()
                        }
                    }

                Toggle("自动修复不用动系统设置的小问题", isOn: $autoFixTier1)

                Picker("菜单栏图标样式", selection: $iconStyle) {
                    Text("彩色状态灯").tag(0)
                    Text("单色图标").tag(1)
                }

                DisclosureGroup("高级：服务分组") {
                    serviceGroupsBlock
                }
            }

            Section {
                Text("需要重新登录才能使部分登录项设置生效。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }

    // MARK: - Services

    private var servicesTab: some View {
        VStack(alignment: .leading, spacing: 0) {
            serviceGroupsBlock
        }
    }

    private var serviceGroupsBlock: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let error = loadError {
                Text(error)
                    .foregroundStyle(.red)
                    .padding()
            } else if serviceGroups.isEmpty {
                ProgressView("加载服务列表…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(serviceGroups) { group in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(group.name)
                                .font(.headline)
                            Text("\(group.services.count) 个服务")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }

                Text("服务分组用于定向检测，暂不支持单独开关。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
            }
        }
    }

    // MARK: - AI 编程助手 / MCP

    private var agentTab: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "terminal")
                            .foregroundStyle(.blue)
                        Text("把 Netfix 接进 AI 编程助手")
                            .font(.headline)
                        Spacer()
                        Text(mcpServerExists ? "已就绪" : "缺少 MCP 文件")
                            .font(.caption2)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background((mcpServerExists ? Color.green : Color.orange).opacity(0.14))
                            .foregroundStyle(mcpServerExists ? Color.green : Color.orange)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }

                    Text("已下载 App 的用户不用找仓库脚本。Codex 可以直接复制注册命令；Kimi 如果当前版本没有 MCP 注册入口，就复制通用 stdio 配置给支持 MCP 的宿主。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section("复制注册命令") {
                HStack {
                    Button {
                        copyMCPCommand(kind: .codex)
                    } label: {
                        Label("复制给 Codex", systemImage: "doc.on.doc")
                    }
                    .disabled(!mcpServerExists)

                    Button {
                        copyMCPCommand(kind: .kimi)
                    } label: {
                        Label("复制 Kimi/通用配置", systemImage: "doc.on.doc")
                    }
                    .disabled(!mcpServerExists)

                    Button {
                        copyMCPCommand(kind: .all)
                    } label: {
                        Label("复制全部", systemImage: "square.on.square")
                    }
                    .disabled(!mcpServerExists)
                }

                Text(mcpCommandPreview)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)

                if let mcpStatus {
                    Text(mcpStatus)
                        .font(.caption)
                        .foregroundStyle(mcpStatus.hasPrefix("失败") ? Color.red : Color.secondary)
                } else {
                    Text("MCP 不保存 API Key 或代理密码；部署系统代理和保存密钥仍回到 Netfix App 里确认。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section("如果复制后不能用") {
                Button("在 Finder 里显示 MCP 文件") {
                    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: mcpServerPath)])
                }
                .disabled(!mcpServerExists)

                Text("确认 Netfix.app 没有被移走；如果你重新安装了 App，需要重新复制注册命令。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
    }

    // MARK: - AI

    private var aiTab: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "sparkles")
                            .foregroundStyle(.purple)
                        Text("让 AI 解释诊断结果")
                            .font(.headline)
                        Spacer()
                        Toggle("启用", isOn: $llmEnabled)
                            .labelsHidden()
                    }

                    Text("这是可选的 AI 看报告功能。没有 API Key 也能诊断、部署代理和处理 IPv6；需要 AI 帮你解释报告时再填写。密钥只保存在本机密码库。")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    HStack {
                        Button {
                            prepareRecommendedLLMProvider("minimax")
                        } label: {
                            Label("用 MiniMax 配置", systemImage: "wand.and.stars")
                        }
                        .disabled(!backend.isReady && llmProviders.isEmpty)

                        Button {
                            prepareRecommendedLLMProvider("deepseek")
                        } label: {
                            Label("用 DeepSeek 文本解释", systemImage: "text.bubble")
                        }
                        .disabled(!backend.isReady && llmProviders.isEmpty)
                    }
                }

                Picker("AI 服务", selection: $llmProvider) {
                    ForEach(llmProviders) { provider in
                        Text(provider.label).tag(provider.id)
                    }
                }
                .onChange(of: llmProvider) { newValue in
                    applyProviderPreset(newValue)
                }

                if let provider = selectedLLMProvider {
                    Text(providerStatusText(provider))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                SecureField(llmAPIKeySet ? "已保存 AI 密钥，留空则不覆盖" : "可选：AI 密钥（只用于 AI 看报告）", text: $llmAPIKey)
                    .textFieldStyle(.roundedBorder)
                    .help("只写入本机密码库，不会进入诊断报告、日志或导出文件。")

                Picker("隐私保护", selection: $redactionLevel) {
                    Text("默认").tag("balanced")
                    Text("严格").tag("strict")
                }

                Picker("发报告前", selection: $uploadConsent) {
                    Text("每次问我").tag("ask_each_time")
                    Text("总是发送").tag("always")
                    Text("从不发送").tag("never")
                }

                Toggle("允许带截图问 AI", isOn: $llmImageQuestionEnabled)
                Text("开启后，主界面的问 AI 可以在你确认后发送选中的 PNG、JPEG、WebP 或 GIF 截图；MiniMax/Kimi/Qwen 可处理图片，DeepSeek 只处理文字报告。")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                DisclosureGroup("高级：模型地址、备用模型和预算", isExpanded: $showAdvancedAISettings) {
                    VStack(alignment: .leading, spacing: 8) {
                        TextField("Base URL", text: $llmBaseURL)
                            .textFieldStyle(.roundedBorder)
                        TextField("模型", text: $llmModel)
                            .textFieldStyle(.roundedBorder)
                        TextField("密钥名称", text: $llmAPIKeyAccount)
                            .textFieldStyle(.roundedBorder)

                        if let provider = selectedLLMProvider {
                            Text(providerAdapterEvidenceText(provider))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }

                        Toggle("启用国内备用链路", isOn: $llmFallbackEnabled)
                        Text("文本链路：DeepSeek -> Kimi -> MiniMax -> Qwen；图片问诊链路：MiniMax -> Kimi -> Qwen。未保存对应密钥的供应商会自动跳过。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        llmChainReadinessBlock

                        Toggle("启用本地请求预算", isOn: $llmBudgetEnabled)
                        Toggle("记住我的使用次数", isOn: $llmBudgetPersistLedger)
                        Stepper("每小时云端请求上限：\(llmMaxRequestsPerHour)", value: $llmMaxRequestsPerHour, in: 0...10_000)
                        Stepper("每小时图片问诊上限：\(llmMaxImageRequestsPerHour)", value: $llmMaxImageRequestsPerHour, in: 0...10_000)
                        Text("持久化预算账本只记录供应商、模式、时间戳和冷却状态；关闭持久化或关闭预算会删除旧账本。这不是供应商账单硬上限。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 4)
                }
            }

            Section {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Button("保存 AI 设置") {
                            Task { _ = await saveLLMSettings() }
                        }
                        .disabled(!backend.isReady)

                        Button("保存并测试") {
                            Task { await saveAndTestLLMSettings() }
                        }
                        .disabled(!backend.isReady || (llmAPIKey.isEmpty && !llmAPIKeySet))
                    }

                    HStack {
                        Button("导入 DeepSeek 侧车 Key") {
                            Task { await importDeepSeekSidecarKey() }
                        }
                        .disabled(!backend.isReady)

                        Button("测试连接") {
                            showLLMProviderTestConfirmation = true
                        }
                        .disabled(!backend.isReady || !llmAPIKeySet && llmAPIKey.isEmpty)

                        Button("测试链路") {
                            showLLMChainTestConfirmation = true
                        }
                        .disabled(!backend.isReady)

                        Button("刷新") {
                            Task { await loadCloudAndProxySettings() }
                        }
                        .disabled(!backend.isReady)
                    }
                }

                if let aiStatus {
                    Text(aiStatus)
                        .font(.caption)
                        .foregroundStyle(aiStatus.hasPrefix("失败") ? Color.red : Color.secondary)
                } else {
                    Text("AI 解释默认关闭；发送前会先脱敏，执行动作仍由本地规则决定。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
    }

    // MARK: - Proxy

    private var proxyDeployStepGuide: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                proxyStepBadge("1", "粘贴整行参数")
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                proxyStepBadge("2", "检查能不能用")
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                proxyStepBadge("3", "保存")
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                proxyStepBadge("4", "开始使用")
            }

            Text("保存不会改网络；点“开始使用这台 Mac 上网”才会让浏览器和其他 App 使用这个代理。")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color.blue.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func proxyStepBadge(_ number: String, _ title: String) -> some View {
        HStack(spacing: 5) {
            Text(number)
                .font(.caption2)
                .fontWeight(.bold)
                .foregroundStyle(.white)
                .frame(width: 18, height: 18)
                .background(Color.blue)
                .clipShape(Circle())
            Text(title)
                .font(.caption)
                .fontWeight(.semibold)
                .lineLimit(1)
        }
    }

    private var proxyPasteGuideCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("去哪里复制？", systemImage: "doc.on.clipboard")
                .font(.subheadline)
                .fontWeight(.semibold)

            Text("打开你的代理服务后台，找“代理生成”“我的订阅”“Endpoint”“API Access”这类页面，复制包含地址、端口、用户名、密码的整行。")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text("可以粘贴这些格式：host:port:username:password，或 host,port,username,password 表格。没有写协议时，默认按常见 HTTP 代理处理。")
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)

            Label("不要只复制出口 IP。单独一个 IP 没有端口和账号密码，Netfix 没法部署。", systemImage: "exclamationmark.triangle")
                .font(.caption)
                .foregroundStyle(.orange)
        }
        .padding(10)
        .background(Color.orange.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var proxyTab: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 8) {
                        Image(systemName: "point.3.connected.trianglepath.dotted")
                            .foregroundStyle(.blue)
                        Text("让这台 Mac 用代理上网")
                            .font(.headline)
                        Spacer()
                    }

                    proxyDeployStepGuide

                    proxyPasteGuideCard

                    Text("粘贴代理连接")
                        .font(.subheadline)
                        .fontWeight(.semibold)

                    ZStack(alignment: .topLeading) {
                        TextEditor(text: $proxyInput)
                            .font(.system(.body, design: .monospaced))
                            .frame(minHeight: 96, maxHeight: 136)
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Color.secondary.opacity(0.25))
                            )
                            .help("支持 URL、host:port:user:pass、host,port,user,password，以及带表头的多行列表。")

                        if proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            Text("在这里粘贴整行，例如 proxy.example.com:8001:username:password")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 9)
                                .allowsHitTesting(false)
                        }
                    }

                    Text("服务商给的是表格也可以整段粘贴；Netfix 会只保存可识别的代理，密码只进本机密码库。")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Picker("检测目标", selection: $proxyTargetProfile) {
                        ForEach(proxyValidationTargets) { target in
                            Text(target.label ?? target.id).tag(target.id)
                        }
                    }
                    .pickerStyle(.segmented)

                    Picker("参数类型", selection: $proxyProtocolHint) {
                        Text("自动判断（大多数选这个）").tag("auto")
                        Text("HTTP 代理").tag("http")
                        Text("SOCKS5 代理").tag("socks5h")
                    }
                    .pickerStyle(.segmented)

                    Text("如果服务商后台只给四段参数，例如 host:port:username:password，直接粘贴即可；如果服务商明确写 SOCKS5，就把参数类型切到 SOCKS5。")
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    HStack {
                        Button {
                            Task { await saveProxyProfile() }
                        } label: {
                            Label("检查并保存到这台 Mac", systemImage: "tray.and.arrow.down")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                        Button {
                            Task { await importProxyPreview() }
                        } label: {
                            Label("只检查，不保存", systemImage: "checklist")
                        }
                        .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                        Button("我没有代理服务商参数") {
                            proxyStatus = "这块只给已经有代理服务商参数的人用。没有参数也可以直接回主界面点“一键诊断”，Netfix 仍能检查 Wi-Fi、DNS、IPv6 和现有代理问题。"
                        }
                    }

                    Toggle("保存后自动启动健康监控", isOn: $proxyStartMonitorOnSave)
                    Text("检查并保存只是把参数放到本机，暂不影响浏览器。要开始使用，请在已保存代理里点“开始使用这台 Mac 上网”。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section("结果和下一步") {
                if let preview = proxyImportPreviewResult {
                    proxyImportPreviewBlock(preview)
                }
                if let result = proxyParseResult, let redacted = result.redactedURL, !redacted.isEmpty {
                    Label("已识别：\(redacted)", systemImage: "checkmark.seal")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let decision = proxyParseResult?.deploymentDecision {
                    proxyDeploymentDecisionBlock(decision)
                }
                if let check = proxyValidateResult?.proxyCheck {
                    Text(proxyCheckSummary(check))
                        .font(.caption)
                        .foregroundStyle(check.status == "ok" ? Color.secondary : Color.orange)
                }
                if let identity = proxyValidateResult?.identityReport {
                    Text(proxyIdentitySummary(identity))
                        .font(.caption)
                        .foregroundStyle(identity.status == "ok" ? Color.secondary : Color.orange)
                }
                if let proxyStatus {
                    Text(proxyStatus)
                        .font(.caption)
                        .foregroundStyle(proxyStatus.hasPrefix("失败") ? Color.red : Color.secondary)
                    if proxyStatus.hasPrefix("已保存"), let profile = lastSavedProxyProfile {
                        Button {
                            Task { await prepareProxyDeployment(profile) }
                        } label: {
                            Label("下一步：开始使用这台 Mac 上网", systemImage: "play.circle.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!backend.isReady)
                    }
                } else {
                        Text("下一步：粘贴整行参数 → 检查并保存到这台 Mac → 开始使用这台 Mac 上网。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Section("已保存的代理") {
                if proxyProfiles.isEmpty {
                    Text("还没有保存的代理。保存后会出现在这里，密码只写入本机密码库，列表不会显示明文。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(proxyProfiles) { profile in
                        proxyProfileRow(profile)
                    }
                }
            }

            Section("健康维护") {
                if let monitor = proxyMonitorState {
                    Text(proxyMonitorLabel(monitor))
                        .font(.caption)
                        .foregroundStyle((monitor.running ?? false) ? Color.secondary : Color.orange)
                    if let last = monitor.lastEvent {
                        Text("最近检查：\(friendlyProxyStatus(last.status)) / \(last.proxyCheck?.latencyMs ?? 0)ms")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        proxyRepairActionsBlock(last.repairActions ?? last.proxyCheck?.repairActions ?? [])
                    }
                } else {
                    Text("健康监控未启动。保存代理时打开“自动启动健康监控”，Netfix 会持续检查可用性。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                HStack {
                    Button("刷新健康状态") {
                        Task { await loadProxyMonitor() }
                    }
                    .disabled(!backend.isReady)

                    Button("停止监控") {
                        Task { await stopProxyMonitor() }
                    }
                    .disabled(!backend.isReady || !(proxyMonitorState?.running ?? false))
                }
            }

            Section {
                DisclosureGroup("更多：导出、恢复网络设置", isExpanded: $showAdvancedProxyControls) {
                    VStack(alignment: .leading, spacing: 10) {
                        if let proxyExportResult {
                            proxyExportBlock(proxyExportResult)
                            Divider()
                        }

                        Toggle("重启时自动恢复上次代理连接", isOn: $proxyBridgeAutoRestartEnabled)
                            .onChange(of: proxyBridgeAutoRestartEnabled) { newValue in
                                Task { await saveProxyBridgeSettings(autoRestartEnabled: newValue) }
                            }
                        Text("只在上次部署没有正常退出时尝试恢复；不会静默修改网络代理设置。")
                            .font(.caption2)
                            .foregroundStyle(.secondary)

                        Text(proxyBridgeLabel(proxyBridgeState))
                            .font(.caption)
                            .foregroundStyle(proxyBridgeState?.lifecycle?.needsAttention == true || proxyBridgeState?.staleCheck?.recoveryAvailable == true ? Color.orange : Color.secondary)

                        HStack {
                            Button("刷新部署状态") {
                                Task { await loadProxyBridge() }
                            }
                            .disabled(!backend.isReady)

                            Button("修复失效部署", role: .destructive) {
                                showBridgeRecoveryConfirmation = true
                            }
                            .disabled(!backend.isReady || !(proxyBridgeState?.staleCheck?.recoveryAvailable ?? false))

                            Button("恢复原来的网络设置", role: .destructive) {
                                showProxyRollbackConfirmation = true
                            }
                            .disabled(!backend.isReady)
                        }
                    }
                    .padding(.top, 4)
                }
            }
        }
        .padding()
    }

    // MARK: - Permissions

    private var permissionsTab: some View {
        Form {
            Section {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("本地网络访问")
                            .font(.headline)
                        Text("用于检测网关、DNS 和代理状态")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("打开系统设置") {
                        openLocalNetworkSettings()
                    }
                }

                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("通知权限")
                            .font(.headline)
                        Text(notificationStatusLabel)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("打开系统设置") {
                        openNotificationSettings()
                    }
                }
            }

            Section("本地数据") {
                Toggle("保留最近诊断报告", isOn: $saveLatestReport)
                Toggle("自动裁剪事件日志", isOn: $logRetentionEnabled)
                Stepper("事件日志保留 \(logRetentionDays) 天", value: $logRetentionDays, in: 1...365)
                Toggle("保存完整出口检测报告", isOn: $persistProxyIdentityReport)
                Text("关闭时，配置只保留出口摘要，不长期保存完整出口 IP、运营商信息和每个检测目标明细。")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    Button("保存隐私设置") {
                        Task { await savePrivacySettings() }
                    }
                    .disabled(!backend.isReady)

                    Button("清理本地日志", role: .destructive) {
                        Task { await clearLogs() }
                    }
                    .disabled(!backend.isReady)
                }

                Button("删除全部本地数据与已保存密钥", role: .destructive) {
                    showClearAllDataConfirmation = true
                }
                .disabled(!backend.isReady)

                if let privacyStatus {
                    Text(privacyStatus)
                        .font(.caption)
                        .foregroundStyle(privacyStatus.hasPrefix("失败") ? Color.red : Color.secondary)
                } else {
                    Text("只清理 Netfix 的最近报告和事件日志，不会删除设置、AI 密钥或代理密码。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding()
    }

    private var notificationStatusLabel: String {
        switch notificationStatus {
        case .authorized: return "已授权"
        case .denied: return "未授权"
        case .notDetermined: return "尚未请求"
        case .provisional: return "临时授权"
        case .ephemeral: return "临时授权"
        @unknown default: return "未知"
        }
    }

    // MARK: - About

    private var aboutTab: some View {
        VStack(spacing: 16) {
            Image(systemName: "network")
                .font(.system(size: 48))
                .foregroundStyle(.blue)

            Text("netfix")
                .font(.title2)
                .fontWeight(.semibold)

            Text("版本 \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.2.0")")
                .font(.body)
                .foregroundStyle(.secondary)

            Text("macOS 网络自救工具")
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            HStack(spacing: 12) {
                Link("支持网站", destination: URL(string: "https://github.com/netfix/netfix")!)
                Button("开发者：打开本地 API") {
                    if let url = backend.apiURL {
                        NSWorkspace.shared.open(url)
                    }
                }
                .disabled(!backend.isReady)
                Button("退出 netfix") {
                    NSApplication.shared.terminate(nil)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    private var canUseNotifications: Bool {
        Bundle.main.bundlePath.hasSuffix(".app")
    }

    private enum MCPCommandKind {
        case codex
        case kimi
        case all
    }

    private var mcpServerPath: String {
        if let resourceURL = Bundle.main.resourceURL {
            let bundled = resourceURL.appendingPathComponent("netfix/mcp_server.py").path
            if FileManager.default.fileExists(atPath: bundled) {
                return bundled
            }
        }
        return URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("netfix/mcp_server.py")
            .path
    }

    private var mcpServerExists: Bool {
        FileManager.default.fileExists(atPath: mcpServerPath)
    }

    private var codexMCPCommand: String {
        "codex mcp add netfix -- python3 \(shellQuote(mcpServerPath))"
    }

    private var kimiMCPCommand: String {
        """
        # Kimi Code 当前 CLI 如果没有 `mcp add`，不要粘贴旧命令。
        # 在支持 MCP stdio 的 Kimi/Agent 宿主里填：
        name: netfix
        command: python3
        args: \(shellQuote(mcpServerPath))
        """
    }

    private var mcpCommandPreview: String {
        [codexMCPCommand, kimiMCPCommand].joined(separator: "\n")
    }

    private func shellQuote(_ value: String) -> String {
        "'\(value.replacingOccurrences(of: "'", with: "'\\''"))'"
    }

    private func copyMCPCommand(kind: MCPCommandKind) {
        let text: String
        switch kind {
        case .codex:
            text = codexMCPCommand
        case .kimi:
            text = kimiMCPCommand
        case .all:
            text = mcpCommandPreview
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        mcpStatus = "已复制。Codex 粘贴命令后重启对应的 AI 编程助手；Kimi 用通用 stdio 配置，前提是宿主支持 MCP。"
    }

    private func refreshNotificationStatus() async {
        guard canUseNotifications else { return }
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        notificationStatus = settings.authorizationStatus
        // 同步 Toggle 与系统真实授权状态，避免“开关开着但实际没授权”的误导。
        if settings.authorizationStatus == .denied {
            notificationsEnabled = false
        }
    }

    private func requestNotificationAuthorization() {
        guard canUseNotifications else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, _ in
            Task { @MainActor in
                notificationsEnabled = granted
                await refreshNotificationStatus()
            }
        }
    }

    private func loadServiceGroups() async {
        guard let path = Bundle.main.path(forResource: "services", ofType: "json", inDirectory: "rules"),
              FileManager.default.fileExists(atPath: path) else {
            loadError = "找不到服务列表文件，请确认 App Bundle 完整或重新安装 Netfix。"
            return
        }
        do {
            let url = URL(fileURLWithPath: path)
            let data = try Data(contentsOf: url)
            let response = try JSONDecoder().decode(ServiceGroupResponse.self, from: data)
            serviceGroups = response.groups
        } catch {
            loadError = "加载服务列表失败：\(error.localizedDescription)"
        }
    }

    private func client() -> APIClient? {
        guard let url = backend.apiURL, let token = backend.apiToken else { return nil }
        return APIClient(baseURL: url, apiToken: token)
    }

    private func loadCloudAndProxySettings() async {
        guard let client = client() else {
            aiStatus = "Netfix 准备好后可配置 AI 和代理。"
            return
        }
        do {
            let providers = try await client.llmProviders()
            llmProviders = providers.providers
            if llmProviders.isEmpty {
                aiStatus = "Netfix 暂时没有返回 AI 供应商列表，请刷新或重启 App。"
            }
            llmChainReadiness = try await client.llmChainReadiness()
            let settings = try await client.llmSettings().settings
            llmEnabled = settings.enabled
            llmProvider = settings.provider
            llmBaseURL = settings.baseURL
            llmModel = settings.model
            llmAPIKeyAccount = settings.apiKeyAccount
            llmAPIKeySet = settings.apiKeySet
            redactionLevel = settings.redactionLevel ?? "balanced"
            uploadConsent = settings.uploadConsent ?? "ask_each_time"
            llmFallbackEnabled = settings.fallback?.enabled ?? true
            llmBudgetEnabled = settings.budget?.enabled ?? true
            llmBudgetPersistLedger = settings.budget?.persistUsageLedger ?? true
            llmMaxRequestsPerHour = settings.budget?.maxRequestsPerHour ?? 60
            llmMaxImageRequestsPerHour = settings.budget?.maxImageRequestsPerHour ?? 12
            llmImageQuestionEnabled = settings.features?.imageQuestion ?? false
            let profiles = try await client.proxyProfiles()
            proxyProfiles = profiles.profiles
            let targets = try await client.proxyValidationTargets()
            if !targets.profiles.isEmpty {
                proxyValidationTargets = targets.profiles
                if !targets.profiles.contains(where: { $0.id == proxyTargetProfile }) {
                    proxyTargetProfile = targets.defaultProfile ?? targets.profiles[0].id
                }
            }
            let monitor = try await client.proxyMonitor()
            proxyMonitorState = monitor.monitor
            let bridgeSettings = try await client.proxyBridgeSettings().settings
            proxyBridgeAutoRestartEnabled = bridgeSettings.autoRestartEnabled
            proxyBridgeState = try await client.proxyBridge()
            let privacy = try await client.privacySettings().settings
            logRetentionEnabled = privacy.logRetentionEnabled
            logRetentionDays = privacy.logRetentionDays
            saveLatestReport = privacy.saveLatestReport
            persistProxyIdentityReport = privacy.persistProxyIdentityReport
            aiStatus = nil
        } catch {
            aiStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func proxyMonitorLabel(_ monitor: ProxyMonitorState) -> String {
        if monitor.running == true {
            let restored = monitor.restored == true ? "，本次启动已自动恢复" : ""
            let persisted = monitor.persisted?.enabled == true ? "，重启后会自动恢复" : ""
            let matrix = monitor.targetProfile ?? monitor.persisted?.targetProfile ?? "baseline"
            return "运行中：\(monitor.profileName ?? monitor.profileId ?? "未知配置")，检测目标 \(matrix)，间隔 \(monitor.interval ?? 0) 秒，已检查 \(monitor.runCount ?? 0) 次\(restored)\(persisted)。"
        }
        if let error = monitor.lastError, !error.isEmpty {
            if monitor.persisted?.enabled == true {
                return "未运行：\(error)。已保存自动恢复配置，修复后重启 Netfix 会再次尝试。"
            }
            return "未运行：\(error)"
        }
        if monitor.persisted?.enabled == true {
            return "未运行：已保存自动恢复配置，等待 Netfix 恢复监控。"
        }
        return "未运行：保存配置后可启动持续健康检查。"
    }

    @ViewBuilder
    private func proxyRepairActionsBlock(_ actions: [ProxyRepairAction]) -> some View {
        if !actions.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("修复建议")
                    .font(.caption2)
                    .fontWeight(.semibold)
                ForEach(actions) { action in
                    VStack(alignment: .leading, spacing: 3) {
                        Text("• \(action.label ?? action.id)：\(action.detail ?? "")")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        if let label = proxyRepairActionButtonLabel(action.uiAction?.type) {
                            Button(label) {
                                Task { await handleProxyRepairAction(action) }
                            }
                            .font(.caption2)
                            .disabled(!backend.isReady)
                        }
                    }
                }
            }
        }
    }

    private func proxyRepairActionButtonLabel(_ type: String?) -> String? {
        switch type {
        case "replace_profile_credentials":
            return "更新凭据"
        case "start_monitor":
            return "重启监控"
        case "import_preview":
            return "重新粘贴代理"
        case "validate_profile":
            return "重新验证"
        case "export_profile":
            return "导出配置"
        case "save_profile":
            return "保存配置"
        default:
            return nil
        }
    }

    @ViewBuilder
    private func proxyProfileRow(_ profile: ProxyProfile) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(profile.name ?? profile.host ?? profile.id)
                            .font(.headline)
                        proxyDeploymentBadge(profile)
                    }
                    Text("\(profile.protocolName ?? "proxy")://\(profile.host ?? "-"):\(profile.port ?? 0)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let check = profile.lastCheck {
                        Text(proxyCheckSummary(check))
                            .font(.caption2)
                            .foregroundStyle(check.status == "ok" ? Color.secondary : Color.orange)
                    } else {
                        Text("已保存但尚未验证。点“开始使用这台 Mac 上网”前，建议先检查或保存时自动检测。")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                HStack(spacing: 6) {
                    Button {
                        Task { await prepareProxyDeployment(profile) }
                    } label: {
                        Label("开始使用这台 Mac 上网", systemImage: "play.circle.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!backend.isReady)

                    Button("更新参数") {
                        Task { await replaceProxyProfile(profile) }
                    }
                    .disabled(!backend.isReady)

                    Button("删除", role: .destructive) {
                        pendingDeleteProxyProfile = profile
                        showDeleteProxyProfileConfirmation = true
                    }
                    .disabled(!backend.isReady)
                }
            }

            DisclosureGroup("更多操作") {
                HStack(spacing: 6) {
                    Button("验证") {
                        Task { await validateSavedProxyProfile(profile) }
                    }
                    .disabled(!backend.isReady)

                    Button("启动监控") {
                        Task { await startProxyMonitor(profile) }
                    }
                    .disabled(!backend.isReady)

                    Button("导出配置包") {
                        Task { await exportProxyProfile(profile) }
                    }
                    .disabled(!backend.isReady)

                    Button("给终端工具使用") {
                        Task { await applyProxyProfile(profile, mode: "app-env", confirmed: false) }
                    }
                    .disabled(!backend.isReady)
                }
                Text("部署会改网络设置，macOS 可能要求管理员密码；需要账号密码的代理会由 Netfix 代管密码。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .font(.caption)
        }
        .padding(.vertical, 4)
    }

    private func proxyDeploymentBadge(_ profile: ProxyProfile) -> some View {
        let lifecycle = proxyBridgeState?.lifecycle
        let deployed = lifecycle?.profileId == profile.id && lifecycle?.status == "running_system"
        let needsAttention = deployed && lifecycle?.needsAttention == true
        return Text(needsAttention ? "异常" : (deployed ? "已部署" : "未部署"))
            .font(.caption2)
            .fontWeight(.semibold)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background((needsAttention ? Color.orange : (deployed ? Color.green : Color.secondary)).opacity(0.14))
            .foregroundStyle(needsAttention ? Color.orange : (deployed ? Color.green : Color.secondary))
            .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func proxyDeploymentConfirmationText() -> String {
        var lines = [
            "Netfix 会先备份当前网络设置。",
            "部署后，Safari、Chrome、微信、钉钉、终端和大多数 App 都会按系统代理使用这组代理。",
        ]
        if let plan = pendingSystemProxyPlan {
            let steps = (plan.steps ?? []).map { friendlyProxyApplyStep($0) }.filter { !$0.isEmpty }
            if !steps.isEmpty {
                lines.append("将执行：\(steps.joined(separator: "；"))。")
            }
            if plan.steps?.contains(where: { ($0.safePreview ?? "").contains("127.0.0.1") || ($0.label ?? "").contains("桥接") }) == true {
                lines.append("这组代理需要 Netfix 保持打开，用来安全代管账号密码。")
            }
        }
        lines.append("不用时可以点“恢复原来的网络设置”，回到部署前的网络配置。")
        return lines.joined(separator: "\n")
    }

    private func friendlyProxyApplyStep(_ step: ProxyApplyStep) -> String {
        let label = step.label ?? ""
        if label.contains("Web/SOCKS") || label.contains("Network Service") {
            return "把这台 Mac 的网络代理指向已保存配置"
        }
        if label.contains("127.0.0.1") || label.contains("桥接") {
            return "需要账号密码时，由 Netfix 在本机安全转发"
        }
        if label.contains("HTTP_PROXY") || label.contains("ALL_PROXY") {
            return "生成给终端工具使用的代理变量"
        }
        if let preview = step.safePreview, !preview.isEmpty {
            return preview
        }
        return label
    }

    private func proxyCheckSummary(_ check: ProxyCheck) -> String {
        if check.status == "ok" {
            let latency = check.latencyMs.map { "\($0)ms" } ?? "延迟未知"
            return "健康：可用，\(latency)。"
        }
        if let error = check.error, !error.isEmpty {
            return "健康：需要处理，\(friendlyProxyError(error))"
        }
        return "健康：\(friendlyProxyStatus(check.status))，TCP \(friendlyProxyStatus(check.tcp))。"
    }

    private func friendlyProxyStatus(_ status: String?) -> String {
        switch status {
        case "ok", "ready", "running": return "正常"
        case "fail", "failed", "error": return "失败"
        case "warn": return "有风险"
        case "timeout": return "超时"
        case "auth_failed": return "认证失败"
        case "unknown", nil: return "未知"
        default: return status ?? "未知"
        }
    }

    private func friendlyProxyError(_ error: String) -> String {
        let lower = error.lowercased()
        if lower.contains("auth") || lower.contains("407") {
            return "账号或密码可能不对，请粘贴新凭据后点“更新凭据”。"
        }
        if lower.contains("timeout") || lower.contains("timed out") {
            return "连接超时，可能是节点不可用或网络质量差，可以换候选或稍后重试。"
        }
        if lower.contains("dns") || lower.contains("name") {
            return "域名解析失败，请检查供应商给的 host 是否正确。"
        }
        if lower.contains("connection refused") || lower.contains("refused") {
            return "代理端口拒绝连接，请检查端口或换一个候选。"
        }
        return error
    }

    private func proxyBridgeLabel(_ state: ProxyBridgeResponse?) -> String {
        guard let state else {
            return "尚未读取代理部署状态。"
        }
        let startupNotice: String
        if let startup = state.startupCheck,
           let startupLifecycle = startup.lifecycle,
           startupLifecycle.needsAttention == true || startupLifecycle.status == "recovery_required" || startupLifecycle.status == "check_failed" {
            startupNotice = "启动时代理检查：\(startupLifecycle.headline ?? startupLifecycle.status ?? "需要处理")。"
        } else if let restart = state.startupCheck?.autoRestart, restart.status == "restarted" {
            let port = restart.bridge?.listenPort.map(String.init) ?? "?"
            startupNotice = "启动时已自动恢复代理连接，本机转发端口 \(port)。"
        } else if state.startupCheck?.settings?.autoRestartEnabled == true {
            startupNotice = "已启用启动时自动恢复；当前没有需要恢复的代理连接。"
        } else {
            startupNotice = ""
        }
        if let lifecycle = state.lifecycle {
            var parts: [String] = []
            if !startupNotice.isEmpty {
                parts.append(startupNotice)
            }
            parts.append("\(lifecycle.headline ?? "代理部署状态")：\(lifecycle.status ?? "unknown")。")
            if let detail = lifecycle.detail, !detail.isEmpty {
                parts.append(detail)
            }
            if let audit = lifecycle.audit {
                parts.append("最近请求 \(audit.requestCount ?? 0) 次，活跃连接 \(audit.activeConnections ?? 0)，最近客户端 \(audit.recentClientCount ?? 0) 个。")
            }
            if lifecycle.requiresNetfixRunning == true {
                parts.append("当前代理需要 Netfix 保持打开；退出前请先恢复原来的网络设置。")
            }
            if lifecycle.recoveryAvailable == true {
                let service = lifecycle.networkService ?? "当前网络服务"
                parts.append("\(service) 可恢复部署前备份的网络代理设置。")
            }
            if let step = lifecycle.nextSteps?.first {
                parts.append(step)
            }
            return parts.joined(separator: " ")
        }
        if state.staleCheck?.recoveryAvailable == true {
            let status = state.staleCheck?.status ?? "unknown"
            let service = state.staleCheck?.networkService ?? "当前网络服务"
            return "\(startupNotice)需要处理：\(service) 仍在使用上次 Netfix 部署的代理（\(status)）。可恢复部署前备份的网络代理设置。"
        }
        if let first = state.bridges.first {
            let port = first.listenPort.map(String.init) ?? "?"
            let idle = (first.idleTimeoutS ?? 0) > 0 ? "，空闲 \(Int(first.idleTimeoutS ?? 0)) 秒后自动关闭" : ""
            return "已让这台 Mac 使用该代理。Netfix 正在本机端口 \(port) 转发请求；请保持 Netfix 打开。不用时点“恢复原来的网络设置”\(idle)。"
        }
        if let status = state.staleCheck?.status, status != "no_journal" {
            return "未启动；恢复检查：\(status)。"
        }
        return "未部署。部署需要账号密码的 HTTP/HTTPS/SOCKS 代理后，会在这里显示当前代理状态。"
    }

    @ViewBuilder
    private func proxyDeploymentDecisionBlock(_ decision: ProxyDeploymentDecision) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(friendlyDeploymentHeadline(decision))
                .font(.caption)
                .fontWeight(.semibold)
            Text(friendlySystemApplyText(decision.systemApply))
                .font(.caption2)
                .foregroundStyle(decision.systemApply?.status == "blocked" ? Color.orange : Color.secondary)
            Text("也可以导出给 Clash / Mihomo / sing-box 等客户端使用。")
                .font(.caption2)
                .foregroundStyle(.secondary)
            if decision.systemApply?.reasonCode == "authenticated_socks_bridge_required" {
                Text("这个代理需要账号密码。开始使用后，请保持 Netfix 打开，系统会先连本机，再由 Netfix 转发到供应商代理。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            ForEach(decision.nextSteps ?? [], id: \.self) { step in
                Text("• \(step)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func friendlyDeploymentHeadline(_ decision: ProxyDeploymentDecision) -> String {
        if decision.systemApply?.status == "blocked" {
            return "这组参数还不能让这台 Mac 使用"
        }
        if decision.systemApply?.status == "available" {
            return "可以开始使用这台 Mac 上网"
        }
        return "已识别代理参数"
    }

    private func friendlySystemApplyText(_ plan: ProxyDeploymentCapability?) -> String {
        guard let plan else {
            return "保存后可以选择是否让这台 Mac 使用它。"
        }
        switch plan.status {
        case "blocked":
            return "还缺信息，先修正代理地址、端口、账号或密码。"
        case "available":
            return "保存到这台 Mac 后，可以点“开始使用这台 Mac 上网”。"
        default:
            return "保存后可以继续检测，再决定是否让这台 Mac 使用。"
        }
    }

    @ViewBuilder
    private func proxyImportPreviewBlock(_ preview: ProxyImportPreviewResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("预检：\(preview.summary.validCount ?? 0) 条可用，\(preview.summary.invalidCount ?? 0) 条需修正")
                .font(.caption)
                .fontWeight(.semibold)
            if let recommendation = preview.recommendation {
                Text("推荐先使用第 \(recommendation.lineNumber ?? 0) 行：\(recommendation.redactedURL ?? "-")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text("已处理 \(preview.summary.processedCount ?? 0) 条，跳过 \(preview.summary.skippedCount ?? 0) 条。预检不会保存代理密码；可先挑一条可用参数，也可直接保存并按当前设置启动监控。")
                .font(.caption2)
                .foregroundStyle(.secondary)

            ForEach(preview.candidates) { candidate in
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("第 \(candidate.lineNumber ?? 0) 行 · \(candidate.ok ? candidate.deploymentDecision?.status ?? "valid" : "invalid")")
                            .font(.caption2)
                            .fontWeight(.semibold)
                        Text(candidate.ok ? candidate.redactedURL ?? "" : candidate.errors?.joined(separator: " / ") ?? "解析失败")
                            .font(.caption2)
                            .foregroundStyle(candidate.ok ? Color.secondary : Color.orange)
                        if let headline = candidate.deploymentDecision?.headline, !headline.isEmpty {
                            Text(headline)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    if candidate.ok {
                        VStack(alignment: .trailing, spacing: 6) {
                            Button("使用此行") {
                                useProxyImportCandidate(candidate)
                            }
                            .disabled(!backend.isReady)

                            Button("保存到这台 Mac") {
                                Task { await saveProxyImportCandidate(candidate) }
                            }
                            .disabled(!backend.isReady)
                        }
                    }
                }
                .padding(6)
                .background(Color(nsColor: .textBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            ForEach(preview.warnings, id: \.self) { warning in
                Text(warning)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func proxyInputLine(_ lineNumber: Int?) -> String {
        guard let lineNumber, lineNumber > 0 else { return "" }
        let lines = proxyInput.components(separatedBy: .newlines)
        let index = lineNumber - 1
        guard index >= 0, index < lines.count else { return "" }
        return lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func useProxyImportCandidate(_ candidate: ProxyImportCandidate) {
        let selected = proxyInputLine(candidate.lineNumber)
        guard !selected.isEmpty else {
            proxyStatus = "失败：未找到对应原始行，请重新粘贴后再试。"
            return
        }
        proxyInput = selected
        proxyImportPreviewResult = nil
        proxyValidateResult = nil
        proxyExportResult = nil
        Task { await parseProxy() }
    }

    private func saveProxyImportCandidate(_ candidate: ProxyImportCandidate) async {
        let selected = proxyInputLine(candidate.lineNumber)
        guard !selected.isEmpty else {
            proxyStatus = "失败：未找到对应原始行，请重新粘贴后再试。"
            return
        }
        proxyInput = selected
        proxyStatus = "正在保存并启动监控..."
        await saveProxyProfile(input: selected)
    }

    private func bridgeStopLabel(_ stop: ProxyBridgeStop?) -> String {
        guard let stop else { return "" }
        if stop.stopped == true {
            return "代理转发已停止：\(stop.bridgeId ?? "unknown")。"
        }
        if stop.missing == true {
            return "代理转发进程已不存在：\(stop.bridgeId ?? "unknown")。"
        }
        if stop.ok == false {
            return "代理转发停止状态未知：\(stop.bridgeId ?? "unknown")。"
        }
        return ""
    }

    @ViewBuilder
    private func proxyExportBlock(_ export: ProxyClientExportResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("客户端配置导出：\(export.profileName ?? export.profileId ?? "当前配置")")
                .font(.caption)
                .fontWeight(.semibold)
            Text("不会显示已保存的代理密码；认证配置需要把 <password> 替换为供应商给你的密码。")
                .font(.caption2)
                .foregroundStyle(.secondary)

            if let package = export.package {
                VStack(alignment: .leading, spacing: 6) {
                    Text("配置包：\(package.name ?? "netfix-proxy") · 推荐 \(package.recommendedFormat ?? "url") · \(package.fileCount ?? package.files?.count ?? 0) 个文件")
                        .font(.caption2)
                        .fontWeight(.semibold)
                    ForEach(package.files ?? []) { file in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Text(file.path ?? file.format ?? "file")
                                    .font(.caption2)
                                    .fontWeight(.semibold)
                                Text(file.secretPlaceholder == true ? "需替换 <password>" : "无明文密码")
                                    .font(.caption2)
                                    .foregroundStyle(file.secretPlaceholder == true ? Color.orange : Color.secondary)
                                Spacer()
                                Button("复制这一段") {
                                    copyToPasteboard(file.content ?? "")
                                }
                                .disabled((file.content ?? "").isEmpty)
                            }
                            Text(file.content ?? "")
                                .font(.system(.caption2, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(6)
                                .background(Color(nsColor: .textBackgroundColor))
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                        }
                    }
                }
            }

            ForEach(export.sortedSnippets, id: \.key) { item in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Text(item.value.label ?? item.key)
                            .font(.caption)
                            .fontWeight(.semibold)
                        Text(item.value.secretPlaceholder == true ? "需替换 <password>" : "无明文密码")
                            .font(.caption2)
                            .foregroundStyle(item.value.secretPlaceholder == true ? Color.orange : Color.secondary)
                        Spacer()
                        Button("复制这一段") {
                            copyToPasteboard(item.value.content ?? "")
                        }
                        .disabled((item.value.content ?? "").isEmpty)
                    }

                    Text(item.value.content ?? "")
                        .font(.system(.caption2, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(6)
                        .background(Color(nsColor: .textBackgroundColor))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                }
            }

            ForEach(export.warnings ?? [], id: \.self) { warning in
                Text(warning)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var selectedLLMProvider: LLMProviderInfo? {
        llmProviders.first(where: { $0.id == llmProvider })
    }

    private var llmChainReadinessBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("链路就绪度")
                .font(.caption)
                .foregroundStyle(.secondary)
            if let readiness = llmChainReadiness, let chains = readiness.chains, !chains.isEmpty {
                if let budget = readiness.budget {
                    Text(budgetStatusText(budget))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                ForEach(chains) { chain in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(chain.label ?? chain.id)
                                .font(.subheadline)
                            Spacer()
                            Text(chain.status ?? "unknown")
                                .font(.caption)
                                .foregroundStyle(chain.ready == true ? .green : .secondary)
                        }
                        Text(chain.nextStep ?? "")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        ForEach(chain.providers ?? []) { provider in
                            HStack {
                                Text(provider.label ?? provider.provider)
                                Spacer()
                                Text(provider.status ?? "unknown")
                                    .foregroundStyle(provider.ready == true ? .green : .secondary)
                                if provider.status == "missing_key" {
                                    Button("配置 Key") {
                                        selectLLMProviderForKey(provider.provider)
                                    }
                                }
                            }
                            .font(.caption2)
                            Text("\(provider.model ?? "") · 密钥 \(provider.apiKeyAccount ?? provider.provider)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            Text(providerAdapterEvidenceText(provider))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                    Divider()
                }
            } else {
                Text("Netfix 准备好后显示 DeepSeek 文本链和 MiniMax/Kimi/Qwen 图片链的密钥就绪状态。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func budgetStatusText(_ budget: LLMChainBudgetStatus) -> String {
        if budget.enabled == false {
            return "本地 AI 请求预算未启用；供应商账单仍以对方后台为准。"
        }
        let totalRemaining = budget.remainingRequests ?? 0
        let totalLimit = budget.maxRequestsPerHour ?? 0
        let imageRemaining = budget.remainingImageRequests ?? 0
        let imageLimit = budget.maxImageRequestsPerHour ?? 0
        let persistence = budget.persisted == true ? "跨重启保留本地计数" : "仅本次运行计数"
        return "本地预算剩余：\(totalRemaining)/\(totalLimit)；图片剩余：\(imageRemaining)/\(imageLimit)。\(persistence)。"
    }

    private func providerAdapterEvidenceText(_ provider: LLMProviderInfo) -> String {
        let checked = provider.metadataCheckedAt?.isEmpty == false ? provider.metadataCheckedAt! : "未记录"
        let tokenField = provider.maxTokensField?.isEmpty == false ? provider.maxTokensField! : "max_tokens"
        let docs = provider.officialDocs?.filter { !$0.isEmpty }.count ?? 0
        return "官方文档核验 \(checked)；请求字段 \(tokenField)；文档 \(docs) 个"
    }

    private func providerAdapterEvidenceText(_ provider: LLMChainProviderReadiness) -> String {
        let checked = provider.metadataCheckedAt?.isEmpty == false ? provider.metadataCheckedAt! : "未记录"
        let tokenField = provider.maxTokensField?.isEmpty == false ? provider.maxTokensField! : "max_tokens"
        let docs = provider.officialDocs?.filter { !$0.isEmpty }.count ?? 0
        return "官方文档核验 \(checked)；请求字段 \(tokenField)；文档 \(docs) 个"
    }

    private func providerStatusText(_ provider: LLMProviderInfo) -> String {
        var parts: [String] = []
        if provider.id == "deepseek" {
            parts.append("适合解释文字诊断报告，暂不处理截图")
        } else if provider.id == "minimax" {
            parts.append("适合国内账号，支持文字解释和截图问诊")
        } else if provider.market == "domestic" {
            parts.append("国内模型，可用于解释脱敏诊断报告")
        } else {
            parts.append("自定义接口")
        }
        if provider.imageQuestionReady == true {
            parts.append("截图问诊已可用")
        } else if provider.imageQuestionProviderSupported == true && provider.imageQuestionAdapterReady != true {
            parts.append("供应商支持图片，但当前适配未启用")
        } else if provider.imageQuestionProviderSupported == true {
            parts.append("支持截图问诊，需在本页开启并保存")
        } else {
            parts.append("只用于文字解释")
        }
        if let notes = provider.notes, !notes.isEmpty {
            parts.append(notes)
        }
        let account = provider.apiKeyAccount ?? provider.id
        if provider.apiKeySet == true {
            parts.append("API Key 已保存（本机密码库：\(account)）")
        } else {
            parts.append("还没保存这个供应商的 API Key")
        }
        return parts.joined(separator: "；")
    }

    private func applyProviderPreset(_ providerID: String) {
        guard let provider = llmProviders.first(where: { $0.id == providerID }) else { return }
        if !provider.baseURL.isEmpty {
            llmBaseURL = provider.baseURL
        }
        if !provider.model.isEmpty {
            llmModel = provider.model
        }
        llmAPIKeyAccount = provider.id
        aiStatus = providerStatusText(provider)
    }

    private func prepareRecommendedLLMProvider(_ providerID: String) {
        llmEnabled = true
        llmProvider = providerID
        applyProviderPreset(providerID)
        llmAPIKey = ""
        uploadConsent = "ask_each_time"
        llmFallbackEnabled = true
        llmBudgetEnabled = true
        llmBudgetPersistLedger = true
        if providerID == "minimax" || providerID == "moonshot_kimi" || providerID == "qwen" {
            llmImageQuestionEnabled = true
        }
        let label = llmProviders.first(where: { $0.id == providerID })?.label ?? providerID
        aiStatus = "已选择 \(label)。粘贴 API Key 后点“保存并测试”；密钥只保存在本机密码库。"
    }

    private func selectLLMProviderForKey(_ providerID: String) {
        llmProvider = providerID
        applyProviderPreset(providerID)
        llmAPIKey = ""
        let label = llmProviders.first(where: { $0.id == providerID })?.label ?? providerID
        aiStatus = "正在配置 \(label) 的 API Key，保存后链路就绪度会刷新。"
    }

    private func proxyIdentitySummary(_ report: ProxyIdentityReport) -> String {
        let identity = report.identity
        let exit = report.exitIP ?? "未知出口 IP"
        let location = [identity?.countryCode, identity?.region, identity?.city]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " / ")
        let network = [identity?.isp, identity?.asn]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " / ")
        let type = identity?.ipType ?? "未知类型"
        let dns = report.dnsLeak?.status ?? "unknown"
        let ipv6 = report.ipv6Leak?.status ?? "unknown"
        let targetFails = (report.targets ?? []).filter { $0.status == "fail" }.count
        let matrix = report.targetProfileLabel ?? report.targetProfile ?? "baseline"
        var parts = ["检测目标 \(matrix)", "出口 \(exit)", "位置 \(location.isEmpty ? "未知" : location)", "类型 \(type)", "DNS/IPv6 \(dns)/\(ipv6)"]
        if !network.isEmpty {
            parts.append(network)
        }
        if targetFails > 0 {
            parts.append("目标失败 \(targetFails) 个")
        }
        if let warning = report.warnings?.first, !warning.isEmpty {
            parts.append(warning)
        }
        return parts.joined(separator: "；")
    }

    private func proxyValidationStatus(_ result: ProxyValidateResponse, matrix: String) -> String {
        if !result.ok {
            return "验证未通过：\(result.proxyCheck?.error ?? "未知错误")"
        }
        if result.identityReport?.status == "warn" {
            return "验证有风险：\(matrix)。"
        }
        return "验证通过：\(matrix)。"
    }

    @discardableResult
    private func saveLLMSettings() async -> Bool {
        guard let client = client() else {
            aiStatus = "失败：Netfix 还没准备好。"
            return false
        }
        do {
            let response = try await client.saveLLMSettings(
                enabled: llmEnabled,
                provider: llmProvider,
                baseURL: llmBaseURL,
                model: llmModel,
                apiKeyAccount: llmAPIKeyAccount,
                apiKey: llmAPIKey,
                redactionLevel: redactionLevel,
                uploadConsent: uploadConsent,
                fallbackEnabled: llmFallbackEnabled,
                budgetEnabled: llmBudgetEnabled,
                persistUsageLedger: llmBudgetPersistLedger,
                maxRequestsPerHour: llmMaxRequestsPerHour,
                maxImageRequestsPerHour: llmMaxImageRequestsPerHour,
                imageQuestionEnabled: llmImageQuestionEnabled
            )
            llmAPIKeySet = response.settings.apiKeySet
            llmAPIKey = ""
            let providers = try await client.llmProviders()
            llmProviders = providers.providers
            llmChainReadiness = try await client.llmChainReadiness()
            aiStatus = "已保存 AI 设置。现在可以回到主界面问 AI。"
            return true
        } catch {
            aiStatus = "失败：\(error.localizedDescription)"
            return false
        }
    }

    private func saveAndTestLLMSettings() async {
        guard llmAPIKeySet || !llmAPIKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            aiStatus = "先粘贴 API Key，再点“保存并测试”。"
            return
        }
        aiStatus = "正在保存并测试当前 AI 供应商。"
        if await saveLLMSettings() {
            await testLLMConnection()
        }
    }

    private func importDeepSeekSidecarKey() async {
        guard let client = client() else {
            aiStatus = "失败：Netfix 还没准备好。"
            return
        }
        aiStatus = "正在导入 DeepSeek 侧车 Key；不会显示或记录密钥。"
        do {
            let response = try await client.importDeepSeekSidecarKey()
            if let settings = response.settings {
                llmEnabled = settings.enabled
                llmProvider = settings.provider
                llmBaseURL = settings.baseURL
                llmModel = settings.model
                llmAPIKeyAccount = settings.apiKeyAccount
                llmAPIKeySet = settings.apiKeySet
            } else {
                llmEnabled = response.llmEnabled ?? true
                llmProvider = "deepseek"
                llmAPIKeyAccount = response.apiKeyAccount ?? "deepseek"
                llmAPIKeySet = response.apiKeySet ?? true
                if let model = response.model {
                    llmModel = model
                }
            }
            llmAPIKey = ""
            let providers = try await client.llmProviders()
            llmProviders = providers.providers
            llmChainReadiness = try await client.llmChainReadiness()
            aiStatus = "已导入 DeepSeek 侧车 Key，模型：\(response.model ?? llmModel)。现在可以问 AI 或测试链路。"
        } catch {
            aiStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func testLLMConnection() async {
        guard let client = client() else {
            aiStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            _ = try await client.testLLM(timeout: 30)
            let label = llmProviders.first(where: { $0.id == llmProvider })?.label ?? llmProvider
            aiStatus = "测试成功：\(label) 可以返回结构化解释。现在可以回到主界面问 AI。"
        } catch {
            aiStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func llmChainTestSummary(_ result: LLMChainTestResponse) -> String {
        let chains = result.chains ?? []
        let parts = chains.map { chain in
            "\(chain.label ?? chain.id)：\(chain.status ?? "unknown") ok \(chain.okCount ?? 0) / failed \(chain.failedCount ?? 0) / skipped \(chain.skippedCount ?? 0)"
        }
        if parts.isEmpty {
            return result.error ?? "没有可测试的链路。"
        }
        return parts.joined(separator: "；")
    }

    private func testLLMChain() async {
        guard let client = client() else {
            aiStatus = "失败：Netfix 还没准备好。"
            return
        }
        aiStatus = "正在测试国内模型链路；这会调用已配置供应商并可能计入用量。"
        do {
            let result = try await client.testLLMChain(timeout: 60)
            aiStatus = result.ok ? "链路测试通过：\(llmChainTestSummary(result))" : "链路测试未通过：\(llmChainTestSummary(result))"
            llmChainReadiness = try await client.llmChainReadiness()
        } catch {
            aiStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func parseProxy() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let result = try await client.parseProxy(input: proxyInput, protocolHint: proxyProtocolHint)
            proxyParseResult = result
            proxyImportPreviewResult = nil
            proxyValidateResult = nil
            proxyExportResult = nil
            proxyStatus = result.ok ? "解析成功，未保存明文密码。" : "失败：\(result.errors?.joined(separator: "、") ?? "格式不正确")"
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func importProxyPreview() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let result = try await client.importProxyPreview(input: proxyInput, limit: 50, protocolHint: proxyProtocolHint)
            proxyImportPreviewResult = result
            proxyParseResult = nil
            proxyValidateResult = nil
            proxyExportResult = nil
            let valid = result.summary.validCount ?? 0
            let invalid = result.summary.invalidCount ?? 0
            proxyStatus = result.ok ? "预检完成：\(valid) 条可用，\(invalid) 条需修正。" : "预检没有找到可用候选。"
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func validateProxy() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let result = try await client.validateProxy(input: proxyInput, timeout: 10, targetProfile: proxyTargetProfile, protocolHint: proxyProtocolHint)
            proxyValidateResult = result
            proxyImportPreviewResult = nil
            proxyExportResult = nil
            let matrix = proxyValidationTargets.first(where: { $0.id == proxyTargetProfile })?.label ?? proxyTargetProfile
            proxyStatus = proxyValidationStatus(result, matrix: matrix)
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func validateSavedProxyProfile(_ profile: ProxyProfile) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let result = try await client.validateProxyProfile(profileID: profile.id, timeout: 10, targetProfile: proxyTargetProfile)
            proxyValidateResult = result
            proxyImportPreviewResult = nil
            proxyExportResult = nil
            if let updated = result.profile {
                proxyProfiles.removeAll { $0.id == updated.id }
                proxyProfiles.append(updated)
            }
            let matrix = proxyValidationTargets.first(where: { $0.id == proxyTargetProfile })?.label ?? proxyTargetProfile
            proxyStatus = proxyValidationStatus(result, matrix: matrix)
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func saveProxyProfile(input overrideInput: String? = nil) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let profileInput = overrideInput ?? proxyInput
            let result = try await client.saveProxyProfile(input: profileInput, startMonitor: proxyStartMonitorOnSave, targetProfile: proxyTargetProfile, protocolHint: proxyProtocolHint)
            if let profile = result.profile {
                proxyProfiles.removeAll { $0.id == profile.id }
                proxyProfiles.append(profile)
                lastSavedProxyProfile = profile
            }
            if let monitor = result.monitor {
                proxyMonitorState = monitor
            }
            proxyImportPreviewResult = nil
            proxyParseResult = nil
            proxyValidateResult = nil
            proxyExportResult = nil
            if result.ok {
                if result.monitor?.running == true {
                    proxyStatus = "已保存到这台 Mac，密码已写入本机密码库，后台监控已启动。还没有影响浏览器，下一步点“开始使用这台 Mac 上网”。"
                } else if result.monitor != nil {
                    proxyStatus = "已保存到这台 Mac，密码已写入本机密码库，但后台监控未启动。还没有影响浏览器，下一步点“开始使用这台 Mac 上网”。"
                } else {
                    proxyStatus = "已保存到这台 Mac，密码已写入本机密码库。还没有影响浏览器，下一步点“开始使用这台 Mac 上网”。"
                }
            } else {
                lastSavedProxyProfile = nil
                proxyStatus = "失败：\(result.error ?? "无法保存")"
            }
            if result.monitor == nil {
                await loadProxyMonitor()
            }
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func replaceProxyProfile(_ profile: ProxyProfile) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        let input = proxyInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !input.isEmpty else {
            proxyStatus = "请先在输入框粘贴新的代理连接参数，再点击对应配置的“更新参数”。"
            return
        }
        do {
            let result = try await client.replaceProxyProfile(
                profileID: profile.id,
                input: input,
                startMonitor: proxyStartMonitorOnSave,
                targetProfile: proxyTargetProfile,
                protocolHint: proxyProtocolHint
            )
            if let updated = result.profile {
                proxyProfiles.removeAll { $0.id == updated.id }
                proxyProfiles.append(updated)
            }
            if let monitor = result.monitor {
                proxyMonitorState = monitor
            }
            proxyImportPreviewResult = nil
            proxyParseResult = nil
            proxyValidateResult = nil
            proxyExportResult = nil
            proxyStatus = result.ok
                ? "已更新代理连接参数。新密码已写入本机密码库；要切全机流量请点“开始使用这台 Mac 上网”。"
                : "失败：\(result.error ?? "无法更新凭据")"
            if result.monitor == nil {
                await loadProxyMonitor()
            }
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func handleProxyRepairAction(_ action: ProxyRepairAction) async {
        guard let type = action.uiAction?.type else { return }
        let profileId = action.uiAction?.profileId ?? ""
        switch type {
        case "replace_profile_credentials":
            guard let profile = proxyProfiles.first(where: { $0.id == profileId }) else {
                proxyStatus = "请先在输入框粘贴新的代理连接参数，并选择要更新的配置。"
                return
            }
            await replaceProxyProfile(profile)
        case "start_monitor":
            guard !profileId.isEmpty, let client = client() else {
                proxyStatus = "失败：Netfix 还没准备好，或没有可重启的配置。"
                return
            }
            do {
                let response = try await client.startProxyMonitor(profileID: profileId, interval: 60, timeout: 10, targetProfile: proxyTargetProfile)
                proxyMonitorState = response.monitor
                proxyStatus = response.ok ? "后台监控已重启。" : "失败：\(response.error ?? "无法重启监控")"
            } catch {
                proxyStatus = "失败：\(error.localizedDescription)"
            }
        case "import_preview":
            await importProxyPreview()
        case "validate_profile":
            guard let profile = proxyProfiles.first(where: { $0.id == profileId }) else {
                proxyStatus = "失败：没有可重新验证的配置。"
                return
            }
            await validateSavedProxyProfile(profile)
        case "export_profile":
            guard let profile = proxyProfiles.first(where: { $0.id == profileId }) else {
                proxyStatus = "失败：没有可导出的配置。"
                return
            }
            await exportProxyProfile(profile)
        case "save_profile":
            await saveProxyProfile()
        default:
            proxyStatus = "失败：未识别的修复动作 \(type)。"
        }
    }

    private func loadProxyMonitor() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.proxyMonitor()
            proxyMonitorState = response.monitor
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func loadProxyBridge() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            proxyBridgeState = try await client.proxyBridge()
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func saveProxyBridgeSettings(autoRestartEnabled: Bool) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.saveProxyBridgeSettings(autoRestartEnabled: autoRestartEnabled)
            proxyBridgeAutoRestartEnabled = response.settings.autoRestartEnabled
            proxyStatus = response.settings.autoRestartEnabled
                ? "已启用启动时自动恢复代理连接。不会静默修改网络代理设置。"
                : "已关闭启动时自动恢复代理连接。"
            await loadProxyBridge()
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func startProxyMonitor(_ profile: ProxyProfile) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.startProxyMonitor(profileID: profile.id, interval: 60, timeout: 10, targetProfile: proxyTargetProfile)
            proxyMonitorState = response.monitor
            proxyStatus = response.ok ? "后台监控已启动。" : "失败：\(response.error ?? "无法启动监控")"
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func prepareProxyDeployment(_ profile: ProxyProfile) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        pendingSystemProxyProfile = profile
        pendingSystemProxyPlan = nil
        proxyStatus = "正在生成部署预览，不会修改网络设置…"
        do {
            pendingSystemProxyPlan = try await client.applyProxyDryRun(profileID: profile.id, mode: "system")
            showSystemProxyConfirmation = true
            proxyStatus = nil
        } catch {
            pendingSystemProxyProfile = nil
            pendingSystemProxyPlan = nil
            proxyStatus = "失败：无法生成部署预览。\(error.localizedDescription)"
        }
    }

    private func stopProxyMonitor() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.stopProxyMonitor()
            proxyMonitorState = response.monitor
            proxyStatus = response.ok ? "后台监控已停止。" : "失败：\(response.error ?? "无法停止监控")"
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func deleteProxyProfile(_ profile: ProxyProfile) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.deleteProxyProfile(profileID: profile.id)
            pendingDeleteProxyProfile = nil
            if response.ok {
                proxyProfiles.removeAll { $0.id == profile.id }
                proxyParseResult = nil
                proxyValidateResult = nil
                proxyExportResult = nil
                var detail: [String] = []
                if response.monitorStopped == true {
                    detail.append("停止对应后台监控")
                }
                if response.monitorPersistedCleared == true {
                    detail.append("清理重启自动恢复配置")
                }
                proxyStatus = detail.isEmpty
                    ? "已删除配置。"
                    : "已删除配置，并\(detail.joined(separator: "，"))。"
                await loadProxyMonitor()
            } else {
                proxyStatus = "失败：\(response.error ?? "无法删除配置")"
            }
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func exportProxyProfile(_ profile: ProxyProfile) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.exportProxyProfile(profileID: profile.id, format: "all")
            proxyExportResult = response
            proxyStatus = response.ok ? "已生成客户端配置片段。" : "失败：\(response.error ?? "无法导出配置")"
        } catch {
            proxyExportResult = nil
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func applyProxyProfile(_ profile: ProxyProfile, mode: String, confirmed: Bool) async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.applyProxyProfile(profileID: profile.id, mode: mode, confirmed: confirmed, targetProfile: proxyTargetProfile)
            pendingSystemProxyProfile = nil
            pendingSystemProxyPlan = nil
            lastSavedProxyProfile = nil
            if response.ok && response.status == "applied" {
                if mode == "app-env" {
                    let keys = response.applied?.envKeys?.joined(separator: ", ") ?? "HTTP_PROXY/HTTPS_PROXY"
                    proxyStatus = "已生成给终端工具使用的代理环境：\(keys)。"
                } else if response.applied?.scope == "loopback_bridge" {
                    let port = response.bridge?.listenPort.map(String.init) ?? "?"
                    proxyStatus = "已部署到这台 Mac，本机转发端口 \(port)。请保持 Netfix 打开；不用时点“恢复原来的网络设置”。"
                } else {
                    let service = response.networkService ?? "当前网络服务"
                    proxyStatus = "已部署到 \(service)。不用时点“恢复原来的网络设置”。"
                }
                await loadProxyBridge()
                await startProxyMonitor(profile)
                return
            }
            if response.reasonCode == "bridge_unsupported_upstream_protocol" {
                proxyStatus = response.friendlyFailureMessage
                return
            }
            if response.ok && response.status == "pending_confirmation" {
                proxyStatus = "还需要确认。请重新点“开始使用这台 Mac 上网”，并在中文确认框里确认。"
                return
            }
            proxyStatus = "失败：\(response.friendlyFailureMessage)"
        } catch {
            pendingSystemProxyProfile = nil
            pendingSystemProxyPlan = nil
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func rollbackProxyProfile() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.rollbackProxyProfile(confirmed: true)
            if response.ok {
                let stop = bridgeStopLabel(response.bridgeStop)
                proxyStatus = response.status == "rolled_back"
                    ? "已恢复原来的网络设置。\(stop)"
                    : "恢复状态：\(response.status ?? "unknown")。\(stop)"
                await loadProxyBridge()
            } else {
                proxyStatus = "失败：\(response.error ?? response.status ?? "无法恢复网络设置")"
            }
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func recoverProxyBridge() async {
        guard let client = client() else {
            proxyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.recoverProxyBridge(confirmed: true)
            if response.ok {
                let stop = bridgeStopLabel(response.bridgeStop)
                proxyStatus = response.status == "recovered"
                    ? "已恢复原来的网络设置，失效代理已处理。\(stop)"
                    : "恢复状态：\(response.status ?? "unknown")。\(stop)"
                await loadProxyBridge()
            } else {
                proxyStatus = "失败：\(response.error ?? response.status ?? "无法恢复桥接")"
            }
        } catch {
            proxyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func savePrivacySettings() async {
        guard let client = client() else {
            privacyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let response = try await client.savePrivacySettings(
                logRetentionEnabled: logRetentionEnabled,
                logRetentionDays: logRetentionDays,
                saveLatestReport: saveLatestReport,
                persistProxyIdentityReport: persistProxyIdentityReport
            )
            logRetentionEnabled = response.settings.logRetentionEnabled
            logRetentionDays = response.settings.logRetentionDays
            saveLatestReport = response.settings.saveLatestReport
            persistProxyIdentityReport = response.settings.persistProxyIdentityReport
            let removed = response.retention?.removed ?? 0
            privacyStatus = "已保存。事件日志已裁剪 \(removed) 条。"
        } catch {
            privacyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func clearLogs() async {
        guard let client = client() else {
            privacyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let result = try await client.clearLogs()
            privacyStatus = result.ok ? "已清理 \(result.removed.count) 个日志文件。" : "失败：部分日志无法清理。"
        } catch {
            privacyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func clearAllLocalData() async {
        guard let client = client() else {
            privacyStatus = "失败：Netfix 还没准备好。"
            return
        }
        do {
            let result = try await client.clearAllLocalData()
            let deletedSecrets = result.keychain?.deleted?.count ?? 0
            let removedLogs = result.logs?.removed.count ?? 0
            let removedBudgetLedgers = result.llmBudget?.removed.count ?? 0
            privacyStatus = result.ok
                ? "已删除 \(removedLogs) 个日志文件、\(removedBudgetLedgers) 个 AI 预算账本，并清理 \(deletedSecrets) 个已保存密钥。"
                : "失败：部分本地数据无法删除。"
            if result.ok {
                llmAPIKeySet = false
                proxyProfiles = []
                await loadCloudAndProxySettings()
            }
        } catch {
            privacyStatus = "失败：\(error.localizedDescription)"
        }
    }

    private func setLoginItem(enabled: Bool) {
        if #available(macOS 13.0, *) {
            let service = SMAppService.mainApp
            do {
                if enabled {
                    try service.register()
                } else {
                    try service.unregister()
                }
                loginItemError = nil
            } catch {
                launchAtLogin = !enabled
                loginItemError = "无法\(enabled ? "开启" : "关闭")登录时启动：\(error.localizedDescription)\n请确认 Netfix 已放入 /Applications 目录，且你有管理员权限。"
            }
        }
    }

    private func openLocalNetworkSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocalNetwork") {
            NSWorkspace.shared.open(url)
        }
    }

    private func openNotificationSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.notifications") {
            NSWorkspace.shared.open(url)
        }
    }

    private func copyToPasteboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}
