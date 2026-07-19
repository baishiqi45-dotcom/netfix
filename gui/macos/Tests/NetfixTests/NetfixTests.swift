import XCTest
@testable import Netfix

final class NetfixTests: XCTestCase {
    func testDashboardStateContractDecodingAndCTAVisibility() throws {
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v1",
            "decision": {
                "ui_state": "network_recovery",
                "effective_route": "recovery_required",
                "severity": "fail",
                "primary_action": "recover_system_proxy",
                "reason_codes": ["bridge_needs_recovery"],
                "headline": "系统网络需要恢复",
                "next_step": "点恢复原来的网络设置。",
                "requires_confirmation": true
            },
            "machine": {
                "platform": "darwin",
                "primary_interface": "en0",
                "self_ipv4": "192.168.1.10",
                "gateway": "192.168.1.1",
                "has_ipv6_default_route": true
            },
            "proxy": {
                "saved": { "count": 1, "selected_profile_id": "p1" },
                "system": { "active": true, "kind": "http_https", "redacted": {}, "network_service": "Wi-Fi" },
                "bridge": { "lifecycle_status": "recovery_required", "in_use": false, "needs_recovery": true, "recovery_available": true, "profile_id": "p1" },
                "applied": { "active": false, "owner": "netfix", "profile_id": "p1", "via": "system_proxy" },
                "verified": { "status": "unknown", "checked_at": null, "source": "none" }
            },
            "egress": { "status": "unchecked", "cached": false },
            "last_report_summary": {},
            "state": {
                "state": "network_recovery",
                "headline": "系统网络需要恢复",
                "next_step": "点恢复原来的网络设置。",
                "saved_profile_count": 1,
                "bridge_in_use": false,
                "bridge_needs_recovery": true
            },
            "saved_profile_count": 1
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)

        XCTAssertEqual(response.schemaVersion, "netfix_current_mac_state.v1")
        XCTAssertEqual(response.primaryActionID, "recover_system_proxy")
        XCTAssertFalse(response.shouldShowProxyDeployCTA)
        XCTAssertEqual(response.machine?.primaryInterface, "en0")
        XCTAssertEqual(response.proxy?.system.kind, "http_https")
        XCTAssertEqual(response.egress?.status, "unchecked")
        XCTAssertTrue(response.decision?.requiresConfirmation == true)
    }

    func testDashboardStateShowsProxyCTAOnlyForPasteAction() throws {
        let json = """
        {
            "ok": true,
            "decision": {
                "ui_state": "no_proxy",
                "effective_route": "none",
                "severity": "info",
                "primary_action": "paste_proxy",
                "reason_codes": ["no_saved_profile_or_system_proxy"],
                "headline": "还没有粘贴代理参数",
                "next_step": "点粘贴代理参数。",
                "requires_confirmation": false
            },
            "state": {
                "state": "no_proxy",
                "headline": "还没有粘贴代理参数",
                "next_step": "点粘贴代理参数。"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)

        XCTAssertTrue(response.shouldShowProxyDeployCTA)
        XCTAssertEqual(response.primaryActionID, "paste_proxy")
    }

    func testDashboardStateV2VerdictDecodingUsesPrimaryActionLabel() throws {
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": {
                "ui_state": "ready",
                "effective_route": "external_system_proxy",
                "severity": "ok",
                "primary_action": "verify_current_proxy",
                "reason_codes": ["external_system_proxy_active"],
                "headline": "外部系统代理已启用",
                "next_step": "保持现状即可；想再确认一次就点「检查当前网络」。",
                "requires_confirmation": false
            },
            "verdict": {
                "status": "ok",
                "severity": "ok",
                "usability": "usable",
                "headline": "外部系统代理已启用",
                "detail": "Netfix 没有改这台 Mac 的系统代理。",
                "next_step": "保持现状即可；想再确认一次就点「检查当前网络」。",
                "issue_count": 0,
                "blocking_issue_count": 0,
                "advisory_count": 0,
                "diagnostic_counts": { "ok": 0, "warn": 0, "fail": 0, "unknown": 0 },
                "primary_action": {
                    "id": "verify_current_proxy",
                    "label": "检查当前网络",
                    "enabled": true,
                    "target": "run:doctor",
                    "requires_confirmation": false
                },
                "freshness": {
                    "checked_at": null,
                    "age_seconds": null,
                    "stale": true
                }
            },
            "presentation": {
                "visible_sections": ["current_status", "connection_quality"],
                "collapsed_sections": ["diagnostic_evidence"],
                "suppressed_sections": [
                    { "id": "recent_events", "reason": "history_only" }
                ]
            },
            "connection_quality": {
                "status": "ok",
                "headline": "体感顺畅",
                "detail": "速度、延迟和稳定性都有数据。",
                "speed": { "label": "充足", "value": "下载 28.4 Mbps / 上传 5.2 Mbps", "hint": "日常使用够用" },
                "latency": { "label": "中等", "value": "延迟 62ms", "hint": "打开网页时可能稍等一下" },
                "stability": { "label": "稳定", "value": "丢包 0%", "hint": "路径稳定" },
                "background_activity": { "label": "平稳", "value": "后台占用不高", "hint": "没有看到明显上传或下载占用" },
                "checked_at": "2026-07-09T06:00:00+00:00",
                "stale": false,
                "source": "last_report"
            },
            "machine": {
                "platform": "darwin",
                "primary_interface": "en0",
                "self_ipv4": "192.168.1.10",
                "gateway": "192.168.1.1",
                "has_ipv6_default_route": false
            },
            "proxy": {
                "saved": { "count": 0, "selected_profile_id": null },
                "system": { "active": true, "kind": "http_https", "network_service": "Wi-Fi" },
                "bridge": { "lifecycle_status": "stopped", "in_use": false, "needs_recovery": false, "recovery_available": false, "profile_id": null },
                "applied": { "active": true, "owner": "external", "profile_id": null, "via": "system_proxy" },
                "verified": { "status": "unknown", "checked_at": null, "source": "none" }
            },
            "egress": { "status": "unchecked", "cached": false },
            "state": {
                "state": "ready",
                "headline": "外部系统代理已启用",
                "next_step": "保持现状即可；想再确认一次就点「检查当前网络」。"
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)

        XCTAssertEqual(response.schemaVersion, "netfix_current_mac_state.v2")
        XCTAssertEqual(response.primaryActionID, "verify_current_proxy")
        XCTAssertEqual(response.primaryActionLabel, "检查当前网络")
        XCTAssertEqual(response.headline, "外部系统代理已启用")
        XCTAssertFalse(response.nextStep.contains("一键诊断"))
        XCTAssertEqual(response.presentation?.visibleSections, ["current_status", "connection_quality"])
        XCTAssertEqual(response.connectionQuality?.speed.value, "下载 28.4 Mbps / 上传 5.2 Mbps")
        XCTAssertEqual(response.connectionQuality?.latency.value, "延迟 62ms")
    }

    func testReportUnknownAndUncheckedDoNotCountAsIssues() throws {
        let json = """
        {
            "diagnostics": [
                { "name": "gateway", "status": "ok" },
                { "name": "egress_identity", "status": "unchecked" },
                { "name": "network_quality", "status": "unknown" }
            ],
            "root_causes": [],
            "fixes": [],
            "manual_steps": []
        }
        """.data(using: .utf8)!

        let report = try JSONDecoder().decode(NetfixReport.self, from: json)

        XCTAssertEqual(report.overallStatus, .ok)
        XCTAssertEqual(report.summaryHeadline, "网络看起来正常")
    }

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

    func testPrimaryActionLabelIsVerdictAuthoritativeAndEmptyWhenMissing() throws {
        // Backend omits label entirely — UI must NOT invent hard-coded copy.
        let jsonMissing = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": {
                "ui_state": "proxy_in_use",
                "effective_route": "netfix_applied",
                "primary_action": "diagnose",
                "requires_confirmation": false
            },
            "verdict": {
                "status": "unknown",
                "severity": "info",
                "primary_action": {
                    "id": "diagnose",
                    "enabled": true
                }
            },
            "presentation": {
                "visible_sections": ["current_status"],
                "collapsed_sections": [],
                "suppressed_sections": []
            },
            "state": {
                "state": "proxy_in_use",
                "headline": "正在使用代理上网",
                "next_step": "Netfix 会持续检查网络状态。"
            }
        }
        """.data(using: .utf8)!
        let missing = try JSONDecoder().decode(DashboardStateResponse.self, from: jsonMissing)
        XCTAssertEqual(missing.primaryActionLabel, "")
        XCTAssertEqual(missing.primaryActionTarget, "run:doctor")
        XCTAssertEqual(missing.primaryActionID, "diagnose")

        // Backend supplies label — UI must use it verbatim, no fallback switch.
        let jsonPaste = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": {
                "ui_state": "no_proxy",
                "effective_route": "none",
                "primary_action": "paste_proxy",
                "requires_confirmation": false
            },
            "verdict": {
                "status": "unknown",
                "severity": "info",
                "primary_action": {
                    "id": "paste_proxy",
                    "label": "粘贴代理参数",
                    "enabled": true,
                    "target": "settings:proxy"
                }
            },
            "presentation": {
                "visible_sections": ["current_status"],
                "collapsed_sections": [],
                "suppressed_sections": []
            },
            "state": {
                "state": "no_proxy",
                "headline": "还没有粘贴代理参数",
                "next_step": "点「粘贴代理参数」，把服务商给的那一行粘进来。"
            }
        }
        """.data(using: .utf8)!
        let paste = try JSONDecoder().decode(DashboardStateResponse.self, from: jsonPaste)
        XCTAssertEqual(paste.primaryActionLabel, "粘贴代理参数")
        XCTAssertEqual(paste.primaryActionTarget, "flow:proxy_setup")
    }

    func testPresentationVisibleSectionsAreDecoded() throws {
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "proxy_degraded" },
            "verdict": { "status": "attention" },
            "presentation": {
                "visible_sections": ["current_status", "diagnostic_evidence", "first_aid", "diagnose_goals"],
                "collapsed_sections": ["network_quality"],
                "suppressed_sections": [
                    {"id": "ai", "reason": "optional_support"},
                    {"id": "logs", "reason": "history_only"}
                ]
            },
            "state": { "state": "proxy_degraded", "headline": "代理需要复查", "next_step": "点检查" }
        }
        """.data(using: .utf8)!
        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)
        XCTAssertTrue(response.presentation?.visibleSections.contains("diagnostic_evidence") == true)
        XCTAssertTrue(response.presentation?.visibleSections.contains("first_aid") == true)
        XCTAssertTrue(response.presentation?.visibleSections.contains("diagnose_goals") == true)
    }

    // MARK: - P0 contract guard rails added 2026-07-09

    func testProxySystemMissing_decodesWithNilSystem() throws {
        // Backend may omit `proxy.system` when it cannot read the Mac's
        // system proxy; the home screen must not crash decoding.
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "proxy_in_use" },
            "verdict": { "status": "ok", "severity": "info" },
            "presentation": { "visible_sections": ["current_status"], "collapsed_sections": [], "suppressed_sections": [] },
            "proxy": { "saved": null, "bridge": null, "applied": null, "verified": null },
            "state": { "state": "proxy_in_use", "headline": "代理已启用", "next_step": "" }
        }
        """.data(using: .utf8)!
        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)
        XCTAssertNil(response.proxy?.system, "proxy.system must be Optional and decode to nil")
    }

    func testConnectionQualitySpeedMetricMissing_decodesWithoutCrash() throws {
        // Missing one metric (e.g. speed not sampled) must NOT take down the
        // whole ConnectionQuality decode.
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "ready" },
            "verdict": { "status": "unknown", "severity": "info" },
            "presentation": { "visible_sections": ["current_status"], "collapsed_sections": [], "suppressed_sections": [] },
            "connection_quality": {
                "status": "unchecked",
                "headline": "还没采样",
                "detail": "",
                "latency": { "label": "延迟", "value": "未测", "hint": "" },
                "stability": { "label": "稳定性", "value": "未测", "hint": "" },
                "background_activity": { "label": "后台占用", "value": "未测", "hint": "" }
            },
            "state": { "state": "ready", "headline": "系统代理", "next_step": "" }
        }
        """.data(using: .utf8)!
        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)
        XCTAssertNil(response.connectionQuality?.speed, "missing speed must decode as nil")
        XCTAssertNotNil(response.connectionQuality?.latency, "other metrics still present")
    }

    func testPrimaryActionTargetRoutingKnownValues() throws {
        // Legacy Settings target must normalize to the canonical setup flow.
        let settingsJSON = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "no_proxy" },
            "verdict": {
                "status": "unknown",
                "severity": "info",
                "primary_action": {
                    "id": "paste_proxy",
                    "label": "粘贴代理参数",
                    "enabled": true,
                    "target": "settings:proxy",
                    "requires_confirmation": false
                }
            },
            "presentation": { "visible_sections": ["current_status"], "collapsed_sections": [], "suppressed_sections": [] },
            "state": { "state": "no_proxy", "headline": "", "next_step": "" }
        }
        """.data(using: .utf8)!
        let r1 = try JSONDecoder().decode(DashboardStateResponse.self, from: settingsJSON)
        XCTAssertEqual(r1.primaryActionTarget, "flow:proxy_setup")
        XCTAssertEqual(r1.verdict?.primaryAction?.id, "paste_proxy")

        // Legacy recovery target must normalize to the stale-bridge endpoint.
        let recoverJSON = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "network_recovery" },
            "verdict": {
                "status": "blocked",
                "severity": "fail",
                "primary_action": {
                    "id": "recover_system_proxy",
                    "label": "恢复原来的网络设置",
                    "enabled": true,
                    "target": "recover:system_proxy",
                    "requires_confirmation": true
                }
            },
            "presentation": { "visible_sections": ["current_status"], "collapsed_sections": [], "suppressed_sections": [] },
            "state": { "state": "network_recovery", "headline": "", "next_step": "" }
        }
        """.data(using: .utf8)!
        let r2 = try JSONDecoder().decode(DashboardStateResponse.self, from: recoverJSON)
        XCTAssertEqual(r2.primaryActionTarget, "recover:stale_bridge")
        XCTAssertEqual(r2.verdict?.primaryAction?.id, "recover_system_proxy")
        XCTAssertEqual(r2.verdict?.primaryAction?.requiresConfirmation, true)

        // None target must round-trip and decode to an empty / no-op action.
        let noneJSON = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "ready" },
            "verdict": {
                "status": "ok",
                "severity": "ok",
                "primary_action": { "id": "none", "label": "", "enabled": false, "target": "none", "requires_confirmation": false }
            },
            "presentation": { "visible_sections": ["current_status"], "collapsed_sections": [], "suppressed_sections": [] },
            "state": { "state": "ready", "headline": "", "next_step": "" }
        }
        """.data(using: .utf8)!
        let r3 = try JSONDecoder().decode(DashboardStateResponse.self, from: noneJSON)
        XCTAssertEqual(r3.primaryActionTarget, "none")
        XCTAssertEqual(r3.verdict?.primaryAction?.enabled, false)
    }

    func testTopLevelHeadlineAndDetailAreDecoded() throws {
        // Swift side reads `response.headline / detail / next_step` at the top
        // level (DashboardHomePresentation); the contract must expose them.
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": { "ui_state": "no_proxy" },
            "verdict": {
                "status": "unknown",
                "severity": "info",
                "headline": "还没有粘贴代理参数",
                "detail": "当前没有 Netfix 保存或启用的代理。",
                "next_step": "点「粘贴代理参数」。"
            },
            "presentation": { "visible_sections": ["current_status"], "collapsed_sections": [], "suppressed_sections": [] },
            "state": { "state": "no_proxy", "headline": "", "next_step": "" },
            "headline": "还没有粘贴代理参数",
            "detail": "当前没有 Netfix 保存或启用的代理。",
            "next_step": "点「粘贴代理参数」。"
        }
        """.data(using: .utf8)!
        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)
        XCTAssertEqual(response.headline, "还没有粘贴代理参数")
        XCTAssertEqual(response.narrativeDetail, "当前没有 Netfix 保存或启用的代理。")
        XCTAssertEqual(response.nextStep, "点「粘贴代理参数」。")
    }

    @MainActor
    func testExternalProxyHidesLegacyRestoreActionAndOpaqueEgressHash() throws {
        let json = """
        {
            "ok": true,
            "schema_version": "netfix_current_mac_state.v2",
            "decision": {
                "ui_state": "ready",
                "effective_route": "external_system_proxy",
                "primary_action": "verify_current_proxy"
            },
            "verdict": {
                "status": "attention",
                "severity": "warn",
                "headline": "延迟偏高，操作会有等待",
                "detail": "当前线路可用。",
                "next_step": "点「检查当前网络」。",
                "primary_action": {
                    "id": "verify_current_proxy",
                    "label": "检查当前网络",
                    "enabled": true,
                    "target": "run:doctor"
                }
            },
            "proxy": {
                "applied": { "active": true, "owner": "external" },
                "bridge": { "in_use": false }
            },
            "egress": {
                "status": "ok",
                "public_ipv4": "public_ipv4_hash:secret",
                "isp": "Example Network",
                "ip_type": "unknown"
            },
            "state": {
                "state": "ready",
                "headline": "网络看起来正常",
                "next_step": "点「检查当前网络」。",
                "bridge_in_use": true
            }
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(DashboardStateResponse.self, from: json)
        let presentation = DashboardViewModel.DashboardHomePresentation(response: response)

        XCTAssertEqual(response.resolvedSecondaryActionTarget, .none)
        XCTAssertFalse(response.canOfferNetfixRestore)
        XCTAssertNil(response.secondaryActionLabel)
        XCTAssertEqual(presentation.egressLabel, "Example Network")
        XCTAssertFalse(presentation.egressLabel.contains("public_ipv4_hash"))
        XCTAssertFalse(presentation.egressLabel.contains("unknown"))
    }

    /// P1-A.3: 恢复历史会话时，后端 turns 要能映射回 user 提问 + assistant 回答的对话轮次。
    func testChatTurnMappingRestoresConversation() {
        func turn(
            _ id: String,
            role: String,
            content: String,
            planSteps: [ChatStep]? = nil,
            observations: [ChatObservation]? = nil,
            providerUsed: String? = nil
        ) -> ChatTurn {
            ChatTurn(
                turnID: id,
                sessionID: "s1",
                role: role,
                content: content,
                createdAt: "2026-07-18T00:00:00Z",
                planSteps: planSteps,
                observations: observations,
                rootCauseID: nil,
                rootCauseConfidence: nil,
                keyDiagnostics: nil,
                providerUsed: providerUsed,
                redactedReportHash: nil,
                attachments: nil
            )
        }

        let turns = [
            // 开头的孤立 assistant（没有对应提问）也要保留
            turn("t0", role: "assistant", content: "补充：刚才的检查已过期。"),
            turn("t1", role: "user", content: "家里网速很慢"),
            turn(
                "t2",
                role: "assistant",
                content: "检测发现 DNS 解析偏慢。",
                planSteps: [ChatStep(tool: "dns_check", label: "查 DNS", why: nil, status: "ok")],
                observations: [ChatObservation(fact: "DNS 平均 300ms", confidence: 0.8, source: "rule")],
                providerUsed: "deepseek"
            ),
            turn("t3", role: "user", content: "下一步怎么处理？"),
            // system 等非对话角色忽略
            turn("t5", role: "system", content: "session created"),
        ]

        let conversation = DashboardViewModel.aiChatTurns(from: turns)

        XCTAssertEqual(conversation.count, 3)
        XCTAssertEqual(conversation[0].question, "")
        XCTAssertEqual(conversation[0].result?.explanation, "补充：刚才的检查已过期。")
        XCTAssertEqual(conversation[1].question, "家里网速很慢")
        XCTAssertEqual(conversation[1].result?.explanation, "检测发现 DNS 解析偏慢。")
        XCTAssertEqual(conversation[1].result?.source, "llm")
        XCTAssertEqual(conversation[1].result?.planSteps?.first?.tool, "dns_check")
        XCTAssertEqual(conversation[1].result?.observations?.first?.fact, "DNS 平均 300ms")
        // 还没有回答的提问保持 result == nil，和发出等待中的轮次一致
        XCTAssertEqual(conversation[2].question, "下一步怎么处理？")
        XCTAssertNil(conversation[2].result)
    }
}
