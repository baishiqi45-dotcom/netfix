from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "gui" / "macos" / "Sources" / "Backend.swift"


def _source() -> str:
    return BACKEND.read_text(encoding="utf-8")


def test_backend_startup_failures_retry_before_final_failure():
    source = _source()

    assert "private let maxLaunchAttempts = 3" in source
    assert "private func handleRecoverableBackendFailure" in source
    assert "if launchAttempt < maxLaunchAttempts" in source
    assert "self.start(resetAttempts: false)" in source
    assert "已连续尝试 \\(maxLaunchAttempts) 次仍失败" in source


def test_backend_timeout_and_health_failures_enter_recovery_flow():
    source = _source()

    assert "startupTimeoutSeconds: TimeInterval = 15.0" in source
    assert 'handleRecoverableBackendFailure("Netfix 启动超时。")' in source
    assert 'handleRecoverableBackendFailure("后端进程异常退出。")' in source
    assert 'handleRecoverableBackendFailure("健康检查连续失败。")' in source
    assert 'handleRecoverableBackendFailure("健康检查连续失败：\\(error.localizedDescription)")' in source


def test_backend_restart_terminates_stale_process_off_main_thread():
    source = _source()

    assert "private let restartGraceSeconds: TimeInterval = 2.0" in source
    assert "private func terminate(_ task: Process, completion: (() -> Void)? = nil)" in source
    assert "task.terminate()" in source
    assert "DispatchQueue.global(qos: .utility).async" in source
    assert "Thread.sleep(forTimeInterval: 0.05)" in source
    assert "Darwin.kill(task.processIdentifier, SIGKILL)" in source
    assert "task.waitUntilExit()" in source
    assert "RunLoop.current.run" not in source


def test_backend_launch_generation_guards_stale_output_and_health_checks():
    source = _source()

    assert "private var lifecycleGeneration = 0" in source
    assert "let generation = lifecycleGeneration" in source
    assert "self.lifecycleGeneration == generation" in source
    assert "self.process === task" in source
    assert "parseEndpoint(from: self.outputBuffer, generation: generation)" in source
    assert "finishReadyTransition(url: url, token: token, generation: generation)" in source
    assert "performHealthCheck(generation: generation)" in source
    assert "case .ready(let currentURL) = state" in source
    assert "currentURL == url" in source


def test_backend_health_check_is_short_timeout_and_non_overlapping():
    source = _source()

    assert "timeoutIntervalForRequest = 3.0" in source
    assert "timeoutIntervalForResource = 5.0" in source
    assert "private var healthCheckInFlight = false" in source
    assert "!self.healthCheckInFlight" in source
    assert "healthCheckTask?.cancel()" in source


def test_backend_stdout_and_stderr_buffers_are_mutated_on_main_thread():
    source = _source()

    stdout_handler = re.search(r"if let pipe = task\.standardOutput as\? Pipe \{(.*?)if let pipe = task\.standardError", source, re.S)
    stderr_handler = re.search(r"if let pipe = task\.standardError as\? Pipe \{(.*?)task\.terminationHandler", source, re.S)

    assert stdout_handler is not None
    assert stderr_handler is not None
    assert "DispatchQueue.main.async" in stdout_handler.group(1)
    assert "outputBuffer.append" in stdout_handler.group(1)
    assert "errorBuffer.append" not in stdout_handler.group(1)
    assert "DispatchQueue.main.async" in stderr_handler.group(1)
    assert "errorBuffer.append" in stderr_handler.group(1)
    assert "outputBuffer.append" not in stderr_handler.group(1)
