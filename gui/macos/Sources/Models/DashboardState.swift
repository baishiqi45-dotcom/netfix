import Foundation
import SwiftUI

enum DashboardActionTarget: Equatable {
    case proxySetup
    case doctor
    case staleBridgeRecovery
    case none
    case unsupported(String)

    var canonicalValue: String {
        switch self {
        case .proxySetup:
            return "flow:proxy_setup"
        case .doctor:
            return "run:doctor"
        case .staleBridgeRecovery:
            return "recover:stale_bridge"
        case .none:
            return "none"
        case .unsupported(let value):
            return value
        }
    }

    static func resolve(target: String?, actionID: String?) -> DashboardActionTarget {
        let normalized = target?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()

        switch normalized {
        case "flow:proxy_setup", "settings:proxy", "flow:proxy", "proxy:setup", "proxy_setup":
            return .proxySetup
        case "run:doctor", "run:diagnose", "check:network", "doctor", "diagnose":
            return .doctor
        case "recover:stale_bridge", "recover:system_proxy", "restore:system_proxy", "rollback:system_proxy", "stale_bridge:recover":
            return .staleBridgeRecovery
        case "none", "noop", "no-op":
            return .none
        case .some(let value) where !value.isEmpty:
            return .unsupported(value)
        default:
            break
        }

        switch actionID?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "paste_proxy", "start_saved_proxy":
            return .proxySetup
        case "verify_current_proxy", "diagnose":
            return .doctor
        case "recover_system_proxy", "stop_and_restore":
            return .staleBridgeRecovery
        case "none":
            return .none
        case .some(let value) where !value.isEmpty:
            return .unsupported(value)
        default:
            return .none
        }
    }
}

/// One of six user-facing states shown on the home screen.
/// Matches the keys resolved by `netfix/dashboard_state.py`.
enum DashboardUIState: String, CaseIterable {
    case noProxy = "no_proxy"
    case proxySaved = "proxy_saved"
    case proxyInUse = "proxy_in_use"
    case proxyDegraded = "proxy_degraded"
    case networkRecovery = "network_recovery"
    case ready
    case unknown

    var headline: String {
        switch self {
        case .noProxy:        return "还没有粘贴代理参数"
        case .proxySaved:     return "代理已保存到这台 Mac，但还没开始使用"
        case .proxyInUse:     return "正在使用代理上网"
        case .proxyDegraded:  return "代理还在用，但刚才一次检测没通过"
        case .networkRecovery: return "系统网络需要恢复"
        case .ready:          return "网络看起来正常"
        case .unknown:        return "暂时读不到当前网络状态"
        }
    }

    var nextStep: String {
        switch self {
        case .noProxy:        return "点「粘贴代理参数」，把服务商给的那一行粘进来。"
        case .proxySaved:     return "点「开始使用代理」。"
        case .proxyInUse:     return "Netfix 会持续检查网络状态；出问题时主动提示你。"
        case .proxyDegraded:  return "点「检查当前网络」看哪一项失败；常见原因是代理线路暂时不可用或账号临时失效。"
        case .networkRecovery: return "点「恢复原来的网络设置」；不想恢复也可以直接退出 App。"
        case .ready:          return "保持现状即可；想再确认一次就点「检查当前网络」。"
        case .unknown:        return "重新读取状态；如果仍无法读取，再检查当前网络。"
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
        case .unknown:        return "questionmark.circle.fill"
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
        case .unknown:        return .secondary
        }
    }
}

/// Decoded payload from GET /dashboard/state.
struct DashboardStateResponse: Decodable {
    struct Decision: Decodable {
        let uiState: String?
        let effectiveRoute: String?
        let severity: String?
        let primaryAction: String?
        let reasonCodes: [String]?
        let headline: String?
        let nextStep: String?
        let requiresConfirmation: Bool?

        enum CodingKeys: String, CodingKey {
            case uiState = "ui_state"
            case effectiveRoute = "effective_route"
            case severity
            case primaryAction = "primary_action"
            case reasonCodes = "reason_codes"
            case headline
            case nextStep = "next_step"
            case requiresConfirmation = "requires_confirmation"
        }
    }

    struct Verdict: Decodable {
        struct PrimaryAction: Decodable {
            let id: String?
            let label: String?
            let enabled: Bool?
            let target: String?
            let requiresConfirmation: Bool?

            enum CodingKeys: String, CodingKey {
                case id
                case label
                case enabled
                case target
                case requiresConfirmation = "requires_confirmation"
            }
        }

        struct Freshness: Decodable {
            let checkedAt: String?
            let ageSeconds: Int?
            let stale: Bool?

            enum CodingKeys: String, CodingKey {
                case checkedAt = "checked_at"
                case ageSeconds = "age_seconds"
                case stale
            }
        }

        let status: String?
        let severity: String?
        let usability: String?
        let routeHealth: String?
        let headline: String?
        let detail: String?
        let nextStep: String?
        let issueCount: Int?
        let blockingIssueCount: Int?
        let advisoryCount: Int?
        let diagnosticCounts: [String: Int]?
        let primaryAction: PrimaryAction?
        let secondaryAction: PrimaryAction?
        let freshness: Freshness?

        enum CodingKeys: String, CodingKey {
            case status
            case severity
            case usability
            case routeHealth = "route_health"
            case headline
            case detail
            case nextStep = "next_step"
            case issueCount = "issue_count"
            case blockingIssueCount = "blocking_issue_count"
            case advisoryCount = "advisory_count"
            case diagnosticCounts = "diagnostic_counts"
            case primaryAction = "primary_action"
            case secondaryAction = "secondary_action"
            case freshness
        }
    }

    struct Presentation: Decodable {
        struct SuppressedSection: Decodable {
            let id: String?
            let reason: String?
        }

        let visibleSections: [String]
        let collapsedSections: [String]
        let suppressedSections: [SuppressedSection]

        enum CodingKeys: String, CodingKey {
            case visibleSections = "visible_sections"
            case collapsedSections = "collapsed_sections"
            case suppressedSections = "suppressed_sections"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            self.visibleSections = try container.decodeIfPresent([String].self, forKey: .visibleSections) ?? []
            self.collapsedSections = try container.decodeIfPresent([String].self, forKey: .collapsedSections) ?? []
            self.suppressedSections = try container.decodeIfPresent([SuppressedSection].self, forKey: .suppressedSections) ?? []
        }
    }

    struct Machine: Decodable {
        let platform: String?
        let primaryInterface: String?
        let selfIPv4: String?
        let selfIPv6: [String]?
        let gateway: String?
        let hasIPv6DefaultRoute: Bool?

        enum CodingKeys: String, CodingKey {
            case platform
            case primaryInterface = "primary_interface"
            case selfIPv4 = "self_ipv4"
            case selfIPv6 = "self_ipv6"
            case gateway
            case hasIPv6DefaultRoute = "has_ipv6_default_route"
        }
    }

    struct Proxy: Decodable {
        struct Saved: Decodable {
            let count: Int?
            let selectedProfileID: String?

            enum CodingKeys: String, CodingKey {
                case count
                case selectedProfileID = "selected_profile_id"
            }
        }

        struct SystemProxy: Decodable {
            let active: Bool?
            let kind: String?
            let networkService: String?

            enum CodingKeys: String, CodingKey {
                case active
                case kind
                case networkService = "network_service"
            }
        }

        struct Bridge: Decodable {
            let lifecycleStatus: String?
            let inUse: Bool?
            let needsRecovery: Bool?
            let recoveryAvailable: Bool?
            let profileID: String?

            enum CodingKeys: String, CodingKey {
                case lifecycleStatus = "lifecycle_status"
                case inUse = "in_use"
                case needsRecovery = "needs_recovery"
                case recoveryAvailable = "recovery_available"
                case profileID = "profile_id"
            }
        }

        struct Applied: Decodable {
            let active: Bool?
            let owner: String?
            let profileID: String?
            let via: String?

            enum CodingKeys: String, CodingKey {
                case active
                case owner
                case profileID = "profile_id"
                case via
            }
        }

        struct Verified: Decodable {
            let status: String?
            let checkedAt: String?
            let source: String?

            enum CodingKeys: String, CodingKey {
                case status
                case checkedAt = "checked_at"
                case source
            }
        }

        let saved: Saved?
        // `system` is intentionally optional: a backend that has not yet been
        // able to read the Mac's system-proxy state must not crash the entire
        // dashboard decode path.
        let system: SystemProxy?
        let bridge: Bridge?
        let applied: Applied?
        let verified: Verified?
    }

    struct Egress: Decodable {
        let status: String?
        let publicIPv4: String?
        let isp: String?
        let asn: String?
        let ipType: String?
        let riskScore: Double?
        let sameAsLocal: Bool?
        let cached: Bool?
        let source: String?
        let checkedAt: String?

        enum CodingKeys: String, CodingKey {
            case status
            case publicIPv4 = "public_ipv4"
            case isp
            case asn
            case ipType = "ip_type"
            case riskScore = "risk_score"
            case sameAsLocal = "same_as_local"
            case cached
            case source
            case checkedAt = "checked_at"
        }
    }

    struct ConnectionQuality: Decodable {
        struct Metric: Decodable {
            let label: String
            let value: String
            let hint: String

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                label = try container.decodeIfPresent(String.self, forKey: .label) ?? "未测"
                value = try container.decodeIfPresent(String.self, forKey: .value) ?? "未采到"
                hint = try container.decodeIfPresent(String.self, forKey: .hint) ?? "本机未返回这项数据。"
            }

            private enum CodingKeys: String, CodingKey {
                case label
                case value
                case hint
            }
        }

        let status: String?
        let collectionState: String?
        let headline: String?
        let detail: String?
        // The four metrics below are intentionally optional: the backend may
        // report them as missing when no sample is available, and we must not
        // let a single missing metric take down the entire home-screen decode.
        let speed: Metric?
        let latency: Metric?
        let stability: Metric?
        let backgroundActivity: Metric?
        let checkedAt: String?
        let stale: Bool?
        let source: String?

        enum CodingKeys: String, CodingKey {
            case status
            case collectionState = "collection_state"
            case headline
            case detail
            case speed
            case latency
            case stability
            case backgroundActivity = "background_activity"
            case checkedAt = "checked_at"
            case stale
            case source
        }
    }

    struct LastReportSummary: Decodable {
        struct DiagnosticChannel: Decodable {
            let status: String?
            let ok: Int?
            let warn: Int?
            let fail: Int?
            let unknown: Int?
            let unchecked: Int?
            let notSampled: Int?
            let sampleCount: Int?

            enum CodingKeys: String, CodingKey {
                case status
                case ok
                case warn
                case fail
                case unknown
                case unchecked
                case notSampled
                case sampleCount = "sample_count"
            }
        }

        let hasReport: Bool?
        let scope: String?
        let origin: String?
        let coverage: String?
        let checkedAt: String?
        let ageSeconds: Int?
        let status: String?
        let diagnosticCount: Int?
        let diagnosticCounts: [String: Int]?
        let diagnosticChannels: [String: DiagnosticChannel]?
        let validSampleCount: Int?
        let issueCount: Int?
        let blockingIssueCount: Int?
        let advisoryCount: Int?
        let stale: Bool?
        let routeMatchesCurrent: Bool?
        let invalidReason: String?
        let usableForDashboard: Bool?

        enum CodingKeys: String, CodingKey {
            case hasReport = "has_report"
            case scope
            case origin
            case coverage
            case checkedAt = "checked_at"
            case ageSeconds = "age_seconds"
            case status
            case diagnosticCount = "diagnostic_count"
            case diagnosticCounts = "diagnostic_counts"
            case diagnosticChannels = "diagnostic_channels"
            case validSampleCount = "valid_sample_count"
            case issueCount = "issue_count"
            case blockingIssueCount = "blocking_issue_count"
            case advisoryCount = "advisory_count"
            case stale
            case routeMatchesCurrent = "route_matches_current"
            case invalidReason = "invalid_reason"
            case usableForDashboard = "usable_for_dashboard"
        }
    }

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
    let schemaVersion: String?
    let decision: Decision?
    let verdict: Verdict?
    let presentation: Presentation?
    let machine: Machine?
    let proxy: Proxy?
    let egress: Egress?
    let connectionQuality: ConnectionQuality?
    let lastReportSummary: LastReportSummary?
    let state: StateBlock
    let savedProfileCount: Int?
    // Top-level narrative copies of verdict.* — backend mirrors verdict
    // copy here so the home view can read `response.headline / detail /
    // next_step` even before decoding the nested verdict block.
    let topHeadline: String?
    let detail: String?
    let topNextStep: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case decision
        case verdict
        case presentation
        case machine
        case proxy
        case egress
        case connectionQuality = "connection_quality"
        case lastReportSummary = "last_report_summary"
        case state
        case savedProfileCount = "saved_profile_count"
        case topHeadline = "headline"
        case detail
        case topNextStep = "next_step"
    }

    var uiState: DashboardUIState {
        DashboardUIState(rawValue: decision?.uiState ?? state.state) ?? .ready
    }

    var headline: String {
        topHeadline ?? verdict?.headline ?? decision?.headline ?? state.headline
    }

    var narrativeDetail: String? {
        detail ?? verdict?.detail
    }

    var nextStep: String {
        topNextStep ?? verdict?.nextStep ?? decision?.nextStep ?? state.nextStep
    }

    var primaryActionID: String {
        verdict?.primaryAction?.id ?? decision?.primaryAction ?? "diagnose"
    }

    var primaryActionLabel: String {
        // The backend owns the action label. If it is missing or empty we
        // return an empty string so the view can hide the primary CTA rather
        // than invent copy the contract does not bless.
        if let label = verdict?.primaryAction?.label, !label.isEmpty {
            return label
        }
        guard verdict == nil else { return "" }
        switch resolvedPrimaryActionTarget {
        case .proxySetup: return "粘贴代理参数"
        case .doctor: return "检查当前网络"
        case .staleBridgeRecovery: return "恢复原来的网络设置"
        case .none, .unsupported: return ""
        }
    }

    var primaryActionTarget: String {
        resolvedPrimaryActionTarget.canonicalValue
    }

    var resolvedPrimaryActionTarget: DashboardActionTarget {
        if verdict?.primaryAction?.enabled == false {
            return .none
        }
        return DashboardActionTarget.resolve(
            target: verdict?.primaryAction?.target,
            actionID: verdict?.primaryAction?.id ?? decision?.primaryAction
        )
    }

    var resolvedSecondaryActionTarget: DashboardActionTarget {
        let resolved = DashboardActionTarget.resolve(
            target: verdict?.secondaryAction?.target,
            actionID: verdict?.secondaryAction?.id
        )
        if resolved != .none {
            return verdict?.secondaryAction?.enabled == false ? .none : resolved
        }
        if proxy?.bridge?.inUse == true
            || state.bridgeInUse == true
            || decision?.effectiveRoute == "netfix_applied" {
            return .staleBridgeRecovery
        }
        return .none
    }

    var secondaryActionLabel: String? {
        guard resolvedSecondaryActionTarget != .none,
              verdict?.secondaryAction?.enabled != false else {
            return nil
        }
        if let label = verdict?.secondaryAction?.label, !label.isEmpty {
            return label
        }
        return "停止使用并恢复原设置"
    }

    var shouldShowProxyDeployCTA: Bool {
        resolvedPrimaryActionTarget == .proxySetup
    }

    var requiresConfirmation: Bool {
        verdict?.primaryAction?.requiresConfirmation ?? decision?.requiresConfirmation ?? false
    }
}
