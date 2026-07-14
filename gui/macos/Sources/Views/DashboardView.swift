import SwiftUI
import Combine
import AppKit
import UniformTypeIdentifiers

/// 主仪表盘：状态区、四张状态卡片、诊断 / 修复按钮、进度与结果摘要。
struct DashboardView: View {
    @ObservedObject var backend: Backend
    @ObservedObject var healthMonitor: HealthMonitor
    @ObservedObject var dashboardStore: DashboardStateStore
    @StateObject private var viewModel = DashboardViewModel()
    @State private var pendingAction: Action?
    @State private var showConfirmation = false
    @State private var showRollbackConfirmation = false
    @State private var showLogsSheet = false
    @State private var showAIQuestionSheet = false
    @State private var aiQuestionContext: AIQuestionContext = .diagnosis
    @State private var aiQuestionPrompt: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            statusHeader
                .padding()

            Divider()

            ScrollView {
                VStack(spacing: 16) {
                    currentStatusSection
                    connectionQualitySection

                    if let stateError = dashboardStore.errorMessage {
                        stateReadError(stateError)
                    }

                    if viewModel.isWorking {
                        progressSection
                    }

                    if let error = viewModel.errorMessage, !error.isEmpty {
                        errorBanner(error)
                    }

                    diagnosticEvidenceSection
                }
                .padding()
            }

            Divider()

            actionToolbar
                .padding()
        }
        .frame(minWidth: 420, idealWidth: 460, minHeight: 520)
        .task {
            await viewModel.bind(backend: backend, dashboardStore: dashboardStore)
        }
        .confirmationDialog("让 Netfix 处理这个问题？", isPresented: $showConfirmation, titleVisibility: .visible) {
            Button("让 Netfix 处理", role: .none) {
                if let action = pendingAction {
                    Task { await viewModel.executeAction(action, confirmed: true) }
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
                Task { await viewModel.recoverStaleBridge() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("这会停止 Netfix 代理，并恢复使用代理前的网络设置。")
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
                initialPrompt: aiQuestionPrompt,
                onOpenAISettings: {
                    NSApp.sendAction(#selector(AppDelegate.showAISettings), to: nil, from: nil)
                }
            ) { question, images in
                showAIQuestionSheet = false
                aiQuestionPrompt = nil
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
                Text("Netfix")
                    .font(.headline)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let route = viewModel.dashboardState?.routeLabel {
                Text(route)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Netfix，\(viewModel.dashboardState?.headline ?? subtitle)")
    }

    private var subtitle: String {
        if !backend.isReady {
            return friendlyStatusMessage(backend.statusMessage)
        }
        if dashboardStore.isRefreshing {
            return "正在更新当前状态…"
        }
        if let date = dashboardStore.lastUpdated {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .short
            return "更新于 \(formatter.localizedString(for: date, relativeTo: Date()))"
        }
        return friendlyStatusMessage(backend.statusMessage)
    }

    private func friendlyStatusMessage(_ message: String) -> String {
        if message.hasPrefix("正在启动 Netfix") {
            return "Netfix 正在启动…"
        }
        if message.hasPrefix("Netfix 已就绪") {
            return "Netfix 已就绪"
        }
        if message.hasPrefix("Netfix 异常") {
            return "Netfix 启动出错，可以查看日志或重启 App"
        }
        if message.hasPrefix("Netfix 已停止") {
            return "Netfix 已停止"
        }
        return message
    }

    @ViewBuilder
    private var statusDot: some View {
        if let severity = viewModel.dashboardState?.severity {
            Circle()
                .fill(statusColor(for: severity))
                .frame(width: 12, height: 12)
        } else {
            Circle()
                .fill(Color.secondary)
                .frame(width: 12, height: 12)
        }
    }

    private func statusColor(for severity: String) -> Color {
        switch severity {
        case "ok": return .green
        case "warn": return .orange
        case "fail": return .red
        default: return .blue
        }
    }

    // MARK: - 状态卡片

    /// 三张状态卡片：网络 / 代理 / 目标。技术细节折叠在「查看技术详情」。
    private let statusGroups: [(ids: [String], title: String, icon: String, summaryKey: PlainSummaryKey)] = [
        (["network", "dns", "path"], "网络连接", "wifi", .network),
        (["proxy", "egress"], "代理状态", "network", .proxy),
        (["service"], "目标网站", "server.rack", .targets),
    ]

    private var statusCards: some View {
        VStack(alignment: .leading, spacing: 12) {
            responsivenessCard
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                ForEach(statusGroups, id: \.title) { group in
                    let items = group.ids.flatMap { viewModel.items(for: $0) }
                    layerCard(title: group.title, icon: group.icon, summary: plainSummary(for: group.summaryKey, items: items), items: items)
                }
            }
        }
    }

    @ViewBuilder
    private var responsivenessCard: some View {
        let summary = viewModel.responsivenessSummary
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 8) {
                Image(systemName: summary.icon)
                    .foregroundStyle(summary.color)
                Text("网络质量")
                    .font(.headline)
                Spacer()
                Label(summary.headline, systemImage: summary.icon)
                    .font(.caption)
                    .foregroundStyle(summary.color)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(summary.color.opacity(0.14))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            Text(summary.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let insight = viewModel.insights?.primaryInsight {
                primaryInsightSection(insight)
            }
            if summary.showMetrics {
                HStack(alignment: .top, spacing: 12) {
                    responsivenessMetric(label: "速度", value: summary.speedLabel, hint: summary.speedHint, color: summary.speedColor)
                    responsivenessMetric(label: "延迟", value: summary.latencyLabel, hint: summary.latencyHint, color: summary.latencyColor)
                    responsivenessMetric(label: "稳定性", value: summary.stabilityLabel, hint: summary.stabilityHint, color: summary.stabilityColor)
                }
            }
            if summary.showMetrics || viewModel.hasBusyNetworkActivity {
                networkActivityTop3Section
            }
            if summary.showMetrics || !(viewModel.insights?.lagEvents ?? []).isEmpty {
                recentLagEventsSection
            }
            if summary.showMetrics || !(viewModel.insights?.proxyHealthTrend?.samples ?? []).isEmpty {
                proxyHealthTrendSection
            }
            if let hog = summary.bandwidthHint {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: hog.icon)
                        .foregroundStyle(hog.color)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(hog.headline)
                            .font(.caption)
                            .fontWeight(.semibold)
                        Text(hog.detail)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(8)
                .background(hog.color.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            DisclosureGroup("查看技术详情") {
                VStack(alignment: .leading, spacing: 4) {
                    if let rpm = summary.responsivenessRPM {
                        Text("• responsiveness_rpm: \(rpm)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let rtt = summary.baseRTTMs {
                        Text("• base_rtt_ms: \(rtt)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let dl = summary.dlThroughputKbps {
                        Text("• dl_throughput_kbps: \(dl)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let ul = summary.ulThroughputKbps {
                        Text("• ul_throughput_kbps: \(ul)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let loss = summary.packetLossPercent {
                        Text("• packet_loss_percent: \(loss)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if summary.responsivenessRPM == nil && summary.baseRTTMs == nil
                        && summary.dlThroughputKbps == nil && summary.ulThroughputKbps == nil
                        && summary.packetLossPercent == nil {
                        Text("本次未采集速度和延迟数据。")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 4)
            }
            .font(.caption)
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func primaryInsightSection(_ insight: DashboardPrimaryInsight) -> some View {
        let color = primaryInsightColor(insight.severity)
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: primaryInsightIcon(insight.state, severity: insight.severity))
                .foregroundStyle(color)
            VStack(alignment: .leading, spacing: 3) {
                Text(insight.headline ?? "当前状态")
                    .font(.caption)
                    .fontWeight(.semibold)
                if let detail = insight.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let action = insight.action, !action.isEmpty {
                    Text("\(insight.severity == "ok" ? "当前" : "可以做")：\(action)")
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .foregroundStyle(color)
                }
            }
            Spacer()
        }
        .padding(8)
        .background(Color.secondary.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func primaryInsightColor(_ severity: String?) -> Color {
        switch severity {
        case "ok": return .green
        case "warn": return .blue
        case "fail": return .orange
        default: return .secondary
        }
    }

    private func primaryInsightIcon(_ state: String?, severity: String?) -> String {
        switch state {
        case "busyUpload": return "icloud.and.arrow.up"
        case "busyDownload": return "arrow.down.circle"
        case "recentLag": return "clock.arrow.circlepath"
        case "authFailing": return "key.slash"
        case "failing": return "network.slash"
        case "slow": return "tortoise"
        case "notSampled": return "play.circle"
        case "activityUnavailable": return "info.circle"
        default:
            return severity == "ok" ? "checkmark.circle" : "info.circle"
        }
    }

    @ViewBuilder
    private func responsivenessMetric(label: String, value: String, hint: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(color)
            Text(hint)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(color.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    @ViewBuilder
    private var networkActivityTop3Section: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "arrow.up.arrow.down.circle")
                    .foregroundStyle(.secondary)
                Text("后台网络活动")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if viewModel.insights?.monitor?.running == true {
                    Text("后台检测中")
                        .font(.caption2)
                        .foregroundStyle(.green)
                }
            }

            if let activity = viewModel.insights?.networkActivity {
                let processes = activity.topProcesses.filter { $0.ignored != true }
                let busy = activity.state == "busyUpload" || activity.state == "busyDownload"
                if activity.state == "notSampled" {
                    Text("还没采样。运行一次检查后，会显示后台是否有较高流量。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if activity.state == "unavailable" {
                    Text(activity.headline ?? "暂时没法读取后台占用。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if processes.isEmpty {
                    Text(activity.headline ?? "后台网络活动平稳。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if busy {
                    ForEach(processes.prefix(3)) { process in
                        networkActivityProcessRow(process, actionable: true)
                    }
                } else {
                    Text(activity.headline ?? "后台网络活动平稳。")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    DisclosureGroup("查看当前活动") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(processes.prefix(3)) { process in
                                networkActivityProcessRow(process, actionable: false)
                            }
                        }
                    }
                    .font(.caption)
                }
            } else {
                Text("还没读取后台活动。运行一次检查后会显示。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    @ViewBuilder
    private func networkActivityProcessRow(_ process: NetworkActivityProcess, actionable: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: process.direction == "upload" ? "arrow.up.circle" : "arrow.down.circle")
                .foregroundStyle(process.direction == "upload" ? Color.blue : Color.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(process.displayName) · \(directionLabel(process.direction)) · \(rateLabel(process))")
                    .font(.caption)
                    .fontWeight(.semibold)
                Text(actionable
                    ? (process.direction == "upload" ? "如需优先保证实时应用，可暂停后复查。" : "如需优先保证实时应用，可暂停下载后复查。")
                    : "当前只是活动记录，不代表异常。")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if actionable {
                Button("这次不提醒") {
                    Task { await viewModel.ignoreNetworkProcess(process) }
                }
                .font(.caption2)
                .buttonStyle(.borderless)
            }
        }
    }

    @ViewBuilder
    private var recentLagEventsSection: some View {
        let events = Array((viewModel.insights?.lagEvents ?? []).reversed())
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath")
                    .foregroundStyle(.secondary)
                Text("近期网络事件")
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }
            if events.isEmpty {
                Text("近期没有记录到明显影响。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(events.prefix(2)), id: \.stableID) { event in
                    lagEventRow(event)
                }
                if events.count > 2 {
                    DisclosureGroup("再看 \(min(events.count - 2, 3)) 条") {
                        ForEach(Array(events.dropFirst(2).prefix(3)), id: \.stableID) { event in
                            lagEventRow(event)
                        }
                    }
                    .font(.caption)
                }
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    @ViewBuilder
    private var proxyHealthTrendSection: some View {
        let trend = viewModel.insights?.proxyHealthTrend
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "waveform.path.ecg")
                    .foregroundStyle(.secondary)
                Text("代理近 10 次")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                proxyHealthDots(trend?.samples ?? [])
            }
            Text(proxyTrendSummary(trend))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(8)
        .background(Color.secondary.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func lagEventRow(_ event: LagEventSummary) -> some View {
        let top = event.evidence?.topProcesses?.first
        let cause = event.suspectedCause?.isEmpty == false
            ? event.suspectedCause!
            : (top?.displayName ?? "后台任务")
        return HStack(alignment: .top, spacing: 8) {
            Image(systemName: "clock.arrow.circlepath")
                .foregroundStyle(.blue)
            VStack(alignment: .leading, spacing: 2) {
                Text(event.headline ?? "近期网络事件")
                    .font(.caption)
                    .fontWeight(.semibold)
                Text("\(eventTimeLabel(event.timestamp)) · 上次相关：\(cause)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    private func proxyHealthDots(_ samples: [ProxyHealthSample]) -> some View {
        HStack(spacing: 3) {
            ForEach(Array(samples.suffix(10).enumerated()), id: \.offset) { _, sample in
                Circle()
                    .fill(proxyHealthColor(sample.status))
                    .frame(width: 7, height: 7)
            }
            if samples.isEmpty {
                Text("暂无")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func proxyHealthColor(_ status: String?) -> Color {
        switch status {
        case "ok": return .green
        case "warn": return .orange
        case "fail": return .red
        default: return .secondary
        }
    }

    private func proxyTrendSummary(_ trend: ProxyHealthTrend?) -> String {
        guard let trend, !trend.samples.isEmpty else {
            return "还没有代理健康记录。保存代理后，Netfix 会记录脱敏的成功/失败趋势。"
        }
        let ok = trend.okCount ?? 0
        let warn = trend.warnCount ?? 0
        let fail = trend.failCount ?? 0
        let latency = trend.medianLatencyMs.map { " · 中位延迟 \($0)ms" } ?? ""
        return "近 \(trend.samples.count) 次：\(ok) 次正常，\(warn) 次不稳，\(fail) 次失败\(latency)。"
    }

    private func directionLabel(_ value: String?) -> String {
        switch value {
        case "upload": return "上传"
        case "download": return "下载"
        default: return "占用"
        }
    }

    private func rateLabel(_ process: NetworkActivityProcess) -> String {
        if let bucket = process.rateBucket, !bucket.isEmpty {
            return bucket
        }
        guard let kbps = process.rateKbps else { return "粗略速率未知" }
        if kbps >= 1_000 {
            return String(format: "%.1f Mbps", kbps / 1_000)
        }
        return "\(Int(kbps)) Kbps"
    }

    private func eventTimeLabel(_ timestamp: String?) -> String {
        guard let timestamp, !timestamp.isEmpty else { return "刚才" }
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: timestamp) {
            let relative = RelativeDateTimeFormatter()
            relative.unitsStyle = .short
            return relative.localizedString(for: date, relativeTo: Date())
        }
        return timestamp
    }

    private enum PlainSummaryKey { case network, proxy, targets }

    private func plainSummary(for key: PlainSummaryKey, items: [DiagnosticItem]) -> (label: String, hint: String) {
        if items.isEmpty {
            switch key {
            case .network: return ("未检测", "运行一次诊断后这里会显示网络情况")
            case .proxy:   return ("未配置", "粘贴代理参数后会显示这里")
            case .targets: return ("未检测", "点「检查常用网站」会显示能不能打开")
            }
        }
        let hasFail = items.contains { $0.status == "fail" }
        let hasWarn = items.contains { $0.status == "warn" }
        if hasFail {
            switch key {
            case .network: return ("异常", "Wi-Fi / DNS / 路由有问题")
            case .proxy:   return ("异常", "代理没在用或被拒绝")
            case .targets: return ("失败", "目标网站大多打不开")
            }
        }
        if hasWarn {
            switch key {
            case .network: return ("需复查", "网络可用，有几项信息需要复查")
            case .proxy:   return ("需复查", "代理可用性需要再确认")
            case .targets: return ("部分失败", "只有部分目标网站能打开")
            }
        }
        switch key {
        case .network: return ("正常", "本机网络、网关和 DNS 都正常")
        case .proxy:   return ("已就绪", "代理参数已保存或正在使用")
        case .targets: return ("可访问", "常用网站都能打开")
        }
    }

    private func layerCard(title: String, icon: String, summary: (label: String, hint: String), items: [DiagnosticItem]) -> some View {
        let status: DiagnosticStatus = {
            if items.isEmpty { return .unknown }
            if items.contains(where: { $0.status == "fail" }) { return .fail }
            if items.contains(where: { $0.status == "warn" }) { return .warn }
            return .ok
        }()

        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .foregroundStyle(.blue)
                Text(title)
                    .font(.headline)
                Spacer()
            }

            StatusIconView(status: status, label: summary.label)
                .help(summary.hint)

            Text(summary.hint)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            if !items.isEmpty {
                DisclosureGroup("查看技术详情") {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(items) { item in
                            Text("• \(item.displayTitle)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    .padding(.top, 4)
                }
                .font(.caption2)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
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
        let card = UserFacingMessages.classify(message)
        let humanReadable = "\(card.headline)\n\(card.nextStep)"

        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .padding(.top, 2)
                Text(humanReadable)
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

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    if viewModel.lastOperation != nil {
                        Button("重试") {
                            Task { await viewModel.retryLastOperation() }
                        }
                        // Kept intentionally as `.bordered` (not `.borderedProminent`)
                        // so the home screen never shows two prominent CTAs at
                        // once when an error banner is up — the primary CTA
                        // (state.primaryActionLabel) stays the only `.borderedProminent`.
                        .buttonStyle(.bordered)
                        .tint(.orange)
                        .controlSize(.small)
                        .fixedSize()
                    }

                    Button("复制这段说明") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(humanReadable, forType: .string)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .fixedSize()
                    .help("复制结论和下一步，不包含详细日志。")

                    Button("查看日志") {
                        openNetfixLogsFolder()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .fixedSize()
                }
            }

        }
        .padding()
        .background(Color.orange.opacity(0.15))
        .cornerRadius(8)
    }

    /// 把 reason_code / HTTP 400 / proxy_used / layer / traceback / raw JSON
    /// 这类内部词替换成用户可读说明。
    private func scrubInternalPhrases(_ raw: String) -> String {
        var out = raw
        let replacements: [(String, String)] = [
            ("reason_code", "原因代号"),
            ("proxy_used", "代理通道"),
            ("layer", "网络层"),
            ("traceback", "堆栈信息"),
            ("raw JSON", "原始数据"),
            ("HTTP 400", "请求被后端拒绝"),
            ("HTTP 401", "后端要求登录"),
            ("HTTP 403", "操作被拒绝"),
            ("HTTP 404", "后端没找到这条"),
            ("HTTP 502", "后端链路失败"),
        ]
        for (src, dst) in replacements {
            out = out.replacingOccurrences(of: src, with: dst)
        }
        return out
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

    private func structuredErrorCard(for message: String) -> UserFacingMessage {
        UserFacingMessages.classify(message)
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

    private func performDashboardPrimaryAction() {
        let target = viewModel.dashboardPrimaryActionTarget
        switch target {
        case .proxySetup:
            openProxySettings()
        case .doctor:
            Task { await viewModel.diagnose() }
        case .staleBridgeRecovery:
            showRollbackConfirmation = true
        case .none:
            return
        case .unsupported(let value):
            viewModel.errorMessage = "当前版本还不能执行这个动作。请重新读取状态后再试。"
            NSLog("Netfix dashboard action target unsupported: %@", value)
        }
    }

    // MARK: - 首页状态条

    @ViewBuilder
    private var currentStatusSection: some View {
        if let state = viewModel.dashboardState {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: state.iconName)
                        .font(.title3)
                        .foregroundStyle(state.tintColor)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(state.headline)
                            .font(.headline)
                        Text(state.detail)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer()
                    Text(state.routeLabel)
                        .font(.caption2)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(state.tintColor.opacity(0.14))
                        .foregroundStyle(state.tintColor)
                        .cornerRadius(6)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("当前结论：\(state.headline)。影响：\(state.detail)")

                Divider()

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        compactIdentityItem(
                            "\(state.interfaceLabel) · \(state.localIPLabel)",
                            icon: "wifi"
                        )
                        Divider().frame(height: 16)
                        compactIdentityItem(state.systemProxyLabel, icon: "switch.2")
                        Divider().frame(height: 16)
                        compactIdentityItem(state.egressLabel, icon: "globe")
                    }
                }
                .accessibilityLabel("当前网络身份")

                if !state.primaryActionLabel.isEmpty && state.primaryActionTarget != .none {
                    Button {
                        performDashboardPrimaryAction()
                    } label: {
                        Label(state.primaryActionLabel, systemImage: state.primaryActionIcon)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!backend.isReady || viewModel.isWorking)
                    .accessibilityHint(state.nextStep)
                }

                if let secondaryLabel = state.secondaryActionLabel,
                   state.secondaryActionTarget == .staleBridgeRecovery {
                    Button {
                        showRollbackConfirmation = true
                    } label: {
                        Label(secondaryLabel, systemImage: "stop.circle")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!backend.isReady || viewModel.isWorking)
                    .accessibilityHint("停止使用 Netfix 代理，并恢复之前的网络设置")
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(state.tintColor.opacity(0.18), lineWidth: 1)
            )
        }
    }

    private func compactIdentityItem(_ value: String, icon: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(value)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .fixedSize()
    }

    @ViewBuilder
    private var connectionQualitySection: some View {
        if isSectionRendered("connection_quality") {
            let quality = viewModel.dashboardState?.connectionQuality
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: connectionQualityIcon(quality?.status))
                        .foregroundStyle(connectionQualityColor(quality?.status))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("网络体感")
                            .font(.headline)
                        Text(connectionQualitySourceText(quality))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(connectionQualityBadge(quality))
                        .font(.caption2)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(connectionQualityColor(quality?.status).opacity(0.12))
                        .foregroundStyle(connectionQualityColor(quality?.status))
                        .cornerRadius(6)
                }

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 8) {
                    connectionQualityMetric(title: "速度", metric: quality?.speed, icon: "speedometer")
                    connectionQualityMetric(title: "延迟", metric: quality?.latency, icon: "timer")
                    connectionQualityMetric(title: "稳定性", metric: quality?.stability, icon: "waveform.path")
                    connectionQualityMetric(title: "后台占用", metric: quality?.backgroundActivity, icon: "arrow.up.arrow.down.circle")
                }
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
            )
        }
    }

    @ViewBuilder
    private func connectionQualityMetric(title: String, metric: DashboardStateResponse.ConnectionQuality.Metric?, icon: String) -> some View {
        let label = metric?.label ?? "未测"
        let value = metric?.value ?? "还没测"
        let hint = metric?.hint ?? "本机还没有返回这项数据。"
        let color = metricColor(label)
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon)
                .foregroundStyle(color)
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("\(label) · \(value)")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(color)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Text(hint)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title)：\(label)，\(value)。\(hint)")
    }

    private func connectionQualityIcon(_ status: String?) -> String {
        switch status {
        case "ok": return "gauge.with.dots.needle.67percent"
        case "partial": return "gauge.with.dots.needle.33percent"
        case "warn": return "gauge.with.dots.needle.33percent"
        case "fail": return "exclamationmark.triangle"
        default: return "gauge.with.dots.needle.0percent"
        }
    }

    private func connectionQualitySourceText(_ quality: DashboardStateResponse.ConnectionQuality?) -> String {
        switch quality?.collectionState {
        case "never_run": return "还没有本次数据。"
        case "unavailable": return "本机未能采样，未使用猜测值。"
        case "partial": return "来自最近一次检查，缺少的项目保持未测。"
        case "stale": return "上次数据已过期，请重新检查。"
        case "complete": return "来自最近一次检查，不会额外测速。"
        default: return "只显示本机实际返回的数据。"
        }
    }

    private func connectionQualityBadge(_ quality: DashboardStateResponse.ConnectionQuality?) -> String {
        if quality?.collectionState == "stale" { return "已过期" }
        switch quality?.status {
        case "ok": return "已测"
        case "warn": return "需留意"
        case "fail": return "体感较差"
        default: return "未测"
        }
    }

    private func connectionQualityColor(_ status: String?) -> Color {
        switch status {
        case "ok": return .green
        case "partial": return .blue
        case "warn": return .blue
        case "fail": return .orange
        default: return .secondary
        }
    }

    private func metricColor(_ label: String) -> Color {
        if label.contains("未测") {
            return .secondary
        }
        if label.contains("偏低") || label.contains("较高") || label.contains("不稳") || label.contains("上传") || label.contains("下载") {
            return .blue
        }
        if label.contains("充足") || label.contains("够用") || label == "低" || label.contains("稳定") || label.contains("平稳") {
            return .green
        }
        return .secondary
    }

    private func isSectionVisible(_ id: String) -> Bool {
        let visible = viewModel.dashboardState?.visibleSections ?? ["current_status"]
        if visible.isEmpty { return true }
        return visible.contains(id)
    }

    private func isSectionRendered(_ id: String) -> Bool {
        if isSectionVisible(id) { return true }
        return viewModel.dashboardState?.collapsedSections.contains(id) == true
    }

    private func stateReadError(_ message: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "arrow.clockwise.circle")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                Task { await dashboardStore.refresh() }
            } label: {
                Label("重新读取", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.bordered)
            .disabled(dashboardStore.isRefreshing)
        }
        .padding(10)
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private var diagnosticEvidenceSection: some View {
        if isSectionRendered("diagnostic_evidence") {
            DisclosureGroup("诊断证据") {
                VStack(alignment: .leading, spacing: 12) {
                    if let summary = dashboardStore.state?.lastReportSummary,
                       summary.hasReport == true || summary.checkedAt != nil {
                        evidenceRow("检查时间", value: summary.checkedAt ?? "尚未完成检查")
                        evidenceRow("当前线路", value: summary.routeMatchesCurrent == true ? "与检查时一致" : "尚未确认")
                        evidenceRow("可用证据", value: summary.usableForDashboard == true ? "可用" : "需要重新检查")
                    }
                    if let report = viewModel.report {
                        Divider()
                        Text(report.summaryHeadline)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        ForEach(report.diagnostics) { item in
                            HStack(spacing: 8) {
                                StatusIconView(status: DiagnosticStatus(item.status), label: "")
                                    .frame(width: 16)
                                Text(item.displayTitle)
                                    .font(.caption)
                                Spacer()
                                Text(friendlyDiagnosticStatus(item.status))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            .accessibilityElement(children: .combine)
                        }
                    }
                    if !hasDashboardReportEvidence && viewModel.report == nil {
                        Text("还没有诊断证据。点「检查当前网络」后会显示在这里。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 8)
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
            )
        }
    }

    private func evidenceRow(_ title: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .multilineTextAlignment(.trailing)
                .textSelection(.enabled)
        }
    }

    private var hasDashboardReportEvidence: Bool {
        guard let summary = dashboardStore.state?.lastReportSummary else { return false }
        return summary.hasReport == true || summary.checkedAt != nil
    }

    private func friendlyDiagnosticStatus(_ status: String) -> String {
        switch status {
        case "ok": return "正常"
        case "warn": return "需复查"
        case "fail": return "未通过"
        default: return "未采样"
        }
    }

    // MARK: - 结果区

    private func resultSection(report: NetfixReport) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if let explanation = report.explanation {
                explanationCard(explanation)
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
                    Label("生成简明说明", systemImage: "message")
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
                Text(result.source == "llm" ? "AI 解释" : "Netfix 本地解释")
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
        case "missing_key": return "需要 AI 密钥"
        default: return status
        }
    }

    private func friendlyLLMReason(_ reason: String?) -> String? {
        guard let reason, !reason.isEmpty else { return nil }
        let lower = reason.lowercased()
        if lower.contains("missing_api_key") || lower.contains("missing api key") {
            return "还没有配置 AI 密钥。"
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

    // legacyResultCard was the v1 fallback path. It has been removed: the
    // home view renders only the verdict-driven currentStatusSection. The
    // report's explanation (when present) flows through explanationCard.

    private func requestAction(_ action: Action) {
        if action.needsConfirm {
            pendingAction = action
            showConfirmation = true
        } else {
            Task { await viewModel.executeAction(action) }
        }
    }

    // MARK: - 事件时间线

    private var statusHistorySection: some View {
        DisclosureGroup("历史记录") {
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
        secondaryActionToolbar
    }

    private var secondaryActionToolbar: some View {
        HStack(spacing: 10) {
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

            Menu("更多") {
                if let recommendedAction = viewModel.recommendedAction {
                    Button("处理建议") {
                        requestAction(recommendedAction)
                    }
                    .disabled(!backend.isReady || viewModel.isWorking)
                }
                if viewModel.rollbackAvailable {
                    Button("恢复原来的网络设置") {
                        showRollbackConfirmation = true
                    }
                    .disabled(!backend.isReady || viewModel.isWorking)
                }
                Button("生成简明说明") {
                    aiQuestionContext = .diagnosis
                    showAIQuestionSheet = true
                }
                .disabled(viewModel.report == nil || viewModel.isWorking)
                Button("代理说明") {
                    aiQuestionContext = .proxy
                    showAIQuestionSheet = true
                }
                .disabled(viewModel.isWorking)
                Button("复制脱敏报告") {
                    Task { await viewModel.copySupportBundle() }
                }
                .disabled(!backend.isReady)
            }
            .menuStyle(.borderlessButton)
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

fileprivate enum AIQuestionContext: Equatable {
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
    let initialPrompt: String?
    let onOpenAISettings: () -> Void
    let onSend: (String, [String]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var question: String
    @State private var images: [AIQuestionImage] = []
    @State private var uploadConfirmed = false
    @State private var errorMessage: String?

    init(
        isWorking: Bool,
        context: AIQuestionContext,
        initialPrompt: String? = nil,
        onOpenAISettings: @escaping () -> Void,
        onSend: @escaping (String, [String]) -> Void
    ) {
        self.isWorking = isWorking
        self.context = context
        self.initialPrompt = initialPrompt
        self.onOpenAISettings = onOpenAISettings
        self.onSend = onSend
        self._question = State(initialValue: initialPrompt ?? "")
    }

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

            Text("这只影响 AI 看报告，不影响检查网络、使用代理或恢复网络设置。没有 AI 密钥时，主流程照常可用；需要 AI 时再到设置里填写。截图问诊仅支持 PNG、JPEG、WebP 或 GIF。")
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
    @Published var dashboardState: DashboardHomePresentation?
    @Published var insights: DashboardInsightsResponse?
    @Published var hasCloudAI: Bool = false
    @Published var copyFeedback: String?

    struct DashboardHomePresentation {
        let uiState: DashboardUIState
        let headline: String
        let detail: String
        let nextStep: String
        let iconName: String
        let tintColor: Color
        let severity: String
        let primaryActionID: String
        let primaryActionLabel: String
        let primaryActionTarget: DashboardActionTarget
        let secondaryActionLabel: String?
        let secondaryActionTarget: DashboardActionTarget
        let shouldShowProxyDeployCTA: Bool
        let routeLabel: String
        let interfaceLabel: String
        let localIPLabel: String
        let systemProxyLabel: String
        let egressLabel: String
        let connectionQuality: DashboardStateResponse.ConnectionQuality?
        let visibleSections: [String]
        let collapsedSections: [String]

        init(_ state: DashboardUIState) {
            self.uiState = state
            self.headline = state.headline
            self.detail = state.nextStep
            self.nextStep = state.nextStep
            self.iconName = state.iconName
            self.tintColor = state.tintColor
            self.severity = "info"
            self.primaryActionID = "diagnose"
            self.primaryActionLabel = ""
            self.primaryActionTarget = .none
            self.secondaryActionLabel = nil
            self.secondaryActionTarget = .none
            self.shouldShowProxyDeployCTA = state == .noProxy
            self.routeLabel = state.headline
            self.interfaceLabel = "未检测"
            self.localIPLabel = "未检测"
            self.systemProxyLabel = "未检测"
            self.egressLabel = "未检测"
            self.connectionQuality = nil
            self.visibleSections = ["current_status"]
            self.collapsedSections = []
        }

        init(response: DashboardStateResponse) {
            let state = response.uiState
            self.uiState = state
            self.headline = response.headline
            self.detail = response.narrativeDetail ?? response.nextStep
            self.nextStep = response.nextStep
            self.iconName = state.iconName
            self.severity = response.verdict?.severity ?? response.decision?.severity ?? "info"
            self.tintColor = Self.tintColor(for: self.severity, fallback: state.tintColor)
            self.primaryActionID = response.primaryActionID
            self.primaryActionLabel = response.primaryActionLabel
            self.primaryActionTarget = response.resolvedPrimaryActionTarget
            self.secondaryActionLabel = response.secondaryActionLabel
            self.secondaryActionTarget = response.resolvedSecondaryActionTarget
            self.shouldShowProxyDeployCTA = response.shouldShowProxyDeployCTA
            self.routeLabel = Self.routeLabel(for: response.decision?.effectiveRoute, fallback: state.headline)
            self.interfaceLabel = response.machine?.primaryInterface?.isEmpty == false ? "当前连接" : "未检测"
            self.localIPLabel = response.machine?.selfIPv4 ?? "未检测"
            self.systemProxyLabel = Self.systemProxyLabel(response.proxy?.system)
            self.egressLabel = Self.egressLabel(response.egress)
            self.connectionQuality = response.connectionQuality
            self.visibleSections = response.presentation?.visibleSections ?? ["current_status"]
            self.collapsedSections = response.presentation?.collapsedSections ?? []
        }

        var primaryActionIcon: String {
            switch primaryActionTarget {
            case .proxySetup: return "slider.horizontal.3"
            case .doctor: return "stethoscope"
            case .staleBridgeRecovery: return "arrow.uturn.backward.circle"
            case .none: return "checkmark.circle"
            case .unsupported: return "questionmark.circle"
            }
        }

        private static func tintColor(for severity: String?, fallback: Color) -> Color {
            switch severity {
            case "ok": return .green
            case "warn": return .orange
            case "fail": return .red
            case "info": return .blue
            default: return fallback
            }
        }

        private static func routeLabel(for value: String?, fallback: String) -> String {
            switch value {
            case "none": return "未使用代理"
            case "saved_only": return "已保存未启用"
            case "external_system_proxy": return "其他代理正在使用"
            case "netfix_applied": return "Netfix 已启用"
            case "degraded": return "代理待复查"
            case "recovery_required": return "需要恢复"
            default: return fallback
            }
        }

        private static func systemProxyLabel(_ system: DashboardStateResponse.Proxy.SystemProxy?) -> String {
            guard let system, system.active == true else { return "未启用" }
            switch system.kind {
            case "http_https": return "HTTP/HTTPS"
            case "socks": return "SOCKS"
            case "pac": return "PAC"
            case "mixed": return "多种代理"
            default: return "已启用"
            }
        }

        private static func egressLabel(_ egress: DashboardStateResponse.Egress?) -> String {
            guard let egress else { return "未检测" }
            if let ip = egress.publicIPv4, !ip.isEmpty {
                if let ipType = egress.ipType, !ipType.isEmpty {
                    return "\(ip) · \(ipType)"
                }
                return ip
            }
            switch egress.status {
            case "ok": return "已检测"
            case "warn": return "需复查"
            case "fail": return "检测失败"
            case "stale": return "结果已过期"
            default: return "未检测"
            }
        }
    }

    var shouldShowProxyDeploySection: Bool {
        dashboardState?.shouldShowProxyDeployCTA ?? false
    }

    var dashboardPrimaryActionID: String {
        dashboardState?.primaryActionID ?? "diagnose"
    }

    var dashboardPrimaryActionTarget: DashboardActionTarget {
        dashboardState?.primaryActionTarget ?? .none
    }

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
        dashboardState?.secondaryActionTarget == .staleBridgeRecovery
    }

    private var client: APIClient?
    private weak var dashboardStore: DashboardStateStore?
    private var dashboardStoreCancellable: AnyCancellable?
    private var progressTimer: Timer?
    private var progressIndex = 0
    private var cancellationRequested = false
    fileprivate(set) var lastOperation: LastOperation?

    enum LastOperation {
        case diagnose
        case fix
        case checkServices(String)
        case executeAction(Action)
        case recover
    }

    private func actionLooksLikeRollback(_ action: Action) -> Bool {
        let text = "\(action.id) \(action.label)".lowercased()
        return text.contains("rollback") || text.contains("restore") || text.contains("回滚") || text.contains("恢复")
    }

    func bind(backend: Backend, dashboardStore: DashboardStateStore) async {
        if self.dashboardStore !== dashboardStore {
            self.dashboardStore = dashboardStore
            dashboardStoreCancellable = dashboardStore.$state
                .compactMap { $0 }
                .receive(on: DispatchQueue.main)
                .sink { [weak self] response in
                    guard let self else { return }
                    self.dashboardState = DashboardHomePresentation(response: response)
                    if !self.isWorking {
                        self.headline = response.headline
                    }
                }
            if let response = dashboardStore.state {
                self.dashboardState = DashboardHomePresentation(response: response)
                self.headline = response.headline
            }
        }

        for await _ in backend.$state.values {
            updateHeadline(backend: backend)
            if backend.isReady, let url = backend.apiURL, let token = backend.apiToken, client == nil {
                let apiClient = APIClient(baseURL: url, apiToken: token)
                client = apiClient
                dashboardStore.configure(client: apiClient)
                await dashboardStore.refresh()
            } else if !backend.isReady {
                client = nil
            }
        }
    }

    func refreshDashboardState() async {
        await dashboardStore?.refresh()
    }

    func refreshDashboardInsights() async {
        guard let client else { return }
        do {
            insights = try await client.dashboardInsights()
        } catch {
            // insights 是辅助信息，失败时不阻断诊断、部署和修复主流程。
        }
    }

    func ignoreNetworkProcess(_ process: NetworkActivityProcess) async {
        guard let client else { return }
        let match = (process.process?.isEmpty == false ? process.process : process.label) ?? ""
        guard !match.isEmpty else { return }
        do {
            let current = try await client.networkActivitySettings().settings
            var rules = current.processWhitelist
            if !rules.contains(where: { $0.match.caseInsensitiveCompare(match) == .orderedSame }) {
                rules.append(NetworkActivityIgnoreRule(
                    match: match,
                    label: process.displayName,
                    reason: "user_ignored",
                    enabled: true
                ))
            }
            _ = try await client.saveNetworkActivitySettings(
                enabled: current.enabled,
                interval: current.interval,
                processWhitelist: rules
            )
            copyFeedback = "以后不再提醒 \(process.displayName)。"
            await refreshDashboardInsights()
        } catch {
            copyFeedback = "保存忽略名单失败：\(error.localizedDescription)"
        }
    }

    func refreshCloudAIStatus() async {
        guard let client else { return }
        do {
            let response = try await client.llmProviders()
            hasCloudAI = response.providers.contains { $0.apiKeySet == true }
        } catch {
            hasCloudAI = false
        }
    }

    func copySupportBundle() async {
        guard let client else { return }
        copyFeedback = nil
        do {
            let response = try await client.supportBundle()
            let text = response.supportText ?? "暂无可复制的支持包。"
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
            copyFeedback = "已复制支持包到剪贴板。"
        } catch {
            copyFeedback = UserFacingMessages.classify(error.localizedDescription).headline
        }
    }

    /// 让普通用户点 AI 按钮时不再依赖 API Key：先按本地规则给出结论，
    /// 只有当云端 AI 已启用时再让云端覆盖本地结论。
    fileprivate func answerQuickQuestion(prompt: String, context: AIQuestionContext) async {
        guard let client else { return }
        llmError = nil
        copyFeedback = nil
        let localAnswer = buildLocalAnswer(prompt: prompt, context: context)
        llmExplanation = LLMExplainResult(
            source: "local_rule",
            fallbackReason: nil,
            fallbackReasonLabel: nil,
            failureReasonCode: nil,
            providerUsed: nil,
            fallbackChain: nil,
            needsUploadConfirmation: false,
            headline: localAnswer.headline,
            severity: localAnswer.severity,
            explanation: localAnswer.body,
            redactedReportHash: nil
        )
        headline = localAnswer.headline
        if hasCloudAI {
            startWork(steps: ["本地已给出结论，正在请云端 AI 再确认…"])
            do {
                let response = try await client.explainWithLLM(
                    question: prompt,
                    mode: "explain",
                    uploadConfirmed: false,
                    images: []
                )
                llmExplanation = response.result
                headline = response.result.headline ?? headline
            } catch {
                llmError = "云端 AI 没回：\(friendlyAIError(error.localizedDescription))。先按上方本地结论处理即可。"
            }
            stopWork()
        } else {
            copyFeedback = "已给出本地结论（无需 AI 密钥）。需要更详细的解释时，到「设置 → AI」填写 AI 密钥。"
        }
    }

    /// 「检查我的代理参数格式」专用：基于本地规则给出清楚提示。
    func checkProxyInputFormat() async {
        let headline = "代理参数格式参考"
        let body = "支持的格式：\n• host:port:user:pass（最常见）\n• http://user:pass@host:port\n• socks5h://user:pass@host:port\n• 多行带表头的列表\n不支持：ss://、vmess://、Clash 订阅链接。\n保存时密码只写入本机密码库。"
        llmExplanation = LLMExplainResult(
            source: "local_rule",
            fallbackReason: nil,
            fallbackReasonLabel: nil,
            failureReasonCode: nil,
            providerUsed: nil,
            fallbackChain: nil,
            needsUploadConfirmation: false,
            headline: headline,
            severity: "info",
            explanation: body,
            redactedReportHash: nil
        )
        self.headline = headline
        copyFeedback = "格式参考已显示。"
    }

    private func buildLocalAnswer(prompt: String, context: AIQuestionContext) -> (headline: String, body: String, severity: String) {
        switch context {
        case .diagnosis:
            if let report = report {
                let detail = report.explanation?.explanation ?? report.firstRootCause ?? "当前没有可解释的诊断条目。"
                let action = report.explanation?.primaryAction?.label
                let next = report.explanation?.actions.first?.label
                let extra = (action ?? next).map { "\n建议先点：\($0)。" } ?? ""
                let severity = report.overallStatus == .ok ? "ok" : (report.overallStatus == .fail ? "fail" : "warn")
                return (report.summaryHeadline, detail + extra, severity)
            }
            return ("还没有诊断结果", "请先点「检查当前网络」；结果出来后这里会基于本地规则直接告诉你现在该怎么办，不需要 AI 密钥。", "info")
        case .proxy:
            return (
                "代理部署的常见问题",
                "一般流程：1) 粘贴 host:port:user:pass；2) 点「检查并保存」；3) 点「开始使用代理」。\n中间会备份你现在的网络设置；不用时点「恢复原来的网络设置」即可。\n需要账号密码的代理会由 Netfix 在本机安全代管。",
                "info"
            )
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
        if let dashboard = dashboardState {
            headline = dashboard.headline
        } else if let report = report {
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
        await refreshDashboardState()
        await refreshDashboardInsights()
    }

    func fix() async {
        errorMessage = nil
        guard recommendedAction != nil else {
            headline = "没有可直接处理的建议"
            errorMessage = "先点“检查当前网络”。只有 Netfix 找到明确建议后，才会出现可处理按钮。"
            return
        }
        headline = "请选择上方的处理建议"
        errorMessage = "这一步需要按报告里的具体建议处理；如果会改系统网络设置，Netfix 会先弹出确认。"
    }

    func executeAction(_ action: Action) async {
        await executeAction(action, confirmed: false)
    }

    func executeAction(_ action: Action, confirmed: Bool) async {
        guard let client = client else { return }
        errorMessage = nil
        lastOperation = .executeAction(action)
        startWork(steps: [
            "正在执行：\(action.label)…",
            "正在验证修复结果…",
        ])
        do {
            let result = try await client.executeFix(
                fixId: action.id,
                timeout: 60,
                confirmed: confirmed
            )
            self.report = result
            headline = result.explanation?.headline ?? result.summaryHeadline
            await refreshDashboardState()
            await refreshDashboardInsights()
        } catch {
            let message = error.localizedDescription
            let card = UserFacingMessages.classify(message)
            errorMessage = message
            headline = card.code == UserFacingErrorCode.ipv6FallbackRisk.rawValue ? card.headline : "修复失败"
        }
        stopWork()
    }

    func recoverStaleBridge() async {
        guard let client = client else { return }
        errorMessage = nil
        lastOperation = .recover
        startWork(steps: [
            "正在停止 Netfix 代理…",
            "正在恢复原来的网络设置…",
        ])
        do {
            let response = try await client.recoverProxyBridge(confirmed: true)
            if response.ok && response.status == "recovered" {
                headline = "已恢复原来的网络设置"
                errorMessage = nil
            } else if response.ok && response.status == "no_recovery_needed" {
                headline = "当前没有执行恢复"
                errorMessage = "代理可能仍在使用中。请保持 Netfix 运行，重新读取状态后再试。"
            } else {
                headline = "恢复失败"
                errorMessage = response.error ?? response.status ?? "恢复没有完成。"
            }
            await refreshDashboardState()
        } catch {
            errorMessage = error.localizedDescription
            headline = "恢复失败"
            await refreshDashboardState()
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
        await refreshDashboardInsights()
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
            return "还没配置 AI：这只影响 AI 看报告，不影响检查网络和使用代理。需要 AI 时，到设置里选择供应商并填写 AI 密钥。"
        }
        if lower.contains("cloud ai explanation is disabled") || lower.contains("llm_disabled") {
            return "AI 还没启用：打开设置里的 AI，启用后填写 AI 密钥并保存测试。"
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
        case .recover:
            await recoverStaleBridge()
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

    var hasBusyNetworkActivity: Bool {
        let state = insights?.networkActivity?.state
        return state == "busyUpload" || state == "busyDownload" || state == "unavailable"
    }

    // MARK: - 网络质量摘要

    struct ResponsivenessMetric {
        let label: String
        let hint: String
        let color: Color
    }

    struct BandwidthHint {
        let icon: String
        let color: Color
        let headline: String
        let detail: String
    }

    struct ResponsivenessSummary {
        let headline: String
        let detail: String
        let icon: String
        let color: Color
        let speedLabel: String
        let speedHint: String
        let speedColor: Color
        let showMetrics: Bool
        let latencyLabel: String
        let latencyHint: String
        let latencyColor: Color
        let stabilityLabel: String
        let stabilityHint: String
        let stabilityColor: Color
        let bandwidthHint: BandwidthHint?
        let responsivenessRPM: Int?
        let baseRTTMs: Int?
        let dlThroughputKbps: Int?
        let ulThroughputKbps: Int?
        let packetLossPercent: Double?
    }

    var responsivenessSummary: ResponsivenessSummary {
        guard let report else {
            return ResponsivenessSummary(
                headline: "还没诊断",
                detail: "运行一次检查后，这里会显示速度、延迟和稳定性。",
                icon: "questionmark.circle",
                color: .secondary,
                speedLabel: "未测",
                speedHint: "本次检查会补上",
                speedColor: .secondary,
                showMetrics: false,
                latencyLabel: "未测",
                latencyHint: "本次检查会补上",
                latencyColor: .secondary,
                stabilityLabel: "未测",
                stabilityHint: "本次检查会补上",
                stabilityColor: .secondary,
                bandwidthHint: nil,
                responsivenessRPM: nil,
                baseRTTMs: nil,
                dlThroughputKbps: nil,
                ulThroughputKbps: nil,
                packetLossPercent: nil
            )
        }
        let networkQuality = report.diagnostics.first { $0.name == "network_quality" }
        let bandwidthHog = report.diagnostics.first { $0.name == "bandwidth_hog" }
        let pathTrace = report.diagnostics.first { $0.name == "path_trace" }
        let nqDetails = networkQuality?.details ?? [:]
        let bandwidthDetails = bandwidthHog?.details ?? [:]
        let pathDetails = pathTrace?.details ?? [:]

        let rpm = nqDetails["responsiveness_rpm"]?.intValue
        let baseRTT = nqDetails["base_rtt_ms"]?.doubleValue.map { Int($0) }
        let dlKbps = nqDetails["dl_throughput_kbps"]?.doubleValue.map { Int($0) }
        let ulKbps = nqDetails["ul_throughput_kbps"]?.doubleValue.map { Int($0) }
        let qualityStatus = networkQuality?.status ?? ""
        let qualityWarnWithoutNumbers = (qualityStatus == "warn" || qualityStatus == "fail")
            && rpm == nil && baseRTT == nil && dlKbps == nil && ulKbps == nil
        let packetLoss: Double? = pathDetails["hops"]?.arrayValue?
            .compactMap { item -> Double? in
                guard let dict = item.objectValue,
                      let loss = dict["loss_percent"]?.doubleValue else { return nil }
                return loss
            }
            .max()

        let (speedLabel, speedHint, speedColor): (String, String, Color) = {
            if dlKbps == nil && ulKbps == nil {
                if qualityWarnWithoutNumbers {
                    return ("需复查", "本次没有拿到速度数据", .blue)
                }
                return ("未测", "本次检查会补上", .secondary)
            }
            let down = dlKbps.map { Double($0) / 1_000.0 }
            let up = ulKbps.map { Double($0) / 1_000.0 }
            let hint: String = {
                switch (down, up) {
                case let (.some(down), .some(up)):
                    return String(format: "下载 %.1f Mbps / 上传 %.1f Mbps", down, up)
                case let (.some(down), .none):
                    return String(format: "下载 %.1f Mbps", down)
                case let (.none, .some(up)):
                    return String(format: "上传 %.1f Mbps", up)
                default:
                    return "还没测"
                }
            }()
            if let down, down < 5 {
                return ("偏低", hint, .blue)
            }
            if let up, up < 1 {
                return ("偏低", hint, .blue)
            }
            if let down, down >= 25, (up ?? 3) >= 3 {
                return ("充足", hint, .green)
            }
            return ("够用", hint, .green)
        }()

        let (latencyLabel, latencyHint, latencyColor): (String, String, Color) = {
            if baseRTT == nil { return ("未测", "本次检查会补上", .secondary) }
            if let rtt = baseRTT {
                if rtt <= 60 { return ("低", "延迟 \(rtt)ms，实时输出比较顺", .green) }
                if rtt <= 150 { return ("中等", "延迟 \(rtt)ms，实时输出会有轻微等待", .blue) }
                return ("较高", "延迟 \(rtt)ms，实时输出会有明显等待", .orange)
            }
            return ("未测", "", .secondary)
        }()

        let (stabilityLabel, stabilityHint, stabilityColor): (String, String, Color) = {
            if let loss = packetLoss {
                if loss == 0 { return ("稳定", "路径上几乎没有丢包", .green) }
                if loss <= 5 { return ("轻微波动", "路径上有轻微丢包（\(Int(loss))%）", .blue) }
                return ("丢包较明显", "路径丢包 \(Int(loss))%，换网络或节点后再试", .orange)
            }
            return ("未测", "本次检查会补上", .secondary)
        }()

        let (headline, icon, color, detail): (String, String, Color, String) = {
            let bandwidthReason = bandwidthDetails["reason"]?.stringValue ?? ""
            let bandwidthStatus = bandwidthHog?.status ?? ""
            if bandwidthStatus == "warn" && bandwidthReason == "upload_saturated" {
                let topNames = bandwidthTopProcessNames(bandwidthDetails["top_processes"])
                return (
                    "响应较慢",
                    "speedometer",
                    Color.blue,
                    topNames.isEmpty
                        ? "检测到上行流量较高。如需优先保证实时应用，可暂停同步或上传后复查。"
                        : "检测到 \(topNames.joined(separator: "、")) 上行流量较高。如需优先保证实时应用，可暂停后复查。"
                )
            }
            if bandwidthStatus == "warn" && bandwidthReason == "download_saturated" {
                return (
                    "响应较慢",
                    "speedometer",
                    Color.blue,
                    "检测到下行流量较高。如需优先保证实时应用，可暂停下载或系统更新后复查。"
                )
            }
            if let rtt = baseRTT, rtt > 200 {
                return ("响应较慢", "speedometer", Color.blue, "延迟较高，实时应用会有明显等待。")
            }
            if let rtt = baseRTT, rtt > 120 {
                return ("响应一般", "speedometer", Color.blue, "延迟 \(rtt)ms，实时输出可能会慢一点。")
            }
            if let rpm = rpm {
                if rpm < 50 { return ("响应较慢", "speedometer", Color.blue, "实时应用会有明显等待。") }
                if rpm < 200 { return ("响应一般", "speedometer", Color.blue, "实时输出可能会慢一点。") }
                return ("顺畅", "hare.fill", Color.green, "日常使用没问题。")
            }
            if qualityWarnWithoutNumbers {
                return ("可用", "checkmark.circle", Color.green, "网络可用；本次没有拿到速度/延迟数据，可重新检测确认。")
            }
            return ("未知", "questionmark.circle", Color.secondary, "还没有速度和延迟检测结果。")
        }()

        let bandwidthHint: BandwidthHint? = {
            guard let bandwidthHog, let reason = bandwidthDetails["reason"]?.stringValue else { return nil }
            let status = bandwidthHog.status
            guard status == "warn" || status == "fail" else { return nil }
            let icon: String = reason == "upload_saturated" ? "icloud.and.arrow.up" : "arrow.down.circle"
            let color: Color = Color.blue
            let topNames = bandwidthTopProcessNames(bandwidthDetails["top_processes"])
            let headline = reason == "upload_saturated"
                ? "检测到上行流量较高"
                : "检测到下行流量较高"
            let detail = topNames.isEmpty
                ? (reason == "upload_saturated"
                    ? "如需优先保证实时应用，可先暂停同步或上传后复查。"
                    : "如需优先保证实时应用，可先暂停下载或系统更新后复查。")
                : "\(topNames.joined(separator: "、")) 的流量较高；需要优先保证实时应用时，可暂停后复查。"
            return BandwidthHint(icon: icon, color: color, headline: headline, detail: detail)
        }()

        let showMetrics = rpm != nil || baseRTT != nil || dlKbps != nil || ulKbps != nil || packetLoss != nil || qualityWarnWithoutNumbers

        return ResponsivenessSummary(
            headline: headline,
            detail: detail,
            icon: icon,
            color: color,
            speedLabel: speedLabel,
            speedHint: speedHint,
            speedColor: speedColor,
            showMetrics: showMetrics,
            latencyLabel: latencyLabel,
            latencyHint: latencyHint,
            latencyColor: latencyColor,
            stabilityLabel: stabilityLabel,
            stabilityHint: stabilityHint,
            stabilityColor: stabilityColor,
            bandwidthHint: bandwidthHint,
            responsivenessRPM: rpm,
            baseRTTMs: baseRTT,
            dlThroughputKbps: dlKbps,
            ulThroughputKbps: ulKbps,
            packetLossPercent: packetLoss
        )
    }

    private func intValue(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? Double { return Int(value) }
        if let value = value as? NSNumber { return value.intValue }
        return nil
    }

    private func doubleValue(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? Int { return Double(value) }
        if let value = value as? NSNumber { return value.doubleValue }
        return nil
    }

    private func bandwidthTopProcessNames(_ raw: AnyCodable?) -> [String] {
        guard let items = raw?.arrayValue else { return [] }
        var names: [String] = []
        for item in items.prefix(3) {
            guard let dict = item.objectValue else { continue }
            let label = dict["label"]?.stringValue ?? dict["process"]?.stringValue ?? ""
            if !label.isEmpty { names.append(label) }
        }
        return names
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
                    Text("暂无事件。运行一次检查后，这里会显示历史记录。")
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
