from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DELEGATE = ROOT / "gui" / "macos" / "Sources" / "AppDelegate.swift"


def test_macos_quit_guard_checks_proxy_bridge_before_stopping_backend():
    source = APP_DELEGATE.read_text(encoding="utf-8")

    assert "func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply" in source
    assert "return .terminateLater" in source
    assert "handleGuardedTermination(sender)" in source
    assert "try await client.proxyBridge()" in source
    assert "bridgeQuitAction(for: state)" in source
    assert "sender.reply(toApplicationShouldTerminate: true)" in source
    assert "sender.reply(toApplicationShouldTerminate: false)" in source


def test_macos_quit_guard_offers_confirmed_recovery_or_rollback():
    source = APP_DELEGATE.read_text(encoding="utf-8")

    assert 'lifecycle.status == "recovery_required"' in source
    assert 'lifecycle.status == "running_system"' in source
    assert "recoverProxyBridge(confirmed: true)" in source
    assert "rollbackProxyProfile(confirmed: true)" in source
    assert "恢复网络设置后退出" in source
    assert "取消退出" in source
    assert "仍然退出" in source
    assert "forceQuit" in source
