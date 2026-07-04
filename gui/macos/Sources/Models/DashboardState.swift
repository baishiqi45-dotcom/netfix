import Foundation
import SwiftUI

/// One of six user-facing states shown on the home screen.
/// Matches the keys resolved by `netfix/dashboard_state.py`.
enum DashboardUIState: String, CaseIterable {
    case noProxy = "no_proxy"
    case proxySaved = "proxy_saved"
    case proxyInUse = "proxy_in_use"
    case proxyDegraded = "proxy_degraded"
    case networkRecovery = "network_recovery"
    case ready

    var headline: String {
        switch self {
        case .noProxy:        return "还没有粘贴代理参数"
        case .proxySaved:     return "代理已保存到这台 Mac，但还没开始使用"
        case .proxyInUse:     return "正在通过 Netfix 使用代理上网"
        case .proxyDegraded:  return "代理还在用，但刚才一次检测没通过"
        case .networkRecovery: return "系统网络需要恢复"
        case .ready:          return "网络看起来正常"
        }
    }

    var nextStep: String {
        switch self {
        case .noProxy:        return "点下方「粘贴代理参数」，把服务商后台给的那一行粘进来。"
        case .proxySaved:     return "点「开始使用这台 Mac 上网」，Netfix 会先备份当前网络设置再帮你切。"
        case .proxyInUse:     return "后台健康监控会持续检查；出问题时 Netfix 会主动提示。"
        case .proxyDegraded:  return "点「一键诊断」看哪一项失败；常见原因是节点挂了或账号临时失效。"
        case .networkRecovery: return "到「部署代理 → 更多 → 恢复原来的网络设置」点恢复；不想恢复也可以直接退出 App。"
        case .ready:          return "保持现状即可；想再确认一次就点「一键诊断」。"
        }
    }

    var iconName: String {
        switch self {
        case .noProxy:        return "tray"
        case .proxySaved:     return "tray.and.arrow.down.fill"
        case .proxyInUse:     return "checkmark.shield.fill"
        case .proxyDegraded:  return "exclamationmark.triangle.fill"
        case .networkRecovery: return "arrow.uturn.backward.circle.fill"
        case .ready:          return "checkmark.circle.fill"
        }
    }

    var tintColor: Color {
        switch self {
        case .noProxy:        return .secondary
        case .proxySaved:     return .blue
        case .proxyInUse:     return .green
        case .proxyDegraded:  return .orange
        case .networkRecovery: return .red
        case .ready:          return .green
        }
    }
}

/// Decoded payload from GET /dashboard/state.
struct DashboardStateResponse: Decodable {
    struct StateBlock: Decodable {
        let state: String
        let headline: String
        let nextStep: String
        let icon: String?
        let color: String?
        let savedProfileCount: Int?
        let bridgeInUse: Bool?
        let bridgeNeedsRecovery: Bool?

        enum CodingKeys: String, CodingKey {
            case state
            case headline
            case nextStep = "next_step"
            case icon
            case color
            case savedProfileCount = "saved_profile_count"
            case bridgeInUse = "bridge_in_use"
            case bridgeNeedsRecovery = "bridge_needs_recovery"
        }
    }

    let ok: Bool
    let state: StateBlock
    let savedProfileCount: Int?

    enum CodingKeys: String, CodingKey {
        case ok
        case state
        case savedProfileCount = "saved_profile_count"
    }

    var uiState: DashboardUIState {
        DashboardUIState(rawValue: state.state) ?? .ready
    }
}