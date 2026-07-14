import SwiftUI
import AppKit

/// 首次启动的代理设置页。
struct ProxySetupView: View {
    @ObservedObject var backend: Backend
    @ObservedObject var dashboardStore: DashboardStateStore
    var onContinue: () -> Void
    var onSkip: () -> Void

    @State private var isScanning = false
    @State private var baselineDone = false
    @State private var errorMessage: String?
    @State private var client: APIClient?
    @State private var environment: EnvironmentResponse?
    @State private var proxyInput = ""
    @State private var proxyProtocolHint = "auto"
    @State private var proxyTargetProfile = "baseline"
    @State private var proxyValidationTargets: [ProxyValidationTargetProfile] = [
        ProxyValidationTargetProfile(id: "baseline", label: "通用连通性", description: nil, probes: nil),
        ProxyValidationTargetProfile(id: "ai_dev", label: "AI 与开发工具", description: nil, probes: nil),
    ]
    @State private var proxyPreview: ProxyImportPreviewResponse?
    @State private var proxyParseResult: ProxyParseResponse?
    @State private var proxyValidateResult: ProxyValidateResponse?
    @State private var proxySaveStatus: String?
    @State private var savedProxyProfile: ProxyProfile?
    @State private var proxyDeployPlan: ProxyApplyPlan?
    @State private var showProxyDeployConfirmation = false
    @State private var showProxyRecoveryConfirmation = false
    @State private var isProxyWorking = false

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "network.badge.shield.half.filled")
                .font(.system(size: 46))
                .foregroundStyle(.blue)
                .accessibilityHidden(true)

            VStack(spacing: 10) {
                Text("添加你的代理")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("首次设置，有代理参数可以直接粘贴")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if let env = detectedEnvironment {
                    VStack(spacing: 6) {
                        Text(env.headline)
                            .font(.headline)
                            .multilineTextAlignment(.center)
                        if let detail = env.detail {
                            Text(detail)
                                .font(.body)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                    }
                } else if backend.isReady {
                    Text("没看到你电脑里有代理软件。没关系，可以直接粘贴你已有的合法代理参数。")
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                } else {
                    Text("正在准备…")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("你有合法代理参数吗？有的话复制粘贴")
                    .font(.headline)
                Text("去你的代理服务后台，复制一整行连接信息。一般包含地址、端口、用户名和密码。密码保存到本机密码库，不上传。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("复制下来大概是：地址:端口:用户名:密码 这种样子。不要只复制出口 IP。没有这类参数也可以先跳过。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Picker("服务商写的类型", selection: $proxyProtocolHint) {
                    Text("自动判断").tag("auto")
                    Text("HTTP 代理").tag("http")
                    Text("SOCKS5").tag("socks5h")
                }
                .pickerStyle(.segmented)
                .accessibilityHint("不确定时保持自动判断")

                Picker("检测目标", selection: $proxyTargetProfile) {
                    ForEach(proxyValidationTargets) { target in
                        Text(target.label ?? target.id).tag(target.id)
                    }
                }
                .pickerStyle(.segmented)
                .help("默认选「通用连通性」；只有当你需要检查 GitHub / OpenAI / DeepSeek / Kimi / MiniMax 时再选「AI 与开发工具」。")
                .accessibilityHint("选择你最关心的网络用途")

                ZStack(alignment: .topLeading) {
                    TextEditor(text: $proxyInput)
                        .font(.system(.body, design: .monospaced))
                        .frame(minHeight: 72, maxHeight: 96)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.secondary.opacity(0.25))
                        )
                        .accessibilityLabel("代理连接参数")
                        .accessibilityHint("粘贴包含地址、端口、用户名和密码的完整一行")
                    if proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text("例如 proxy.example.com:8001:用户名:密码\n也支持 http:// 或 socks5h:// 链接")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 8)
                            .allowsHitTesting(false)
                    }
                }
                HStack {
                    Button {
                        Task { await saveProxyInput() }
                    } label: {
                        Label("检查并保存到这台 Mac", systemImage: "tray.and.arrow.down")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isProxyWorking)

                    Button("只检查") {
                        Task { await previewProxyInput() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isProxyWorking)
                }

                Text("“只检查”不会保存密码；确认没问题后再点“检查并保存”。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Text("不支持 ss://、vmess://、Clash / sing-box 订阅链接。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                if isProxyWorking {
                    ProgressView("正在处理代理参数…")
                        .controlSize(.small)
                }
                if let preview = proxyPreview {
                    Text("预检：\(preview.summary.validCount ?? 0) 条可用，\(preview.summary.invalidCount ?? 0) 条需修正。\(preview.recommendation?.headline ?? "可选择可用候选保存。")")
                        .font(.caption)
                        .foregroundStyle((preview.summary.validCount ?? 0) > 0 ? Color.secondary : Color.orange)
                }
                if let proxySaveStatus {
                    Text(proxySaveStatus)
                        .font(.caption)
                        .foregroundStyle(proxySaveStatus.hasPrefix("失败") ? Color.red : Color.secondary)
                }
                if let profile = savedProxyProfile {
                    HStack {
                        Button {
                            Task { await prepareProxyDeployment(profile) }
                        } label: {
                            Label("开始使用代理", systemImage: "play.circle.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!backend.isReady || isProxyWorking)

                        Button("进入主界面") {
                            onContinue()
                        }
                    }
                    .font(.caption)
                }
                if dashboardStore.state?.resolvedSecondaryActionTarget == .staleBridgeRecovery {
                    Button(role: .destructive) {
                        showProxyRecoveryConfirmation = true
                    } label: {
                        Label("停止使用并恢复原设置", systemImage: "stop.circle")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!backend.isReady || isProxyWorking)
                }
            }
            .padding()
            .background(Color(nsColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 10))

            if let error = errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            }

            HStack(spacing: 16) {
                Button("跳过") {
                    onSkip()
                }
                .buttonStyle(.borderless)

                Button("快速检测一下网络（可选）") {
                    Task { await runBaseline() }
                }
                .buttonStyle(.borderless)
                .controlSize(.small)
                .disabled(!backend.isReady || isScanning)
            }
        }
        .padding(32)
        .frame(minWidth: 460, minHeight: 560)
        .task {
            bindClient()
            await dashboardStore.refresh()
            await loadEnvironment()
        }
        .onChange(of: backend.state) { _ in
            bindClient()
            Task { await loadEnvironment() }
        }
        .confirmationDialog("开始使用代理？", isPresented: $showProxyDeployConfirmation, titleVisibility: .visible) {
            Button("确认开始使用") {
                if let profile = savedProxyProfile {
                    Task { await applySavedProxyProfile(profile) }
                }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text(proxyDeploymentConfirmationText())
        }
        .confirmationDialog("停止使用代理？", isPresented: $showProxyRecoveryConfirmation, titleVisibility: .visible) {
            Button("停止并恢复", role: .destructive) {
                Task { await recoverProxyBridge() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会停止 Netfix 代理，并恢复使用代理前的网络设置。")
        }
    }

    private func previewProxyInput() async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = nil
        savedProxyProfile = nil
        do {
            let parsed = try await client.parseProxy(
                input: proxyInput,
                protocolHint: proxyProtocolHint
            )
            guard parsed.ok else {
                throw ProxySetupWorkflowError.parseFailed(
                    parsed.errors?.joined(separator: "、") ?? "格式不正确"
                )
            }
            proxyParseResult = parsed
            let validation = try await client.validateProxy(
                input: proxyInput,
                timeout: 10,
                includeIdentity: true,
                targetProfile: proxyTargetProfile,
                protocolHint: proxyProtocolHint
            )
            proxyValidateResult = validation
            proxyPreview = nil
            if validation.ok && validation.proxyCheck?.status == "ok" {
                let latency = validation.proxyCheck?.latencyMs.map { "，延迟 \($0)ms" } ?? ""
                proxySaveStatus = "检查通过\(latency)。还没有保存或启用。"
            } else {
                throw ProxySetupWorkflowError.validationFailed(
                    validation.errors?.joined(separator: "、")
                        ?? validation.proxyCheck?.error
                        ?? "无法连通"
                )
            }
        } catch {
            proxyParseResult = nil
            proxyValidateResult = nil
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        isProxyWorking = false
    }

    private func saveProxyInput() async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = "正在识别并检查这组代理，通过后才会保存…"
        savedProxyProfile = nil
        do {
            let result = try await ProxySetupWorkflow(client: client).validateAndSave(
                input: proxyInput,
                protocolHint: proxyProtocolHint,
                targetProfile: proxyTargetProfile,
                startMonitor: true
            )
            proxyParseResult = result.parsed
            proxyValidateResult = result.validation
            proxyPreview = nil
            savedProxyProfile = result.savedProfile
            proxySaveStatus = result.saveResponse.monitor?.running == true
                ? "检查通过，已保存并开始持续检查。点下面「开始使用代理」才会改变网络设置。"
                : "检查通过，已保存到这台 Mac。点下面「开始使用代理」才会改变网络设置。"
            await dashboardStore.refresh()
        } catch {
            proxyParseResult = nil
            proxyValidateResult = nil
            savedProxyProfile = nil
            let card = UserFacingMessages.classify(error.localizedDescription)
            proxySaveStatus = "失败：\(card.headline)\n\(card.nextStep)"
        }
        isProxyWorking = false
    }

    private func prepareProxyDeployment(_ profile: ProxyProfile) async {
        guard let client = client else { return }
        guard profile.verificationStatus == "verified", profile.canApply == true else {
            proxySaveStatus = "这条代理还没通过检查，不会启用。请重新检查并保存。"
            return
        }
        isProxyWorking = true
        proxySaveStatus = "正在准备启用预览，不会修改网络设置…"
        do {
            proxyDeployPlan = try await client.applyProxyDryRun(profileID: profile.id, mode: "system")
            proxySaveStatus = nil
            showProxyDeployConfirmation = true
        } catch {
            proxyDeployPlan = nil
            proxySaveStatus = "失败：无法准备启用预览。\(error.localizedDescription)"
        }
        isProxyWorking = false
    }

    private func applySavedProxyProfile(_ profile: ProxyProfile) async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = "正在让这台 Mac 使用代理上网。会先备份原来的网络设置…"
        do {
            let response = try await client.applyProxyProfile(profileID: profile.id, mode: "system", confirmed: true, targetProfile: proxyTargetProfile)
            if response.ok && response.status == "applied" {
                if response.verify?.ok == false {
                    proxySaveStatus = "失败：启用后的网络检查未通过，Netfix 已停止继续使用这条线路。"
                    await dashboardStore.refresh()
                    isProxyWorking = false
                    return
                }
                if response.applied?.scope == "loopback_bridge" {
                    proxySaveStatus = "已开始使用代理。请保持 Netfix 打开；不用时点「停止使用并恢复原设置」。"
                } else {
                    let service = response.networkService ?? "当前网络服务"
                    proxySaveStatus = "已在 \(service) 开始使用代理。不用时点「停止使用并恢复原设置」。"
                }
            } else if response.status == "pending_confirmation" {
                proxySaveStatus = "还需要确认。请再点一次“开始使用代理”。"
            } else {
                proxySaveStatus = "失败：\(response.friendlyFailureMessage)"
            }
        } catch {
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        await dashboardStore.refresh()
        isProxyWorking = false
    }

    private func recoverProxyBridge() async {
        guard let client else { return }
        isProxyWorking = true
        proxySaveStatus = "正在停止代理并恢复原设置…"
        do {
            let response = try await client.recoverProxyBridge(confirmed: true)
            if response.ok && response.status == "recovered" {
                proxySaveStatus = "已停止使用代理，并恢复原来的网络设置。"
            } else if response.ok && response.status == "no_recovery_needed" {
                proxySaveStatus = "失败：当前没有执行恢复。代理可能仍在使用中，请保持 Netfix 运行并重新读取状态。"
            } else {
                proxySaveStatus = "失败：\(response.error ?? response.status ?? "恢复没有完成")"
            }
        } catch {
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        await dashboardStore.refresh()
        isProxyWorking = false
    }

    private func proxyDeploymentConfirmationText() -> String {
        var lines = [
            "开始使用后，Netfix 会先备份你现在的网络设置，再让这台 Mac 走代理。",
            "Safari、Chrome、微信、钉钉和大多数 App 都会使用这个代理。",
        ]
        if proxyDeployPlan?.steps?.contains(where: { ($0.safePreview ?? "").contains("127.0.0.1") || ($0.label ?? "").contains("桥接") }) == true {
            lines.append("这组代理需要 Netfix 保持打开，用来安全代管账号密码。")
        }
        lines.append("不用时到设置里点“恢复原来的网络设置”，随时回到现在的配置。")
        return lines.joined(separator: "\n")
    }

    private func bindClient() {
        guard client == nil, let url = backend.apiURL, let token = backend.apiToken else { return }
        client = APIClient(baseURL: url, apiToken: token)
    }

    private func loadEnvironment() async {
        guard let client = client else { return }
        do {
            environment = try await client.environment()
        } catch {
            // 环境接口可选，失败不影响主流程。
        }
    }

    private func runBaseline() async {
        guard let client = client else { return }
        isScanning = true
        errorMessage = nil
        do {
            _ = try await client.diagnose(timeout: 120)
            baselineDone = true
            onContinue()
        } catch {
            errorMessage = "网络检测失败：\(error.localizedDescription)"
        }
        isScanning = false
    }

    private struct DetectedEnv {
        let headline: String
        let detail: String?
    }

    private var detectedEnvironment: DetectedEnv? {
        guard backend.isReady else { return nil }
        if let env = environment, env.ok {
            if let client = env.guiClient, !client.isEmpty {
                return DetectedEnv(
                    headline: "检测到你已经运行了 \(client)（如 Clash），可以跳过直接进主界面",
                    detail: nil
                )
            }
            return DetectedEnv(
                headline: "没检测到代理客户端，直接粘贴参数",
                detail: "也可以先跳过，进主界面后再粘贴。"
            )
        }
        return DetectedEnv(
            headline: "正在识别…",
            detail: nil
        )
    }
}
