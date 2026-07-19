import SwiftUI
import AppKit
import UniformTypeIdentifiers

private struct AIQuestionImage: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let dataURL: String
    let preview: NSImage?
}

/// 「问 AI」对话场景：目前只有结合当前检查的 diagnosis 一种。
fileprivate enum AIQuestionContext: Equatable {
    case diagnosis

    var prompts: [String] {
        switch self {
        case .diagnosis:
            return ["下一步怎么处理？", "怎么看出来的？", "是不是代理没生效？"]
        }
    }

    var placeholder: String {
        switch self {
        case .diagnosis:
            return "留空也可以，Netfix 会直接解释当前诊断报告；也可以补一句你现在遇到什么。"
        }
    }
}

/// 主界面常驻的「问 AI」内联对话区：消息列表 + 输入框，不再使用独立弹窗。
/// 发送默认不带上传确认；后端回 needs_upload_confirmation 时，在对话流里内联确认后重发。
struct AIChatView: View {
    let isWorking: Bool
    let isAIStatusLoading: Bool
    let hasCurrentReport: Bool
    let hasCloudAI: Bool
    let providerLabels: [String]
    let uploadConsent: String
    let imageQuestionEnabled: Bool
    let conversation: [AIChatTurn]
    let errorMessage: String?
    let composerFocused: FocusState<Bool>.Binding
    let onOpenAISettings: () -> Void
    let onRunCheck: () -> Void
    let onCancelRequest: () -> Void
    let onRunAction: (Action) -> Void
    let onSend: (String, [String], Bool) -> Void
    /// P1-A.3: 历史可恢复的 sessions；如果非空且 conversation 为空，会显示 SessionRecoveryBanner。
    var recoverableSessions: [ChatSession] = []
    /// P1-B.1: 主动告警列表，会插入对话流顶部。
    var proactiveAlerts: [ProactiveAlert] = []
    /// P1-A.3: 用户在 SessionRecoveryBanner 里点了「恢复」后回调。
    var onResumeSession: ((ChatSession) -> Void)?
    /// P1-B.1: 三类告警回调。
    var onDismissAlert: ((ProactiveAlert) -> Void)?
    var onActOnAlert: ((ProactiveAlert, String) -> Void)?
    var onIgnoreAlert: ((ProactiveAlert) -> Void)?
    /// P1-A.3: 头部「清空对话」按钮回调，仅 conversation 非空时显示。
    var onClearConversation: (() -> Void)?

    private let context: AIQuestionContext = .diagnosis
    @State private var question = ""
    @State private var images: [AIQuestionImage] = []
    @State private var attachmentError: String?
    /// 最近一次发出的原文和截图，供「确认发送」后重发同一问题。
    @State private var pendingUpload: PendingUpload?
    /// 已经处理过（确认或取消）上传确认气泡的轮次，不再重复展示。
    @State private var dismissedUploadConfirmation: Set<UUID> = []
    /// 同 session 内用户勾过「这次不再问同会话」的 confirmation category。
    @State private var dontAskCategoriesThisSession: Set<String> = []
    /// 用户是否已经看过 SessionRecoveryBanner；首次出现时为 true。
    @State private var showSessionRecovery: Bool = true
    /// 消息列表高度：随内容增长，夹在 160…380 之间。
    @State private var messageListHeight: CGFloat = 160
    /// 用户是否停留在消息列表底部附近；不在底部时不强制自动滚动。
    @State private var isNearBottom: Bool = true
    /// 「回车发送」的本地键盘监听（macOS 13 没有 onKeyPress）。
    @State private var returnKeyMonitor: Any?

    private struct PendingUpload {
        let question: String
        let images: [String]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Label("问 AI", systemImage: "sparkles")
                    .font(.headline)
                Spacer()
                if !conversation.isEmpty, let onClearConversation {
                    Button {
                        onClearConversation()
                    } label: {
                        Label("清空对话", systemImage: "trash")
                    }
                    .buttonStyle(.borderless)
                    .disabled(isWorking)
                    .help("删除当前会话并清空对话记录")
                }
                Button {
                    onOpenAISettings()
                } label: {
                    Label("AI 设置", systemImage: "key")
                }
                .buttonStyle(.borderless)
                .disabled(isWorking)
            }

            aiAvailability

            if !hasCurrentReport {
                noReportBanner
            }

            messageList

            attachmentPicker

            composerRow

            HStack(spacing: 8) {
                if isWorking {
                    Button("停止这次解释", role: .cancel, action: onCancelRequest)
                        .controlSize(.small)
                }
                Text(hasCurrentReport ? "留空会直接解释当前检查。" : "没有检查报告时，直接用文字描述你的问题。")
                Spacer()
                Text("\(question.count)/2000")
                    .foregroundStyle(question.count > 2_000 ? Color.red : Color.secondary)
            }
            .font(.caption2)

            privacyNotice
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
        .onAppear { installReturnKeyMonitor() }
        .onDisappear { removeReturnKeyMonitor() }
    }

    /// 消息列表：高度随内容增长（160…380），内部滚动；对话为空时给出快捷问题。
    private var messageList: some View {
        ScrollViewReader { reader in
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if conversation.isEmpty {
                        Text("可以点一个常见问题，或直接在下方输入。")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        promptGrid
                    }
                    conversationSection
                    Color.clear
                        .frame(height: 1)
                        .id("conversationBottom")
                        // 底部锚点在可视范围内才算「在底部附近」
                        .onAppear { isNearBottom = true }
                        .onDisappear { isNearBottom = false }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
                .animation(.easeOut(duration: 0.2), value: conversation.count)
                .background(
                    GeometryReader { proxy in
                        Color.clear.preference(key: AIChatContentHeightKey.self, value: proxy.size.height)
                    }
                )
            }
            .frame(height: messageListHeight)
            .animation(.easeOut(duration: 0.2), value: messageListHeight)
            .background(Color(NSColor.textBackgroundColor))
            .cornerRadius(6)
            .onPreferenceChange(AIChatContentHeightKey.self) { contentHeight in
                messageListHeight = min(380, max(160, contentHeight))
            }
            .onChange(of: isWorking) { _ in
                scrollToBottomIfNeeded(reader)
            }
            .onChange(of: conversation.count) { _ in
                scrollToBottomIfNeeded(reader)
            }
        }
    }

    /// 自动滚动策略：用户本来就在底部附近、或刚发出新提问（最后一轮还没回答）时才滚到底部，
    /// 避免用户往上翻历史时被拽回去。
    private func scrollToBottomIfNeeded(_ reader: ScrollViewProxy) {
        let justSentQuestion = conversation.last?.result == nil && !conversation.isEmpty
        guard isNearBottom || justSentQuestion else { return }
        withAnimation {
            reader.scrollTo("conversationBottom", anchor: .bottom)
        }
    }

    /// 没有新鲜报告时的精简提示：仍然可以通用问答，也可以先跑检查。
    private var noReportBanner: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "doc.text.magnifyingglass")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text("还没有当前检查报告")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Text("先描述问题，或先检查网络让 AI 结合报告回答。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button("检查当前网络", action: onRunCheck)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
            Spacer()
        }
        .padding(10)
        .background(Color(NSColor.windowBackgroundColor))
        .cornerRadius(8)
    }

    private var aiAvailability: some View {
        HStack(alignment: .top, spacing: 8) {
            if isAIStatusLoading {
                ProgressView()
                    .controlSize(.small)
            } else {
                Image(systemName: hasCloudAI ? "checkmark.circle.fill" : "info.circle")
                    .foregroundStyle(hasCloudAI ? Color.green : Color.secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(hasCloudAI ? "AI 已就绪" : "当前使用 Netfix 本地解释")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Text(availabilityDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
    }

    private var availabilityDetail: String {
        if isAIStatusLoading { return "正在读取本机 AI 设置…" }
        if hasCloudAI {
            let providers = providerLabels.isEmpty ? "已配置的 AI" : providerLabels.joined(separator: "、")
            return "将由\(providers)解释脱敏后的当前检查。"
        }
        return "没有云端 AI 也能看本地解释；需要更自然的回答时，到 AI 设置里选择供应商并填写 AI 密钥。"
    }

    /// 输入行：回形针加截图 + 输入框 + 发送按钮。
    private var composerRow: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if hasCloudAI && imageQuestionEnabled {
                Button {
                    pickImages()
                } label: {
                    Image(systemName: "paperclip")
                }
                .buttonStyle(.borderless)
                .disabled(isWorking || images.count >= 3)
                .help("添加截图")
                .accessibilityLabel("添加截图")
            }
            ZStack(alignment: .topLeading) {
                TextEditor(text: $question)
                    .focused(composerFocused)
                    .frame(height: 44)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.18), lineWidth: 1)
                    )
                    .accessibilityLabel("还想问什么")
                if question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(hasCurrentReport ? context.placeholder : "描述你的网络问题，例如：家里 Wi-Fi 很慢、某个 App 打不开…")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 8)
                        .allowsHitTesting(false)
                }
            }
            Button(conversation.isEmpty ? "发送并解释" : "继续追问") {
                send()
            }
            .buttonStyle(.borderedProminent)
            .disabled(isWorking || sendDisabled)
        }
    }

    private var promptGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 136), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(context.prompts, id: \.self) { prompt in
                Button(prompt) {
                    question = prompt
                    composerFocused.wrappedValue = true
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(isWorking)
            }
        }
    }

    /// 已选截图的缩略图行；添加按钮在输入行左侧（回形针）。
    @ViewBuilder
    private var attachmentPicker: some View {
        if hasCloudAI && imageQuestionEnabled && !images.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Button("清空") {
                        images.removeAll()
                    }
                    .disabled(isWorking)

                    Spacer()
                    Text("\(images.count)/3")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

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
        }
    }

    private var privacyNotice: some View {
        Text(privacyDetail)
            .font(.caption2)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var privacyDetail: String {
        if !hasCloudAI || uploadConsent == "never" {
            return "这只影响 AI 看报告，不影响检查网络、使用代理或恢复网络设置。当前不会把报告发到云端。"
        }
        if images.isEmpty {
            return "问题和检查报告会先脱敏，代理密码不会发送。AI 只负责解释，不能更改网络设置。"
        }
        return "问题和检查报告会先脱敏。截图只移除文件元数据，图中可见文字和内容仍会发送给\(providerSummary)。"
    }

    private var providerSummary: String {
        providerLabels.isEmpty ? "已配置的 AI" : providerLabels.joined(separator: "、")
    }

    private var sendDisabled: Bool {
        // 没有报告时不能只发空问题；有报告时留空表示直接解释当前检查
        let emptyWithoutReport = !hasCurrentReport && question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return question.count > 2_000 || emptyWithoutReport
    }

    private func send() {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        let dataURLs = images.map(\.dataURL)
        // 「总是允许」且不带截图时直接确认；其余情况由后端回 needs_upload_confirmation 后在对话里内联确认
        let confirmed = uploadConsent == "always" && dataURLs.isEmpty
        pendingUpload = PendingUpload(question: text, images: dataURLs)
        onSend(text, dataURLs, confirmed)
        // 追问是真多轮：发出后清空输入框和截图，准备下一轮
        question = ""
        images = []
        // 发送后保持输入焦点，可以接着敲下一句
        composerFocused.wrappedValue = true
    }

    // MARK: - 回车发送（Return 发送、Shift+Return 换行）

    /// macOS 13 没有 onKeyPress：用本地事件监听，仅在输入框聚焦时拦截 Return 并吞掉事件。
    private func installReturnKeyMonitor() {
        guard returnKeyMonitor == nil else { return }
        returnKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            guard event.keyCode == 36, !event.modifierFlags.contains(.shift) else { return event }
            guard composerFocused.wrappedValue, !isWorking, !sendDisabled else { return event }
            send()
            return nil
        }
    }

    private func removeReturnKeyMonitor() {
        if let returnKeyMonitor {
            NSEvent.removeMonitor(returnKeyMonitor)
            self.returnKeyMonitor = nil
        }
    }

    /// 多轮对话流：每一轮是用户提问 + AI/本地回答卡片，追问不再覆盖旧答案。
    @ViewBuilder
    private var conversationSection: some View {
        // P1-A.3: 顶部插入 session 恢复横幅（仅在 conversation 为空且发现历史 session 时显示）。
        if conversation.isEmpty, !recoverableSessions.isEmpty, showSessionRecovery {
            SessionRecoveryBanner(
                sessions: recoverableSessions,
                onResume: { session in
                    showSessionRecovery = false
                    onResumeSession?(session)
                },
                onStartNew: {
                    showSessionRecovery = false
                },
                onDismiss: {
                    showSessionRecovery = false
                }
            )
        }

        // P1-B.1: 主动告警卡片，插入对话流顶部。
        if !proactiveAlerts.isEmpty {
            ProactiveAlertList(
                alerts: proactiveAlerts,
                onDismiss: { alert in onDismissAlert?(alert) },
                onActNow: { alert, action in onActOnAlert?(alert, action) },
                onIgnore: { alert in onIgnoreAlert?(alert) }
            )
        }

        ForEach(conversation) { turn in
            VStack(alignment: .leading, spacing: 8) {
                if !turn.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "person.circle.fill")
                            .foregroundStyle(.secondary)
                            .accessibilityHidden(true)
                        Text(turn.question)
                            .font(.callout)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)
                    }
                }
                if let result = turn.result {
                    planCard(for: result)
                    observationCard(for: result)
                    answerCard(result)
                    if let request = result.confirmationRequest,
                       !dismissedUploadConfirmation.contains(turn.id),
                       !dontAskCategoriesThisSession.contains(request.category) {
                        confirmationBubble(for: turn, request: request)
                    } else if result.needsUploadConfirmation == true && result.confirmationRequest == nil
                                && !dismissedUploadConfirmation.contains(turn.id) {
                        uploadConfirmationBubble(for: turn)
                    }
                } else {
                    HStack(spacing: 8) {
                        TypingDotsView()
                        Text("正在解释…")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            // 新一轮对话出现时轻轻浮入，避免生硬闪烁
            .transition(.opacity.combined(with: .move(edge: .bottom)))
        }

        if let errorMessage, !errorMessage.isEmpty {
            Label(errorMessage, systemImage: "exclamationmark.circle")
                .font(.caption)
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
        }

        if let attachmentError, !attachmentError.isEmpty {
            Label(attachmentError, systemImage: "photo.badge.exclamationmark")
                .font(.caption)
                .foregroundStyle(.red)
        }
    }

    /// P0-A.2 plan/act/observe：plan 步骤条，让用户看到 AI 准备做什么。
    @ViewBuilder
    private func planCard(for result: LLMExplainResult) -> some View {
        let steps = result.planSteps ?? []
        if steps.isEmpty {
            EmptyView()
        } else {
            planCardContent(steps: steps)
        }
    }

    private func planCardContent(steps: [ChatStep]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("AI 准备做的步骤", systemImage: "list.bullet.rectangle")
                .font(.caption)
                .fontWeight(.semibold)
            // P0-A.4 增强：currentStep 高亮（动画）+ StepStatus 枚举
            ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                ChatStepCard(
                    step: step,
                    isCurrent: isCurrentStep(step: step, index: index, steps: steps)
                )
            }
        }
        .padding(8)
        .background(Color.blue.opacity(0.06))
        .cornerRadius(6)
    }

    /// 判断当前 step：找到第一个 running 或第一个还没 ok 的。
    private func isCurrentStep(step: ChatStep, index: Int, steps: [ChatStep]) -> Bool {
        let status = StepStatus(raw: step.status)
        if status == .running { return true }
        let hasRunning = steps.contains { StepStatus(raw: $0.status) == .running }
        if hasRunning { return false }
        let firstPendingIndex = steps.firstIndex { StepStatus(raw: $0.status) == .pending }
        if let pendingIndex = firstPendingIndex {
            return index == pendingIndex
        }
        let firstUnfinishedIndex = steps.firstIndex {
            let s = StepStatus(raw: $0.status)
            return s != .ok && s != .cancelled
        }
        if let unfinishedIndex = firstUnfinishedIndex {
            return index == unfinishedIndex
        }
        return false
    }

    /// P0-A.2 observation：本地规则或 LLM 观察到的事实链。
    @ViewBuilder
    private func observationCard(for result: LLMExplainResult) -> some View {
        let observations = result.observations ?? []
        if observations.isEmpty {
            EmptyView()
        } else {
            observationCardContent(observations: observations)
        }
    }

    private func observationCardContent(observations: [ChatObservation]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("当前观察", systemImage: "eye")
                .font(.caption)
                .fontWeight(.semibold)
            ForEach(observations) { item in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "circle.fill")
                        .font(.system(size: 4))
                        .foregroundStyle(.secondary)
                        .padding(.top, 6)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.fact)
                            .font(.caption)
                            .fixedSize(horizontal: false, vertical: true)
                        if let confidence = item.confidence, confidence > 0 {
                            Text("置信度 \(Int(confidence * 100))%")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding(8)
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(6)
    }

    private func stepIcon(for status: String?) -> String {
        switch status {
        case "running": return "arrow.triangle.2.circlepath"
        case "ok": return "checkmark.circle.fill"
        case "error": return "xmark.octagon.fill"
        case "cancelled": return "minus.circle"
        default: return "circle"
        }
    }

    private func stepColor(for status: String?) -> Color {
        switch status {
        case "ok": return .green
        case "running": return .blue
        case "error": return .red
        default: return .secondary
        }
    }

    /// P0-A.3: 通用 confirmation_request 气泡，覆盖 upload / system_fix / node switch 等。
    /// P1-A.3 增强：替换为通用 ConfirmationRequestBubble，支持「这次不再问同会话」复选框
    /// + change_system_setting / switch_proxy_node 徽章。
    @ViewBuilder
    private func confirmationBubble(for turn: AIChatTurn, request: ConfirmationRequest) -> some View {
        ConfirmationRequestBubble(
            request: request,
            onConfirm: {
                confirmAction(for: turn, request: request)
            },
            onCancel: {
                dismissedUploadConfirmation.insert(turn.id)
            },
            onToggleDontAskAgain: { dontAsk in
                if dontAsk {
                    // 标记这次 session 不再问同 category 的 confirmation
                    dontAskCategoriesThisSession.insert(request.category)
                    dismissedUploadConfirmation.insert(turn.id)
                } else {
                    dontAskCategoriesThisSession.remove(request.category)
                }
            }
        )
    }

    private func confirmationIcon(for category: String) -> String {
        switch category {
        case "upload_redacted_report", "upload_image": return "lock.shield"
        case "switch_proxy_node": return "arrow.triangle.swap"
        case "disable_ipv6": return "network.badge.shield.half.filled"
        case "flush_dns": return "arrow.clockwise.circle"
        default: return "wrench.and.screwdriver"
        }
    }

    private func confirmationColor(for category: String) -> Color {
        switch category {
        case "upload_redacted_report", "upload_image": return .purple
        case "switch_proxy_node": return .blue
        case "disable_ipv6": return .orange
        default: return .orange
        }
    }

    private func confirmAction(for turn: AIChatTurn, request: ConfirmationRequest) {
        dismissedUploadConfirmation.insert(turn.id)
        // 上传类：重发同一问题，uploadConfirmed=true
        if request.category == "upload_redacted_report" || request.category == "upload_image" {
            if let pending = pendingUpload, turn.id == conversation.last?.id {
                onSend(pending.question, pending.images, true)
            } else {
                onSend(turn.question, [], true)
            }
            pendingUpload = nil
            return
        }
        // 修改类：直接调用主界面修复入口（DashboardViewModel 会弹 confirm + 跑 fix）
        if let action = firstTierAction(for: turn) {
            onRunAction(action)
        }
    }

    private func firstTierAction(for turn: AIChatTurn) -> Action? {
        guard let result = turn.result, let actions = result.actions else { return nil }
        return actions.first(where: { $0.tier >= 2 })
    }

    /// 需要上传确认时的内联气泡：确认后以 uploadConfirmed=true 重发同一问题。
    private func uploadConfirmationBubble(for turn: AIChatTurn) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("需要把脱敏后的报告发给 AI 供应商，确认发送？", systemImage: "lock.shield")
                .font(.caption)
                .fontWeight(.semibold)
                .fixedSize(horizontal: false, vertical: true)
            Text("问题和检查报告会先脱敏，代理密码不会发送。AI 只负责解释，不能更改网络设置。")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Button("确认发送") {
                    confirmUpload(for: turn)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                Button("取消", role: .cancel) {
                    dismissedUploadConfirmation.insert(turn.id)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(10)
        .background(Color.purple.opacity(0.08))
        .cornerRadius(8)
    }

    private func confirmUpload(for turn: AIChatTurn) {
        dismissedUploadConfirmation.insert(turn.id)
        // 重发同一问题：pendingUpload 保存了刚发出的原文和截图；对不上时只重发文字
        if let pending = pendingUpload, turn.id == conversation.last?.id {
            onSend(pending.question, pending.images, true)
        } else {
            onSend(turn.question, [], true)
        }
        pendingUpload = nil
    }

    private func answerCard(_ result: LLMExplainResult) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(result.source == "llm" ? "AI 解释" : "Netfix 本地解释", systemImage: result.source == "llm" ? "sparkles" : "checklist.checked")
                .font(.headline)
            if let headline = result.headline, !headline.isEmpty {
                Text(headline)
                    .font(.subheadline)
                    .fontWeight(.semibold)
            }
            if let explanation = result.explanation, !explanation.isEmpty {
                Text(explanation)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            actionButtons(for: result)
            manualStepsList(for: result)
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
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .padding(.top, 4)
            }
            .font(.caption)
        }
        .padding(12)
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(8)
    }

    /// AI 建议的修复动作：低风险的直接给按钮，走主界面同一执行路径；会更改系统设置的只展示说明。
    @ViewBuilder
    private func actionButtons(for result: LLMExplainResult) -> some View {
        if let actions = result.actions, !actions.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(actions) { action in
                    if action.tier >= 2 {
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "hand.raised")
                                .font(.caption)
                                .foregroundStyle(.orange)
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(action.label)
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                Text("会更改系统网络设置，请在主界面确认后执行。")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                if let reason = action.reason, !reason.isEmpty {
                                    Text(reason)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 2) {
                            Button {
                                onRunAction(action)
                            } label: {
                                Label(action.label, systemImage: "wrench.and.screwdriver")
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .disabled(isWorking)
                            if let reason = action.reason, !reason.isEmpty {
                                Text(reason)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
    }

    /// 只能手动完成的步骤清单。
    @ViewBuilder
    private func manualStepsList(for result: LLMExplainResult) -> some View {
        if let steps = result.manualSteps, !steps.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("手动步骤")
                    .font(.caption)
                    .fontWeight(.semibold)
                ForEach(steps) { step in
                    VStack(alignment: .leading, spacing: 2) {
                        if let description = step.description, !description.isEmpty {
                            Text("• \(description)")
                        }
                        if let substeps = step.steps, !substeps.isEmpty {
                            ForEach(Array(substeps.enumerated()), id: \.offset) { index, substep in
                                Text("\(index + 1). \(substep)")
                            }
                        }
                    }
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func providerDisplayName(_ provider: String?) -> String? {
        switch provider {
        case "deepseek": return "DeepSeek"
        case "moonshot_kimi": return "Kimi"
        case "minimax": return "MiniMax"
        case "qwen": return "Qwen"
        case "openai": return "OpenAI"
        case "anthropic": return "Anthropic"
        case let value?: return value
        case nil: return nil
        }
    }

    private func friendlyLLMReason(_ reason: String?) -> String? {
        guard let reason, !reason.isEmpty else { return nil }
        switch reason {
        case "llm_disabled": return "云端 AI 未启用，已使用本地解释。"
        case "missing_api_key", "no_provider_available": return "没有可用的 AI 密钥，已使用本地解释。"
        case "upload_consent_required": return "未获得发送确认，已使用本地解释。"
        default: return reason
        }
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
                        attachmentError = "\(url.lastPathComponent) 太大，请选择 4.5MB 以内的图片。"
                        continue
                    }
                    let mime = mimeType(for: url)
                    guard allowedImageMimeTypes.contains(mime) else {
                        attachmentError = "\(url.lastPathComponent) 只支持 PNG、JPEG、WebP 或 GIF。"
                        continue
                    }
                    let dataURL = "data:\(mime);base64,\(data.base64EncodedString())"
                    next.append(AIQuestionImage(name: url.lastPathComponent, dataURL: dataURL, preview: NSImage(contentsOf: url)))
                    attachmentError = nil
                } catch {
                    attachmentError = "无法读取 \(url.lastPathComponent)：\(error.localizedDescription)"
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


// MARK: - 消息列表内容高度

/// 消息列表内容高度的 PreferenceKey：列表高度随内容增长，夹在 160…380 之间。
private struct AIChatContentHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 160

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

// MARK: - 「正在解释…」跳点动画

/// 等待 AI 回答时的三个跳点，轻量循环动画。
private struct TypingDotsView: View {
    @State private var animating = false

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(Color.secondary)
                    .frame(width: 4, height: 4)
                    .opacity(animating ? 1.0 : 0.25)
                    .animation(
                        .easeInOut(duration: 0.5)
                            .repeatForever(autoreverses: true)
                            .delay(Double(index) * 0.15),
                        value: animating
                    )
            }
        }
        .onAppear { animating = true }
        .accessibilityHidden(true)
    }
}
