import Foundation
import Combine
import UserNotifications

/// 后台健康监测：定时拉取最新报告，计算网络健康状态，
/// 在状态变化时更新菜单栏图标并推送本地通知。
@MainActor
final class HealthMonitor: ObservableObject {
    @Published var healthStatus: DiagnosticStatus = .unknown
    @Published var lastReport: NetfixReport?
    @Published var lastCheck: Date?
    @Published var isMonitoring = false

    /// 最近 24 小时内状态发生变化的快照，用于时间线视图。
    @Published private(set) var events: [HealthEvent] = []

    private var client: APIClient?
    private var timer: Timer?
    private var autoFixInProgress = false
    private var lastAutoFix: Date?
    private let interval: TimeInterval
    private let maxEvents: Int
    private let autoFixCooldown: TimeInterval = 120

    init(interval: TimeInterval = 30.0, maxEvents: Int = 100) {
        self.interval = interval
        self.maxEvents = maxEvents
        if notificationsEnabled {
            requestNotificationAuthorization()
        }
    }

    func bind(client: APIClient) {
        self.client = client
        Task { await loadBackendEvents() }
        start()
    }

    private func loadBackendEvents() async {
        guard let client = client else { return }
        do {
            let response = try await client.events()
            let loaded = response.events.map { event in
                HealthEvent(
                    timestamp: ISO8601DateFormatter().date(from: event.timestamp) ?? Date(),
                    status: DiagnosticStatus(event.status),
                    headline: event.headline ?? "状态变化",
                    rootCause: event.rootCause
                )
            }
            events.append(contentsOf: loaded)
            trimEvents()
        } catch {
            // 后端事件可选，失败不影响主流程。
        }
    }

    func start() {
        guard timer == nil else { return }
        isMonitoring = true
        // 立即执行一次，随后按间隔执行。
        Task { await checkNow() }
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            Task { await self?.checkNow() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        isMonitoring = false
    }

    func checkNow() async {
        guard let client = client else { return }
        do {
            let report = try await client.latestReport()
            lastReport = report
            lastCheck = Date()
            let newStatus = report.overallStatus
            if newStatus != healthStatus {
                let event = HealthEvent(
                    timestamp: Date(),
                    status: newStatus,
                    headline: report.explanation?.headline ?? report.summaryHeadline,
                    rootCause: report.firstRootCause
                )
                events.append(event)
                trimEvents()
                if healthStatus != .unknown {
                    notifyStatusChange(from: healthStatus, to: newStatus, event: event)
                }
                healthStatus = newStatus

                // 状态恶化且开启自动处理时，只尝试不会改系统网络设置的低风险修复。
                if newStatus != .ok {
                    await maybeAutoFix(client: client, report: report)
                }
            }
        } catch {
            // 网络/后端不可达时标记为异常，但只在状态变化时通知一次。
            let newStatus = DiagnosticStatus.fail
            if newStatus != healthStatus {
                let event = HealthEvent(
                    timestamp: Date(),
                    status: newStatus,
                    headline: "网络监测失败",
                    rootCause: error.localizedDescription
                )
                events.append(event)
                trimEvents()
                if healthStatus != .unknown {
                    notifyStatusChange(from: healthStatus, to: newStatus, event: event)
                }
                healthStatus = newStatus
            }
        }
    }

    private func maybeAutoFix(client: APIClient, report: NetfixReport) async {
        guard UserDefaults.standard.bool(forKey: "netfix.autoFixTier1") else { return }
        guard !autoFixInProgress else { return }
        if let last = lastAutoFix, Date().timeIntervalSince(last) < autoFixCooldown {
            return
        }
        // 只有报告解释层明确给出低风险、无需确认的 action 时才执行。
        let allActions = [report.explanation?.primaryAction].compactMap { $0 } + (report.explanation?.actions ?? [])
        let autoFixAction = allActions.first { action in
            action.tier == 1 && !action.needsConfirm
        }
        guard let action = autoFixAction else { return }

        autoFixInProgress = true
        defer {
            autoFixInProgress = false
            lastAutoFix = Date()
        }
        do {
            let fixed = try await client.executeFix(fixId: action.id)
            lastReport = fixed
            let fixedStatus = fixed.overallStatus
            let event = HealthEvent(
                timestamp: Date(),
                status: fixedStatus,
                headline: "已自动处理：\(action.label)",
                rootCause: fixed.firstRootCause
            )
            events.append(event)
            trimEvents()
            healthStatus = fixedStatus
            notifyAutoFix(result: event)
        } catch {
            let event = HealthEvent(
                timestamp: Date(),
                status: .fail,
                headline: "自动修复失败",
                rootCause: error.localizedDescription
            )
            events.append(event)
            trimEvents()
            notifyAutoFix(result: event)
        }
    }

    private func notifyAutoFix(result: HealthEvent) {
        guard notificationsEnabled else { return }
        let content = UNMutableNotificationContent()
        content.title = "Netfix 自动修复"
        content.body = result.headline
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    private func trimEvents() {
        let cutoff = Date().addingTimeInterval(-24 * 60 * 60)
        events.removeAll { $0.timestamp < cutoff }
        if events.count > maxEvents {
            events = Array(events.suffix(maxEvents))
        }
    }

    private func requestNotificationAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    private func notifyStatusChange(from: DiagnosticStatus, to: DiagnosticStatus, event: HealthEvent) {
        guard notificationsEnabled else { return }
        let content = UNMutableNotificationContent()
        content.title = "Netfix 网络状态变化"
        switch to {
        case .ok:
            content.body = "网络已恢复正常"
        case .warn:
            content.body = "网络出现注意项：\(event.headline)"
        case .fail, .unknown:
            content.body = "网络异常：\(event.headline)"
        }
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    private var notificationsEnabled: Bool {
        Bundle.main.bundlePath.hasSuffix(".app")
            && UserDefaults.standard.bool(forKey: "netfix.notificationsEnabled")
    }
}

struct HealthEvent: Identifiable {
    let id = UUID()
    let timestamp: Date
    let status: DiagnosticStatus
    let headline: String
    let rootCause: String?
}
