import SwiftUI

// MARK: - P0-A.4 增强：ChatStepCard + StepStatus

/// P0-A.4: 把单条 plan step 抽成独立卡片。
/// 后续增强：currentStep 高亮（动画）、StepStatus 枚举显示不同图标/颜色。
enum StepStatus: String, Equatable {
    case pending
    case running
    case ok
    case timeout
    case error
    case cancelled
    case unknown

    init(raw: String?) {
        switch raw {
        case "pending": self = .pending
        case "running": self = .running
        case "ok", "success", "done": self = .ok
        case "timeout": self = .timeout
        case "error", "fail", "failed": self = .error
        case "cancelled", "canceled": self = .cancelled
        default: self = .unknown
        }
    }

    var icon: String {
        switch self {
        case .pending: return "circle"
        case .running: return "arrow.triangle.2.circlepath"
        case .ok: return "checkmark.circle.fill"
        case .timeout: return "clock.badge.exclamationmark"
        case .error: return "xmark.octagon.fill"
        case .cancelled: return "minus.circle"
        case .unknown: return "questionmark.circle"
        }
    }

    var color: Color {
        switch self {
        case .pending: return .secondary
        case .running: return .blue
        case .ok: return .green
        case .timeout: return .orange
        case .error: return .red
        case .cancelled: return .secondary
        case .unknown: return .secondary
        }
    }

    var label: String {
        switch self {
        case .pending: return "等待"
        case .running: return "进行中"
        case .ok: return "完成"
        case .timeout: return "超时"
        case .error: return "失败"
        case .cancelled: return "已取消"
        case .unknown: return "未知"
        }
    }
}

struct ChatStepCard: View {
    let step: ChatStep
    let isCurrent: Bool

    private var status: StepStatus { StepStatus(raw: step.status) }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: status.icon)
                .font(.caption)
                .foregroundStyle(status.color)
                .frame(width: 18)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(step.label ?? step.tool)
                        .font(.caption)
                        .fontWeight(isCurrent ? .semibold : .regular)
                    if isCurrent {
                        Text("当前")
                            .font(.caption2)
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.blue.opacity(0.14))
                            .cornerRadius(4)
                    }
                    Text(status.label)
                        .font(.caption2)
                        .foregroundStyle(status.color)
                }
                if let why = step.why, !why.isEmpty {
                    Text(why)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 6)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isCurrent ? Color.blue.opacity(0.08) : Color.clear)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isCurrent ? Color.blue.opacity(0.35) : Color.clear, lineWidth: 1)
        )
        .animation(.easeInOut(duration: 0.25), value: isCurrent)
    }
}

// MARK: - 通用化 ConfirmationRequestBubble

/// P0-A.3 通用 confirmation bubble：
/// - 上传类（upload_redacted_report / upload_image）保持现有紫色样式；
/// - 系统变更类（change_system_setting）显示「会修改：系统代理 / 路由表 / DNS」徽章；
/// - 节点切换类（switch_proxy_node）显示节点相关徽章。
/// 增加「这次不再问同会话」复选框。
struct ConfirmationRequestBubble: View {
    let request: ConfirmationRequest
    let onConfirm: () -> Void
    let onCancel: () -> Void
    let onToggleDontAskAgain: (Bool) -> Void

    @State private var dontAskAgain: Bool = false

    private var kind: ConfirmationRequest.Kind { request.kind }

    private var icon: String {
        switch kind {
        case .uploadRedactedReport, .uploadImage: return "lock.shield"
        case .changeSystemSetting: return "gear.badge.questionmark"
        case .switchProxyNode: return "arrow.triangle.swap"
        case .unknown: return "wrench.and.screwdriver"
        }
    }

    private var tint: Color {
        switch kind {
        case .uploadRedactedReport, .uploadImage: return .purple
        case .changeSystemSetting: return .orange
        case .switchProxyNode: return .blue
        case .unknown: return .gray
        }
    }

    private var surfaces: [String] { request.affectedSurfaces }

    private var confirmLabel: String {
        switch kind {
        case .uploadRedactedReport, .uploadImage: return "确认发送"
        case .changeSystemSetting: return "确认执行"
        case .switchProxyNode: return "确认切换"
        case .unknown: return "确认"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .foregroundStyle(tint)
                    .accessibilityHidden(true)
                Text(request.summary)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !request.impact.isEmpty {
                Text(request.impact)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            // P1-A.3: 系统变更类展示「会修改：系统代理 / 路由表 / DNS」徽章
            if !surfaces.isEmpty {
                HStack(spacing: 4) {
                    Text("会修改：")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(surfaces, id: \.self) { surface in
                        Text(surface)
                            .font(.caption2)
                            .foregroundStyle(tint)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(tint.opacity(0.12))
                            .cornerRadius(4)
                    }
                }
            }

            if let previewAction = request.preview?["action_id"]?.stringValue {
                Text("将执行：\(previewAction)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            Toggle("这次不再问同会话", isOn: $dontAskAgain)
                .font(.caption2)
                .toggleStyle(.checkbox)
                .onChange(of: dontAskAgain) { newValue in
                    onToggleDontAskAgain(newValue)
                }

            HStack(spacing: 8) {
                Button(confirmLabel, action: onConfirm)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                Button("取消", role: .cancel, action: onCancel)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .padding(10)
        .background(tint.opacity(0.08))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(tint.opacity(0.18), lineWidth: 1)
        )
    }
}

// MARK: - P1-A.3: EvidenceChainPanel（折叠面板）

/// 展示「为什么判断这个根因」：root_cause_id / confidence / key_diagnostics[] / observations[]。
struct EvidenceChainPanel: View {
    let chain: EvidenceChain
    @State private var isExpanded: Bool = false

    private var confidencePercent: Int {
        Int(((chain.confidence ?? 0) * 100).rounded())
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            DisclosureGroup(isExpanded: $isExpanded) {
                evidenceContent
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "checklist")
                        .foregroundStyle(.secondary)
                    Text("证据链")
                        .font(.caption)
                        .fontWeight(.semibold)
                    if let id = chain.rootCauseID {
                        Text(id)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.12))
                            .cornerRadius(4)
                    }
                    if let confidence = chain.confidence, confidence > 0 {
                        Text("置信度 \(confidencePercent)%")
                            .font(.caption2)
                            .foregroundStyle(confidence >= 0.7 ? .green : (confidence >= 0.4 ? .orange : .secondary))
                    }
                    Spacer()
                }
            }
            .font(.caption)
        }
        .padding(8)
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(6)
    }

    @ViewBuilder
    private var evidenceContent: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let desc = chain.rootCauseDescription, !desc.isEmpty {
                Text(desc)
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !chain.keyDiagnostics.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("关键诊断")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(chain.keyDiagnostics, id: \.self) { key in
                        Text("• \(key)")
                            .font(.caption2)
                    }
                }
            }
            if !chain.observations.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("观察")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(chain.observations) { observation in
                        HStack(alignment: .top, spacing: 4) {
                            Image(systemName: "circle.fill")
                                .font(.system(size: 4))
                                .foregroundStyle(.secondary)
                                .padding(.top, 6)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(observation.fact)
                                    .font(.caption2)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let confidence = observation.confidence, confidence > 0 {
                                    Text("置信度 \(Int(confidence * 100))%")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(.top, 4)
    }
}

// MARK: - P1-A.3: SessionRecoveryBanner

/// AIChatView 出现时如果发现历史 session，提示「恢复上次对话吗？」
struct SessionRecoveryBanner: View {
    let sessions: [ChatSession]
    let onResume: (ChatSession) -> Void
    let onStartNew: () -> Void
    let onDismiss: () -> Void

    private var latest: ChatSession? { sessions.first }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "clock.arrow.circlepath")
                .foregroundStyle(.blue)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text("发现上次还没结束的对话")
                    .font(.caption)
                    .fontWeight(.semibold)
                if let latest {
                    Text(latest.title ?? "未命名会话")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                HStack(spacing: 8) {
                    if let latest {
                        Button("恢复") {
                            onResume(latest)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                    }
                    Button("开新对话", action: onStartNew)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    Button("忽略", role: .cancel, action: onDismiss)
                        .buttonStyle(.borderless)
                        .controlSize(.small)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(Color.blue.opacity(0.06))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.blue.opacity(0.20), lineWidth: 1)
        )
    }
}

// MARK: - P1-B.1: RollbackButton

/// DashboardView 修复成功页加「撤销此修复」按钮。
/// 走 POST /proxy/profiles/rollback 或 POST /chat/sessions/{id}/decide。
struct RollbackButton: View {
    let isAvailable: Bool
    let onRollback: () -> Void
    let isWorking: Bool

    var body: some View {
        Button {
            onRollback()
        } label: {
            Label("撤销此修复", systemImage: "arrow.uturn.backward.circle")
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .disabled(!isAvailable || isWorking)
        .help(isAvailable ? "恢复到修复之前的网络设置" : "当前没有可撤销的修复")
    }
}