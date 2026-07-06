import XCTest
@testable import Netfix

final class NetfixTests: XCTestCase {
    /// 验证后端可执行文件路径解析不为空。
    func testBackendPathResolution() {
        let path = Backend.backendPath
        XCTAssertNotNil(path, "backendPath 不应为空")
        XCTAssertTrue(path?.hasSuffix("netfix.py") == true, "应指向 netfix.py 文件")
    }

    /// 验证 APIClient 能够正确解码 netfix 诊断报告 JSON。
    func testReportJSONDecoding() throws {
        let json = """
        {
            "meta": { "version": "0.2.0", "timestamp": "2026-06-18T07:15:00" },
            "environment": {
                "gui_client": "netfix-mac",
                "active_core": "clash",
                "mixed_port": 7890,
                "system_proxy": { "http": "127.0.0.1:7890", "https": "127.0.0.1:7890", "socks": null }
            },
            "diagnostics": [
                { "name": "gateway", "status": "ok" },
                { "name": "dns_resolver", "status": "warn" },
                { "name": "openai_api", "status": "fail", "proxy_used": "clash" }
            ],
            "root_causes": [
                { "description": "当前节点 IP 被风控", "confidence": 0.85 }
            ],
            "fixes": [
                { "id": "switch_node", "description": "切换到健康节点", "tier": 2, "command": "python3 netfix.py proxy-switch" }
            ],
            "manual_steps": []
        }
        """.data(using: .utf8)!

        let report = try JSONDecoder().decode(NetfixReport.self, from: json)
        XCTAssertEqual(report.meta?.version, "0.2.0")
        XCTAssertEqual(report.diagnostics.count, 3)
        XCTAssertEqual(report.overallStatus, .fail)
        XCTAssertEqual(report.summaryHeadline, "检测到 1 个问题")
        XCTAssertEqual(report.firstRootCause, "当前节点 IP 被风控")
        XCTAssertEqual(report.diagnostics[2].proxyUsed, "clash")
    }

    /// 验证服务分组 JSON 解码。
    func testServiceGroupDecoding() throws {
        let json = """
        {
            "version": "0.2.0",
            "groups": [
                {
                    "id": "ai",
                    "name": "AI / 大模型",
                    "services": [
                        { "id": "openai_api", "name": "OpenAI API", "url": "https://api.openai.com", "path": "/v1/models", "expect": 200 }
                    ]
                }
            ]
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(ServiceGroupResponse.self, from: json)
        XCTAssertEqual(response.groups.count, 1)
        XCTAssertEqual(response.groups.first?.services.first?.name, "OpenAI API")
    }

    func testIPv6FallbackTextIsNotClassifiedAsConfirmedLeak() {
        let card = UserFacingMessages.classify("proxy active and IPv6 default route present; no public IPv6 observed")
        XCTAssertEqual(card.code, UserFacingErrorCode.ipv6FallbackRisk.rawValue)
        XCTAssertNotEqual(card.code, UserFacingErrorCode.ipv6LeakConfirmed.rawValue)
    }

    func testIPv6FallbackHTTPErrorUsesWarningCopy() {
        let detail = "修复命令已执行，但复查还没通过：ipv6_leak 仍有风险。看到的情况：proxy active and IPv6 default route present; no public IPv6 observed"
        let message = APIError.httpStatus(400, detail).localizedDescription

        XCTAssertTrue(message.contains("没有检测到公网 IPv6"))
        XCTAssertTrue(message.contains("不用反复点修复按钮"))
        XCTAssertFalse(message.contains("HTTP 错误 400"))
        XCTAssertFalse(message.contains("ipv6_leak"))
    }

    func testLLMProviderAndSettingsDecoding() throws {
        let providersJSON = """
        {
            "ok": true,
            "providers": [
                {
                    "id": "deepseek",
                    "label": "DeepSeek",
                    "base_url": "https://api.deepseek.com",
                    "model": "deepseek-v4-flash",
                    "openai_compatible": true,
                    "supports_vision": false,
                    "market": "domestic",
                    "cost_tier": "low",
                    "text_explain_ready": false,
                    "image_question_provider_supported": false,
                    "image_question_ready": false,
                    "netfix_mode": "text_report_only"
                }
            ]
        }
        """.data(using: .utf8)!
        let providers = try JSONDecoder().decode(LLMProvidersResponse.self, from: providersJSON)
        XCTAssertEqual(providers.providers.first?.id, "deepseek")
        XCTAssertEqual(providers.providers.first?.baseURL, "https://api.deepseek.com")

        let settingsJSON = """
        {
            "ok": true,
            "settings": {
                "enabled": false,
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "api_key_account": "deepseek",
                "api_key_set": false,
                "redaction_level": "balanced",
                "upload_consent": "ask_each_time",
                "fallback": {
                    "enabled": true,
                    "domestic_only": true,
                    "include_custom": false,
                    "include_global": false,
                    "chain": ["deepseek", "moonshot_kimi", "minimax", "qwen"],
                    "vision_chain": ["minimax", "moonshot_kimi", "qwen"]
                }
            }
        }
        """.data(using: .utf8)!
        let settings = try JSONDecoder().decode(LLMSettingsResponse.self, from: settingsJSON)
        XCTAssertEqual(settings.settings.provider, "deepseek")
        XCTAssertFalse(settings.settings.apiKeySet)
        XCTAssertEqual(settings.settings.fallback?.chain, ["deepseek", "moonshot_kimi", "minimax", "qwen"])
        XCTAssertEqual(settings.settings.fallback?.visionChain, ["minimax", "moonshot_kimi", "qwen"])
    }

    func testLogsAndProxyResponseDecoding() throws {
        let logsJSON = """
        {
            "ok": true,
            "journal_dir": "/Users/test/.netfix",
            "latest_report_path": "/Users/test/.netfix/last_report.json",
            "latest_report_exists": true,
            "latest_report_summary": { "timestamp": "2026-06-24T00:00:00Z", "headline": "网络看起来正常" },
            "events": [
                { "timestamp": "2026-06-24T00:00:00Z", "type": "report", "status": "ok", "headline": "网络看起来正常", "root_cause": null }
            ]
        }
        """.data(using: .utf8)!
        let logs = try JSONDecoder().decode(LogsResponse.self, from: logsJSON)
        XCTAssertEqual(logs.events.count, 1)
        XCTAssertEqual(logs.latestReportSummary?.headline, "网络看起来正常")

        let proxyJSON = """
        {
            "ok": false,
            "profile": {
                "id": "p1",
                "name": "proxy-http",
                "protocol": "http",
                "host": "proxy.example.com",
                "port": 8080,
                "username": "user",
                "credential_ref": "keychain://netfix.proxy/p1",
                "password_set": true
            },
            "redacted_url": "http://user:***@proxy.example.com:8080",
            "credential_present": true,
            "warnings": [],
            "errors": ["dns_failed"]
        }
        """.data(using: .utf8)!
        let proxy = try JSONDecoder().decode(ProxyParseResponse.self, from: proxyJSON)
        XCTAssertEqual(proxy.profile?.protocolName, "http")
        XCTAssertEqual(proxy.redactedURL, "http://user:***@proxy.example.com:8080")

        let importPreviewJSON = """
        {
            "ok": true,
            "schema_version": "netfix_proxy_import_preview.v1",
            "summary": {
                "input_line_count": 3,
                "processed_count": 2,
                "skipped_count": 1,
                "valid_count": 1,
                "invalid_count": 1,
                "ready_count": 1,
                "limited_count": 0
            },
            "truncated": false,
            "recommendation": {
                "line_number": 2,
                "redacted_url": "http://user:***@proxy.example.com:8080",
                "status": "ready",
                "headline": "可系统应用"
            },
            "candidates": [
                {
                    "line_number": 2,
                    "ok": true,
                    "redacted_url": "http://user:***@proxy.example.com:8080",
                    "credential_present": true,
                    "deployment_decision": {
                        "schema_version": "netfix_proxy_deployment_decision.v1",
                        "status": "ready",
                        "headline": "可系统应用",
                        "system_apply": {
                            "status": "bridge_required",
                            "reason_code": "authenticated_http_bridge_required",
                            "requires_netfix_running": true
                        }
                    },
                    "warnings": [],
                    "errors": [],
                    "profile": {
                        "id": "p1",
                        "name": "proxy-http",
                        "protocol": "http",
                        "host": "proxy.example.com",
                        "port": 8080,
                        "username": "user",
                        "password_set": true
                    }
                },
                {
                    "line_number": 3,
                    "ok": false,
                    "redacted_url": "",
                    "credential_present": false,
                    "warnings": [],
                    "errors": ["host is required"]
                }
            ],
            "warnings": ["预检结果只返回脱敏 URL 和部署决策，不会回显供应商密码。"]
        }
        """.data(using: .utf8)!
        let importPreview = try JSONDecoder().decode(ProxyImportPreviewResponse.self, from: importPreviewJSON)
        XCTAssertEqual(importPreview.schemaVersion, "netfix_proxy_import_preview.v1")
        XCTAssertEqual(importPreview.summary.validCount, 1)
        XCTAssertEqual(importPreview.recommendation?.lineNumber, 2)
        XCTAssertEqual(importPreview.candidates.first?.redactedURL, "http://user:***@proxy.example.com:8080")
        XCTAssertEqual(importPreview.candidates.first?.deploymentDecision?.systemApply?.reasonCode, "authenticated_http_bridge_required")

        let validateJSON = """
        {
            "ok": true,
            "proxy_check": {
                "profile_id": "p1",
                "status": "ok",
                "auth": "ok",
                "tcp": "ok",
                "target": "https://www.gstatic.com/generate_204",
                "http_code": 204,
                "latency_ms": 42,
                "checked_via": "http://user:***@proxy.example.com:8080"
            },
            "identity_report": {
                "status": "warn",
                "exit_ip": "203.0.113.10",
                "identity": {
                    "country_code": "US",
                    "isp": "Example ISP",
                    "asn": "AS64500 Example",
                    "ip_type": "residential"
                },
                "expected_geo": { "status": "ok", "mismatches": [] },
                "dns_leak": { "status": "unknown", "confidence": "heuristic" },
                "ipv6_leak": { "status": "unknown", "confidence": "not_tested" },
                "targets": [
                    { "id": "google_204", "target": "https://www.gstatic.com/generate_204", "status": "ok", "http_code": 204, "latency_ms": 31 }
                ],
                "warnings": ["IP 类型无法可靠判断"]
            }
        }
        """.data(using: .utf8)!
        let validate = try JSONDecoder().decode(ProxyValidateResponse.self, from: validateJSON)
        XCTAssertEqual(validate.identityReport?.exitIP, "203.0.113.10")
        XCTAssertEqual(validate.identityReport?.identity?.ipType, "residential")

        let monitorJSON = """
        {
            "ok": true,
            "monitor": {
                "running": true,
                "profile_id": "p1",
                "profile_name": "proxy-http",
                "interval": 60,
                "target_url": "https://www.gstatic.com/generate_204",
                "timeout": 10,
                "run_count": 2,
                "thread_alive": true,
                "restored": true,
                "persisted": {
                    "enabled": true,
                    "profile_id": "p1",
                    "interval": 60,
                    "target_url": "https://www.gstatic.com/generate_204",
                    "timeout": 10,
                    "updated_at": "2026-06-24T00:00:00Z"
                }
            }
        }
        """.data(using: .utf8)!
        let monitor = try JSONDecoder().decode(ProxyMonitorResponse.self, from: monitorJSON)
        XCTAssertTrue(monitor.monitor?.restored == true)
        XCTAssertTrue(monitor.monitor?.persisted?.enabled == true)
    }

    func testProxyBridgeStartupAutoRestartDecoding() throws {
        let settingsJSON = """
        {
            "ok": true,
            "settings": {
                "auto_restart_enabled": true,
                "idle_timeout": 30,
                "updated_at": "2026-06-24T00:00:00Z"
            }
        }
        """.data(using: .utf8)!
        let settings = try JSONDecoder().decode(ProxyBridgeSettingsResponse.self, from: settingsJSON)
        XCTAssertTrue(settings.settings.autoRestartEnabled)
        XCTAssertEqual(settings.settings.idleTimeout, 30)

        let bridgeJSON = """
        {
            "ok": true,
            "bridges": [
                {
                    "id": "new",
                    "listen_host": "127.0.0.1",
                    "listen_port": 19080,
                    "upstream_protocol": "http",
                    "upstream_host": "proxy.example.com",
                    "upstream_port": 8000,
                    "request_count": 0,
                    "active_connections": 0,
                    "recent_clients": []
                }
            ],
            "startup_check": {
                "schema_version": "netfix_proxy_bridge_startup_check.v1",
                "checked_at": "2026-06-24T00:00:00Z",
                "ok": true,
                "bridges_count": 1,
                "settings": {
                    "auto_restart_enabled": true,
                    "idle_timeout": 30,
                    "updated_at": ""
                },
                "auto_restart": {
                    "ok": true,
                    "status": "restarted",
                    "restart_available": false,
                    "profile_id": "p1",
                    "network_service": "Wi-Fi",
                    "system_proxy_changed": false,
                    "bridge": {
                        "id": "new",
                        "listen_host": "127.0.0.1",
                        "listen_port": 19080
                    }
                },
                "lifecycle": {
                    "schema_version": "netfix_proxy_bridge_lifecycle.v1",
                    "status": "running_system",
                    "headline": "系统代理桥接运行中",
                    "requires_netfix_running": true
                }
            }
        }
        """.data(using: .utf8)!
        let bridge = try JSONDecoder().decode(ProxyBridgeResponse.self, from: bridgeJSON)
        XCTAssertEqual(bridge.startupCheck?.autoRestart?.status, "restarted")
        XCTAssertFalse(bridge.startupCheck?.autoRestart?.systemProxyChanged ?? true)
        XCTAssertTrue(bridge.startupCheck?.settings?.autoRestartEnabled == true)
        XCTAssertEqual(bridge.startupCheck?.autoRestart?.bridge?.listenPort, 19080)
    }

    func testProxyClientPackageExportDecoding() throws {
        let json = """
        {
            "ok": true,
            "profile_id": "p1",
            "profile_name": "proxy",
            "format": "all",
            "redacted_url": "socks5h://user:***@proxy.example.com:1080",
            "snippets": {
                "sing-box": {
                    "label": "sing-box outbound JSON snippet",
                    "content": "{\\"password\\":\\"<password>\\"}",
                    "secret_placeholder": true
                }
            },
            "package": {
                "schema_version": "netfix_proxy_client_package.v1",
                "name": "proxy",
                "recommended_format": "mihomo",
                "file_count": 2,
                "secret_placeholder": true,
                "files": [
                    {
                        "path": "README.md",
                        "format": "readme",
                        "label": "First-run instructions",
                        "content": "Replace <password>",
                        "secret_placeholder": false
                    },
                    {
                        "path": "proxy.sing-box.json",
                        "format": "sing-box",
                        "label": "sing-box outbound JSON snippet",
                        "content": "{\\"password\\":\\"<password>\\"}",
                        "secret_placeholder": true
                    }
                ]
            },
            "warnings": ["不会返回 Keychain 密码"]
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(ProxyClientExportResponse.self, from: json)
        XCTAssertEqual(response.package?.schemaVersion, "netfix_proxy_client_package.v1")
        XCTAssertEqual(response.package?.recommendedFormat, "mihomo")
        XCTAssertEqual(response.package?.files?.count, 2)
        XCTAssertEqual(response.package?.files?.last?.path, "proxy.sing-box.json")
        XCTAssertTrue(response.package?.files?.last?.secretPlaceholder == true)
    }
}
