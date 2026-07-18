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

    func dashboardInsights() async throws -> DashboardInsightsResponse {
        try await get(path: "dashboard/insights", timeout: 25)
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

    func explainWithLLM(question: String = "", mode: String = "explain", uploadConfirmed: Bool = false, images: [String] = [], history: [[String: String]] = []) async throws -> LLMExplainAPIResponse {
        var body: [String: Any] = [
            "question": question,
            "mode": mode,
            "upload_confirmed": uploadConfirmed,
        ]
        if !images.isEmpty {
            body["images"] = images
        }
        if !history.isEmpty {
            body["history"] = history
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

    func saveProxyProfile(
        input: String,
        validationReceipt: String? = nil,
        startMonitor: Bool = true,
        targetProfile: String = "baseline",
        protocolHint: String = "auto"
    ) async throws -> ProxyProfileResponse {
        var body = proxyProtocolBody(input: input, protocolHint: protocolHint)
        if let validationReceipt, !validationReceipt.isEmpty {
            body["validation_receipt"] = validationReceipt
        }
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

    func replaceProxyProfile(
        profileID: String,
        input: String,
        validationReceipt: String? = nil,
        startMonitor: Bool = true,
        targetProfile: String = "baseline",
        protocolHint: String = "auto"
    ) async throws -> ProxyProfileResponse {
        var body = proxyProtocolBody(input: input, protocolHint: protocolHint)
        if let validationReceipt, !validationReceipt.isEmpty {
            body["validation_receipt"] = validationReceipt
        }
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

    func groupedProxyProfiles() async throws -> ProxyProfilesGroupedResponse {
        try await get(path: "proxy/profiles/grouped", timeout: 20)
    }

    func cleanupDuplicateProxyProfiles() async throws -> ProxyProfilesCleanupResponse {
        try await postDecodingClientError(
            path: "proxy/profiles/cleanup-dupes",
            body: [:],
            timeout: 30
        )
    }

    func renameProxyProfile(profileID: String, name: String) async throws -> ProxyProfileResponse {
        try await postDecodingClientError(
            path: "proxy/profiles/\(profileID)/rename",
            body: ["name": name],
            timeout: 15
        )
    }

    func rollbackProxyProfile(confirmed: Bool = false) async throws -> ProxyRollbackResponse {
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

    func networkActivitySettings() async throws -> NetworkActivitySettingsResponse {
        try await get(path: "settings/network-activity", timeout: 20)
    }

    func saveNetworkActivitySettings(
        enabled: Bool,
        interval: Int,
        processWhitelist: [NetworkActivityIgnoreRule]
    ) async throws -> NetworkActivitySettingsSaveResponse {
        try await post(
            path: "settings/network-activity",
            body: [
                "enabled": enabled,
                "interval": interval,
                "process_whitelist": processWhitelist.map { $0.apiBody() },
            ],
            timeout: 20
        )
    }

    func proxyBridge() async throws -> ProxyBridgeResponse {
        try await get(path: "proxy/bridge", timeout: 20)
    }

    func recoverProxyBridge(confirmed: Bool = false) async throws -> ProxyApplyResponse {
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

    func executeFix(fixId: String, timeout: Int = 120, confirmed: Bool = false) async throws -> NetfixReport {
        var body: [String: Any] = [
            "fix_id": fixId,
            "timeout": timeout,
        ]
        if confirmed {
            body["confirmed"] = true
            body["confirmation"] = "APPLY_SYSTEM_FIX"
        }
        let response: NetfixReport = try await post(
            path: "fixes/execute",
            body: body,
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

    // MARK: - P1-A / P1-B: 多轮对话 session / 主动告警 / 记忆

    /// 创建或延续一个 chat session；同一 symptom 下继续问答会复用同一 session。
    func createSession(symptomID: String? = nil, title: String? = nil) async throws -> ChatSessionDetailResponse {
        var body: [String: Any] = [:]
        if let symptomID, !symptomID.isEmpty { body["symptom_id"] = symptomID }
        if let title, !title.isEmpty { body["title"] = title }
        return try await post(path: "chat/sessions", body: body, timeout: 20)
    }

    /// 列出最近的 chat session。
    func listSessions(limit: Int = 20) async throws -> ChatSessionListResponse {
        try await get(path: "chat/sessions?limit=\(limit)", timeout: 20)
    }

    /// 取单条 session 和它的 turns。
    func getSession(sessionID: String) async throws -> ChatSessionDetailResponse {
        try await get(path: "chat/sessions/\(sessionID)", timeout: 20)
    }

    /// 把一轮 user/assistant 文本追加到 session。
    func appendTurn(
        sessionID: String,
        role: String,
        content: String,
        planSteps: [ChatStep]? = nil,
        observations: [ChatObservation]? = nil,
        rootCauseID: String? = nil,
        keyDiagnostics: [String]? = nil,
        providerUsed: String? = nil,
        redactedReportHash: String? = nil
    ) async throws -> ChatSessionActionResponse {
        var body: [String: Any] = [
            "role": role,
            "content": content,
        ]
        if let planSteps, !planSteps.isEmpty {
            body["plan_steps"] = planSteps.map { step -> [String: Any] in
                var dict: [String: Any] = ["tool": step.tool]
                if let label = step.label { dict["label"] = label }
                if let why = step.why { dict["why"] = why }
                if let status = step.status { dict["status"] = status }
                return dict
            }
        }
        if let observations, !observations.isEmpty {
            body["observations"] = observations.map { obs -> [String: Any] in
                var dict: [String: Any] = ["fact": obs.fact]
                if let confidence = obs.confidence { dict["confidence"] = confidence }
                if let source = obs.source { dict["source"] = source }
                return dict
            }
        }
        if let rootCauseID, !rootCauseID.isEmpty {
            body["root_cause_id"] = rootCauseID
        }
        if let keyDiagnostics, !keyDiagnostics.isEmpty {
            body["key_diagnostics"] = keyDiagnostics
        }
        if let providerUsed, !providerUsed.isEmpty {
            body["provider_used"] = providerUsed
        }
        if let redactedReportHash, !redactedReportHash.isEmpty {
            body["redacted_report_hash"] = redactedReportHash
        }
        return try await post(path: "chat/sessions/\(sessionID)/turns", body: body, timeout: 20)
    }

    /// 用户对 confirmation_request 做出确认或拒绝。
    func confirm(sessionID: String, turnID: String, decision: String, requestID: String? = nil) async throws -> ChatSessionActionResponse {
        var body: [String: Any] = ["turn_id": turnID, "decision": decision]
        if let requestID, !requestID.isEmpty { body["request_id"] = requestID }
        return try await post(path: "chat/sessions/\(sessionID)/confirm", body: body, timeout: 20)
    }

    /// 标记某个概念已经被解释过（用于去重「又解释一次相同概念」）。
    func markConceptExplained(sessionID: String, conceptKey: String) async throws -> ChatSessionActionResponse {
        try await post(
            path: "chat/sessions/\(sessionID)/concepts",
            body: ["concept_key": conceptKey],
            timeout: 20
        )
    }

    /// 决定一个 proactive alert 是立即处理 / 这次忽略 / 永久关闭。
    func decide(alertID: String, action: String, cooldownSeconds: Int? = nil) async throws -> ProactiveAlertListResponse {
        var body: [String: Any] = ["action": action]
        if let cooldownSeconds { body["cooldown_seconds"] = cooldownSeconds }
        return try await postDecodingClientError(path: "alerts/\(alertID)/decide", body: body, timeout: 20)
    }

    /// 删除一个 chat session（前端「清空对话」按钮）。
    func deleteSession(sessionID: String) async throws -> ChatSessionActionResponse {
        try await postDecodingClientError(path: "chat/sessions/\(sessionID)/delete", body: [:], timeout: 20)
    }

    /// 拉取当前的主动告警。
    func listProactiveAlerts(includeDismissed: Bool = false) async throws -> ProactiveAlertListResponse {
        let suffix = includeDismissed ? "?include_dismissed=1" : ""
        return try await get(path: "alerts\(suffix)", timeout: 20)
    }

    /// 关闭某条告警（用户主动忽略）。
    func dismissAlert(alertID: String) async throws -> ProactiveAlertListResponse {
        try await postDecodingClientError(path: "alerts/\(alertID)/dismiss", body: [:], timeout: 20)
    }

    /// 给某条告警设置冷却时间。
    func cooldownAlert(alertID: String, seconds: Int) async throws -> ProactiveAlertListResponse {
        try await postDecodingClientError(path: "alerts/\(alertID)/cooldown", body: ["seconds": seconds], timeout: 20)
    }

    /// 拉取长期记忆条目。
    func listMemory(kind: String? = nil, limit: Int = 50) async throws -> MemoryListResponse {
        var query = "?limit=\(limit)"
        if let kind, !kind.isEmpty { query += "&kind=\(kind)" }
        return try await get(path: "memory\(query)", timeout: 20)
    }

    /// 写入一条记忆（事实 / 偏好 / 忽略过的告警）。
    func appendMemory(kind: String, summary: String, detail: String? = nil, reference: String? = nil, weight: Double = 1.0) async throws -> MemoryListResponse {
        var body: [String: Any] = [
            "memory_kind": kind,
            "summary": summary,
            "weight": weight,
        ]
        if let detail, !detail.isEmpty { body["detail"] = detail }
        if let reference, !reference.isEmpty { body["reference"] = reference }
        return try await post(path: "memory", body: body, timeout: 20)
    }

    /// 衰减某条记忆的权重（用于「这条记忆很久没用了」）。
    func decayMemory(memoryID: String, factor: Double = 0.5) async throws -> MemoryListResponse {
        try await postDecodingClientError(path: "memory/\(memoryID)/decay", body: ["factor": factor], timeout: 20)
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
            return "还没配置 AI：这只影响 AI 看报告，不影响检查网络和使用代理。需要 AI 时，到设置里选择供应商并填写 AI 密钥。"
        }
        if lower.contains("cloud ai explanation is disabled") || lower.contains("llm_disabled") {
            return "AI 还没启用：打开设置里的 AI，启用后填写 AI 密钥并保存测试。"
        }
        if lower.contains("auth_failed") || lower.contains("unauthorized") || lower.contains("forbidden") || lower.contains("invalid api key") || lower.contains("invalid authentication") {
            return "AI 密钥验证失败：请检查从供应商后台复制的内容是否完整，保存后再测试。"
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
        if lower.contains("no public ipv6") || lower.contains("fallback_risk") || lower.contains("proxy active and ipv6 default route present") {
            return "没有检测到公网 IPv6。系统保留了一条 IPv6 默认路由，一般可以继续用；如果某个 App 启动一直卡，再处理 IPv6，不用反复点修复按钮。"
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
