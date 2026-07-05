import Foundation

/// Mirror of `netfix/user_facing_errors.py` so Swift UI and Python backend
/// always agree on what a reason code means. Keep this list in sync with the
/// Python module — the canonical codes are documented there.
enum UserFacingErrorCode: String, CaseIterable {
    case proxyAuthFailed = "proxy_auth_failed"
    case proxyAuthRequired = "proxy_auth_required"
    case proxyUnreachable = "proxy_unreachable"
    case dnsFailed = "dns_failed"
    case timeout
    case systemProxyNotSet = "system_proxy_not_set"
    case systemProxyRecoveryRequired = "system_proxy_recovery_required"
    case autoProxyPacConflict = "auto_proxy_pac_conflict"
    case ipv6LeakConfirmed = "ipv6_leak_confirmed"
    case ipv6FallbackRisk = "ipv6_fallback_risk"
    case dnsLeakDetected = "dns_leak_detected"
    case unsupportedInputFormat = "unsupported_input_format"
    case missingRequiredField = "missing_required_field"
    case fixCancelled = "fix_cancelled"
    case fixVerificationFailed = "fix_verification_failed"
    case fixCommandFailed = "fix_command_failed"
    case backendUnreachable = "backend_unreachable"
    case decodeFailed = "decode_failed"
    case keychainFailed = "keychain_failed"
    case permissionDenied = "permission_denied"
    case llmDisabled = "llm_disabled"
    case missingAPIKey = "missing_api_key"
}

struct UserFacingMessage {
    let code: String
    let headline: String
    let nextStep: String
    let technical: String?

    var combined: String {
        if let technical, !technical.isEmpty {
            return "\(headline)\n\(nextStep)"
        }
        return "\(headline)\n\(nextStep)"
    }
}

enum UserFacingMessages {
    /// Returned message for a known reason code, or `nil` when we should fall
    /// back to free-text classification via ``classify(_:)``.
    static func lookup(_ code: String?) -> UserFacingMessage? {
        guard let raw = code, let mapped = UserFacingErrorCode(rawValue: raw) else { return nil }
        return table[mapped]
    }

    static func classify(_ text: String?) -> UserFacingMessage {
        guard let text, !text.isEmpty else { return unknownCard() }
        let lower = text.lowercased()

        if lower.contains("407") || lower.contains("proxy auth") || lower.contains("auth_failed") || lower.contains("authentication") {
            return table[.proxyAuthFailed] ?? unknownCard()
        }
        if lower.contains("ss://") || lower.contains("vmess://") || lower.contains("subscription") || lower.contains("clash yaml") || lower.contains("不支持") {
            return table[.unsupportedInputFormat] ?? unknownCard()
        }
        if lower.contains("name or service not known") || lower.contains("name_not_resolved") || lower.contains("nodename") || lower.contains("dns") || lower.contains("getaddrinfo") {
            return table[.dnsFailed] ?? unknownCard()
        }
        if lower.contains("public ipv6") || lower.contains("leak_confirmed") {
            return table[.ipv6LeakConfirmed] ?? unknownCard()
        }
        if lower.contains("no public ipv6") || lower.contains("fallback_risk") || lower.contains("default route") {
            return table[.ipv6FallbackRisk] ?? unknownCard()
        }
        if lower.contains("connection refused") || lower.contains("no route") || lower.contains("host is down") || lower.contains("connect timeout") {
            return table[.proxyUnreachable] ?? unknownCard()
        }
        if lower.contains("timed out") || lower.contains("timeout") {
            return table[.timeout] ?? unknownCard()
        }
        if lower.contains("keychain") || lower.contains("errsecauth") {
            return table[.keychainFailed] ?? unknownCard()
        }
        if lower.contains("decode") || lower.contains("json") {
            return table[.decodeFailed] ?? unknownCard()
        }
        if lower.contains("401") {
            return UserFacingMessage(code: "http_401", headline: "本地服务要求登录或 token", nextStep: "重启 Netfix；问题持续就看日志。", technical: "HTTP 401")
        }
        if lower.contains("403") {
            return UserFacingMessage(code: "http_403", headline: "操作被拒绝（权限或来源）", nextStep: "按上面给的授权说明再试一次。", technical: "HTTP 403")
        }
        if lower.contains("404") {
            return UserFacingMessage(code: "http_404", headline: "本地服务没找到这条", nextStep: "可能接口改版；查看日志或更新 Netfix。", technical: "HTTP 404")
        }
        if lower.contains("502") {
            return UserFacingMessage(code: "http_502", headline: "本地服务链路失败", nextStep: "稍后重试；持续出错就查看日志。", technical: "HTTP 502")
        }
        return unknownCard(technical: text)
    }

    /// Return a card from an optional reason code, message, or HTTP status.
    static func render(code: String? = nil, message rawMessage: String? = nil, httpStatus: Int? = nil) -> UserFacingMessage {
        if let code, let entry = lookup(code) {
            return entry
        }
        if let rawMessage {
            return classify(rawMessage)
        }
        if let status = httpStatus {
            return classify("\(status)")
        }
        return unknownCard()
    }

    private static func unknownCard(technical: String = "") -> UserFacingMessage {
        UserFacingMessage(
            code: "unknown",
            headline: "出现了一个尚未分类的问题",
            nextStep: "可以重试或点「查看日志」给开发者。",
            technical: technical
        )
    }

    private static let table: [UserFacingErrorCode: UserFacingMessage] = [
        .proxyAuthFailed: UserFacingMessage(
            code: "proxy_auth_failed",
            headline: "代理账号或密码不对",
            nextStep: "回服务商后台重新复制完整的地址、端口、用户名和密码，再粘贴进来。",
            technical: "代理服务器返回 407 或认证失败。"
        ),
        .proxyAuthRequired: UserFacingMessage(
            code: "proxy_auth_required",
            headline: "代理需要账号密码，但你没填",
            nextStep: "回服务商后台找到用户名和密码，粘贴完整一行后重试。",
            technical: "HTTP 407。"
        ),
        .proxyUnreachable: UserFacingMessage(
            code: "proxy_unreachable",
            headline: "连不上代理服务器",
            nextStep: "确认地址、端口没抄错；也试试把服务商给的备用节点换一行粘进来。",
            technical: "TCP 或 HTTP 连接失败：connection refused / no route / connect timeout。"
        ),
        .dnsFailed: UserFacingMessage(
            code: "dns_failed",
            headline: "解析不到代理服务器的名字",
            nextStep: "可能是 DNS 暂时出问题；点重试，或把代理地址改成 IP 直连。",
            technical: "name resolution failure。"
        ),
        .timeout: UserFacingMessage(
            code: "timeout",
            headline: "网络太慢或代理没响应",
            nextStep: "等几秒再点重试；如果是 SOCKS5/HTTP 一直超时，看下是不是节点挂了。",
            technical: "请求在时间内没收到响应。"
        ),
        .systemProxyNotSet: UserFacingMessage(
            code: "system_proxy_not_set",
            headline: "系统代理没有切过去",
            nextStep: "到「部署代理」里点「开始使用这台 Mac 上网」，Netfix 会备份后帮你切。",
            technical: "macOS Network Service 的 Web/Secure Web/SOCKS 代理未启用。"
        ),
        .systemProxyRecoveryRequired: UserFacingMessage(
            code: "system_proxy_recovery_required",
            headline: "系统网络需要恢复",
            nextStep: "到「设置 → 代理 → 恢复原来的网络设置」点恢复。",
            technical: "Stale proxy bridge detected."
        ),
        .autoProxyPacConflict: UserFacingMessage(
            code: "auto_proxy_pac_conflict",
            headline: "手动代理和自动代理同时开着，App 启动容易卡住",
            nextStep: "打开 Netfix 设置，在代理区域关闭自动代理（PAC / WPAD），只留 Netfix 帮你设的代理。",
            technical: "Mixed PAC + manual proxy detected."
        ),
        .ipv6LeakConfirmed: UserFacingMessage(
            code: "ipv6_leak_confirmed",
            headline: "IPv6 可能正在绕过代理",
            nextStep: "打开 Netfix 设置，在代理区域关闭 IPv6；之后能完整走代理。",
            technical: "Confirmed IPv6 leak."
        ),
        .ipv6FallbackRisk: UserFacingMessage(
            code: "ipv6_fallback_risk",
            headline: "没有检测到 IPv6 泄漏，只是留了一条默认路由",
            nextStep: "一般可以继续用；如果某个 App 启动一直卡，再去处理 IPv6，不用反复点修复按钮。",
            technical: "ipv6_leak warn with no public IPv6."
        ),
        .dnsLeakDetected: UserFacingMessage(
            code: "dns_leak_detected",
            headline: "DNS 在泄漏你的真实位置",
            nextStep: "在代理客户端里开启 DNS 劫持/远程解析，或用 socks5h:// 让 SOCKS 代理解析域名。",
            technical: "DNS queries bypass the proxy."
        ),
        .unsupportedInputFormat: UserFacingMessage(
            code: "unsupported_input_format",
            headline: "目前不支持这种代理链接",
            nextStep: "请到服务商后台复制 HTTP 或 SOCKS5 的地址、端口、用户名和密码。",
            technical: "ss://、vmess:// 或 Clash 订阅链接暂不支持。"
        ),
        .missingRequiredField: UserFacingMessage(
            code: "missing_required_field",
            headline: "代理参数没写全",
            nextStep: "补齐地址、端口、用户名、密码后再粘贴。",
            technical: "host/port/username/password 不完整。"
        ),
        .fixCancelled: UserFacingMessage(
            code: "fix_cancelled",
            headline: "你刚才取消了",
            nextStep: "系统设置没改动；要继续时重新点对应按钮即可。",
            technical: "Tier 2 确认弹窗点了取消。"
        ),
        .fixVerificationFailed: UserFacingMessage(
            code: "fix_verification_failed",
            headline: "处理了一下，但还没完全好",
            nextStep: "再点一次诊断；如果仍然提示同一项，按下面手动步骤继续处理。",
            technical: "fix.executed ok，但 verify_diagnostic 仍非 ok。"
        ),
        .fixCommandFailed: UserFacingMessage(
            code: "fix_command_failed",
            headline: "修复没有跑完",
            nextStep: "重试一次；如果仍然失败，再点「查看日志」把最近一次失败记录拿来排查。",
            technical: "fix.executed[*].ok == false。"
        ),
        .backendUnreachable: UserFacingMessage(
            code: "backend_unreachable",
            headline: "Netfix 本地服务还没准备好",
            nextStep: "等几秒重试；如果一直是这个，退出 Netfix 再打开一次。",
            technical: "本地 HTTP API 没有响应或 token 校验失败；常见于本地服务未启动。"
        ),
        .decodeFailed: UserFacingMessage(
            code: "decode_failed",
            headline: "App 和本地服务没对上话",
            nextStep: "点「查看日志」记录错误；退出 Netfix 重开一次；仍然出错就到 GitHub 提 issue。",
            technical: "JSON 数据结构与客户端解码模型不一致。"
        ),
        .keychainFailed: UserFacingMessage(
            code: "keychain_failed",
            headline: "本机密码库写入失败",
            nextStep: "打开「系统设置 → 隐私与安全性 → 密码」授权 Netfix 访问；然后重新粘贴。",
            technical: "Keychain 写入失败。"
        ),
        .permissionDenied: UserFacingMessage(
            code: "permission_denied",
            headline: "macOS 没给 Netfix 权限",
            nextStep: "在「设置 → 权限」里点授权按钮，系统会弹窗让你同意。",
            technical: "TCC 权限被拒。"
        ),
        .llmDisabled: UserFacingMessage(
            code: "llm_disabled",
            headline: "AI 还没启用，不影响诊断",
            nextStep: "想让人话解释时，到「设置 → AI」启用并粘贴 Key。",
            technical: "settings.llm.enabled == false。"
        ),
        .missingAPIKey: UserFacingMessage(
            code: "missing_api_key",
            headline: "还没填 AI 密钥",
            nextStep: "到「设置 → AI」选供应商并粘贴 API Key。不填也能照常用诊断和代理部署。",
            technical: "keychain has no API key."
        ),
    ]
}