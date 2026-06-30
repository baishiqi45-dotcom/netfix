import Foundation
import Darwin
import UserNotifications

/// 后端进程状态。
enum BackendState: Equatable {
    case starting
    case ready(URL)
    case failed(String)
    case stopped
}

/// 负责启动、监控和重启 Python 后端进程。
final class Backend: ObservableObject {
    @Published private(set) var state: BackendState = .starting

    private var process: Process?
    private var outputBuffer = Data()
    private var errorBuffer = Data()
    private var healthCheckTimer: Timer?
    private var startupTimer: Timer?
    private var stableReadyTimer: Timer?
    private var recoveryWorkItem: DispatchWorkItem?
    private var portParsed = false
    private var tokenParsed = false
    private var healthCheckFailures = 0
    private var healthCheckInFlight = false
    private var healthCheckTask: Task<Void, Never>?
    private var launchAttempt = 0
    private var lifecycleGeneration = 0
    private var isStopping = false
    private var launchLabel: String?
    private(set) var apiToken: String?

    private let maxLaunchAttempts = 3
    private let startupTimeoutSeconds: TimeInterval = 15.0
    private let restartGraceSeconds: TimeInterval = 2.0
    private lazy var healthCheckSession: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 3.0
        configuration.timeoutIntervalForResource = 5.0
        return URLSession(configuration: configuration)
    }()

    private struct LaunchCommand {
        let executableURL: URL
        let arguments: [String]
        let label: String
    }

    /// 解析后端脚本路径。源码版仍使用 netfix.py；正式外发版应优先内置
    /// netfix-backend 独立二进制或 Resources/python/bin/python3。
    static var backendPath: String? {
        Bundle.main.path(forResource: "netfix", ofType: "py")
    }

    static var bundledBackendPath: String? {
        Bundle.main.path(forAuxiliaryExecutable: "netfix-backend")
            ?? Bundle.main.path(forResource: "netfix-backend", ofType: nil)
    }

    static var bundledPythonPath: String? {
        Bundle.main.path(forResource: "python3", ofType: nil, inDirectory: "python/bin")
    }

    var apiURL: URL? {
        if case .ready(let url) = state { return url }
        return nil
    }

    var statusMessage: String {
        switch state {
        case .starting:
            if launchAttempt > 1 {
                return "正在启动 Netfix…（第 \(launchAttempt)/\(maxLaunchAttempts) 次）"
            }
            return "正在启动 Netfix…"
        case .ready: return "Netfix 已就绪"
        case .failed(let reason): return "Netfix 异常：\(reason)"
        case .stopped: return "Netfix 已停止"
        }
    }

    var isReady: Bool {
        apiURL != nil
    }

    init() {}

    deinit {
        stop()
    }

    // MARK: - 启动 / 停止 / 重启

    func start() {
        guard Thread.isMainThread else {
            DispatchQueue.main.async { [weak self] in
                self?.start()
            }
            return
        }
        start(resetAttempts: true)
    }

    private func start(resetAttempts: Bool) {
        guard process == nil || process?.isRunning == false else { return }
        lifecycleGeneration += 1
        if resetAttempts {
            launchAttempt = 0
        }

        let launch: LaunchCommand
        do {
            launch = try Self.makeLaunchCommand()
        } catch {
            state = .failed(error.localizedDescription)
            return
        }

        recoveryWorkItem?.cancel()
        stableReadyTimer?.invalidate()
        stableReadyTimer = nil
        healthCheckTask?.cancel()
        healthCheckTask = nil
        healthCheckInFlight = false
        launchAttempt += 1
        let generation = lifecycleGeneration
        launchLabel = launch.label
        state = .starting
        outputBuffer.removeAll()
        errorBuffer.removeAll()
        portParsed = false
        tokenParsed = false
        apiToken = nil
        healthCheckFailures = 0
        isStopping = false

        // 15 秒内必须解析到监听端口，否则进入自动恢复流程。
        startupTimer?.invalidate()
        startupTimer = Timer.scheduledTimer(withTimeInterval: startupTimeoutSeconds, repeats: false) { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, self.lifecycleGeneration == generation, !self.isReady else { return }
                self.handleRecoverableBackendFailure("Netfix 启动超时。")
            }
        }

        let task = Process()
        task.executableURL = launch.executableURL
        task.arguments = launch.arguments
        task.standardOutput = Pipe()
        task.standardError = Pipe()

        if let pipe = task.standardOutput as? Pipe {
            pipe.fileHandleForReading.readabilityHandler = { [weak self, weak task] handle in
                let data = handle.availableData
                guard let self = self, !data.isEmpty else { return }
                DispatchQueue.main.async { [weak self, weak task] in
                    // Late pipe callbacks from an old process must not mark a new backend ready.
                    guard let self = self,
                          let task = task,
                          self.lifecycleGeneration == generation,
                          self.process === task else { return }
                    self.outputBuffer.append(data)
                    if !self.portParsed || !self.tokenParsed {
                        self.parseEndpoint(from: self.outputBuffer, generation: generation)
                    }
                }
            }
        }

        if let pipe = task.standardError as? Pipe {
            pipe.fileHandleForReading.readabilityHandler = { [weak self, weak task] handle in
                guard let self = self else { return }
                let data = handle.availableData
                guard !data.isEmpty else { return }
                DispatchQueue.main.async { [weak self, weak task] in
                    // Keep stderr diagnostics tied to the same launch that produced them.
                    guard let self = self,
                          let task = task,
                          self.lifecycleGeneration == generation,
                          self.process === task else { return }
                    self.errorBuffer.append(data)
                    if self.errorBuffer.count > 8192 {
                        self.errorBuffer.removeFirst(self.errorBuffer.count - 8192)
                    }
                }
            }
        }

        task.terminationHandler = { [weak self] terminatedTask in
            DispatchQueue.main.async {
                guard let self = self else { return }
                guard self.lifecycleGeneration == generation else { return }
                guard self.process === terminatedTask else { return }
                self.clearProcessHandlers(terminatedTask)
                self.process = nil
                guard !self.isStopping else {
                    self.isStopping = false
                    return
                }
                if case .stopped = self.state { return }
                self.handleRecoverableBackendFailure("后端进程异常退出。")
            }
        }

        self.process = task
        do {
            try task.run()
        } catch {
            self.process = nil
            clearProcessHandlers(task)
            startupTimer?.invalidate()
            handleRecoverableBackendFailure("无法启动后端：\(error.localizedDescription)")
        }
    }

    private static func makeLaunchCommand() throws -> LaunchCommand {
        let serverArgs = ["server", "--host", "127.0.0.1", "--port", "0", "--timeout", "120"]

        if let path = bundledBackendPath {
            return LaunchCommand(
                executableURL: URL(fileURLWithPath: path),
                arguments: serverArgs,
                label: "bundled backend binary"
            )
        }

        guard let backendPath else {
            throw NSError(
                domain: "NetfixBackend",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "找不到后端脚本 netfix.py，请重新安装 Netfix。"]
            )
        }

        if let python = bundledPythonPath {
            return LaunchCommand(
                executableURL: URL(fileURLWithPath: python),
                arguments: [backendPath] + serverArgs,
                label: "bundled Python runtime"
            )
        }

        return LaunchCommand(
            executableURL: URL(fileURLWithPath: "/usr/bin/env"),
            arguments: ["python3", backendPath] + serverArgs,
            label: "system python3"
        )
    }

    func stop() {
        guard Thread.isMainThread else {
            DispatchQueue.main.async { [weak self] in
                self?.stop()
            }
            return
        }
        lifecycleGeneration += 1
        recoveryWorkItem?.cancel()
        recoveryWorkItem = nil
        startupTimer?.invalidate()
        startupTimer = nil
        stableReadyTimer?.invalidate()
        stableReadyTimer = nil
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        healthCheckTask?.cancel()
        healthCheckTask = nil
        healthCheckInFlight = false
        isStopping = true
        let generation = lifecycleGeneration
        if let task = process {
            clearProcessHandlers(task)
            terminate(task) { [weak self] in
                guard let self = self, self.lifecycleGeneration == generation else { return }
                self.isStopping = false
            }
        } else {
            isStopping = false
        }
        process = nil
        apiToken = nil
        launchAttempt = 0
        state = .stopped
    }

    func restart() {
        guard Thread.isMainThread else {
            DispatchQueue.main.async { [weak self] in
                self?.restart()
            }
            return
        }
        lifecycleGeneration += 1
        let generation = lifecycleGeneration
        recoveryWorkItem?.cancel()
        recoveryWorkItem = nil
        startupTimer?.invalidate()
        startupTimer = nil
        stableReadyTimer?.invalidate()
        stableReadyTimer = nil
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        healthCheckTask?.cancel()
        healthCheckTask = nil
        healthCheckInFlight = false
        isStopping = true
        let task = process
        process = nil
        apiToken = nil
        launchAttempt = 0
        state = .stopped
        if let task {
            clearProcessHandlers(task)
            terminate(task) { [weak self] in
                guard let self = self, self.lifecycleGeneration == generation else { return }
                self.isStopping = false
                self.start(resetAttempts: true)
            }
        } else {
            isStopping = false
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
                guard let self = self, self.lifecycleGeneration == generation else { return }
                self.start(resetAttempts: true)
            }
        }
    }

    private func handleRecoverableBackendFailure(_ headline: String) {
        lifecycleGeneration += 1
        let generation = lifecycleGeneration
        startupTimer?.invalidate()
        startupTimer = nil
        stableReadyTimer?.invalidate()
        stableReadyTimer = nil
        healthCheckTimer?.invalidate()
        healthCheckTimer = nil
        healthCheckTask?.cancel()
        healthCheckTask = nil
        healthCheckInFlight = false

        let message = backendFailureMessage(headline)
        if let task = process {
            clearProcessHandlers(task)
            process = nil
            terminate(task) { [weak self] in
                self?.finishRecoverableBackendFailure(message, generation: generation)
            }
        } else {
            finishRecoverableBackendFailure(message, generation: generation)
        }
    }

    private func finishRecoverableBackendFailure(_ message: String, generation: Int) {
        guard lifecycleGeneration == generation else { return }
        guard !isStopping else { return }

        if launchAttempt < maxLaunchAttempts {
            let delay = retryDelay(after: launchAttempt)
            recoveryWorkItem?.cancel()
            let workItem = DispatchWorkItem { [weak self] in
                guard let self = self, self.lifecycleGeneration == generation else { return }
                self.start(resetAttempts: false)
            }
            recoveryWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
            state = .starting
        } else {
            recoveryWorkItem = nil
            state = .failed("\(message)\n已连续尝试 \(maxLaunchAttempts) 次仍失败，请打开日志或重新安装 Netfix。")
        }
    }

    private func backendFailureMessage(_ headline: String) -> String {
        var parts = [headline]
        if let launchLabel {
            parts.append("启动方式：\(launchLabel)")
        }
        if let stderr = lastErrorLines() {
            parts.append(stderr)
        }
        return parts.joined(separator: "\n")
    }

    private func retryDelay(after attempt: Int) -> TimeInterval {
        switch attempt {
        case 0, 1: return 0.8
        case 2: return 2.0
        default: return 0
        }
    }

    private func clearProcessHandlers(_ task: Process) {
        task.terminationHandler = nil
        if let pipe = task.standardOutput as? Pipe {
            pipe.fileHandleForReading.readabilityHandler = nil
        }
        if let pipe = task.standardError as? Pipe {
            pipe.fileHandleForReading.readabilityHandler = nil
        }
    }

    private func terminate(_ task: Process, completion: (() -> Void)? = nil) {
        guard task.isRunning else {
            DispatchQueue.main.async {
                completion?()
            }
            return
        }
        task.terminate()
        DispatchQueue.global(qos: .utility).async { [restartGraceSeconds] in
            let deadline = Date().addingTimeInterval(restartGraceSeconds)
            while task.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.05)
            }
            if task.isRunning {
                Darwin.kill(task.processIdentifier, SIGKILL)
                task.waitUntilExit()
            }
            DispatchQueue.main.async {
                completion?()
            }
        }
    }

    private func finishReadyTransition(url: URL, token: String, generation: Int) {
        guard lifecycleGeneration == generation else { return }
        startupTimer?.invalidate()
        startupTimer = nil
        stableReadyTimer?.invalidate()
        stableReadyTimer = Timer.scheduledTimer(withTimeInterval: 30.0, repeats: false) { [weak self] _ in
            self?.launchAttempt = 0
        }
        portParsed = true
        tokenParsed = true
        apiToken = token
        state = .ready(url)
        startHealthChecks(generation: generation)
        notifyBackendReady()
    }

    // MARK: - 端口解析

    private func parseEndpoint(from data: Data, generation: Int) {
        guard lifecycleGeneration == generation else { return }
        guard let text = String(data: data, encoding: .utf8) else { return }
        let urlPattern = "http://127\\.0\\.0\\.1:(\\d+)"
        let tokenFilePattern = "token_file=(\\S+)"
        guard let urlRegex = try? NSRegularExpression(pattern: urlPattern),
              let tokenFileRegex = try? NSRegularExpression(pattern: tokenFilePattern),
              let urlMatch = urlRegex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let tokenFileMatch = tokenFileRegex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return }
        let portRange = urlMatch.range(at: 1)
        let tokenFileRange = tokenFileMatch.range(at: 1)
        guard let swiftPortRange = Range(portRange, in: text),
              let swiftTokenFileRange = Range(tokenFileRange, in: text),
              let port = Int(text[swiftPortRange]),
              let url = URL(string: "http://127.0.0.1:\(port)") else { return }
        let tokenFile = String(text[swiftTokenFileRange])
        guard let token = try? String(contentsOfFile: tokenFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines),
              !token.isEmpty else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.finishReadyTransition(url: url, token: token, generation: generation)
        }
    }

    private func lastErrorLines() -> String? {
        guard let text = String(data: errorBuffer, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty else { return nil }
        let lines = text.components(separatedBy: .newlines)
        return lines.suffix(3).joined(separator: "\n")
    }

    // MARK: - 健康检查

    private func startHealthChecks(generation: Int) {
        healthCheckTimer?.invalidate()
        healthCheckFailures = 0
        healthCheckInFlight = false
        healthCheckTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            guard let self = self,
                  self.lifecycleGeneration == generation,
                  !self.healthCheckInFlight else { return }
            self.healthCheckInFlight = true
            self.healthCheckTask = Task { [weak self] in
                await self?.performHealthCheck(generation: generation)
            }
        }
    }

    @MainActor
    private func performHealthCheck(generation: Int) async {
        defer {
            if lifecycleGeneration == generation {
                healthCheckInFlight = false
                healthCheckTask = nil
            }
        }
        guard lifecycleGeneration == generation else { return }
        guard case .ready(let url) = state else { return }
        do {
            let (_, response) = try await healthCheckSession.data(from: url.appendingPathComponent("health"))
            guard !Task.isCancelled,
                  lifecycleGeneration == generation,
                  case .ready(let currentURL) = state,
                  currentURL == url else { return }
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                self.healthCheckFailures += 1
                if self.healthCheckFailures >= 3 {
                    self.handleRecoverableBackendFailure("健康检查连续失败。")
                }
                return
            }
            self.healthCheckFailures = 0
        } catch {
            guard !Task.isCancelled,
                  lifecycleGeneration == generation,
                  case .ready(let currentURL) = state,
                  currentURL == url else { return }
            self.healthCheckFailures += 1
            if self.healthCheckFailures >= 3 {
                self.handleRecoverableBackendFailure("健康检查连续失败：\(error.localizedDescription)")
            }
        }
    }

    // MARK: - 通知

    /// 仅在作为 .app 运行时发送一次本地通知；裸二进制或测试环境跳过，
    /// 避免 UNUserNotificationCenter 在缺少 bundle 时崩溃。
    private func notifyBackendReady() {
        guard Bundle.main.bundlePath.hasSuffix(".app") else { return }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
        let content = UNMutableNotificationContent()
        content.title = "Netfix"
        content.body = "Netfix 已就绪，可以开始诊断网络"
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        center.add(request)
    }
}
