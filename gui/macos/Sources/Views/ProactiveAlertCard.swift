import SwiftUI

// MARK: - P1-B.1: ProactiveAlertCard

/// 4 类告警不同图标 + dismiss / 立即处理 / 这次忽略 三个按钮。
/// 插入 AIChatView 对话流顶部。
struct ProactiveAlertCard: View {
    let alert: ProactiveAlert
    let onDismiss: () -> Void
    let onActNow: (String) -> Void
    let onIgnore: () -> Void

    private var severityColor: Color {
        switch alert.severity?.lowercased() {
        case "fail", "high", "critical": return .red
        case "warn", "medium": return .orange
        case "info", "low": return .blue
        default: return .secondary
        }
    }

    private var firstSuggestedAction: String? {
        alert.suggestedActions?.first
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: alert.icon)
                    .foregroundStyle(severityColor)
                    .font(.callout)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(alert.localizedTitle)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(severityColor)
                    if let detail = alert.detail, !detail.isEmpty {
                        Text(detail)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 0)
            }

            // evidence 摘要：把关键字段拎出来
            if let evidence = alert.evidence,
               let summary = evidence["summary"]?.stringValue {
                Text(summary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 8) {
                if let action = firstSuggestedAction {
                    Button {
                        onActNow(action)
                    } label: {
                        Label("立即处理", systemImage: "bolt.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }
                Button("这次忽略", action: onIgnore)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                Button("关闭", role: .cancel, action: onDismiss)
                    .buttonStyle(.borderless)
                    .controlSize(.small)
                Spacer(minLength: 0)
            }
        }
        .padding(10)
        .background(severityColor.opacity(0.08))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(severityColor.opacity(0.25), lineWidth: 1)
        )
    }
}

/// 容器：顶部一组 ProactiveAlert 列表。
struct ProactiveAlertList: View {
    let alerts: [ProactiveAlert]
    let onDismiss: (ProactiveAlert) -> Void
    let onActNow: (ProactiveAlert, String) -> Void
    let onIgnore: (ProactiveAlert) -> Void

    var body: some View {
        if alerts.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "bell.badge")
                        .foregroundStyle(.secondary)
                    Text("主动提醒")
                        .font(.caption)
                        .fontWeight(.semibold)
                    Spacer()
                }
                ForEach(alerts) { alert in
                    ProactiveAlertCard(
                        alert: alert,
                        onDismiss: { onDismiss(alert) },
                        onActNow: { action in onActNow(alert, action) },
                        onIgnore: { onIgnore(alert) }
                    )
                }
            }
        }
    }
}