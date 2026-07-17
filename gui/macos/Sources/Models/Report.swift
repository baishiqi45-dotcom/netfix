import Foundation

// MARK: - 诊断报告模型

/// netfix 后端返回的完整 JSON 报告。
/// 与 netfix/report.py 中的 Report.data 结构对应。
struct NetfixReport: Codable {
    let schemaVersion: String?
    let meta: ReportMeta?
    let environment: ReportEnvironment?
    let diagnostics: [DiagnosticItem]
    let rootCauses: [RootCause]
    let fixes: [FixItem]
    let manualSteps: [ManualStep]
    let explanation: Explanation?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case meta
        case environment
        case diagnostics
        case rootCauses = "root_causes"
        case fixes
        case manualSteps = "manual_steps"
        case explanation
    }

    /// 根据诊断项汇总整体状态。
    var overallStatus: DiagnosticStatus {
        let statuses = diagnostics.map { $0.status }
        if statuses.contains("fail") { return .fail }
        if statuses.contains("warn") { return .warn }
        return .ok
    }

    /// 一句话结论（用于 headline）。
    var summaryHeadline: String {
        if let headline = explanation?.headline, !headline.isEmpty {
            return headline
        }
        if overallStatus == .ok {
            return "网络看起来正常"
        }
        if overallStatus == .fail {
            return "当前网络连接失败"
        }
        return "当前网络需要复查"
    }

    /// 首个根因描述，便于用户理解问题。
    var firstRootCause: String? {
        rootCauses.first?.description
    }
}

struct ReportMeta: Codable {
    let version: String?
    let timestamp: String?
    let platform: String?
    let hostname: String?
    let origin: String?
    let coverage: String?
    let routeSignature: String?

    enum CodingKeys: String, CodingKey {
        case version
        case timestamp
        case platform
        case hostname
        case origin
        case coverage
        case routeSignature = "route_signature"
    }
}

struct ReportEnvironment: Codable {
    let guiClient: String?
    let activeCore: String?
    let mixedPort: Int?
    let systemProxy: SystemProxy?
    let activeProfile: ActiveProfile?

    enum CodingKeys: String, CodingKey {
        case guiClient = "gui_client"
        case activeCore = "active_core"
        case mixedPort = "mixed_port"
        case systemProxy = "system_proxy"
        case activeProfile = "active_profile"
    }
}

struct SystemProxy: Codable {
    let http: String?
    let https: String?
    let socks: String?
}

struct ActiveProfile: Codable {
    let id: String?
    let remarks: String?
}

struct DiagnosticItem: Codable, Identifiable {
    let name: String
    let displayName: String?
    let status: String
    let layer: String?
    let proxyUsed: String?
    let details: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case name
        case displayName = "display_name"
        case status
        case layer
        case proxyUsed = "proxy_used"
        case details
    }

    var id: String { name }
    var displayTitle: String { displayName?.isEmpty == false ? displayName! : name }
}

struct RootCause: Codable, Identifiable {
    let description: String
    let confidence: Double?
    var id: String { description }
}

struct FixItem: Codable, Identifiable {
    let id: String
    let description: String
    let tier: Int?
    let command: String?
}

struct ManualStep: Codable, Identifiable {
    let stepId: String?
    let description: String?
    let steps: [String]?

    enum CodingKeys: String, CodingKey {
        case stepId = "id"
        case description
        case steps
    }

    init(stepId: String? = nil, description: String? = nil, steps: [String]? = nil) {
        self.stepId = stepId
        self.description = description
        self.steps = steps
    }

    init(from decoder: Decoder) throws {
        if let container = try? decoder.container(keyedBy: CodingKeys.self) {
            stepId = try container.decodeIfPresent(String.self, forKey: .stepId)
            description = try container.decodeIfPresent(String.self, forKey: .description)
            steps = try container.decodeIfPresent([String].self, forKey: .steps)
        } else {
            // 容错：AI 回答里的 manual_steps 有时是纯字符串，按 description 处理
            stepId = nil
            description = try? decoder.singleValueContainer().decode(String.self)
            steps = nil
        }
    }

    var id: String { stepId ?? description ?? UUID().uuidString }
}

enum DiagnosticStatus: String {
    case ok
    case warn
    case fail
    case unknown
}

extension DiagnosticStatus {
    /// 从字符串构造状态，无法识别时返回 unknown。
    init(_ value: String) {
        self = DiagnosticStatus(rawValue: value) ?? .unknown
    }
}

// MARK: - 人话解释模型

struct Explanation: Codable {
    let headline: String?
    let severity: String?
    let explanation: String?
    let primaryAction: Action?
    let actions: [Action]
    let manualSteps: [ManualStep]

    enum CodingKeys: String, CodingKey {
        case headline
        case severity
        case explanation
        case primaryAction = "primary_action"
        case actions
        case manualSteps = "manual_steps"
    }
}

struct Action: Codable, Identifiable {
    let id: String
    let label: String
    let tier: Int
    let needsConfirm: Bool
    let verifyDiagnostic: String?
    /// AI 解释里附带的推荐理由（本地报告动作没有此字段）。
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case tier
        case needsConfirm = "needs_confirm"
        case verifyDiagnostic = "verify_diagnostic"
        case reason
    }
}

// MARK: - 服务分组模型

struct ServiceGroupResponse: Codable {
    let version: String
    let groups: [ServiceGroup]
}

struct ServiceGroup: Codable, Identifiable {
    let id: String
    let name: String
    let services: [Service]
}

struct Service: Codable, Identifiable {
    let id: String
    let name: String
    let url: String
    let path: String
    let expect: Int
}

// MARK: - 后端通用响应

struct APIHealthResponse: Codable {
    let ok: Bool
    let version: String?
}

struct EventsResponse: Codable {
    let events: [BackendEvent]
    let error: String?
}

struct EnvironmentResponse: Codable {
    let ok: Bool
    let guiClient: String?
    let activeCore: String?
    let mixedPort: Int?
    let activeProfile: ActiveProfile?
    let profiles: [ActiveProfile]
    let systemProxy: SystemProxy?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case guiClient = "gui_client"
        case activeCore = "active_core"
        case mixedPort = "mixed_port"
        case activeProfile = "active_profile"
        case profiles
        case systemProxy = "system_proxy"
        case error
    }
}

struct BackendEvent: Codable, Identifiable {
    let timestamp: String
    let type: String
    let status: String
    let headline: String?
    let rootCause: String?

    enum CodingKeys: String, CodingKey {
        case timestamp
        case type
        case status
        case headline
        case rootCause = "root_cause"
    }

    var id: String { timestamp + type }
}

struct APIRunResponse: Codable {
    let ok: Bool
    let result: NetfixReport?
    let error: String?
    let jobId: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case result
        case error
        case jobId = "job_id"
    }
}

/// Mirrors the payload returned by GET /user-facing/errors.
/// Used to keep Swift in sync with the Python reason code table.
struct UserFacingErrorsResponse: Codable {
    let ok: Bool
    let codes: [UserFacingErrorCodeEntry]
}

/// Payload returned by GET /support/bundle. We only decode the fields
/// the user-facing copy button needs.
struct SupportBundleResponse: Codable {
    let ok: Bool
    let supportText: String?
    let nextSteps: [String]?

    enum CodingKeys: String, CodingKey {
        case ok
        case supportText = "support_text"
        case nextSteps = "next_steps"
    }
}

struct UserFacingErrorCodeEntry: Codable, Identifiable {
    let code: String
    let headline: String
    let nextStep: String
    let technical: String?

    var id: String { code }

    enum CodingKeys: String, CodingKey {
        case code
        case headline
        case nextStep = "next_step"
        case technical
    }
}

/// Optional structured error card returned alongside failed API responses.
struct ErrorCard: Codable {
    let code: String
    let headline: String
    let nextStep: String?
    let technical: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case code
        case headline
        case nextStep = "next_step"
        case technical
        case source
    }

    var toMessage: UserFacingMessage {
        UserFacingMessage(
            code: code,
            headline: headline,
            nextStep: nextStep ?? "可以重试或查看日志。",
            technical: technical
        )
    }
}

struct APIJobResponse: Codable {
    let ok: Bool?
    let status: String
    let result: APIRunResponse?
    let error: String?
    let command: [String]?
    let startedAt: String?
    let finishedAt: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case status
        case result
        case error
        case command
        case startedAt = "started_at"
        case finishedAt = "finished_at"
    }
}

struct APISessionResponse: Codable {
    let ok: Bool
    let token: String
}

struct LogsResponse: Codable {
    let ok: Bool
    let journalDir: String?
    let latestReportPath: String?
    let latestReportExists: Bool?
    let eventsPath: String?
    let eventsExists: Bool?
    let events: [BackendEvent]
    let latestReportSummary: LatestReportSummary?
    let eventsError: String?
    let privacy: PrivacySettings?

    enum CodingKeys: String, CodingKey {
        case ok
        case journalDir = "journal_dir"
        case latestReportPath = "latest_report_path"
        case latestReportExists = "latest_report_exists"
        case eventsPath = "events_path"
        case eventsExists = "events_exists"
        case events
        case latestReportSummary = "latest_report_summary"
        case eventsError = "events_error"
        case privacy
    }
}

struct LatestReportSummary: Codable {
    let timestamp: String?
    let headline: String?
}

struct LLMProvidersResponse: Codable {
    let ok: Bool
    let providers: [LLMProviderInfo]
}

struct LLMChainReadinessResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let llmEnabled: Bool?
    let fallbackEnabled: Bool?
    let imageQuestionEnabled: Bool?
    let budget: LLMChainBudgetStatus?
    let chains: [LLMChainReadiness]?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case llmEnabled = "llm_enabled"
        case fallbackEnabled = "fallback_enabled"
        case imageQuestionEnabled = "image_question_enabled"
        case budget
        case chains
    }
}

struct LLMChainBudgetStatus: Codable {
    let enabled: Bool?
    let persisted: Bool?
    let windowSeconds: Int?
    let maxRequestsPerHour: Int?
    let maxImageRequestsPerHour: Int?
    let usedRequests: Int?
    let remainingRequests: Int?
    let usedImageRequests: Int?
    let remainingImageRequests: Int?

    enum CodingKeys: String, CodingKey {
        case enabled
        case persisted
        case windowSeconds = "window_s"
        case maxRequestsPerHour = "max_requests_per_hour"
        case maxImageRequestsPerHour = "max_image_requests_per_hour"
        case usedRequests = "used_requests"
        case remainingRequests = "remaining_requests"
        case usedImageRequests = "used_image_requests"
        case remainingImageRequests = "remaining_image_requests"
    }
}

struct LLMChainReadiness: Codable, Identifiable {
    let id: String
    let label: String?
    let mode: String?
    let status: String?
    let ready: Bool?
    let readyCount: Int?
    let missingKeyProviders: [String]?
    let nextStep: String?
    let providers: [LLMChainProviderReadiness]?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case mode
        case status
        case ready
        case readyCount = "ready_count"
        case missingKeyProviders = "missing_key_providers"
        case nextStep = "next_step"
        case providers
    }
}

struct LLMChainProviderReadiness: Codable, Identifiable {
    var id: String { provider }

    let provider: String
    let label: String?
    let mode: String?
    let status: String?
    let ready: Bool?
    let apiKeyAccount: String?
    let apiKeySet: Bool?
    let model: String?
    let baseURL: String?
    let supportsVision: Bool?
    let imageAdapterReady: Bool?
    let costTier: String?
    let metadataCheckedAt: String?
    let officialDocs: [String]?
    let maxTokensField: String?
    let nextStep: String?

    enum CodingKeys: String, CodingKey {
        case provider
        case label
        case mode
        case status
        case ready
        case apiKeyAccount = "api_key_account"
        case apiKeySet = "api_key_set"
        case model
        case baseURL = "base_url"
        case supportsVision = "supports_vision"
        case imageAdapterReady = "image_adapter_ready"
        case costTier = "cost_tier"
        case metadataCheckedAt = "metadata_checked_at"
        case officialDocs = "official_docs"
        case maxTokensField = "max_tokens_field"
        case nextStep = "next_step"
    }
}

struct LLMChainTestResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let checkedAt: String?
    let testedCount: Int?
    let chains: [LLMChainTest]?
    let warnings: [String]?
    let error: String?
    let requiresConfirmation: Bool?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case checkedAt = "checked_at"
        case testedCount = "tested_count"
        case chains
        case warnings
        case error
        case requiresConfirmation = "requires_confirmation"
    }
}

struct LLMChainTest: Codable, Identifiable {
    let id: String
    let label: String?
    let mode: String?
    let status: String?
    let okCount: Int?
    let failedCount: Int?
    let skippedCount: Int?
    let providers: [LLMChainTestProvider]?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case mode
        case status
        case okCount = "ok_count"
        case failedCount = "failed_count"
        case skippedCount = "skipped_count"
        case providers
    }
}

struct LLMChainTestProvider: Codable, Identifiable {
    var id: String { provider }

    let provider: String
    let label: String?
    let mode: String?
    let status: String?
    let reasonCode: String?
    let httpStatus: Int?
    let headline: String?
    let model: String?
    let apiKeyAccount: String?

    enum CodingKeys: String, CodingKey {
        case provider
        case label
        case mode
        case status
        case reasonCode = "reason_code"
        case httpStatus = "http_status"
        case headline
        case model
        case apiKeyAccount = "api_key_account"
    }
}

struct LLMProviderInfo: Codable, Identifiable {
    let id: String
    let label: String
    let baseURL: String
    let model: String
    let openAICompatible: Bool?
    let supportsVision: Bool?
    let capabilities: [String]?
    let costTier: String?
    let market: String?
    let netfixRole: String?
    let imageQuestionStatus: String?
    let imageQuestionProviderSupported: Bool?
    let imageQuestionAdapterReady: Bool?
    let imageQuestionReady: Bool?
    let textExplainReady: Bool?
    let netfixMode: String?
    let apiKeyAccount: String?
    let apiKeySet: Bool?
    let fallbackReady: Bool?
    let metadataCheckedAt: String?
    let officialDocs: [String]?
    let maxTokensField: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case baseURL = "base_url"
        case model
        case openAICompatible = "openai_compatible"
        case supportsVision = "supports_vision"
        case capabilities
        case costTier = "cost_tier"
        case market
        case netfixRole = "netfix_role"
        case imageQuestionStatus = "image_question_status"
        case imageQuestionProviderSupported = "image_question_provider_supported"
        case imageQuestionAdapterReady = "image_question_adapter_ready"
        case imageQuestionReady = "image_question_ready"
        case textExplainReady = "text_explain_ready"
        case netfixMode = "netfix_mode"
        case apiKeyAccount = "api_key_account"
        case apiKeySet = "api_key_set"
        case fallbackReady = "fallback_ready"
        case metadataCheckedAt = "metadata_checked_at"
        case officialDocs = "official_docs"
        case maxTokensField = "max_tokens_field"
        case notes
    }
}

struct LLMSettingsResponse: Codable {
    let ok: Bool
    let settings: LLMSettings
}

struct DeepSeekSidecarImportResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let provider: String?
    let apiKeyAccount: String?
    let keyName: String?
    let envPath: String?
    let model: String?
    let llmEnabled: Bool?
    let apiKeySet: Bool?
    let settings: LLMSettings?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case provider
        case apiKeyAccount = "api_key_account"
        case keyName = "key_name"
        case envPath = "env_path"
        case model
        case llmEnabled = "llm_enabled"
        case apiKeySet = "api_key_set"
        case settings
    }
}

struct LLMSettings: Codable {
    let enabled: Bool
    let provider: String
    let baseURL: String
    let model: String
    let apiKeyAccount: String
    let apiKeySet: Bool
    let timeoutSeconds: Int?
    let maxTokens: Int?
    let temperature: Double?
    let redactionLevel: String?
    let uploadConsent: String?
    let features: LLMSettingsFeatures?
    let fallback: LLMSettingsFallback?
    let budget: LLMSettingsBudget?

    enum CodingKeys: String, CodingKey {
        case enabled
        case provider
        case baseURL = "base_url"
        case model
        case apiKeyAccount = "api_key_account"
        case apiKeySet = "api_key_set"
        case timeoutSeconds = "timeout_s"
        case maxTokens = "max_tokens"
        case temperature
        case redactionLevel = "redaction_level"
        case uploadConsent = "upload_consent"
        case features
        case fallback
        case budget
    }
}

struct LLMSettingsBudget: Codable {
    let enabled: Bool?
    let persistUsageLedger: Bool?
    let maxRequestsPerHour: Int?
    let maxImageRequestsPerHour: Int?
    let cooldownSecondsAfterRateLimit: Int?
    let cooldownSecondsAfterQuota: Int?

    enum CodingKeys: String, CodingKey {
        case enabled
        case persistUsageLedger = "persist_usage_ledger"
        case maxRequestsPerHour = "max_requests_per_hour"
        case maxImageRequestsPerHour = "max_image_requests_per_hour"
        case cooldownSecondsAfterRateLimit = "cooldown_seconds_after_rate_limit"
        case cooldownSecondsAfterQuota = "cooldown_seconds_after_quota"
    }
}

struct LLMSettingsFallback: Codable {
    let enabled: Bool?
    let domesticOnly: Bool?
    let includeCustom: Bool?
    let includeGlobal: Bool?
    let chain: [String]?
    let visionChain: [String]?

    enum CodingKeys: String, CodingKey {
        case enabled
        case domesticOnly = "domestic_only"
        case includeCustom = "include_custom"
        case includeGlobal = "include_global"
        case chain
        case visionChain = "vision_chain"
    }
}

struct LLMSettingsFeatures: Codable {
    let explain: Bool?
    let repairSteps: Bool?
    let residentialProxyGuide: Bool?
    let imageQuestion: Bool?

    enum CodingKeys: String, CodingKey {
        case explain
        case repairSteps = "repair_steps"
        case residentialProxyGuide = "residential_proxy_guide"
        case imageQuestion = "image_question"
    }
}

struct LLMTestResponse: Codable {
    let ok: Bool
    let error: String?
}

struct PrivacySettingsResponse: Codable {
    let ok: Bool
    let settings: PrivacySettings
}

struct PrivacySettingsSaveResponse: Codable {
    let ok: Bool
    let settings: PrivacySettings
    let retention: RetentionResult?
}

struct ProxyBridgeSettingsResponse: Codable {
    let ok: Bool
    let settings: ProxyBridgeSettings
}

struct ProxyBridgeSettings: Codable {
    let autoRestartEnabled: Bool
    let idleTimeout: Int
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case autoRestartEnabled = "auto_restart_enabled"
        case idleTimeout = "idle_timeout"
        case updatedAt = "updated_at"
    }
}

struct PrivacySettings: Codable {
    let logRetentionEnabled: Bool
    let logRetentionDays: Int
    let saveLatestReport: Bool
    let persistProxyIdentityReport: Bool

    enum CodingKeys: String, CodingKey {
        case logRetentionEnabled = "log_retention_enabled"
        case logRetentionDays = "log_retention_days"
        case saveLatestReport = "save_latest_report"
        case persistProxyIdentityReport = "persist_proxy_identity_report"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        logRetentionEnabled = try container.decodeIfPresent(Bool.self, forKey: .logRetentionEnabled) ?? true
        logRetentionDays = try container.decodeIfPresent(Int.self, forKey: .logRetentionDays) ?? 7
        saveLatestReport = try container.decodeIfPresent(Bool.self, forKey: .saveLatestReport) ?? true
        persistProxyIdentityReport = try container.decodeIfPresent(Bool.self, forKey: .persistProxyIdentityReport) ?? false
    }
}

struct RetentionResult: Codable {
    let ok: Bool
    let removed: Int?
    let kept: Int?
    let error: String?
}

struct LogsClearResponse: Codable {
    let ok: Bool
    let removed: [String]
    let errors: [String: String]
}

struct DataClearResponse: Codable {
    let ok: Bool
    let error: String?
    let logs: LogsClearResponse?
    let llmBudget: LogsClearResponse?
    let settings: SettingsClearResult?
    let keychain: KeychainClearResult?

    enum CodingKeys: String, CodingKey {
        case ok
        case error
        case logs
        case llmBudget = "llm_budget"
        case settings
        case keychain
    }
}

struct SettingsClearResult: Codable {
    let ok: Bool
    let removed: [String]?
    let error: String?
}

struct KeychainClearResult: Codable {
    let ok: Bool
    let deleted: [KeychainTarget]?
    let missing: [KeychainTarget]?
    let errors: [String: String]?
}

struct KeychainTarget: Codable {
    let service: String
    let account: String
}

struct LLMExplainAPIResponse: Codable {
    let ok: Bool
    let result: LLMExplainResult
}

struct LLMExplainResult: Codable {
    let source: String?
    let fallbackReason: String?
    let fallbackReasonLabel: String?
    let failureReasonCode: String?
    let providerUsed: String?
    let fallbackChain: [LLMFallbackStep]?
    let needsUploadConfirmation: Bool?
    let headline: String?
    let severity: String?
    let explanation: String?
    let actions: [Action]?
    let manualSteps: [ManualStep]?
    let redactedReportHash: String?

    enum CodingKeys: String, CodingKey {
        case source
        case fallbackReason = "fallback_reason"
        case fallbackReasonLabel = "fallback_reason_label"
        case failureReasonCode = "failure_reason_code"
        case providerUsed = "provider_used"
        case fallbackChain = "fallback_chain"
        case needsUploadConfirmation = "needs_upload_confirmation"
        case headline
        case severity
        case explanation
        case actions
        case manualSteps = "manual_steps"
        case redactedReportHash = "redacted_report_hash"
    }
}

/// 一轮「问 AI」对话：用户的提问 + 后端返回的解释（回答回来前 result 为空）。
struct AIChatTurn: Identifiable {
    let id = UUID()
    let question: String
    var result: LLMExplainResult?
}

struct LLMFallbackStep: Codable {
    let provider: String?
    let status: String?
    let reasonCode: String?
    let httpStatus: Int?

    enum CodingKeys: String, CodingKey {
        case provider
        case status
        case reasonCode = "reason_code"
        case httpStatus = "http_status"
    }
}

struct ProxyProfilesResponse: Codable {
    let ok: Bool
    let profiles: [ProxyProfile]
}

struct ProxyProfileResponse: Codable {
    let ok: Bool
    let profile: ProxyProfile?
    let deploymentDecision: ProxyDeploymentDecision?
    let monitor: ProxyMonitorState?
    let warnings: [String]?
    let error: String?
    let reasonCode: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case profile
        case deploymentDecision = "deployment_decision"
        case monitor
        case warnings
        case error
        case reasonCode = "reason_code"
    }
}

struct ProxyProfileDeleteResponse: Codable {
    let ok: Bool
    let profile: ProxyProfile?
    let monitorStopped: Bool?
    let monitorPersistedCleared: Bool?
    let warnings: [String]?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case profile
        case monitorStopped = "monitor_stopped"
        case monitorPersistedCleared = "monitor_persisted_cleared"
        case warnings
        case error
    }
}

struct ProxyProfile: Codable, Identifiable {
    let id: String
    let name: String?
    let protocolName: String?
    let host: String?
    let port: Int?
    let username: String?
    let credentialRef: String?
    let provider: String?
    let passwordSet: Bool?
    let lastCheck: ProxyCheck?
    let lastIdentityReport: ProxyIdentityReport?
    let endpointFingerprint: String?
    let lastSavedAt: String?
    let createdAt: String?
    let deduplicated: Bool?
    let verificationStatus: String?
    let canApply: Bool?
    let validatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case protocolName = "protocol"
        case host
        case port
        case username
        case credentialRef = "credential_ref"
        case provider
        case passwordSet = "password_set"
        case lastCheck = "last_check"
        case lastIdentityReport = "last_identity_report"
        case endpointFingerprint = "endpoint_fingerprint"
        case lastSavedAt = "last_saved_at"
        case createdAt = "created_at"
        case deduplicated
        case verificationStatus = "verification_status"
        case canApply = "can_apply"
        case validatedAt = "validated_at"
    }
}

struct ProxyProfileGroup: Codable, Identifiable {
    let fingerprint: String
    let canonicalId: String
    let count: Int
    let profileIds: [String]
    let profiles: [ProxyProfileGroupMember]

    var id: String { fingerprint }

    enum CodingKeys: String, CodingKey {
        case fingerprint
        case canonicalId = "canonical_id"
        case count
        case profileIds = "profile_ids"
        case profiles
    }
}

struct ProxyProfileGroupMember: Codable, Identifiable {
    let id: String
    let name: String?
    let protocolName: String?
    let host: String?
    let port: Int?
    let username: String?
    let lastSavedAt: String?
    let createdAt: String?
    let endpointFingerprint: String?
    let isCanonical: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case protocolName = "protocol"
        case host
        case port
        case username
        case lastSavedAt = "last_saved_at"
        case createdAt = "created_at"
        case endpointFingerprint = "endpoint_fingerprint"
        case isCanonical = "is_canonical"
    }
}

struct ProxyProfilesGroupedResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let groups: [ProxyProfileGroup]
    let duplicateGroups: Int?
    let duplicateProfileIds: [String]?
    let totalProfiles: Int?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case groups
        case duplicateGroups = "duplicate_groups"
        case duplicateProfileIds = "duplicate_profile_ids"
        case totalProfiles = "total_profiles"
    }
}

struct ProxyProfilesCleanupResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let removedIds: [String]?
    let keptIds: [String]?
    let duplicateGroupsBefore: Int?
    let duplicateGroupsAfter: Int?
    let totalProfilesAfter: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case removedIds = "removed_ids"
        case keptIds = "kept_ids"
        case duplicateGroupsBefore = "duplicate_groups_before"
        case duplicateGroupsAfter = "duplicate_groups_after"
        case totalProfilesAfter = "total_profiles_after"
        case error
    }
}

struct ProxyParseResponse: Codable {
    let ok: Bool
    let profile: ProxyProfile?
    let redactedURL: String?
    let credentialPresent: Bool?
    let deploymentDecision: ProxyDeploymentDecision?
    let warnings: [String]
    let errors: [String]?

    enum CodingKeys: String, CodingKey {
        case ok
        case profile
        case redactedURL = "redacted_url"
        case credentialPresent = "credential_present"
        case deploymentDecision = "deployment_decision"
        case warnings
        case errors
    }
}

struct ProxyImportPreviewResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let summary: ProxyImportSummary
    let truncated: Bool?
    let recommendation: ProxyImportRecommendation?
    let candidates: [ProxyImportCandidate]
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case summary
        case truncated
        case recommendation
        case candidates
        case warnings
    }
}

struct ProxyImportSummary: Codable {
    let inputLineCount: Int?
    let processedCount: Int?
    let skippedCount: Int?
    let validCount: Int?
    let invalidCount: Int?
    let readyCount: Int?
    let limitedCount: Int?

    enum CodingKeys: String, CodingKey {
        case inputLineCount = "input_line_count"
        case processedCount = "processed_count"
        case skippedCount = "skipped_count"
        case validCount = "valid_count"
        case invalidCount = "invalid_count"
        case readyCount = "ready_count"
        case limitedCount = "limited_count"
    }
}

struct ProxyImportRecommendation: Codable {
    let lineNumber: Int?
    let redactedURL: String?
    let status: String?
    let headline: String?

    enum CodingKeys: String, CodingKey {
        case lineNumber = "line_number"
        case redactedURL = "redacted_url"
        case status
        case headline
    }
}

struct ProxyImportCandidate: Codable, Identifiable {
    var id: Int { lineNumber ?? 0 }

    let lineNumber: Int?
    let ok: Bool
    let redactedURL: String?
    let credentialPresent: Bool?
    let deploymentDecision: ProxyDeploymentDecision?
    let warnings: [String]?
    let errors: [String]?
    let profile: ProxyProfile?

    enum CodingKeys: String, CodingKey {
        case lineNumber = "line_number"
        case ok
        case redactedURL = "redacted_url"
        case credentialPresent = "credential_present"
        case deploymentDecision = "deployment_decision"
        case warnings
        case errors
        case profile
    }
}

struct ProxyDeploymentDecision: Codable {
    let schemaVersion: String?
    let status: String?
    let headline: String?
    let primaryAction: String?
    let protocolName: String?
    let credentialPresent: Bool?
    let missingFields: [String]?
    let systemApply: ProxyDeploymentCapability?
    let appEnv: ProxyDeploymentCapability?
    let clientExport: ProxyDeploymentCapability?
    let monitor: ProxyDeploymentCapability?
    let warnings: [String]?
    let nextSteps: [String]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case headline
        case primaryAction = "primary_action"
        case protocolName = "protocol"
        case credentialPresent = "credential_present"
        case missingFields = "missing_fields"
        case systemApply = "system_apply"
        case appEnv = "app_env"
        case clientExport = "client_export"
        case monitor
        case warnings
        case nextSteps = "next_steps"
    }
}

struct ProxyDeploymentCapability: Codable {
    let status: String?
    let label: String?
    let reasonCode: String?
    let requiresConfirmation: Bool?
    let requiresNetfixRunning: Bool?
    let formats: [String]?
    let secretPlaceholder: Bool?
    let secretSource: String?

    enum CodingKeys: String, CodingKey {
        case status
        case label
        case reasonCode = "reason_code"
        case requiresConfirmation = "requires_confirmation"
        case requiresNetfixRunning = "requires_netfix_running"
        case formats
        case secretPlaceholder = "secret_placeholder"
        case secretSource = "secret_source"
    }
}

struct ProxyValidateResponse: Codable {
    let ok: Bool
    let proxyCheck: ProxyCheck?
    let identityReport: ProxyIdentityReport?
    let profile: ProxyProfile?
    let validationReceipt: String?
    let validationReceiptExpiresInSeconds: Int?
    let errors: [String]?

    enum CodingKeys: String, CodingKey {
        case ok
        case proxyCheck = "proxy_check"
        case identityReport = "identity_report"
        case profile
        case validationReceipt = "validation_receipt"
        case validationReceiptExpiresInSeconds = "validation_receipt_expires_in_seconds"
        case errors
    }
}

struct ProxyValidationTargetsResponse: Codable {
    let ok: Bool
    let schemaVersion: String?
    let defaultProfile: String?
    let profiles: [ProxyValidationTargetProfile]
    let allowedHosts: [String]?

    enum CodingKeys: String, CodingKey {
        case ok
        case schemaVersion = "schema_version"
        case defaultProfile = "default_profile"
        case profiles
        case allowedHosts = "allowed_hosts"
    }
}

struct ProxyValidationTargetProfile: Codable, Identifiable {
    let id: String
    let label: String?
    let description: String?
    let probes: [ProxyValidationTargetProbe]?
}

struct ProxyValidationTargetProbe: Codable, Identifiable {
    var id: String { probeID ?? url ?? UUID().uuidString }

    let probeID: String?
    let label: String?
    let url: String?
    let host: String?
    let okCodes: [Int]?

    enum CodingKeys: String, CodingKey {
        case probeID = "id"
        case label
        case url
        case host
        case okCodes = "ok_codes"
    }
}

struct ProxyClientExportResponse: Codable {
    let ok: Bool
    let profileId: String?
    let profileName: String?
    let format: String?
    let redactedURL: String?
    let snippets: [String: ProxyClientSnippet]?
    let package: ProxyClientPackage?
    let warnings: [String]?
    let error: String?
    let supportedFormats: [String]?

    enum CodingKeys: String, CodingKey {
        case ok
        case profileId = "profile_id"
        case profileName = "profile_name"
        case format
        case redactedURL = "redacted_url"
        case snippets
        case package
        case warnings
        case error
        case supportedFormats = "supported_formats"
    }

    var sortedSnippets: [(key: String, value: ProxyClientSnippet)] {
        let order = ["url", "env", "clash", "mihomo", "sing-box"]
        return (snippets ?? [:]).sorted { left, right in
            let leftIndex = order.firstIndex(of: left.key) ?? order.count
            let rightIndex = order.firstIndex(of: right.key) ?? order.count
            if leftIndex == rightIndex {
                return left.key < right.key
            }
            return leftIndex < rightIndex
        }
    }
}

struct ProxyClientPackage: Codable {
    let schemaVersion: String?
    let name: String?
    let recommendedFormat: String?
    let files: [ProxyClientPackageFile]?
    let fileCount: Int?
    let secretPlaceholder: Bool?
    let warnings: [String]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case name
        case recommendedFormat = "recommended_format"
        case files
        case fileCount = "file_count"
        case secretPlaceholder = "secret_placeholder"
        case warnings
    }
}

struct ProxyClientPackageFile: Codable, Identifiable {
    var id: String { path ?? format ?? UUID().uuidString }

    let path: String?
    let format: String?
    let label: String?
    let content: String?
    let secretPlaceholder: Bool?

    enum CodingKeys: String, CodingKey {
        case path
        case format
        case label
        case content
        case secretPlaceholder = "secret_placeholder"
    }
}

struct ProxyClientSnippet: Codable {
    let label: String?
    let content: String?
    let secretPlaceholder: Bool?

    enum CodingKeys: String, CodingKey {
        case label
        case content
        case secretPlaceholder = "secret_placeholder"
    }
}

struct ProxyMonitorResponse: Codable {
    let ok: Bool
    let monitor: ProxyMonitorState?
    let error: String?
}

struct ProxyBridgeResponse: Codable {
    let ok: Bool
    let bridges: [ProxyBridgeInfo]
    let staleCheck: ProxyBridgeStaleCheck?
    let lifecycle: ProxyBridgeLifecycle?
    let startupCheck: ProxyBridgeStartupCheck?

    enum CodingKeys: String, CodingKey {
        case ok
        case bridges
        case staleCheck = "stale_check"
        case lifecycle
        case startupCheck = "startup_check"
    }
}

struct ProxyBridgeStartupCheck: Codable {
    let schemaVersion: String?
    let checkedAt: String?
    let ok: Bool?
    let bridgesCount: Int?
    let staleCheck: ProxyBridgeStaleCheck?
    let lifecycle: ProxyBridgeLifecycle?
    let settings: ProxyBridgeSettings?
    let autoRestart: ProxyBridgeRestartResult?
    let eventAppended: Bool?
    let autoRestartEventAppended: Bool?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case checkedAt = "checked_at"
        case ok
        case bridgesCount = "bridges_count"
        case staleCheck = "stale_check"
        case lifecycle
        case settings
        case autoRestart = "auto_restart"
        case eventAppended = "event_appended"
        case autoRestartEventAppended = "auto_restart_event_appended"
        case error
    }
}

struct ProxyBridgeRestartResult: Codable {
    let ok: Bool?
    let status: String?
    let restartAvailable: Bool?
    let requiresConfirmation: Bool?
    let confirmation: String?
    let reasonCode: String?
    let error: String?
    let profileId: String?
    let networkService: String?
    let bridge: ProxyBridgeInfo?
    let systemProxyChanged: Bool?

    enum CodingKeys: String, CodingKey {
        case ok
        case status
        case restartAvailable = "restart_available"
        case requiresConfirmation = "requires_confirmation"
        case confirmation
        case reasonCode = "reason_code"
        case error
        case profileId = "profile_id"
        case networkService = "network_service"
        case bridge
        case systemProxyChanged = "system_proxy_changed"
    }
}

struct ProxyBridgeLifecycle: Codable {
    let schemaVersion: String?
    let status: String?
    let severity: String?
    let headline: String?
    let detail: String?
    let primaryAction: String?
    let needsAttention: Bool?
    let recoveryAvailable: Bool?
    let requiresNetfixRunning: Bool?
    let networkService: String?
    let profileId: String?
    let profileName: String?
    let confirmation: String?
    let systemPointsToBridge: Bool?
    let bridge: ProxyBridgeInfo?
    let portOpen: Bool?
    let audit: ProxyBridgeLifecycleAudit?
    let nextSteps: [String]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case severity
        case headline
        case detail
        case primaryAction = "primary_action"
        case needsAttention = "needs_attention"
        case recoveryAvailable = "recovery_available"
        case requiresNetfixRunning = "requires_netfix_running"
        case networkService = "network_service"
        case profileId = "profile_id"
        case profileName = "profile_name"
        case confirmation
        case systemPointsToBridge = "system_points_to_bridge"
        case bridge
        case portOpen = "port_open"
        case audit
        case nextSteps = "next_steps"
    }
}

struct ProxyBridgeLifecycleAudit: Codable {
    let requestCount: Int?
    let activeConnections: Int?
    let recentClientCount: Int?
    let idleTimeoutS: Double?

    enum CodingKeys: String, CodingKey {
        case requestCount = "request_count"
        case activeConnections = "active_connections"
        case recentClientCount = "recent_client_count"
        case idleTimeoutS = "idle_timeout_s"
    }
}

struct ProxyBridgeStaleCheck: Codable {
    let ok: Bool?
    let status: String?
    let stale: Bool?
    let recoveryAvailable: Bool?
    let confirmation: String?
    let warning: String?
    let networkService: String?
    let profileId: String?
    let profileName: String?
    let bridge: ProxyBridgeInfo?

    enum CodingKeys: String, CodingKey {
        case ok
        case status
        case stale
        case recoveryAvailable = "recovery_available"
        case confirmation
        case warning
        case networkService = "network_service"
        case profileId = "profile_id"
        case profileName = "profile_name"
        case bridge
    }
}

struct ProxyApplyResponse: Codable {
    let ok: Bool
    let status: String?
    let mode: String?
    let profileId: String?
    let networkService: String?
    let requiresConfirmation: Bool?
    let confirmation: String?
    let error: String?
    let reasonCode: String?
    let recommendedMode: String?
    let redactedURL: String?
    let rollbackAvailable: Bool?
    let verify: ProxyValidateResponse?
    let applied: ProxyAppliedScope?
    let bridge: ProxyBridgeInfo?
    let bridgeStop: ProxyBridgeStop?
    let dryRun: ProxyApplyPlan?
    let rollback: ProxyRollbackDetail?
    let deploymentDecision: ProxyDeploymentDecision?

    enum CodingKeys: String, CodingKey {
        case ok
        case status
        case mode
        case profileId = "profile_id"
        case networkService = "network_service"
        case requiresConfirmation = "requires_confirmation"
        case confirmation
        case error
        case reasonCode = "reason_code"
        case recommendedMode = "recommended_mode"
        case redactedURL = "redacted_url"
        case rollbackAvailable = "rollback_available"
        case verify
        case applied
        case bridge
        case bridgeStop = "bridge_stop"
        case dryRun = "dry_run"
        case rollback
        case deploymentDecision = "deployment_decision"
    }
}

extension ProxyApplyResponse {
    var friendlyFailureMessage: String {
        if let reasonCode, !reasonCode.isEmpty,
           let entry = UserFacingMessages.lookup(reasonCode) {
            return "\(entry.headline)\n\(entry.nextStep)"
        }
        let code = (reasonCode ?? error ?? status ?? "").lowercased()
        if code.contains("rollback_failed") || code.contains("restore_failed") {
            return "代理没有通过验证，而且原网络设置没有完整恢复。\n请保持 Netfix 运行，打开「代理」后点「停止使用并恢复」；不要先退出 App。"
        }
        if code.contains("verify_failed") || status == "rolled_back_after_verify_failure" {
            return "这组代理没通过上网验证，Netfix 已恢复部署前的网络设置。\n请换一组代理参数，或先点「预检这行参数」看地址、端口、用户名、密码是否完整。"
        }
        if code.contains("bridge_unsupported_upstream_protocol") {
            return "这类代理暂时不能直接接管整台 Mac。\n可以先导出客户端配置，或只给终端工具生成代理环境。"
        }
        if code.contains("missing_keychain_password") {
            return "本机密码库里找不到这组代理的密码。\n请重新粘贴完整参数并保存。"
        }
        if code.contains("current_authenticated_proxy_not_restorable") {
            return "当前系统代理本身带账号密码，Netfix 无法保证能完整恢复。\n请先手动关闭现有系统代理，再重新部署。"
        }
        if code.contains("system_proxy_backup_failed") {
            return "备份当前网络设置失败。\n请确认 Netfix 有权限修改网络设置，然后重试。"
        }
        if code.contains("system_proxy_apply_failed") || code.contains("networksetup") {
            return "macOS 没有接受这次网络代理修改。\n请确认管理员权限，或重启 Netfix 后再试。"
        }
        if code.contains("bridge_start_failed") || code.contains("loopback_port_owned_by_unknown_process") {
            return "本机转发端口被占用，Netfix 无法安全代管代理密码。\n请退出占用 127.0.0.1 端口的代理软件，或重启 Netfix。"
        }
        if code.contains("system_apply_requires_macos") {
            return "整机代理部署只支持 macOS。\n其他系统可以导出客户端配置或给终端工具生成代理环境。"
        }
        if status == "pending_confirmation" {
            return "还需要你确认。\n请重新点「部署到这台 Mac」，并在弹出的中文确认框里确认。"
        }
        if let error, !error.isEmpty {
            return UserFacingMessages.classify(error).combined
        }
        if let reasonCode, !reasonCode.isEmpty {
            return reasonCode
        }
        return "无法部署到这台 Mac。"
    }
}

struct ProxyApplyPlan: Codable {
    let ok: Bool?
    let mode: String?
    let status: String?
    let profileId: String?
    let requiresConfirmation: Bool?
    let deploymentDecision: ProxyDeploymentDecision?
    let steps: [ProxyApplyStep]?
    let warnings: [String]?

    enum CodingKeys: String, CodingKey {
        case ok
        case mode
        case status
        case profileId = "profile_id"
        case requiresConfirmation = "requires_confirmation"
        case deploymentDecision = "deployment_decision"
        case steps
        case warnings
    }
}

struct ProxyApplyStep: Codable {
    let tier: Int?
    let label: String?
    let safePreview: String?

    enum CodingKeys: String, CodingKey {
        case tier
        case label
        case safePreview = "safe_preview"
    }
}

struct ProxyAppliedScope: Codable {
    let scope: String?
    let requiresNetfixRunning: Bool?
    let envKeys: [String]?
    let redactedEnv: [String: String]?
    let secretSource: String?

    enum CodingKeys: String, CodingKey {
        case scope
        case requiresNetfixRunning = "requires_netfix_running"
        case envKeys = "env_keys"
        case redactedEnv = "redacted_env"
        case secretSource = "secret_source"
    }
}

struct ProxyBridgeInfo: Codable {
    let id: String?
    let listenHost: String?
    let listenPort: Int?
    let upstreamProtocol: String?
    let upstreamHost: String?
    let upstreamPort: Int?
    let running: Bool?
    let requestCount: Int?
    let activeConnections: Int?
    let lastActivityAt: Double?
    let idleTimeoutS: Double?
    let recentClients: [ProxyBridgeClient]?

    enum CodingKeys: String, CodingKey {
        case id
        case listenHost = "listen_host"
        case listenPort = "listen_port"
        case upstreamProtocol = "upstream_protocol"
        case upstreamHost = "upstream_host"
        case upstreamPort = "upstream_port"
        case running
        case requestCount = "request_count"
        case activeConnections = "active_connections"
        case lastActivityAt = "last_activity_at"
        case idleTimeoutS = "idle_timeout_s"
        case recentClients = "recent_clients"
    }
}

struct ProxyBridgeClient: Codable {
    let host: String?
    let count: Int?
    let firstSeen: Double?
    let lastSeen: Double?

    enum CodingKeys: String, CodingKey {
        case host
        case count
        case firstSeen = "first_seen"
        case lastSeen = "last_seen"
    }
}

struct ProxyRollbackResponse: Codable {
    let ok: Bool
    let status: String?
    let journalId: String?
    let profileId: String?
    let networkService: String?
    let requiresConfirmation: Bool?
    let confirmation: String?
    let error: String?
    let rollback: ProxyRollbackDetail?
    let bridgeStop: ProxyBridgeStop?

    enum CodingKeys: String, CodingKey {
        case ok
        case status
        case journalId = "journal_id"
        case profileId = "profile_id"
        case networkService = "network_service"
        case requiresConfirmation = "requires_confirmation"
        case confirmation
        case error
        case rollback
        case bridgeStop = "bridge_stop"
    }
}

struct ProxyBridgeStop: Codable {
    let ok: Bool?
    let stopped: Bool?
    let missing: Bool?
    let bridgeId: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case stopped
        case missing
        case bridgeId = "bridge_id"
    }
}

struct ProxyRollbackDetail: Codable {
    let ok: Bool?
    let error: String?
    let reasonCode: String?
    let networkService: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case error
        case reasonCode = "reason_code"
        case networkService = "network_service"
    }
}

struct ProxyMonitorState: Codable {
    let running: Bool?
    let profileId: String?
    let profileName: String?
    let interval: Int?
    let targetURL: String?
    let targetProfile: String?
    let timeout: Int?
    let startedAt: String?
    let stoppedAt: String?
    let runCount: Int?
    let lastEvent: ProxyMonitorEvent?
    let lastError: String?
    let threadAlive: Bool?
    let restored: Bool?
    let persisted: ProxyMonitorPersisted?

    enum CodingKeys: String, CodingKey {
        case running
        case profileId = "profile_id"
        case profileName = "profile_name"
        case interval
        case targetURL = "target_url"
        case targetProfile = "target_profile"
        case timeout
        case startedAt = "started_at"
        case stoppedAt = "stopped_at"
        case runCount = "run_count"
        case lastEvent = "last_event"
        case lastError = "last_error"
        case threadAlive = "thread_alive"
        case restored
        case persisted
    }
}

struct ProxyMonitorPersisted: Codable {
    let enabled: Bool?
    let profileId: String?
    let interval: Int?
    let targetURL: String?
    let targetProfile: String?
    let timeout: Int?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case enabled
        case profileId = "profile_id"
        case interval
        case targetURL = "target_url"
        case targetProfile = "target_profile"
        case timeout
        case updatedAt = "updated_at"
    }
}

struct ProxyMonitorEvent: Codable {
    let type: String?
    let event: String?
    let status: String?
    let profileId: String?
    let profileName: String?
    let headline: String?
    let run: Int?
    let proxyCheck: ProxyCheck?
    let repairActions: [ProxyRepairAction]?

    enum CodingKeys: String, CodingKey {
        case type
        case event
        case status
        case profileId = "profile_id"
        case profileName = "profile_name"
        case headline
        case run
        case proxyCheck = "proxy_check"
        case repairActions = "repair_actions"
    }
}

struct ProxyRepairAction: Codable, Identifiable {
    var id: String { actionId }

    let actionId: String
    let label: String?
    let detail: String?
    let uiAction: ProxyRepairUIAction?

    enum CodingKeys: String, CodingKey {
        case actionId = "id"
        case label
        case detail
        case uiAction = "ui_action"
    }
}

struct ProxyRepairUIAction: Codable {
    let type: String?
    let profileId: String?

    enum CodingKeys: String, CodingKey {
        case type
        case profileId = "profile_id"
    }
}

struct ProxyCheck: Codable {
    let profileId: String?
    let status: String?
    let auth: String?
    let tcp: String?
    let target: String?
    let httpCode: Int?
    let latencyMs: Int?
    let error: String?
    let checkedVia: String?
    let checkedAt: String?
    let repairActions: [ProxyRepairAction]?

    enum CodingKeys: String, CodingKey {
        case profileId = "profile_id"
        case status
        case auth
        case tcp
        case target
        case httpCode = "http_code"
        case latencyMs = "latency_ms"
        case error
        case checkedVia = "checked_via"
        case checkedAt = "checked_at"
        case repairActions = "repair_actions"
    }
}

struct ProxyIdentityReport: Codable {
    let status: String?
    let checkedAt: String?
    let targetProfile: String?
    let targetProfileLabel: String?
    let exitIP: String?
    let identity: ProxyIdentityInfo?
    let expectedGeo: ProxyGeoMatch?
    let dnsLeak: ProxyLeakAssessment?
    let ipv6Leak: ProxyLeakAssessment?
    let targets: [ProxyTargetProbe]?
    let warnings: [String]?

    enum CodingKeys: String, CodingKey {
        case status
        case checkedAt = "checked_at"
        case targetProfile = "target_profile"
        case targetProfileLabel = "target_profile_label"
        case exitIP = "exit_ip"
        case identity
        case expectedGeo = "expected_geo"
        case dnsLeak = "dns_leak"
        case ipv6Leak = "ipv6_leak"
        case targets
        case warnings
    }
}

struct ProxyIdentityInfo: Codable {
    let ip: String?
    let country: String?
    let countryCode: String?
    let region: String?
    let city: String?
    let isp: String?
    let org: String?
    let asn: String?
    let ipType: String?
    let status: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case ip
        case country
        case countryCode = "country_code"
        case region
        case city
        case isp
        case org
        case asn
        case ipType = "ip_type"
        case status
        case source
    }
}

struct ProxyGeoMatch: Codable {
    let status: String?
    let mismatches: [String]?
}

struct ProxyLeakAssessment: Codable {
    let status: String?
    let confidence: String?
    let risk: String?
}

struct ProxyTargetProbe: Codable, Identifiable {
    let id: String?
    let label: String?
    let target: String?
    let status: String?
    let httpCode: Int?
    let latencyMs: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case target
        case status
        case httpCode = "http_code"
        case latencyMs = "latency_ms"
        case error
    }

    var stableID: String { id ?? target ?? UUID().uuidString }
}
