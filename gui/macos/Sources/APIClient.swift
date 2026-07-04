import Foundation

/// 封装对 netfix 本地 HTTP API 的调用，使用 async/await。
actor APIClient {
    private let baseURL: URL
    private let session: URLSession
    private var apiToken: String?

    init(baseURL: URL, apiToken: String? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.apiToken = apiToken
    }

    // MARK: - 底层请求

    func get<T: Decodable>(path: String, timeout: Int = 30) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if path != "health", let token = apiToken {
            request.setValue(token, forHTTPHeaderField: "X-Netfix-Token")
        }
        request.timeoutInterval = TimeInterval(timeout + 5)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decode(T.self, from: data)
    }

    func post<T: Decodable>(path: String, body: [String: Any], timeout: Int = 60) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        let token = try await sessionToken()
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(token, forHTTPHeaderField: "X-Netfix-Token")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        request.timeoutInterval = TimeInterval(timeout + 30)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        return try decode(T.self, from: data)
    }

    func postDecodingClientError<T: Decodable>(path: String, body: [String: Any], timeout: Int = 60) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        let token = try await sessionToken()
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(token, forHTTPHeaderField: "X-Netfix-Token")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        request.timeoutInterval = TimeInterval(timeout + 30)
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, (200..<500).contains(http.statusCode), !data.isEmpty {
            return try decode(T.self, from: data)
        }
        try validate(response: response, data: data)
        return try decode(T.self, from: data)
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try JSONDecoder().decode(type, from: data)
        } catch let error as DecodingError {
            throw APIError.decodeFailed(Self.formatDecodingError(error))
        } catch {
            throw APIError.decodeFailed(error.localizedDescription)
        }
    }

    private static func formatDecodingError(_ error: DecodingError) -> String {
        switch error {
        case .keyNotFound(let key, let context):
            return "缺少字段 '\(key.stringValue)'（\(context.debugDescription)）"
        case .typeMismatch(let type, let context):
            return "类型不匹配：需要 \(type)（\(context.debugDescription)）"
        case .valueNotFound(let type, let context):
            return "缺少值：需要 \(type)（\(context.debugDescription)）"
        case .dataCorrupted(let context):
            return "数据损坏：\(context.debugDescription)"
        @unknown default:
            return error.localizedDescription
        }
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode, Self.errorDetail(from: data))
        }
        if data.isEmpty {
            throw APIError.emptyResponse
        }
    }

    private static func errorDetail(from data: Data) -> String? {
        guard !data.isEmpty,
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any] else {
            return nil
        }
        let errorValue = (dict["error"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let value = errorValue, !value.isEmpty,
           !["failed", "fail", "error"].contains(value.lowercased()) {
            return value
        }
        if let value = dict["message"] as? String, !value.isEmpty {
            return value
        }
        if let values = dict["errors"] as? [String], !values.isEmpty {
            return values.joined(separator: "；")
        }
        if let value = dict["reason_code"] as? String, !value.isEmpty {
            return friendlyReasonCode(value)
        }
        if let value = errorValue, !value.isEmpty {
            if ["failed", "fail", "error"].contains(value.lowercased()) {
                return "操作没有完成。请点“查看日志”，把最近一次失败记录拿来排查。"
            }
            return value
        }
        if let value = dict["status"] as? String, !value.isEmpty {
            if ["failed", "fail", "partial", "rollback_failed", "recovery_failed"].contains(value.lowercased()) {
                return "操作没有完成。请点“查看日志”，把最近一次失败记录拿来排查。"
            }
            return value
        }
        return nil
    }

    private static func friendlyReasonCode(_ code: String) -> String {
        switch code {
        case "fix_verification_failed":
            return "修复命令已执行，但复查还没通过。请重新诊断；如果同一项仍然异常，按日志里的建议继续处理。"
        case "fix_command_failed":
            return "修复命令没有跑完。请点“查看日志”看最近一次失败原因。"
        case "fix_cancelled":
            return "你取消了这次修复，系统设置没有改变。"
        default:
            return code
        }
    }

    private func sessionToken() async throws -> String {
        if let token = apiToken {
            return token
        }
        throw APIError.runFailed("本地 API token 尚未从后端启动输出中解析。")
    }

    // MARK: - 业务接口

    func health() async throws -> APIHealthResponse {
        try await get(path: "health")
    }

    func serviceGroups() async throws -> ServiceGroupResponse {
        try await get(path: "services/groups")
    }

    func latestReport() async throws -> NetfixReport {
        try await get(path: "report/latest", timeout: 20)
    }

    func supportBundle() async throws -> SupportBundleResponse {
        try await get(path: "support/bundle", timeout: 20)
    }

    func events() async throws -> EventsResponse {
        try await get(path: "events", timeout: 20)
    }

    func logs() async throws -> LogsResponse {
        try await get(path: "logs", timeout: 20)
    }

    func environment() async throws -> EnvironmentResponse {
        try await get(path: "environment", timeout: 20)
    }

    func dashboardState() async throws -> DashboardStateResponse {
        try await get(path: "dashboard/state", timeout: 20)
    }

    func userFacingErrors() async throws -> UserFacingErrorsResponse {
        try await get(path: "user-facing/errors", timeout: 20)
    }

    func llmProviders() async throws -> LLMProvidersResponse {
        try await get(path: "llm/providers", timeout: 20)
    }

    func llmChainReadiness() async throws -> LLMChainReadinessResponse {
        try await get(path: "llm/chain-readiness", timeout: 20)
    }

    func llmSettings() async throws -> LLMSettingsResponse {
        try await get(path: "settings/llm", timeout: 20)
    }

    func importDeepSeekSidecarKey() async throws -> DeepSeekSidecarImportResponse {
        try await post(
            path: "llm/import-deepseek-sidecar-key",
            body: [
                "confirmation": "IMPORT_DEEPSEEK_SIDECAR_KEY",
                "api_key_account": "deepseek",
                "enable_llm": true,
            ],
            timeout: 20
        )
    }

    func privacySettings() async throws -> PrivacySettingsResponse {
        try await get(path: "settings/privacy", timeout: 20)
    }

    func proxyBridgeSettings() async throws -> ProxyBridgeSettingsResponse {
        try await get(path: "settings/proxy-bridge", timeout: 20)
    }

    func savePrivacySettings(logRetentionEnabled: Bool, logRetentionDays: Int, saveLatestReport: Bool, persistProxyIdentityReport: Bool) async throws -> PrivacySettingsSaveResponse {
        try await post(
            path: "settings/privacy",
            body: [
                "log_retention_enabled": logRetentionEnabled,
                "log_retention_days": logRetentionDays,
                "save_latest_report": saveLatestReport,
                "persist_proxy_identity_report": persistProxyIdentityReport,
            ],
            timeout: 20
        )
    }

    func saveProxyBridgeSettings(autoRestartEnabled: Bool, idleTimeout: Int = 0) async throws -> ProxyBridgeSettingsResponse {
        try await post(
            path: "settings/proxy-bridge",
            body: [
                "auto_restart_enabled": autoRestartEnabled,
                "idle_timeout": idleTimeout,
            ],
            timeout: 20
        )
    }

    func clearLogs() async throws -> LogsClearResponse {
        try await post(path: "logs/clear", body: ["latest_report": true, "events": true], timeout: 20)
    }

    func clearAllLocalData() async throws -> DataClearResponse {
        try await post(
            path: "data/clear",
            body: ["confirm": "DELETE_NETFIX_LOCAL_DATA", "keychain": true],
            timeout: 20
        )
    }

    func saveLLMSettings(
        enabled: Bool,
        provider: String,
        baseURL: String,
        model: String,
        apiKeyAccount: String,
        apiKey: String,
        redactionLevel: String,
        uploadConsent: String,
        fallbackEnabled: Bool,
        budgetEnabled: Bool,
        persistUsageLedger: Bool,
        maxRequestsPerHour: Int,
        maxImageRequestsPerHour: Int,
        imageQuestionEnabled: Bool
    ) async throws -> LLMSettingsResponse {
        var body: [String: Any] = [
            "enabled": enabled,
            "provider": provider,
            "base_url": baseURL,
            "model": model,
            "api_key_account": apiKeyAccount,
            "redaction_level": redactionLevel,
            "upload_consent": uploadConsent,
            "fallback": [
                "enabled": fallbackEnabled,
                "domestic_only": true,
                "include_custom": false,
                "include_global": false,
                "chain": ["deepseek", "moonshot_kimi", "minimax", "qwen"],
                "vision_chain": ["minimax", "moonshot_kimi", "qwen"],
            ],
            "budget": [
                "enabled": budgetEnabled,
                "persist_usage_ledger": persistUsageLedger,
                "max_requests_per_hour": maxRequestsPerHour,
                "max_image_requests_per_hour": maxImageRequestsPerHour,
                "cooldown_seconds_after_rate_limit": 300,
                "cooldown_seconds_after_quota": 3600,
            ],
            "features": [
                "explain": true,
                "repair_steps": true,
                "residential_proxy_guide": true,
                "image_question": imageQuestionEnabled,
            ],
        ]
        if !apiKey.isEmpty {
            body["api_key"] = apiKey
        }
        return try await post(path: "settings/llm", body: body, timeout: 20)
    }

    func testLLM(timeout: Int = 30) async throws -> LLMTestResponse {
        try await post(path: "llm/test", body: ["confirmation": "TEST_LLM_PROVIDER"], timeout: timeout)
    }

    func testLLMChain(timeout: Int = 60) async throws -> LLMChainTestResponse {
        try await post(
            path: "llm/chain-test",
            body: ["confirmation": "TEST_LLM_CHAIN", "mode": "all"],
            timeout: timeout
        )
    }

    func explainWithLLM(question: String = "", mode: String = "explain", uploadConfirmed: Bool = false, images: [String] = []) async throws -> LLMExplainAPIResponse {
        var body: [String: Any] = [
            "question": question,
            "mode": mode,
            "upload_confirmed": uploadConfirmed,
        ]
        if !images.isEmpty {
            body["images"] = images
        }
        return try await post(
            path: "explain_llm",
            body: body,
            timeout: 60
        )
    }

    func proxyProfiles() async throws -> ProxyProfilesResponse {
        try await get(path: "proxy/profiles", timeout: 20)
    }

    func proxyValidationTargets() async throws -> ProxyValidationTargetsResponse {
        try await get(path: "proxy/validation-targets", timeout: 20)
    }

    private func proxyProtocolBody(input: String, protocolHint: String = "auto") -> [String: Any] {
        var body: [String: Any] = ["input": input]
        if protocolHint != "auto" {
            body["protocol"] = protocolHint
        }
        return body
    }

    func parseProxy(input: String, protocolHint: String = "auto") async throws -> ProxyParseResponse {
        try await postDecodingClientError(path: "proxy/parse", body: proxyProtocolBody(input: input, protocolHint: protocolHint), timeout: 20)
    }

    func importProxyPreview(input: String, limit: Int = 50, protocolHint: String = "auto") async throws -> ProxyImportPreviewResponse {
        var body = proxyProtocolBody(input: input, protocolHint: protocolHint)
        body["limit"] = limit
        return try await postDecodingClientError(
            path: "proxy/import-preview",
            body: body,
            timeout: 20
        )
    }

    func validateProxy(input: String, timeout: Int = 10, includeIdentity: Bool = true, targetProfile: String = "baseline", protocolHint: String = "auto") async throws -> ProxyValidateResponse {
        var body = proxyProtocolBody(input: input, protocolHint: protocolHint)
        body["timeout"] = timeout
        body["include_identity"] = includeIdentity
        body["target_profile"] = targetProfile
        return try await postDecodingClientError(
            path: "proxy/validate",
            body: body,
            timeout: timeout
        )
    }

    func validateProxyProfile(profileID: String, timeout: Int = 10, includeIdentity: Bool = true, targetProfile: String = "baseline") async throws -> ProxyValidateResponse {
        try await postDecodingClientError(
            path: "proxy/profiles/\(profileID)/validate",
            body: ["timeout": timeout, "include_identity": includeIdentity, "target_profile": targetProfile],
            timeout: timeout
        )
    }

    func saveProxyProfile(input: String, startMonitor: Bool = true, targetProfile: String = "baseline", protocolHint: String = "auto") async throws -> ProxyProfileResponse {
        var body = proxyProtocolBody(input: input, protocolHint: protocolHint)
        body["start_monitor"] = startMonitor
        body["monitor_interval"] = 60
        body["timeout"] = 10
        body["target_profile"] = targetProfile
        return try await postDecodingClientError(
            path: "proxy/profiles",
            body: body,
            timeout: 20
        )
    }

    func replaceProxyProfile(profileID: String, input: String, startMonitor: Bool = true, targetProfile: String = "baseline", protocolHint: String = "auto") async throws -> ProxyProfileResponse {
        var body = proxyProtocolBody(input: input, protocolHint: protocolHint)
        body["start_monitor"] = startMonitor
        body["monitor_interval"] = 60
        body["timeout"] = 10
        body["target_profile"] = targetProfile
        return try await postDecodingClientError(
            path: "proxy/profiles/\(profileID)/replace",
            body: body,
            timeout: 20
        )
    }

    func applyProxyProfile(profileID: String, mode: String, confirmed: Bool = false, targetProfile: String = "baseline") async throws -> ProxyApplyResponse {
        var body: [String: Any] = ["mode": mode, "target_profile": targetProfile]
        if confirmed {
            body["confirmed"] = true
            body["confirmation"] = "APPLY_PROXY_PROFILE"
            body["verify"] = true
            body["rollback_on_verify_failure"] = true
        }
        return try await postDecodingClientError(path: "proxy/profiles/\(profileID)/apply", body: body, timeout: 30)
    }

    func applyProxyDryRun(profileID: String, mode: String = "system") async throws -> ProxyApplyPlan {
        try await postDecodingClientError(path: "proxy/profiles/\(profileID)/apply-dry-run", body: ["mode": mode], timeout: 15)
    }

    func exportProxyProfile(profileID: String, format: String = "all") async throws -> ProxyClientExportResponse {
        try await postDecodingClientError(
            path: "proxy/profiles/\(profileID)/export",
            body: ["format": format],
            timeout: 20
        )
    }

    func deleteProxyProfile(profileID: String) async throws -> ProxyProfileDeleteResponse {
        try await postDecodingClientError(
            path: "proxy/profiles/\(profileID)/delete",
            body: [:],
            timeout: 20
        )
    }

    func rollbackProxyProfile(confirmed: Bool = true) async throws -> ProxyRollbackResponse {
        var body: [String: Any] = [:]
        if confirmed {
            body["confirmed"] = true
            body["confirmation"] = "ROLLBACK_PROXY_PROFILE"
        }
        return try await postDecodingClientError(path: "proxy/profiles/rollback", body: body, timeout: 30)
    }

    func proxyMonitor() async throws -> ProxyMonitorResponse {
        try await get(path: "proxy/monitor", timeout: 20)
    }

    func proxyBridge() async throws -> ProxyBridgeResponse {
        try await get(path: "proxy/bridge", timeout: 20)
    }

    func recoverProxyBridge(confirmed: Bool = true) async throws -> ProxyApplyResponse {
        var body: [String: Any] = [:]
        if confirmed {
            body["confirmed"] = true
            body["confirmation"] = "RESTORE_STALE_PROXY_BRIDGE"
        }
        return try await postDecodingClientError(path: "proxy/bridge/recover", body: body, timeout: 30)
    }

    func startProxyMonitor(profileID: String, interval: Int = 60, timeout: Int = 10, targetProfile: String = "baseline") async throws -> ProxyMonitorResponse {
        try await post(
            path: "proxy/monitor/start",
            body: ["profile_id": profileID, "interval": interval, "timeout": timeout, "target_profile": targetProfile],
            timeout: timeout
        )
    }

    func stopProxyMonitor() async throws -> ProxyMonitorResponse {
        try await post(path: "proxy/monitor/stop", body: [:], timeout: 20)
    }

    func startRunJob(command: [String], timeout: Int) async throws -> String {
        let response: APIRunResponse = try await post(
            path: "run",
            body: ["command": command, "timeout": timeout, "async": true],
            timeout: 20
        )
        if let jobID = response.jobId {
            return jobID
        }
        throw APIError.runFailed(response.error ?? "后台任务没有返回 job_id")
    }

    func jobStatus(jobID: String) async throws -> APIJobResponse {
        try await get(path: "jobs/\(jobID)", timeout: 20)
    }

    func cancelJob(jobID: String) async throws -> APIJobResponse {
        try await postDecodingClientError(path: "jobs/\(jobID)/cancel", body: [:], timeout: 20)
    }

    func diagnose(timeout: Int = 120) async throws -> NetfixReport {
        let response: APIRunResponse = try await post(
            path: "run",
            body: ["command": ["doctor"], "timeout": timeout],
            timeout: timeout
        )
        if let report = response.result {
            return report
        }
        throw APIError.runFailed(response.error ?? "未知错误")
    }

    func checkServices(group: String, timeout: Int = 90) async throws -> NetfixReport {
        let response: APIRunResponse = try await post(
            path: "run",
            body: ["command": ["services", "--group", group], "timeout": timeout],
            timeout: timeout
        )
        if let report = response.result {
            return report
        }
        throw APIError.runFailed(response.error ?? "未知错误")
    }

    func executeFix(fixId: String, timeout: Int = 120) async throws -> NetfixReport {
        let response: NetfixReport = try await post(
            path: "fixes/execute",
            body: [
                "fix_id": fixId,
                "confirmed": true,
                "confirmation": "APPLY_SYSTEM_FIX",
                "timeout": timeout,
            ],
            timeout: timeout
        )
        return response
    }

    func rollback(timeout: Int = 30) async throws -> NetfixReport {
        let response: APIRunResponse = try await post(
            path: "run",
            body: ["command": ["rollback"], "timeout": timeout],
            timeout: timeout
        )
        if let report = response.result {
            return report
        }
        throw APIError.runFailed(response.error ?? "未知错误")
    }
}

enum APIError: Error, Equatable {
    case invalidResponse
    case httpStatus(Int, String?)
    case emptyResponse
    case decodeFailed(String)
    case runFailed(String)
}

extension APIError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "无效的服务器响应"
        case .httpStatus(let code, let detail):
            if let friendly = Self.friendlyHTTPError(code: code, detail: detail) {
                return friendly
            }
            if let detail, !detail.isEmpty {
                return "HTTP 错误 \(code)：\(detail)"
            }
            return "HTTP 错误 \(code)"
        case .emptyResponse:
            return "服务器返回空数据"
        case .decodeFailed(let reason):
            return "解析失败：\(reason)"
        case .runFailed(let reason):
            return "执行失败：\(reason)"
        }
    }

    private static func friendlyHTTPError(code: Int, detail: String?) -> String? {
        let lower = (detail ?? "").lowercased()
        if lower.contains("missing api key") || lower.contains("missing_api_key") {
            return "还没配置 AI：这只影响 AI 看报告，不影响诊断和代理部署。需要 AI 时，到设置里选择供应商并粘贴 API Key。"
        }
        if lower.contains("cloud ai explanation is disabled") || lower.contains("llm_disabled") {
            return "AI 还没启用：打开设置里的 AI，启用后粘贴 API Key 并保存测试。"
        }
        if lower.contains("auth_failed") || lower.contains("unauthorized") || lower.contains("forbidden") || lower.contains("invalid api key") {
            return "API Key 验证失败：请检查供应商后台复制的 Key 是否完整，保存后再测试。"
        }
        if lower.contains("model_not_found") || lower.contains("model") && lower.contains("not found") {
            return "当前模型不可用：请在 AI 设置里换一个预设供应商，或检查高级模型名。"
        }
        if lower.contains("quota") || lower.contains("billing") || lower.contains("balance") {
            return "供应商额度或账单不可用：请到供应商后台检查余额、额度或套餐状态。"
        }
        if lower.contains("rate_limited") || lower.contains("rate limit") || code == 429 {
            return "供应商暂时限流：稍后再试，或换一个已配置的 AI 供应商。"
        }
        if lower.contains("image_question_disabled") {
            return "截图问 AI 还没开启：到 AI 设置里打开“允许带截图问 AI”后保存。"
        }
        if code == 502 {
            return "AI 供应商暂时没有返回可用结果：请稍后再试，或在 AI 设置里测试连接。"
        }
        return nil
    }
}
