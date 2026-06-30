import SwiftUI

/// 状态徽章视图，用于状态卡片中显示图标 + 状态文字。
/// 同时满足「不能只靠颜色」的可访问性要求。
struct StatusIconView: View {
    let status: DiagnosticStatus
    let label: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: iconName)
                .foregroundStyle(color)
            Text(label)
                .font(.caption)
                .foregroundStyle(color)
        }
    }

    private var iconName: String {
        switch status {
        case .ok: return "checkmark.circle.fill"
        case .warn: return "exclamationmark.triangle.fill"
        case .fail: return "xmark.shield.fill"
        case .unknown: return "questionmark.circle.fill"
        }
    }

    private var color: Color {
        switch status {
        case .ok: return .green
        case .warn: return .orange
        case .fail: return .red
        case .unknown: return .secondary
        }
    }
}


