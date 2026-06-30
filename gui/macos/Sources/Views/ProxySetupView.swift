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
    @State private var isProxyWorking = false

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "network.badge.shield.half.filled")
                .font(.system(size: 46))
                .foregroundStyle(.blue)

            VStack(spacing: 10) {
                Text("添加代理参数")
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
                            Text("检测到本机代理端口：\(port)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                } else if backend.isReady {
                    Text("未识别到常见代理客户端，你可以先跳过，稍后在设置里配置。")
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                } else {
                    Text("正在等待 Netfix 准备好…")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                Text("有供应商给你的代理参数？直接粘贴")
                    .font(.headline)
                Text("去代理服务商后台复制整行 HTTP/SOCKS 连接参数，不是只复制出口 IP。需要地址、端口、用户名和密码；密码保存到本机密码库。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("示例：proxy.example.com:8001:username:password，或 host,port,username,password。没有这类参数也可以跳过，先做基础诊断。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Picker("参数类型", selection: $proxyProtocolHint) {
                    Text("自动（常见 HTTP）").tag("auto")
                    Text("HTTP").tag("http")
                    Text("SOCKS5").tag("socks5h")
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
                    Button("预检") {
                        Task { await previewProxyInput() }
                    }
                    .disabled(!backend.isReady || proxyInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isProxyWorking)

                    Button("保存到这台 Mac") {
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
                if proxySaveStatus?.contains("还没影响浏览器") == true {
                    HStack {
                        Button("去部署到这台 Mac") {
                            NSApp.sendAction(#selector(AppDelegate.showProxySettings), to: nil, from: nil)
                        }
                        .buttonStyle(.borderedProminent)

                        Button("继续诊断") {
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
    }

    private func previewProxyInput() async {
        guard let client = client else { return }
        isProxyWorking = true
        proxySaveStatus = nil
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
        proxySaveStatus = "正在保存到本机密码库并启动健康监控…"
        do {
            let response = try await client.saveProxyProfile(input: proxyInput, startMonitor: true, targetProfile: "ai_dev", protocolHint: proxyProtocolHint)
            if response.ok {
                proxySaveStatus = response.monitor?.running == true
                    ? "已保存并启动健康监控，但还没影响浏览器。要开始使用，请点“去部署到这台 Mac”。"
                    : "已保存，但还没影响浏览器。密码已写入本机密码库；可以去部署到这台 Mac。"
            } else {
                proxySaveStatus = "失败：\(response.error ?? "无法保存代理")"
            }
        } catch {
            proxySaveStatus = "失败：\(error.localizedDescription)"
        }
        isProxyWorking = false
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
