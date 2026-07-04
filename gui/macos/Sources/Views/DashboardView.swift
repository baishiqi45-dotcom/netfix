import SwiftUI
import Combine
import AppKit
import UniformTypeIdentifiers

/// 主仪表盘：状态区、四张状态卡片、诊断 / 修复按钮、进度与结果摘要。
struct DashboardView: View {
    @ObservedObject var backend: Backend
    @ObservedObject var healthMonitor: HealthMonitor
    @AppStorage("netfix.autoFixTier1") private var autoFixTier1 = false
    @StateObject private var viewModel = DashboardViewModel()
    @State private var pendingAction: Action?
    @State private var showConfirmation = false
    @State private var showRollbackConfirmation = false
    @State private var showLogsSheet = false
    @State private var showAIQuestionSheet = false
    @State private var aiQuestionContext: AIQuestionContext = .diagnosis

    var body: some View {
        VStack(spacing: 0) {
            statusHeader
                .padding()

            Divider()

            ScrollView {
                VStack(spacing: 16) {
                    statusCards

                    firstAidSection

                    proxyDeploySection

                    if viewModel.isWorking {
                        progressSection
                    }

                    if let error = viewModel.errorMessage, !error.isEmpty {
                        errorBanner(error)
                    }

                    if let report = viewModel.report {
                        resultSection(report: report)
                    }

                    if !healthMonitor.events.isEmpty {
                        eventsSection
                    }
                }
                .padding()
            }

            Divider()

            actionToolbar
                .padding()
        }
        .frame(minWidth: 420, idealWidth: 460, minHeight: 520)
        .task {
            await viewModel.bind(backend: backend)
        }
        .confirmationDialog("让 Netfix 处理这个问题？", isPresented: $showConfirmation, titleVisibility: .visible) {
            Button("让 Netfix 处理", role: .none) {
                if let action = pendingAction {
                    Task { await viewModel.executeAction(action) }
                }
                pendingAction = nil
            }
            Button("取消", role: .cancel) {
                pendingAction = nil
            }
        } message: {
            if let action = pendingAction {
                Text("将处理「\(action.label)」。如果这一步会改网络设置，macOS 会弹出管理员授权；处理完会自动复查。")
            }
        }
        .alert("恢复原来的网络设置？", isPresented: $showRollbackConfirmation) {
            Button("恢复", role: .destructive) {
                Task { await viewModel.rollback() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会恢复上一次修改网络设置前的配置。")
        }
        .sheet(isPresented: $showLogsSheet) {
            LogsSheetView(
                logs: viewModel.logs,
                error: viewModel.logsError,
                isLoading: viewModel.logsLoading,
                onRefresh: {
                    Task { await viewModel.loadLogs() }
                },
                onOpenFolder: {
                    openNetfixLogsFolder()
                }
            )
        }
        .sheet(isPresented: $showAIQuestionSheet) {
            AIQuestionSheet(
                isWorking: viewModel.isWorking,
                context: aiQuestionContext,
                onOpenAISettings: {
                    NSApp.sendAction(#selector(AppDelegate.showAISettings), to: nil, from: nil)
                }
            ) { question, images in
                showAIQuestionSheet = false
                Task {
                    await viewModel.explainWithAI(
                        question: question,
                        imageDataURLs: images,
                        uploadConfirmed: true
                    )
                }
            }
        }
    }

    // MARK: - 顶部状态区

    private var statusHeader: some View {
        HStack(spacing: 10) {
            statusDot
            VStack(alignment: .leading, spacing: 2) {
                Text(viewModel.headline)
                    .font(.headline)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Label(viewModel.proxyUsageLabel, systemImage: viewModel.proxyUsageIcon)
                    .font(.caption2)
                    .foregroundStyle(viewModel.proxyUsageColor)
            }
            Spacer()
        }
    }

    private var subtitle: String {
        if !backend.isReady {
            return backend.statusMessage
        }
        if let date = healthMonitor.lastCheck {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .short
            return "上次检测：\(formatter.localizedString(for: date, relativeTo: Date()))"
        }
        return backend.statusMessage
    }

    @ViewBuilder
    private var statusDot: some View {
        switch healthMonitor.healthStatus {
        case .ok:
            Circle()
                .fill(Color.green)
                .frame(width: 12, height: 12)
        case .warn:
            Circle()
                .fill(Color.orange)
                .frame(width: 12, height: 12)
        case .fail:
            Circle()
                .fill(Color.red)
                .frame(width: 12, height: 12)
        case .unknown:
            ProgressView()
                .controlSize(.small)
                .frame(width: 14, height: 14)
        }
    }

    // MARK: - 状态卡片

    private let statusGroups: [(ids: [String], title: String, icon: String)] = [
        (["network", "dns", "path"], "网络连接", "wifi"),
        (["proxy", "egress"], "代理状态", "network"),
        (["service"], "目标网站", "server.rack"),
    ]

    private var statusCards: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            ForEach(statusGroups, id: \.title) { group in
                let items = group.ids.flatMap { viewModel.items(for: $0) }
                layerCard(title: group.title, icon: group.icon, items: items)
            }
        }
    }

    private func layerCard(title: String, icon: String, items: [DiagnosticItem]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(.blue)
                Text(title)
                    .font(.headline)
                Spacer()
            }

            if let status = items.layerStatus {
                StatusIconView(status: status, label: statusLabel(status))
            } else {
                StatusIconView(status: .unknown, label: "未检测")
            }

            let visibleItems = Array(items.sorted { lhs, rhs in
                diagnosticPriority(lhs) > diagnosticPriority(rhs)
            }.prefix(5))

            if !visibleItems.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(visibleItems) { item in
                        Text("• \(item.displayTitle)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    private func statusLabel(_ status: DiagnosticStatus) -> String {
        switch status {
        case .ok: return "正常"
        case .warn: return "注意"
        case .fail: return "异常"
        case .unknown: return "未检测"
        }
    }

    private func diagnosticPriority(_ item: DiagnosticItem) -> Int {
        switch DiagnosticStatus(item.status) {
        case .fail: return 4
        case .warn: return 3
        case .unknown: return 2
        case .ok: return 1
        }
    }

    // MARK: - 服务急救包

    private let firstAidItems: [(group: String, title: String, icon: String)] = [
        ("ai", "AI / 大模型", "brain"),
        ("dev", "开发工具", "hammer"),
        ("common", "常用境外网站", "globe"),
    ]

    private var firstAidSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("检查常用网站能不能打开")
                .font(.headline)
            Text("检查 ChatGPT、GitHub 和常用网站是直连失败、代理失败，还是网站本身异常。")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack(spacing: 12) {
                ForEach(firstAidItems, id: \.group) { item in
                    Button {
                        Task { await viewModel.checkServices(group: item.group) }
                    } label: {
                        VStack(spacing: 6) {
                            Image(systemName: item.icon)
                                .font(.title2)
                            Text(item.title)
                                .font(.caption)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity, minHeight: 64)
                    }
                    .buttonStyle(.bordered)
                    .disabled(!backend.isReady || viewModel.isWorking)
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    // MARK: - 进度区

    private var progressSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            ProgressView(value: viewModel.progress, total: 1.0)
                .progressViewStyle(.linear)
            HStack(spacing: 10) {
                Text(viewModel.stepLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if viewModel.activeJobID != nil {
                    Button {
                        Task { await viewModel.cancelActiveJob() }
                    } label: {
                        Label("取消", systemImage: "xmark.circle")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    private func errorBanner(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .padding(.top, 2)
                Text(friendlyErrorMessage(message))
                    .font(.body)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
                Button {
                    viewModel.errorMessage = nil
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 12) {
                if viewModel.lastOperation != nil {
                    Button("重试") {
                        Task { await viewModel.retryLastOperation() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.orange)
                    .controlSize(.small)
                }

                Button("复制错误") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(message, forType: .string)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Button("查看日志") {
                    openNetfixLogsFolder()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding()
        .background(Color.orange.opacity(0.15))
        .cornerRadius(10)
    }

    private func actionabilityBadge(_ explanation: Explanation) -> some View {
        let severity = DiagnosticStatus(explanation.severity ?? "ok")
        if let action = explanation.primaryAction {
            let text = action.needsConfirm ? "点确认后 Netfix 自动处理" : "一键处理"
            let color: Color = action.needsConfirm ? .orange : .blue
            return AnyView(
                Label(text, systemImage: action.needsConfirm ? "hand.raised" : "bolt.fill")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(color.opacity(0.15))
                    .foregroundStyle(color)
                    .cornerRadius(6)
            )
        }
        if severity == .ok {
            return AnyView(
                Label("网络看起来正常", systemImage: "checkmark.circle.fill")
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.green.opacity(0.15))
                    .foregroundStyle(.green)
                    .cornerRadius(6)
            )
        }
        return AnyView(
            Label("需按下方步骤手动处理", systemImage: "person.fill")
                .font(.caption)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.orange.opacity(0.15))
                .foregroundStyle(.orange)
                .cornerRadius(6)
        )
    }

    private func friendlyErrorMessage(_ message: String) -> String {
        let lower = message.lowercased()
        if lower.contains("command timed out") || lower.contains("timed out") {
            return "网络太慢或代理没响应。可以重试一次，或者点“粘贴代理参数”换一组代理。"
        }
        if lower.contains("407") || lower.contains("proxy authentication") || lower.contains("auth_failed") || lower.contains("authentication") {
            return "代理账号或密码没有通过。请从服务商后台重新复制完整的地址、端口、用户名和密码，再粘贴保存。"
        }
        if lower.contains("unsupported") || lower.contains("ss://") || lower.contains("vmess://") || lower.contains("subscription") || lower.contains("订阅") {
            return "这类链接暂时不能直接部署。请到服务商后台复制 HTTP 或 SOCKS5 的地址、端口、用户名和密码。"
        }
        if lower.contains("dns") || lower.contains("could not resolve") || lower.contains("name_not_resolved") {
            return "DNS 解析失败。可能是当前网络打不开这个域名，也可能是代理服务商给的地址写错。"
        }
        if lower.contains("connection refused") || lower.contains("could not connect") {
            return "目标服务或本机转发没有响应。可以先重试；如果是刚部署代理，请确认 Netfix 仍在运行。"
        }
        if lower.contains("ipv6_leak") && lower.contains("no public ipv6 observed") {
            return "没有检测到公网 IPv6 泄漏，只是系统仍保留 IPv6 默认路由。一般可以继续使用；如果某些 App 启动卡住，再按建议处理 IPv6。"
        }
        if lower.contains("decode") || lower.contains("解析失败") {
            return "App 与后端返回的数据格式不匹配，可能是版本不一致。请尝试重启应用。"
        }
        return message
    }

    private func openNetfixLogsFolder() {
        let url = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent(".netfix", isDirectory: true)
        NSWorkspace.shared.open(url)
    }

    private func openLocalConsole() {
        guard let url = backend.apiURL else { return }
        NSWorkspace.shared.open(url)
    }

    private func openProxySettings() {
        NSApp.sendAction(#selector(AppDelegate.showProxySettings), to: nil, from: nil)
    }

    private var proxyDeploySection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("粘贴你已有的代理参数", systemImage: "point.3.connected.trianglepath.dotted")
                    .font(.headline)
                Spacer()
                Text("不需要 API Key 也能用")
                    .font(.caption2)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.green.opacity(0.14))
                    .foregroundStyle(.green)
                    .cornerRadius(6)
            }

            Text("从你的代理服务后台复制完整一行：地址、端口、用户名、密码。Netfix 不卖代理，也不能只靠出口 IP 部署。")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Button {
                    openProxySettings()
                } label: {
                    Label("粘贴代理参数", systemImage: "square.and.arrow.down")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!backend.isReady)

                Button {
                    aiQuestionContext = .proxy
                    showAIQuestionSheet = true
                } label: {
                    Label("问 AI", systemImage: "sparkles")
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isWorking)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.blue.opacity(0.16), lineWidth: 1)
        )
    }

    // MARK: - 结果区

    private func resultSection(report: NetfixReport) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if let explanation = report.explanation {
                explanationCard(explanation)
            } else {
                legacyResultCard(report)
            }

            if let ai = viewModel.llmExplanation {
                aiExplanationCard(ai)
            }

            if let error = viewModel.llmError {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.orange)
            }

            if viewModel.llmExplanation == nil {
                Button {
                    aiQuestionContext = .diagnosis
                    showAIQuestionSheet = true
                } label: {
                    Label("看不懂结果？让 AI 解释一下", systemImage: "message")
                }
                .buttonStyle(.borderless)
                .disabled(viewModel.isWorking)
            }

            DisclosureGroup("查看技术详情") {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(report.diagnostics) { item in
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(item.displayTitle)
                                    .font(.body)
                                if item.displayTitle != item.name {
                                    Text(item.name)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            let status = DiagnosticStatus(item.status)
                            StatusIconView(status: status, label: statusLabel(status))
                        }
                    }
                }
                .padding(.top, 6)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(10)
    }

    private func explanationCard(_ explanation: Explanation) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                StatusIconView(status: DiagnosticStatus(explanation.severity ?? "ok"), label: "")
                Text(explanation.headline ?? "诊断完成")
                    .font(.headline)
                Spacer()
            }

            HStack(spacing: 6) {
                actionabilityBadge(explanation)
                Spacer()
            }

            if let text = explanation.explanation, !text.isEmpty {
                Text(text)
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            if let primary = explanation.primaryAction {
                Button(action: { requestAction(primary) }) {
                    HStack {
                        Image(systemName: primary.needsConfirm ? "exclamationmark.triangle" : "bolt.fill")
                        Text(primary.label)
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(primary.needsConfirm ? .orange : .blue)
                .disabled(viewModel.isWorking)
            }

            let otherActions = explanation.actions.filter { $0.id != explanation.primaryAction?.id }
            if !otherActions.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("还能做")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    ForEach(otherActions) { action in
                        Button(action: { requestAction(action) }) {
                            HStack {
                                Text("• \(action.label)")
                                Spacer()
                                if action.needsConfirm {
                                    Text("会改设置")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isWorking)
                    }
                }
            }

            if !explanation.manualSteps.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("你需要做的事")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    ForEach(explanation.manualSteps) { step in
                        VStack(alignment: .leading, spacing: 2) {
                            if let desc = step.description, !desc.isEmpty {
                                Text("• \(desc)")
                                    .font(.body)
                            }
                            if let substeps = step.steps {
                                ForEach(substeps, id: \.self) { s in
                                    Text("  ◦ \(s)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private func aiExplanationCard(_ result: LLMExplainResult) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: result.source == "llm" ? "sparkles" : "checklist.checked")
                    .foregroundStyle(result.source == "llm" ? .purple : .blue)
                Text(result.source == "llm" ? "AI 给出的解释" : "Netfix 本地解释")
                    .font(.headline)
                Spacer()
            }
            if let headline = result.headline, !headline.isEmpty {
                Text(headline)
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }
            if let explanation = result.explanation, !explanation.isEmpty {
                Text(explanation)
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
            if result.providerUsed != nil || result.fallbackReason != nil || result.redactedReportHash != nil || result.fallbackChain?.isEmpty == false {
                DisclosureGroup("技术详情") {
                    VStack(alignment: .leading, spacing: 4) {
                        if let provider = providerDisplayName(result.providerUsed) {
                            Text("使用模型：\(provider)")
                        }
                        if let reason = friendlyLLMReason(result.fallbackReasonLabel ?? result.fallbackReason) {
                            Text("说明：\(reason)")
                        }
                        if let hash = result.redactedReportHash {
                            Text("脱敏报告指纹：\(hash)")
                                .lineLimit(1)
                        }
                        if let chain = result.fallbackChain, !chain.isEmpty {
                            Text("模型尝试记录：" + chain.compactMap { step in
                                guard let provider = providerDisplayName(step.provider), let status = step.status else { return nil }
                                return "\(provider) \(friendlyProviderStatus(status))"
                            }.joined(separator: " -> "))
                        }
                    }
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                }
                .font(.caption)
            }
        }
        .padding()
        .background(Color.purple.opacity(0.08))
        .cornerRadius(10)
    }

    private func providerDisplayName(_ provider: String?) -> String? {
        guard let provider, !provider.isEmpty else { return nil }
        switch provider {
        case "deepseek": return "DeepSeek"
        case "moonshot_kimi": return "Kimi"
        case "minimax": return "MiniMax"
        case "qwen": return "Qwen"
        case "custom_openai_compatible": return "自定义模型"
        case "openai": return "OpenAI"
        default: return provider
        }
    }

    private func friendlyProviderStatus(_ status: String) -> String {
        switch status {
        case "ok", "ready": return "可用"
        case "failed": return "失败"
        case "skipped": return "已跳过"
        case "missing_key": return "需要 API Key"
        default: return status
        }
    }

    private func friendlyLLMReason(_ reason: String?) -> String? {
        guard let reason, !reason.isEmpty else { return nil }
        let lower = reason.lowercased()
        if lower.contains("missing_api_key") || lower.contains("missing api key") {
            return "还没有配置 API Key。"
        }
        if lower.contains("llm_disabled") || lower.contains("disabled") {
            return "AI 还没有启用。"
        }
        if lower.contains("upload_consent") {
            return "需要你确认发送脱敏诊断报告。"
        }
        if lower.contains("rate_limited") || lower.contains("rate limit") {
            return "供应商暂时限流，稍后再试。"
        }
        if lower.contains("quota") || lower.contains("billing") || lower.contains("balance") {
            return "供应商额度或账单不可用。"
        }
        return reason
    }

    private func legacyResultCard(_ report: NetfixReport) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(report.overallStatus == .ok ? "网络看起来正常" : report.firstRootCause ?? "检测到问题")
                .font(.headline)
            if !report.fixes.isEmpty {
                Text("可执行修复：\(report.fixes.map { $0.description }.joined(separator: "、"))")
                    .font(.body)
            }
        }
    }

    private func requestAction(_ action: Action) {
        if action.needsConfirm {
            pendingAction = action
            showConfirmation = true
        } else {
            Task { await viewModel.executeAction(action) }
        }
    }

    // MARK: - 事件时间线

    private var eventsSection: some View {
        DisclosureGroup("最近状态变化") {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(healthMonitor.events.suffix(5).reversed()) { event in
                    HStack(spacing: 8) {
                        StatusIconView(status: event.status, label: "")
                            .frame(width: 16)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(event.headline)
                                .font(.caption)
                            Text(event.timestamp, style: .time)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                }
            }
            .padding(.top, 6)
        }
    }

    // MARK: - 底部操作栏

    private var actionToolbar: some View {
        VStack(alignment: .leading, spacing: 8) {
            primaryActionToolbar
            secondaryActionToolbar
        }
    }

    private var primaryActionToolbar: some View {
        HStack(spacing: 12) {
            Button("一键诊断") {
                Task {
                    await viewModel.diagnose()
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!backend.isReady || viewModel.isWorking)

            Button("处理建议") {
                if let action = viewModel.recommendedAction {
                    requestAction(action)
                }
            }
            .buttonStyle(.bordered)
            .disabled(!backend.isReady || viewModel.isWorking || viewModel.recommendedAction == nil)
            .help(viewModel.recommendedAction == nil ? "先诊断；Netfix 找到明确建议后才能处理。" : "按上方报告里的建议处理。")

            if viewModel.rollbackAvailable {
                Button("恢复原来的网络设置") {
                    showRollbackConfirmation = true
                }
                .buttonStyle(.borderless)
                .disabled(!backend.isReady || viewModel.isWorking)
            }
        }
    }

    private var secondaryActionToolbar: some View {
        HStack(spacing: 10) {
            Toggle("自动处理低风险问题", isOn: $autoFixTier1)
                .toggleStyle(.switch)
                .fixedSize()
                .help("只自动处理不会改系统网络设置的低风险问题")

            Spacer(minLength: 8)

            Button("代理") {
                openProxySettings()
            }
            .buttonStyle(.borderless)
            .disabled(!backend.isReady)
            .help("粘贴代理参数并确认是否让这台 Mac 使用")

            Button("日志") {
                showLogsSheet = true
                Task {
                    await viewModel.loadLogs()
                }
            }
            .buttonStyle(.borderless)
            .disabled(!backend.isReady)

            Button("设置") {
                NSApp.sendAction(#selector(AppDelegate.showSettings), to: nil, from: nil)
            }
            .buttonStyle(.borderless)
            .disabled(!backend.isReady)
        }
        .lineLimit(1)
    }
}

private struct AIQuestionImage: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let dataURL: String
    let preview: NSImage?
}

private enum AIQuestionContext {
    case diagnosis
    case proxy

    var prompts: [String] {
        switch self {
        case .diagnosis:
            return ["下一步怎么处理？", "怎么看出来的？", "是不是代理没生效？"]
        case .proxy:
            return ["这个代理能用吗？", "粘贴格式对吗？", "为什么 SOCKS5 失败？"]
        }
    }

    var placeholder: String {
        switch self {
        case .diagnosis:
            return "留空也可以，Netfix 会直接解释当前诊断报告；也可以补一句你现在遇到什么。"
        case .proxy:
            return "可以问代理怎么粘贴、HTTP 和 SOCKS5 怎么选、部署失败下一步怎么办。"
        }
    }
}

private struct AIQuestionSheet: View {
    let isWorking: Bool
    let context: AIQuestionContext
    let onOpenAISettings: () -> Void
    let onSend: (String, [String]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var question = ""
    @State private var images: [AIQuestionImage] = []
    @State private var uploadConfirmed = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("问 AI", systemImage: "sparkles")
                    .font(.headline)
                Spacer()
                Button {
                    onOpenAISettings()
                } label: {
                    Label("AI 设置", systemImage: "key")
                }
                .buttonStyle(.borderless)
                .disabled(isWorking)
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
            }

            ZStack(alignment: .topLeading) {
                TextEditor(text: $question)
                    .frame(minHeight: 88)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.18), lineWidth: 1)
                    )
                if question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(context.placeholder)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 8)
                        .allowsHitTesting(false)
                }
            }
            .help("可以描述你遇到的问题；留空时 Netfix 会只解释当前诊断报告。")

            HStack {
                Button {
                    pickImages()
                } label: {
                    Label("添加图片", systemImage: "photo")
                }
                .disabled(isWorking || images.count >= 3)

                if !images.isEmpty {
                    Button("清空") {
                        images.removeAll()
                    }
                    .disabled(isWorking)
                }

                Spacer()

                Text("\(images.count)/3")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if !images.isEmpty {
                ScrollView(.horizontal) {
                    HStack(spacing: 10) {
                        ForEach(images) { item in
                            VStack(alignment: .leading, spacing: 6) {
                                if let preview = item.preview {
                                    Image(nsImage: preview)
                                        .resizable()
                                        .scaledToFill()
                                        .frame(width: 96, height: 64)
                                        .clipped()
                                        .cornerRadius(6)
                                } else {
                                    ZStack {
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(Color.secondary.opacity(0.12))
                                        Image(systemName: "photo")
                                            .foregroundStyle(.secondary)
                                    }
                                    .frame(width: 96, height: 64)
                                }
                                Text(item.name)
                                    .font(.caption2)
                                    .lineLimit(1)
                                    .frame(width: 96, alignment: .leading)
                            }
                        }
                    }
                    .padding(.vertical, 2)
                }
            }

            Toggle(isOn: $uploadConfirmed) {
                Text("我确认发送脱敏诊断报告\(images.isEmpty ? "" : "和上方图片")给已配置的云端模型")
            }

            Text("AI 只负责看报告和回答问题，不影响一键诊断、代理部署、IPv6 处理和网络设置恢复。没有 API Key 时，主流程照常可用；需要 AI 时再到设置里粘贴 Key。截图问诊仅支持 PNG、JPEG、WebP 或 GIF。")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                ForEach(context.prompts, id: \.self) { prompt in
                    Button(prompt) {
                        question = prompt
                    }
                    .buttonStyle(.borderless)
                    .disabled(isWorking)
                }
            }
            .font(.caption)

            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            HStack {
                Spacer()
                Button("取消") {
                    dismiss()
                }
                Button("发送并解释") {
                    onSend(question.trimmingCharacters(in: .whitespacesAndNewlines), images.map(\.dataURL))
                }
                .buttonStyle(.borderedProminent)
                .disabled(isWorking || !uploadConfirmed)
            }
        }
        .padding()
        .frame(width: 440)
    }

    private func pickImages() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        let webPTypes = UTType(filenameExtension: "webp").map { [$0] } ?? []
        panel.allowedContentTypes = [.png, .jpeg, .gif] + webPTypes
        panel.begin { response in
            guard response == .OK else { return }
            var next = images
            for url in panel.urls where next.count < 3 {
                do {
                    let data = try Data(contentsOf: url)
                    if data.count > 4_500_000 {
                        errorMessage = "\(url.lastPathComponent) 太大，请选择 4.5MB 以内的图片。"
                        continue
                    }
                    let mime = mimeType(for: url)
                    guard allowedImageMimeTypes.contains(mime) else {
                        errorMessage = "\(url.lastPathComponent) 只支持 PNG、JPEG、WebP 或 GIF。"
                        continue
                    }
                    let dataURL = "data:\(mime);base64,\(data.base64EncodedString())"
                    next.append(AIQuestionImage(name: url.lastPathComponent, dataURL: dataURL, preview: NSImage(contentsOf: url)))
                    errorMessage = nil
                } catch {
                    errorMessage = "无法读取 \(url.lastPathComponent)：\(error.localizedDescription)"
                }
            }
            images = next
        }
    }

    private func mimeType(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "jpg", "jpeg": return "image/jpeg"
        case "gif": return "image/gif"
        case "webp": return "image/webp"
        case "png": return "image/png"
        default: return "application/octet-stream"
        }
    }

    private var allowedImageMimeTypes: Set<String> {
        ["image/png", "image/jpeg", "image/webp", "image/gif"]
    }
}

// MARK: - DashboardViewModel

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var headline = "正在准备 Netfix…"
    @Published var isWorking = false
    @Published var progress: Double = 0
    @Published var stepLabel = ""
    @Published var report: NetfixReport?
    @Published var errorMessage: String?
    @Published var logs: LogsResponse?
    @Published var logsError: String?
    @Published var logsLoading = false
    @Published var llmExplanation: LLMExplainResult?
    @Published var llmError: String?
    @Published var activeJobID: String?
    @Published private var proxyBridgeState: ProxyBridgeResponse?

    var recommendedAction: Action? {
        report?.explanation?.primaryAction ?? report?.explanation?.actions.first
    }

    var proxyUsageLabel: String {
        guard let lifecycle = proxyBridgeState?.lifecycle else {
            return "代理状态：未使用 Netfix 代理"
        }
        if lifecycle.status == "running_system" || lifecycle.systemPointsToBridge == true {
            let name = lifecycle.profileName ?? lifecycle.profileId
            return name.map { "代理状态：正在使用 Netfix 代理（\($0)）" } ?? "代理状态：正在使用 Netfix 代理"
        }
        if lifecycle.needsAttention == true || lifecycle.recoveryAvailable == true {
            return "代理状态：上次部署需要处理"
        }
        return "代理状态：未使用 Netfix 代理"
    }

    var proxyUsageIcon: String {
        guard let lifecycle = proxyBridgeState?.lifecycle else { return "network" }
        if lifecycle.status == "running_system" || lifecycle.systemPointsToBridge == true {
            return "checkmark.shield"
        }
        if lifecycle.needsAttention == true || lifecycle.recoveryAvailable == true {
            return "exclamationmark.triangle"
        }
        return "network"
    }

    var proxyUsageColor: Color {
        guard let lifecycle = proxyBridgeState?.lifecycle else { return .secondary }
        if lifecycle.status == "running_system" || lifecycle.systemPointsToBridge == true {
            return .green
        }
        if lifecycle.needsAttention == true || lifecycle.recoveryAvailable == true {
            return .orange
        }
        return .secondary
    }

    var rollbackAvailable: Bool {
        guard let report else { return false }
        let actions = [report.explanation?.primaryAction].compactMap { $0 } + (report.explanation?.actions ?? [])
        if actions.contains(where: actionLooksLikeRollback) {
            return true
        }
        return report.fixes.contains { fix in
            let text = "\(fix.id) \(fix.description)".lowercased()
            return text.contains("rollback") || text.contains("restore") || text.contains("回滚") || text.contains("恢复")
        }
    }

    private var client: APIClient?
    private var progressTimer: Timer?
    private var progressIndex = 0
    private var cancellationRequested = false
    fileprivate(set) var lastOperation: LastOperation?

    enum LastOperation {
        case diagnose
        case fix
        case checkServices(String)
        case executeAction(Action)
        case rollback
    }

    private func actionLooksLikeRollback(_ action: Action) -> Bool {
        let text = "\(action.id) \(action.label)".lowercased()
        return text.contains("rollback") || text.contains("restore") || text.contains("回滚") || text.contains("恢复")
    }

    func bind(backend: Backend) async {
        for await _ in backend.$state.values {
            updateHeadline(backend: backend)
            if backend.isReady, let url = backend.apiURL, let token = backend.apiToken, client == nil {
                client = APIClient(baseURL: url, apiToken: token)
                Task { await refreshProxyUsage() }
            }
        }
    }

    private func updateHeadline(backend: Backend) {
        if case .failed(let reason) = backend.state {
            headline = reason
            return
        }
        if isWorking {
            return
        }
        if let report = report {
            headline = report.summaryHeadline
        } else {
            headline = backend.isReady ? "就绪，可以开始" : backend.statusMessage
        }
    }

    func diagnose() async {
        guard let client = client else { return }
        errorMessage = nil
        lastOperation = .diagnose
        await runReadOnlyReportJob(
            client: client,
            command: ["doctor"],
            timeout: 120,
            failureHeadline: "诊断失败",
            steps: [
                "正在检查本地网络…",
                "正在检查网站解析…",
                "正在检查代理状态…",
                "正在检查别人看到的网络位置…",
                "正在检查连接速度…",
                "正在检查目标网站…",
            ]
        )
        await refreshProxyUsage()
    }

    func fix() async {
        errorMessage = nil
        guard recommendedAction != nil else {
            headline = "没有可直接处理的建议"
            errorMessage = "先点“一键诊断”。只有 Netfix 找到明确建议后，才会出现可处理按钮。"
            return
        }
        headline = "请选择上方的处理建议"
        errorMessage = "这一步需要按报告里的具体建议处理；如果会改系统网络设置，Netfix 会先弹出确认。"
    }

    func executeAction(_ action: Action) async {
        guard let client = client else { return }
        errorMessage = nil
        lastOperation = .executeAction(action)
        startWork(steps: [
            "正在执行：\(action.label)…",
            "正在验证修复结果…",
        ])
        do {
            let result = try await client.executeFix(fixId: action.id, timeout: 60)
            self.report = result
            headline = result.explanation?.headline ?? result.summaryHeadline
        } catch {
            errorMessage = error.localizedDescription
            headline = "修复失败"
        }
        stopWork()
    }

    func rollback() async {
        guard let client = client else { return }
        errorMessage = nil
        lastOperation = .rollback
        startWork(steps: [
            "正在检查是否有代理部署需要恢复…",
            "正在重新检测…",
        ])
        do {
            let proxyRollback = try await client.rollbackProxyProfile(confirmed: true)
            if proxyRollback.ok {
                headline = "已恢复代理部署前网络"
                do {
                    let fresh = try await client.diagnose(timeout: 60)
                    self.report = fresh
                    headline = fresh.explanation?.headline ?? fresh.summaryHeadline
                } catch {
                    errorMessage = "已恢复代理部署前网络，但重新检测失败：\(error.localizedDescription)"
                }
                await refreshProxyUsage()
                stopWork()
                return
            }
            if proxyRollback.status == "no_journal" {
                let result = try await client.rollback(timeout: 30)
                self.report = result
                headline = "已恢复"
                await refreshProxyUsage()
                stopWork()
                return
            } else {
                headline = "恢复代理部署失败"
                errorMessage = proxyRollback.error ?? "代理回滚没有完成，请查看日志。"
                stopWork()
                return
            }
        } catch {
            errorMessage = error.localizedDescription
            headline = "恢复失败"
        }
        stopWork()
    }

    private func refreshProxyUsage() async {
        guard let client else { return }
        do {
            proxyBridgeState = try await client.proxyBridge()
        } catch {
            proxyBridgeState = nil
        }
    }

    func checkServices(group: String) async {
        guard let client = client else { return }
        errorMessage = nil
        lastOperation = .checkServices(group)
        await runReadOnlyReportJob(
            client: client,
            command: ["services", "--group", group],
            timeout: 60,
            failureHeadline: "服务检测失败",
            steps: [
                "正在检查目标服务…",
                "正在汇总结果…",
            ]
        )
    }

    func loadLogs() async {
        guard let client = client else {
            logsError = "Netfix 还没准备好"
            logsLoading = false
            return
        }
        logsLoading = true
        logsError = nil
        do {
            logs = try await client.logs()
            logsError = nil
        } catch {
            logsError = error.localizedDescription
        }
        logsLoading = false
    }

    func explainWithAI(question: String = "", imageDataURLs: [String] = [], uploadConfirmed: Bool = false) async {
        guard let client = client else { return }
        llmError = nil
        startWork(steps: [
            "正在生成脱敏报告…",
            "正在请求 AI 解释…",
            "正在校验可执行动作…",
        ])
        do {
            let response = try await client.explainWithLLM(
                question: question,
                mode: imageDataURLs.isEmpty ? "explain" : "image_question",
                uploadConfirmed: uploadConfirmed,
                images: imageDataURLs
            )
            llmExplanation = response.result
            headline = response.result.headline ?? headline
        } catch {
            llmError = friendlyAIError(error.localizedDescription)
        }
        stopWork()
    }

    private func friendlyAIError(_ message: String) -> String {
        let lower = message.lowercased()
        if lower.contains("missing api key") || lower.contains("没有可用 api key") || lower.contains("api key") && lower.contains("missing") {
            return "还没配置 AI：这只影响 AI 看报告，不影响诊断和代理部署。需要 AI 时，到设置里选择供应商并粘贴 API Key。"
        }
        if lower.contains("cloud ai explanation is disabled") || lower.contains("llm_disabled") {
            return "AI 还没启用：打开设置里的 AI，启用后粘贴 API Key 并保存测试。"
        }
        if lower.contains("upload_consent") || lower.contains("上传") {
            return "AI 没有发送报告：确认发送脱敏诊断报告后再试。"
        }
        return "AI 解释失败：\(message)"
    }

    func retryLastOperation() async {
        guard let operation = lastOperation else { return }
        switch operation {
        case .diagnose:
            await diagnose()
        case .fix:
            await fix()
        case .checkServices(let group):
            await checkServices(group: group)
        case .executeAction(let action):
            await executeAction(action)
        case .rollback:
            await rollback()
        }
    }

    func cancelActiveJob() async {
        guard let client = client, let jobID = activeJobID else { return }
        cancellationRequested = true
        stepLabel = "正在取消后台任务…"
        do {
            _ = try await client.cancelJob(jobID: jobID)
            headline = "已取消"
            errorMessage = nil
        } catch {
            errorMessage = "取消失败：\(error.localizedDescription)"
        }
        activeJobID = nil
        stopWork()
    }

    private func runReadOnlyReportJob(
        client: APIClient,
        command: [String],
        timeout: Int,
        failureHeadline: String,
        steps: [String]
    ) async {
        cancellationRequested = false
        startWork(steps: steps)
        do {
            let jobID = try await client.startRunJob(command: command, timeout: timeout)
            activeJobID = jobID
            stepLabel = "后台任务 #\(jobID) 运行中…"
            let report = try await awaitReportJob(jobID: jobID, client: client, timeout: timeout)
            self.report = report
            headline = report.summaryHeadline
        } catch {
            if isCancellation(error) {
                headline = "已取消"
                errorMessage = nil
            } else {
                errorMessage = error.localizedDescription
                headline = failureHeadline
            }
        }
        activeJobID = nil
        stopWork()
    }

    private func awaitReportJob(jobID: String, client: APIClient, timeout: Int) async throws -> NetfixReport {
        let deadline = Date().addingTimeInterval(TimeInterval(timeout + 10))
        while Date() < deadline {
            if cancellationRequested {
                throw APIError.runFailed("job cancelled")
            }
            let job = try await client.jobStatus(jobID: jobID)
            switch job.status {
            case "done":
                if let report = job.result?.result {
                    return report
                }
                throw APIError.runFailed(job.result?.error ?? job.error ?? "后台任务没有返回诊断报告")
            case "cancelled":
                throw APIError.runFailed(job.error ?? "job cancelled")
            default:
                progress = min(0.92, max(progress, progress + 0.03))
                try await Task.sleep(nanoseconds: 1_000_000_000)
            }
        }
        throw APIError.runFailed("后台任务超时")
    }

    private func isCancellation(_ error: Error) -> Bool {
        if case APIError.runFailed(let message) = error {
            return message.localizedCaseInsensitiveContains("cancel") || message.contains("取消")
        }
        return false
    }

    private func startWork(steps: [String]) {
        isWorking = true
        progress = 0
        progressIndex = 0
        stepLabel = steps.first ?? "处理中…"
        progressTimer?.invalidate()
        progressTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] timer in
            Task { @MainActor [weak self] in
                guard let self = self else {
                    timer.invalidate()
                    return
                }
                self.progressIndex += 1
                if self.progressIndex >= steps.count {
                    self.progress = max(self.progress, 0.9)
                    return
                }
                self.stepLabel = steps[self.progressIndex]
                self.progress = Double(self.progressIndex) / Double(steps.count)
            }
        }
    }

    private func stopWork() {
        isWorking = false
        activeJobID = nil
        cancellationRequested = false
        progressTimer?.invalidate()
        progressTimer = nil
        progress = 1.0
        stepLabel = ""
    }

    // MARK: - 卡片数据分组

    func items(for layer: String) -> [DiagnosticItem] {
        report?.diagnostics.filter { $0.layer?.lowercased() == layer } ?? []
    }
}

private struct LogsSheetView: View {
    let logs: LogsResponse?
    let error: String?
    let isLoading: Bool
    let onRefresh: () -> Void
    let onOpenFolder: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("报告与日志")
                    .font(.title3)
                    .fontWeight(.semibold)
                Spacer()
                if isLoading {
                    ProgressView()
                        .controlSize(.small)
                }
                Button("刷新") {
                    onRefresh()
                }
                .disabled(isLoading)
                Button("打开目录") {
                    onOpenFolder()
                }
            }

            if let error {
                VStack(alignment: .leading, spacing: 8) {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text("可以重试刷新，或打开日志目录查看本地文件。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let logs {
                VStack(alignment: .leading, spacing: 6) {
                    Text("日志目录：\(logs.journalDir ?? "-")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("最近报告：\(logs.latestReportExists == true ? logs.latestReportPath ?? "-" : "暂无")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let summary = logs.latestReportSummary?.headline {
                        Text("最近结论：\(summary)")
                            .font(.body)
                    }
                }

                Divider()

                if logs.events.isEmpty {
                    Text("暂无事件。运行一次诊断后，这里会显示最近状态变化。")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(logs.events.suffix(50).reversed()) { event in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(event.headline ?? event.type)
                                .font(.body)
                            HStack {
                                Text(event.status)
                                Text(event.timestamp)
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 3)
                    }
                }
            } else if error == nil {
                ProgressView("正在加载日志…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding()
        .frame(width: 560, height: 420)
    }
}

private extension Array where Element == DiagnosticItem {
    var layerStatus: DiagnosticStatus? {
        if isEmpty { return nil }
        if contains(where: { $0.status == "fail" }) { return .fail }
        if contains(where: { $0.status == "warn" }) { return .warn }
        return .ok
    }
}
