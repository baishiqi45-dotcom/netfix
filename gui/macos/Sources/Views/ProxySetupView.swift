import SwiftUI
import AppKit

/// 首次启动的代理识别与基线检测页。
struct ProxySetupView: View {
    @ObservedObject var backend: Backend
    var onContinue: () -> Void
    var onSkip: () -> Void

    @State private var isScanning = false
    @State private var baselineDone = false
    @State private var errorMessage: String?
    @State private var client: APIClient?
    @State private var environment: EnvironmentResponse?
    @State private var proxyInput = ""
    @State private var proxyProtocolHint = "auto"
    @State private var proxyPreview: ProxyImportPreviewResponse?
    @State private var proxySaveStatus: String?
    @State private var savedProxyProfile: ProxyProfile?
    @State private var proxyDeployPlan: ProxyApplyPlan?
    @State private var showProxyDeployConfirmation = false
    @State private var isProxyWorking = false

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "network.badge.shield.half.filled")
                .font(.system(size: 46))
                .foregroundStyle(.blue)

            VStack(spacing: 10) {
                Text("添加你的代理")
                    .font(.title2)
                    .fontWeight(.semibold)

                if let env = detectedEnvironment {
                    VStack(spacing: 6) {
                        Text(env.detected ? "客户端：\(env.client)" : env.client)
                            .font(.headline)
                        if let profile = env.profile {
                            Text(env.detected ? "当前节点：\(profile)" : profile)
                                .font(.body)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        if let port = env.port {
                            Text("发现你电脑里有代理软件，端口：\(port)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
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
                Text("去你的代理服务后台，复制一整行连接信息。通常需要地址、端口、用户名和密码；密码保存到本机密码库。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("复制下来大概是：地址:端口:用户名:密码 这种样子。不要只复制出口 IP。没有这类参数也可以先跳过。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Picker("参数类型", selection: $proxyProtocolHint) {
                    Text("自动判断（大多数选这个）").tag("auto")
                    Text("HTTP 代理").tag("http")
                    Text("SOCKS5 代理").tag("socks5h")
                }
                .pickerStyle(.segmented)
                TextEditor(text: $proxyInput)
                    .font(.system(.body, design: .monospaced))
                    .frame(minHeight: 72, maxHeight: 96)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.25))
                    )
                HStack {
                    Button("检查这行能不能用") {
                        Task { await previewProxyInput() }
                    }
                    .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isProxyWorking)

                    Button("保存并测试（暂不改网络）") {
                        Task { await saveProxyInput() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isProxyWorking)
                }

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
                            Label("开始使用这台 Mac 上网", systemImage: "play.circle.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!backend.isReady || isProxyWorking)

                        Button("进入主界面") {
                            onContinue()
                        }
                    }
                    .font(.caption)
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

            VStack(spacing: 12) {
                Button {
                    Task { await runBaseline() }
                } label: {
                    if isScanning {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text(baselineDone ? "完成" : "运行基线检测")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!backend.isReady || isScanning)

                Button("跳过") {
                    onSkip()
                }
                .buttonStyle(.borderless)
            }
        }
        .padding(32)
        .frame(minWidth: 460, minHeight: 560)
        .task {
            bindClient()
            await loadEnvironment()
        }
        .onChange(of: backend.state) { _ in
            bindClient()
            Task { await loadEnvironment() }
        }
        .confirmationDialog("开始使用这台 Mac 上网？", isPresented: $showProxyDeployConfirmation, titleVisibility: .visible) {
            Button("确认开始使用") {
                if let profile = savedProxyProfile {
                    Task { await applySavedProxyProfile(profile) }
                }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text(proxyDeploymentConfirmationText())
        }
    }

    private func previewProxyInput() async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = nil
        savedProxyProfile = nil
        do {
            proxyPreview = try await client.importProxyPreview(input: proxyInput, limit: 20, protocolHint: proxyProtocolHint)
        } catch {
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        isProxyWorking = false
    }

    private func saveProxyInput() async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = "正在保存到本机密码库并启动健康监控，暂不改系统网络…"
        savedProxyProfile = nil
        do {
            let response = try await client.saveProxyProfile(input: proxyInput, startMonitor: true, targetProfile: "ai_dev", protocolHint: proxyProtocolHint)
            if response.ok {
                savedProxyProfile = response.profile
                proxySaveStatus = response.monitor?.running == true
                    ? "已保存并启动健康监控。点下面“开始使用这台 Mac 上网”才会生效。"
                    : "已保存到本机，密码已写入本机密码库。点下面“开始使用这台 Mac 上网”才会生效。"
            } else {
                proxySaveStatus = "失败：\(response.error ?? "无法保存代理")"
            }
        } catch {
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        isProxyWorking = false
    }

    private func prepareProxyDeployment(_ profile: ProxyProfile) async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = "正在生成部署预览，不会修改网络设置…"
        do {
            proxyDeployPlan = try await client.applyProxyDryRun(profileID: profile.id, mode: "system")
            proxySaveStatus = nil
            showProxyDeployConfirmation = true
        } catch {
            proxyDeployPlan = nil
            proxySaveStatus = "失败：无法生成部署预览。\(error.localizedDescription)"
        }
        isProxyWorking = false
    }

    private func applySavedProxyProfile(_ profile: ProxyProfile) async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = "正在让这台 Mac 使用代理上网。会先备份原来的网络设置…"
        do {
            let response = try await client.applyProxyProfile(profileID: profile.id, mode: "system", confirmed: true, targetProfile: "ai_dev")
            if response.ok && response.status == "applied" {
                if response.applied?.scope == "loopback_bridge" {
                    let port = response.bridge?.listenPort.map(String.init) ?? "?"
                    proxySaveStatus = "已部署，本机转发端口 \(port)。请保持 Netfix 打开；不用时到设置里点“恢复原来的网络设置”。"
                } else {
                    let service = response.networkService ?? "当前网络服务"
                    proxySaveStatus = "已部署到 \(service)。不用时到设置里点“恢复原来的网络设置”。"
                }
            } else if response.status == "pending_confirmation" {
                proxySaveStatus = "还需要确认。请再点一次“开始使用这台 Mac 上网”。"
            } else {
                proxySaveStatus = "失败：\(response.friendlyFailureMessage)"
            }
        } catch {
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        isProxyWorking = false
    }

    private func proxyDeploymentConfirmationText() -> String {
        var lines = [
            "Netfix 会先备份当前网络设置。",
            "部署后，浏览器和大多数 App 会使用这组代理。",
        ]
        if proxyDeployPlan?.steps?.contains(where: { ($0.safePreview ?? "").contains("127.0.0.1") || ($0.label ?? "").contains("桥接") }) == true {
            lines.append("这组代理需要 Netfix 保持打开，用来安全代管账号密码。")
        }
        lines.append("不用时可以到设置里点“恢复原来的网络设置”。")
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
            errorMessage = "基线检测失败：\(error.localizedDescription)"
        }
        isScanning = false
    }

    private struct DetectedEnv {
        let client: String
        let profile: String?
        let port: Int?
        let detected: Bool
    }

    private var detectedEnvironment: DetectedEnv? {
        guard backend.isReady else { return nil }
        if let env = environment, env.ok {
            if let client = env.guiClient, !client.isEmpty {
                let profileName = env.activeProfile?.remarks ?? env.activeProfile?.id
                return DetectedEnv(
                    client: client,
                    profile: profileName,
                    port: env.mixedPort,
                    detected: true
                )
            }
            return DetectedEnv(
                client: "未识别到常见代理客户端",
                profile: "可以先运行基线检测，稍后再到设置里粘贴代理连接参数。",
                port: env.mixedPort,
                detected: false
            )
        }
        return DetectedEnv(
            client: "正在识别…",
            profile: nil,
            port: nil,
            detected: false
        )
    }
}
