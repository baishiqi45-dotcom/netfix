import Cocoa
import SwiftUI
import Combine
import UserNotifications

/// 应用生命周期与菜单栏图标管理。
/// Netfix 作为菜单栏应用运行：左键点击显示 popover 面板，右键显示菜单。
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem?
    private var popover: NSPopover?
    private var settingsWindowController: NSWindowController?
    let backend = Backend()
    private let healthMonitor = HealthMonitor()
    private let bridgeStatusMenuItem = NSMenuItem(title: "桥接状态：未读取", action: nil, keyEquivalent: "")
    private var bridgeStatusOverride: DiagnosticStatus?
    private var bridgeStatusTimer: Timer?
    private var lastBridgeNotificationKey: String?
    private var terminationDecisionInProgress = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 普通应用：有 Dock 图标，可从 Dock/启动台打开；同时保留菜单栏状态灯。
        NSApp.setActivationPolicy(.regular)

        buildPopover()
        buildStatusItem()
        bindHealthMonitor()
        backend.start()

        // 首次启动或从 Dock 打开时直接显示面板。
        showPopover()
    }

    func applicationWillTerminate(_ notification: Notification) {
        bridgeStatusTimer?.invalidate()
        healthMonitor.stop()
        backend.stop()
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard backend.isReady, backend.apiURL != nil, backend.apiToken != nil else {
            return .terminateNow
        }
        if terminationDecisionInProgress {
            return .terminateLater
        }
        terminationDecisionInProgress = true
        Task { await handleGuardedTermination(sender) }
        return .terminateLater
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showPopover()
        return true
    }

    private func showPopover() {
        guard let popover = popover, let button = statusItem?.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    // MARK: - Popover 面板

    private func buildPopover() {
        let popover = NSPopover()
        popover.contentSize = NSSize(width: 460, height: 620)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(
            rootView: RootView(backend: backend, healthMonitor: healthMonitor)
        )
        self.popover = popover
    }

    @objc private func togglePopover(_ sender: NSStatusBarButton) {
        showPopover()
    }

    @objc func showSettings() {
        if settingsWindowController == nil {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 520, height: 400),
                styleMask: [.titled, .closable, .miniaturizable],
                backing: .buffered,
                defer: false
            )
            window.title = "Netfix 设置"
            window.center()
            window.contentViewController = NSHostingController(rootView: SettingsView(backend: backend))
            settingsWindowController = NSWindowController(window: window)
        }
        settingsWindowController?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func showAISettings() {
        UserDefaults.standard.set("ai", forKey: "netfix.settings.selectedTab")
        showSettings()
    }

    @objc func showProxySettings() {
        UserDefaults.standard.set("proxy", forKey: "netfix.settings.selectedTab")
        showSettings()
    }

    @objc private func terminateApp() {
        NSApplication.shared.terminate(nil)
    }

    private enum BridgeQuitAction {
        case none
        case rollback
        case recover
        case cancel
        case forceQuit
    }

    private func handleGuardedTermination(_ sender: NSApplication) async {
        defer { terminationDecisionInProgress = false }
        guard let url = backend.apiURL, let token = backend.apiToken else {
            sender.reply(toApplicationShouldTerminate: true)
            return
        }
        let client = APIClient(baseURL: url, apiToken: token)
        do {
            let state = try await client.proxyBridge()
            switch bridgeQuitAction(for: state) {
            case .none:
                sender.reply(toApplicationShouldTerminate: true)
            case .recover:
                await confirmAndRecoverBeforeQuit(client: client, sender: sender)
            case .rollback:
                await confirmAndRollbackBeforeQuit(client: client, sender: sender)
            case .cancel:
                sender.reply(toApplicationShouldTerminate: false)
            case .forceQuit:
                sender.reply(toApplicationShouldTerminate: true)
            }
        } catch {
            let shouldQuit = presentBridgeCheckFailedAlert(error.localizedDescription)
            sender.reply(toApplicationShouldTerminate: shouldQuit)
        }
    }

    private func bridgeQuitAction(for state: ProxyBridgeResponse) -> BridgeQuitAction {
        guard let lifecycle = state.lifecycle else {
            return .none
        }
        if lifecycle.status == "recovery_required" || lifecycle.recoveryAvailable == true {
            return presentBridgeQuitAlert(
                title: "退出前恢复原来的网络设置？",
                message: "这台 Mac 还在使用上次 Netfix 部署的代理，但代理转发可能已经失效。建议先恢复，避免退出后网络不可用。",
                primary: "恢复网络设置后退出",
                primaryAction: .recover
            )
        }
        if lifecycle.status == "running_system" || (lifecycle.requiresNetfixRunning == true && lifecycle.systemPointsToBridge == true) {
            return presentBridgeQuitAlert(
                title: "这台 Mac 正在使用 Netfix 部署的代理",
                message: "退出会停止 Netfix 的代理转发。建议先恢复原来的网络设置，避免退出后网络不可用。",
                primary: "恢复网络设置后退出",
                primaryAction: .rollback
            )
        }
        return .none
    }

    private func presentBridgeQuitAlert(
        title: String,
        message: String,
        primary: String,
        primaryAction: BridgeQuitAction
    ) -> BridgeQuitAction {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = message
        alert.addButton(withTitle: primary)
        alert.addButton(withTitle: "取消退出")
        alert.addButton(withTitle: "仍然退出")
        let response = alert.runModal()
        if response == .alertFirstButtonReturn {
            return primaryAction
        }
        if response == .alertThirdButtonReturn {
            return .forceQuit
        }
        return .cancel
    }

    private func presentBridgeCheckFailedAlert(_ error: String) -> Bool {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "无法确认当前代理状态"
        alert.informativeText = "Netfix 没能确认这台 Mac 是否仍在使用 Netfix 部署的代理：\(error)"
        alert.addButton(withTitle: "取消退出")
        alert.addButton(withTitle: "仍然退出")
        return alert.runModal() == .alertSecondButtonReturn
    }

    private func confirmAndRollbackBeforeQuit(client: APIClient, sender: NSApplication) async {
        do {
            let result = try await client.rollbackProxyProfile(confirmed: true)
            if result.ok {
                sender.reply(toApplicationShouldTerminate: true)
            } else {
                presentBridgeOperationFailedAlert("恢复网络设置失败", detail: result.error ?? result.status ?? "unknown")
                sender.reply(toApplicationShouldTerminate: false)
            }
        } catch {
            presentBridgeOperationFailedAlert("恢复网络设置失败", detail: error.localizedDescription)
            sender.reply(toApplicationShouldTerminate: false)
        }
    }

    private func confirmAndRecoverBeforeQuit(client: APIClient, sender: NSApplication) async {
        do {
            let result = try await client.recoverProxyBridge(confirmed: true)
            if result.ok {
                sender.reply(toApplicationShouldTerminate: true)
            } else {
                presentBridgeOperationFailedAlert("恢复网络设置失败", detail: result.error ?? result.status ?? "unknown")
                sender.reply(toApplicationShouldTerminate: false)
            }
        } catch {
            presentBridgeOperationFailedAlert("恢复网络设置失败", detail: error.localizedDescription)
            sender.reply(toApplicationShouldTerminate: false)
        }
    }

    private func presentBridgeOperationFailedAlert(_ title: String, detail: String) {
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = title
        alert.informativeText = detail
        alert.addButton(withTitle: "确定")
        alert.runModal()
    }

    // MARK: - 菜单栏图标

    private lazy var statusMenu: NSMenu = {
        let menu = NSMenu()
        bridgeStatusMenuItem.isEnabled = false
        let items = [
            NSMenuItem(title: "打开 Netfix", action: #selector(showPopoverFromMenu), keyEquivalent: ""),
            NSMenuItem(title: "部署代理…", action: #selector(showProxySettings), keyEquivalent: ""),
            NSMenuItem(title: "设置…", action: #selector(showSettings), keyEquivalent: ","),
            NSMenuItem.separator(),
            bridgeStatusMenuItem,
            NSMenuItem.separator(),
            NSMenuItem(title: "退出", action: #selector(terminateApp), keyEquivalent: "q")
        ]
        for item in items {
            item.target = self
            menu.addItem(item)
        }
        menu.delegate = self
        return menu
    }()

    @objc private func showPopoverFromMenu() {
        togglePopover(statusItem?.button ?? NSStatusBarButton())
    }

    private func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        guard let button = statusItem?.button else { return }

        updateStatusIcon(status: healthMonitor.healthStatus)
        button.imagePosition = .imageOnly
        button.toolTip = "Netfix 网络自救"
        button.action = #selector(statusItemClicked(_:))
        button.target = self
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
    }

    @objc private func statusItemClicked(_ sender: NSStatusBarButton) {
        guard let event = NSApp.currentEvent else { return }
        if event.type == .rightMouseUp {
            statusItem?.menu = statusMenu
            sender.performClick(nil)
        } else {
            statusItem?.menu = nil
            togglePopover(sender)
        }
    }

    private func bindHealthMonitor() {
        healthMonitor.$healthStatus
            .receive(on: DispatchQueue.main)
            .sink { [weak self] status in
                self?.refreshStatusIcon(healthStatus: status)
            }
            .store(in: &cancellables)

        backend.$state
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                guard let self = self else { return }
                if case .ready(let url) = state, let token = self.backend.apiToken, self.healthMonitor.lastReport == nil {
                    self.healthMonitor.bind(client: APIClient(baseURL: url, apiToken: token))
                }
                if case .ready = state {
                    self.startBridgeStatusPolling()
                } else {
                    self.stopBridgeStatusPolling()
                }
            }
            .store(in: &cancellables)
    }

    private func startBridgeStatusPolling() {
        guard bridgeStatusTimer == nil else {
            Task { await refreshBridgeAttentionStatus(notify: true) }
            return
        }
        Task { await refreshBridgeAttentionStatus(notify: true) }
        bridgeStatusTimer = Timer.scheduledTimer(withTimeInterval: 45, repeats: true) { [weak self] _ in
            Task { await self?.refreshBridgeAttentionStatus(notify: true) }
        }
    }

    private func stopBridgeStatusPolling() {
        bridgeStatusTimer?.invalidate()
        bridgeStatusTimer = nil
        bridgeStatusOverride = backend.isReady ? nil : .warn
        lastBridgeNotificationKey = nil
        refreshStatusIcon()
    }

    private func refreshBridgeAttentionStatus(notify: Bool) async {
        guard backend.isReady, let url = backend.apiURL, let token = backend.apiToken else {
            bridgeStatusOverride = .warn
            refreshStatusIcon()
            return
        }
        let client = APIClient(baseURL: url, apiToken: token)
        do {
            let state = try await client.proxyBridge()
            applyBridgeState(state, notify: notify)
        } catch {
            bridgeStatusOverride = .warn
            statusItem?.button?.toolTip = "Netfix 网络自救 · 桥接状态读取失败"
            refreshStatusIcon()
        }
    }

    private func refreshBridgeMenuStatus() {
        guard backend.isReady, let url = backend.apiURL, let token = backend.apiToken else {
            bridgeStatusMenuItem.title = "代理状态：Netfix 还没准备好"
            return
        }
        bridgeStatusMenuItem.title = "桥接状态：读取中…"
        Task {
            let client = APIClient(baseURL: url, apiToken: token)
            do {
                let state = try await client.proxyBridge()
                bridgeStatusMenuItem.title = applyBridgeState(state, notify: false)
            } catch {
                bridgeStatusMenuItem.title = "桥接状态：读取失败"
                bridgeStatusOverride = .warn
                statusItem?.button?.toolTip = "Netfix 网络自救 · 桥接状态读取失败"
                refreshStatusIcon()
            }
        }
    }

    @discardableResult
    private func applyBridgeState(_ state: ProxyBridgeResponse, notify: Bool) -> String {
        let title = bridgeMenuTitle(for: state)
        let attention = bridgeAttention(for: state)
        bridgeStatusOverride = attention.status
        statusItem?.button?.toolTip = bridgeToolTip(for: state, menuTitle: title)
        refreshStatusIcon()
        if notify, let key = attention.notificationKey, key != lastBridgeNotificationKey {
            notifyBridgeAttention(key: key, title: attention.notificationTitle, body: attention.notificationBody)
            lastBridgeNotificationKey = key
        }
        if attention.notificationKey == nil && state.lifecycle?.needsAttention != true {
            lastBridgeNotificationKey = nil
        }
        return title
    }

    private func bridgeToolTip(for state: ProxyBridgeResponse, menuTitle: String) -> String {
        if let lifecycle = state.lifecycle, let headline = lifecycle.headline, !headline.isEmpty {
            return "Netfix 网络自救 · \(headline)"
        }
        if let restart = state.startupCheck?.autoRestart, restart.status == "restarted" {
            return "Netfix 网络自救 · 启动时已自动恢复代理连接"
        }
        return "Netfix 网络自救 · \(menuTitle.replacingOccurrences(of: "代理状态：", with: "代理"))"
    }

    private func bridgeAttention(for state: ProxyBridgeResponse) -> (
        status: DiagnosticStatus?,
        notificationKey: String?,
        notificationTitle: String,
        notificationBody: String
    ) {
        if let lifecycle = state.lifecycle {
            if lifecycle.status == "recovery_required" || lifecycle.recoveryAvailable == true {
                return (
                    .fail,
                    "bridge-recovery-required-\(lifecycle.networkService ?? "default")-\(lifecycle.bridge?.listenPort ?? 0)",
                    "Netfix：需要恢复网络设置",
                    lifecycle.detail ?? "这台 Mac 还在使用上次 Netfix 部署的代理，请打开 Netfix 恢复原来的网络设置。"
                )
            }
            if lifecycle.status == "check_failed" {
                return (
                    .fail,
                    "bridge-check-failed-\(lifecycle.networkService ?? "default")",
                    "Netfix：代理状态检查失败",
                    lifecycle.detail ?? "Netfix 未能确认这台 Mac 是否仍在使用 Netfix 部署的代理。"
                )
            }
            if lifecycle.status == "running_system" || (lifecycle.requiresNetfixRunning == true && lifecycle.systemPointsToBridge == true) {
                return (
                    .warn,
                    nil,
                    "Netfix：这台 Mac 正在使用 Netfix 代理",
                    lifecycle.detail ?? "请保持 Netfix 运行；退出前建议恢复原来的网络设置。"
                )
            }
        }
        if let restart = state.startupCheck?.autoRestart, restart.status == "restarted" {
            let port = restart.bridge?.listenPort.map(String.init) ?? "?"
            return (
                .warn,
                "bridge-auto-restarted-\(restart.profileId ?? "profile")-\(port)",
                "Netfix：已自动恢复代理连接",
                "已在本机端口 \(port) 恢复代理转发；没有静默修改网络代理设置。"
            )
        }
        return (nil, nil, "Netfix", "")
    }

    private func notifyBridgeAttention(key: String, title: String, body: String) {
        guard Bundle.main.bundlePath.hasSuffix(".app") else { return }
        guard UserDefaults.standard.bool(forKey: "netfix.notificationsEnabled") else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: key, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    private func bridgeMenuTitle(for state: ProxyBridgeResponse) -> String {
        guard let lifecycle = state.lifecycle else {
            return "代理状态：未知"
        }
        switch lifecycle.status {
        case "running_system":
            let port = lifecycle.bridge?.listenPort.map(String.init) ?? "?"
            return "代理状态：这台 Mac 正在使用本机端口 \(port)"
        case "running_local":
            let port = lifecycle.bridge?.listenPort.map(String.init) ?? "?"
            return "代理状态：本机端口 \(port) 正在转发"
        case "recovery_required":
            return "代理状态：需要恢复网络设置"
        case "check_failed":
            return "代理状态：检查失败"
        case "not_in_use":
            return "代理状态：这台 Mac 未使用 Netfix 代理"
        case "stopped":
            return "代理状态：未启动"
        default:
            return "代理状态：\(lifecycle.status ?? "未知")"
        }
    }

    private func refreshStatusIcon(healthStatus: DiagnosticStatus? = nil) {
        let status = bridgeStatusOverride ?? healthStatus ?? healthMonitor.healthStatus
        updateStatusIcon(status: status)
    }

    private func updateStatusIcon(status: DiagnosticStatus) {
        guard let button = statusItem?.button else { return }
        let color: NSColor
        switch status {
        case .ok:
            color = .systemGreen
        case .warn:
            color = .systemYellow
        case .fail:
            color = .systemRed
        case .unknown:
            color = backend.isReady ? .systemGreen : .systemYellow
        }
        let monochrome = UserDefaults.standard.integer(forKey: "netfix.iconStyle") == 1
        button.image = makeStatusIcon(color: color, monochrome: monochrome)
    }

    /// 合成 network 图标与右下角状态圆点。
    private func makeStatusIcon(color: NSColor, monochrome: Bool) -> NSImage? {
        guard let base = NSImage(systemSymbolName: "network", accessibilityDescription: "netfix") else {
            return nil
        }
        let size = NSSize(width: 18, height: 18)
        let dotRadius: CGFloat = 3.5
        let image = NSImage(size: size)
        image.lockFocus()
        let rect = NSRect(origin: .zero, size: size)
        base.draw(in: rect)

        if !monochrome {
            let dotPath = NSBezierPath(ovalIn: NSRect(
                x: size.width - dotRadius * 2 - 1,
                y: 1,
                width: dotRadius * 2,
                height: dotRadius * 2
            ))
            color.setFill()
            NSColor.white.setStroke()
            dotPath.fill()
            dotPath.lineWidth = 1
            dotPath.stroke()
        }

        image.unlockFocus()
        image.isTemplate = monochrome
        return image
    }

    private var cancellables = Set<AnyCancellable>()
}

extension AppDelegate: NSMenuDelegate {
    func menuNeedsUpdate(_ menu: NSMenu) {
        refreshBridgeMenuStatus()
    }

    func menuDidClose(_ menu: NSMenu) {
        statusItem?.menu = nil
    }
}
