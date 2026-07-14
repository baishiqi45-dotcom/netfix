import Foundation

struct ProxySetupResult {
    let parsed: ProxyParseResponse
    let validation: ProxyValidateResponse
    let saveResponse: ProxyProfileResponse
    let savedProfile: ProxyProfile
}

enum ProxySetupWorkflowError: LocalizedError {
    case emptyInput
    case parseFailed(String)
    case validationFailed(String)
    case missingValidationReceipt
    case saveFailed(String)
    case savedProfileNotVerified

    var errorDescription: String? {
        switch self {
        case .emptyInput:
            return "请先粘贴完整的代理参数。"
        case .parseFailed(let detail):
            return "这行参数无法识别：\(detail)"
        case .validationFailed(let detail):
            return "这组代理没通过检查：\(detail)"
        case .missingValidationReceipt:
            return "检查结果已失效，请重新检查后再保存。"
        case .saveFailed(let detail):
            return "无法保存这组代理：\(detail)"
        case .savedProfileNotVerified:
            return "保存后的代理未标记为可用，已停止后续启用。"
        }
    }
}

struct ProxySetupWorkflow {
    let client: APIClient

    func validateAndSave(
        input: String,
        protocolHint: String,
        targetProfile: String,
        startMonitor: Bool
    ) async throws -> ProxySetupResult {
        let normalized = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else {
            throw ProxySetupWorkflowError.emptyInput
        }

        let parsed = try await client.parseProxy(input: normalized, protocolHint: protocolHint)
        guard parsed.ok else {
            throw ProxySetupWorkflowError.parseFailed(parsed.errors?.joined(separator: "、") ?? "格式不正确")
        }

        let validation = try await client.validateProxy(
            input: normalized,
            timeout: 10,
            includeIdentity: true,
            targetProfile: targetProfile,
            protocolHint: protocolHint
        )
        guard validation.ok, validation.proxyCheck?.status == "ok" else {
            let detail = validation.errors?.joined(separator: "、")
                ?? validation.proxyCheck?.error
                ?? "地址、账号或网络不可用"
            throw ProxySetupWorkflowError.validationFailed(detail)
        }
        guard let receipt = validation.validationReceipt, !receipt.isEmpty else {
            throw ProxySetupWorkflowError.missingValidationReceipt
        }

        let saveResponse = try await client.saveProxyProfile(
            input: normalized,
            validationReceipt: receipt,
            startMonitor: startMonitor,
            targetProfile: targetProfile,
            protocolHint: protocolHint
        )
        guard saveResponse.ok, let profile = saveResponse.profile else {
            throw ProxySetupWorkflowError.saveFailed(saveResponse.error ?? "保存未完成")
        }
        guard profile.verificationStatus == "verified", profile.canApply == true else {
            throw ProxySetupWorkflowError.savedProfileNotVerified
        }

        return ProxySetupResult(
            parsed: parsed,
            validation: validation,
            saveResponse: saveResponse,
            savedProfile: profile
        )
    }
}
