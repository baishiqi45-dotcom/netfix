import Foundation
import XCTest
@testable import Netfix

final class P0DashboardTests: XCTestCase {
    override func tearDown() {
        RequestRecorderURLProtocol.handler = nil
        super.tearDown()
    }

    func testDashboardV2DecodesRouteActionsQualityAndReportSummary() throws {
        let response = try decodeDashboard("""
        {
          "ok": true,
          "schema_version": "netfix_current_mac_state.v2",
          "decision": {
            "ui_state": "proxy_in_use",
            "effective_route": "netfix_applied",
            "primary_action": "diagnose"
          },
          "verdict": {
            "status": "ok",
            "severity": "ok",
            "route_health": "warn",
            "primary_action": {
              "id": "diagnose",
              "label": "检查当前网络",
              "enabled": true,
              "target": "run:doctor",
              "requires_confirmation": false
            },
            "secondary_action": {
              "id": "stop_and_restore",
              "label": "停止使用并恢复原设置",
              "enabled": true,
              "target": "recover:stale_bridge",
              "requires_confirmation": true
            }
          },
          "connection_quality": {
            "status": "partial",
            "collection_state": "partial",
            "headline": "已采到部分数据"
          },
          "last_report_summary": {
            "origin": "doctor",
            "coverage": "current_mac_full",
            "checked_at": "2026-07-10T08:00:00Z",
            "age_seconds": 12,
            "status": "warn",
            "diagnostic_count": 5,
            "valid_sample_count": 3,
            "issue_count": 1,
            "blocking_issue_count": 0,
            "advisory_count": 2,
            "stale": false,
            "route_matches_current": true,
            "usable_for_dashboard": true,
            "diagnostic_channels": {
              "route_health": {"status": "warn", "ok": 2, "warn": 1, "fail": 0, "sample_count": 3}
            }
          },
          "state": {
            "state": "proxy_in_use",
            "headline": "正在使用代理上网",
            "next_step": "保持现状。"
          }
        }
        """)

        XCTAssertEqual(response.verdict?.routeHealth, "warn")
        XCTAssertEqual(response.resolvedPrimaryActionTarget, .doctor)
        XCTAssertEqual(response.resolvedSecondaryActionTarget, .staleBridgeRecovery)
        XCTAssertEqual(response.verdict?.secondaryAction?.label, "停止使用并恢复原设置")
        XCTAssertEqual(response.connectionQuality?.collectionState, "partial")
        XCTAssertEqual(response.lastReportSummary?.origin, "doctor")
        XCTAssertEqual(response.lastReportSummary?.coverage, "current_mac_full")
        XCTAssertEqual(response.lastReportSummary?.diagnosticChannels?["route_health"]?.sampleCount, 3)
        XCTAssertEqual(response.lastReportSummary?.routeMatchesCurrent, true)
    }

    func testDashboardActionTargetsAcceptCanonicalValuesAndLegacyAliases() {
        XCTAssertEqual(DashboardActionTarget.resolve(target: "flow:proxy_setup", actionID: nil), .proxySetup)
        XCTAssertEqual(DashboardActionTarget.resolve(target: "settings:proxy", actionID: nil), .proxySetup)
        XCTAssertEqual(DashboardActionTarget.resolve(target: "run:doctor", actionID: nil), .doctor)
        XCTAssertEqual(DashboardActionTarget.resolve(target: "run:diagnose", actionID: nil), .doctor)
        XCTAssertEqual(DashboardActionTarget.resolve(target: "recover:stale_bridge", actionID: nil), .staleBridgeRecovery)
        XCTAssertEqual(DashboardActionTarget.resolve(target: "recover:system_proxy", actionID: nil), .staleBridgeRecovery)
        XCTAssertEqual(DashboardActionTarget.resolve(target: "none", actionID: nil), .none)
        XCTAssertEqual(DashboardActionTarget.resolve(target: nil, actionID: "paste_proxy"), .proxySetup)
        XCTAssertEqual(DashboardActionTarget.resolve(target: nil, actionID: "verify_current_proxy"), .doctor)
        XCTAssertEqual(DashboardActionTarget.resolve(target: nil, actionID: "recover_system_proxy"), .staleBridgeRecovery)
    }

    func testReportDecodesCurrentScopeAndRouteFieldsWhileKeepingOldReportsValid() throws {
        let current = try JSONDecoder().decode(
            NetfixReport.self,
            from: Data(#"{"schema_version":"netfix_report.v1","meta":{"version":"1.0","timestamp":"2026-07-10T08:00:00Z","platform":"darwin","hostname":"mac","origin":"doctor","coverage":"current_mac_full","route_signature":"route-1"},"diagnostics":[],"root_causes":[],"fixes":[],"manual_steps":[]}"#.utf8)
        )
        XCTAssertEqual(current.schemaVersion, "netfix_report.v1")
        XCTAssertEqual(current.meta?.origin, "doctor")
        XCTAssertEqual(current.meta?.coverage, "current_mac_full")
        XCTAssertEqual(current.meta?.routeSignature, "route-1")

        let legacy = try JSONDecoder().decode(
            NetfixReport.self,
            from: Self.emptyReportData
        )
        XCTAssertNil(legacy.schemaVersion)
        XCTAssertNil(legacy.meta)
    }

    func testLegacyDashboardInfersActionTargetWithoutUsingEffectiveRouteAsTarget() throws {
        let response = try decodeDashboard("""
        {
          "ok": true,
          "decision": {
            "ui_state": "no_proxy",
            "effective_route": "none",
            "primary_action": "paste_proxy"
          },
          "state": {
            "state": "no_proxy",
            "headline": "还没有粘贴代理参数",
            "next_step": "粘贴代理参数。"
          }
        }
        """)

        XCTAssertEqual(response.resolvedPrimaryActionTarget, .proxySetup)
        XCTAssertEqual(response.primaryActionTarget, "flow:proxy_setup")
    }

    @MainActor
    func testDashboardStateStoreCanRetryAfterAnError() async throws {
        var attempts = 0
        let expected = try decodeDashboard("""
        {
          "ok": true,
          "state": {"state": "ready", "headline": "网络可用", "next_step": "无需处理。"}
        }
        """)
        let store = DashboardStateStore(loader: {
            attempts += 1
            if attempts == 1 {
                throw TestFailure.expected
            }
            return expected
        })

        await store.refresh()
        XCTAssertNil(store.state)
        XCTAssertNotNil(store.errorMessage)

        await store.refresh()
        XCTAssertEqual(store.state?.headline, "网络可用")
        XCTAssertNil(store.errorMessage)
        XCTAssertEqual(attempts, 2)
    }

    func testExecuteFixOmitsConfirmationByDefaultAndAddsItOnlyWhenConfirmed() async throws {
        let recorder = RequestRecorder()
        RequestRecorderURLProtocol.handler = { request in
            recorder.append(request)
            return (200, Self.emptyReportData)
        }
        let client = makeClient()

        _ = try await client.executeFix(fixId: "flush-dns-cache", timeout: 15)
        _ = try await client.executeFix(fixId: "reset-system-proxy", timeout: 15, confirmed: true)

        let first = try XCTUnwrap(recorder.requests.first)
        let firstBody = try jsonBody(first)
        XCTAssertEqual(firstBody["fix_id"] as? String, "flush-dns-cache")
        XCTAssertNil(firstBody["confirmed"])
        XCTAssertNil(firstBody["confirmation"])

        let second = try XCTUnwrap(recorder.requests.last)
        let secondBody = try jsonBody(second)
        XCTAssertEqual(secondBody["confirmed"] as? Bool, true)
        XCTAssertEqual(secondBody["confirmation"] as? String, "APPLY_SYSTEM_FIX")
    }

    func testProxyValidationReceiptDecodesAndIsSentWhenSaving() async throws {
        let recorder = RequestRecorder()
        RequestRecorderURLProtocol.handler = { request in
            recorder.append(request)
            return (200, Data(#"{"ok":true,"profile":{"id":"p1","verification_status":"verified","can_apply":true}}"#.utf8))
        }
        let validation = try JSONDecoder().decode(
            ProxyValidateResponse.self,
            from: Data(#"{"ok":true,"validation_receipt":"receipt-123","validation_receipt_expires_in_seconds":60,"proxy_check":{"status":"ok"}}"#.utf8)
        )
        XCTAssertEqual(validation.validationReceipt, "receipt-123")
        XCTAssertEqual(validation.validationReceiptExpiresInSeconds, 60)

        let client = makeClient()
        _ = try await client.saveProxyProfile(
            input: "proxy.example.com:8000:user:pass",
            validationReceipt: "receipt-123",
            startMonitor: false
        )

        let body = try jsonBody(try XCTUnwrap(recorder.requests.first))
        XCTAssertEqual(body["validation_receipt"] as? String, "receipt-123")
    }

    func testProxySetupWorkflowDoesNotSaveWhenValidationFails() async throws {
        let recorder = RequestRecorder()
        RequestRecorderURLProtocol.handler = { request in
            recorder.append(request)
            switch request.url?.path {
            case "/proxy/parse":
                return (200, Data(#"{"ok":true,"profile":{"id":"preview"},"warnings":[]}"#.utf8))
            case "/proxy/validate":
                return (400, Data(#"{"ok":false,"proxy_check":{"status":"fail"},"errors":["auth_failed"]}"#.utf8))
            default:
                XCTFail("Unexpected request: \(request.url?.path ?? "nil")")
                return (500, Data(#"{"error":"unexpected"}"#.utf8))
            }
        }
        let workflow = ProxySetupWorkflow(client: makeClient())

        do {
            _ = try await workflow.validateAndSave(
                input: "proxy.example.com:8000:user:bad",
                protocolHint: "auto",
                targetProfile: "baseline",
                startMonitor: false
            )
            XCTFail("Expected validation failure")
        } catch {
            XCTAssertEqual(recorder.requests.map { $0.url?.path }, ["/proxy/parse", "/proxy/validate"])
        }
    }

    func testProxySetupWorkflowSavesOnlyAfterValidationAndCarriesReceipt() async throws {
        let recorder = RequestRecorder()
        RequestRecorderURLProtocol.handler = { request in
            recorder.append(request)
            switch request.url?.path {
            case "/proxy/parse":
                return (200, Data(#"{"ok":true,"profile":{"id":"preview"},"warnings":[]}"#.utf8))
            case "/proxy/validate":
                return (200, Data(#"{"ok":true,"validation_receipt":"receipt-ok","proxy_check":{"status":"ok"}}"#.utf8))
            case "/proxy/profiles":
                return (200, Data(#"{"ok":true,"profile":{"id":"p1","verification_status":"verified","can_apply":true}}"#.utf8))
            default:
                XCTFail("Unexpected request: \(request.url?.path ?? "nil")")
                return (500, Data(#"{"error":"unexpected"}"#.utf8))
            }
        }
        let workflow = ProxySetupWorkflow(client: makeClient())

        let result = try await workflow.validateAndSave(
            input: "proxy.example.com:8000:user:pass",
            protocolHint: "auto",
            targetProfile: "baseline",
            startMonitor: false
        )

        XCTAssertEqual(result.savedProfile.id, "p1")
        XCTAssertEqual(recorder.requests.map { $0.url?.path }, ["/proxy/parse", "/proxy/validate", "/proxy/profiles"])
        let saveBody = try jsonBody(try XCTUnwrap(recorder.requests.last))
        XCTAssertEqual(saveBody["validation_receipt"] as? String, "receipt-ok")
    }

    private func decodeDashboard(_ json: String) throws -> DashboardStateResponse {
        try JSONDecoder().decode(DashboardStateResponse.self, from: Data(json.utf8))
    }

    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RequestRecorderURLProtocol.self]
        return APIClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!,
            apiToken: "test-token",
            session: URLSession(configuration: configuration)
        )
    }

    private func jsonBody(_ request: URLRequest) throws -> [String: Any] {
        let data = try XCTUnwrap(request.httpBody)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private static let emptyReportData = Data(#"{"diagnostics":[],"root_causes":[],"fixes":[],"manual_steps":[]}"#.utf8)
}

private enum TestFailure: Error {
    case expected
}

private final class RequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [URLRequest] = []

    var requests: [URLRequest] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func append(_ request: URLRequest) {
        lock.lock()
        storage.append(request)
        lock.unlock()
    }
}

private final class RequestRecorderURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: TestFailure.expected)
            return
        }
        do {
            let (status, data) = try handler(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}
