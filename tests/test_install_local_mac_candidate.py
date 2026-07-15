import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_local_mac_candidate.py"
SPEC = importlib.util.spec_from_file_location("install_local_mac_candidate", SCRIPT)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


def test_process_rows_keep_command_and_parent_relationship():
    rows = installer.parse_process_rows(
        "  101 1 /Users/me/Applications/Netfix.app/Contents/MacOS/Netfix\n"
        "  102 101 /Users/me/Applications/Netfix.app/Contents/MacOS/netfix-backend server\n"
    )

    assert [(row.pid, row.ppid) for row in rows] == [(101, 1), (102, 101)]
    assert rows[1].command.endswith("netfix-backend server")


@pytest.mark.parametrize(
    ("dashboard", "bridge", "expected"),
    [
        (
            {"proxy": {"applied": {"owner": "netfix", "active": True}}},
            {"lifecycle": {"status": "running_system"}},
            "owns the active system proxy",
        ),
        (
            {"proxy": {"applied": {"owner": "none", "active": False}, "bridge": {"needs_recovery": True}}},
            {"lifecycle": {"status": "recovery_required"}},
            "must be restored",
        ),
    ],
)
def test_shutdown_is_blocked_while_netfix_network_state_is_live(dashboard, bridge, expected):
    assert expected in installer.bridge_payload_blocks_shutdown(dashboard, bridge)


def test_external_proxy_without_netfix_bridge_is_safe_to_stop():
    dashboard = {
        "decision": {"effective_route": "external_system_proxy"},
        "proxy": {
            "applied": {"owner": "external", "active": True},
            "bridge": {"in_use": False, "needs_recovery": False},
        },
    }
    bridge = {"lifecycle": {"status": "stopped"}}

    assert installer.bridge_payload_blocks_shutdown(dashboard, bridge) is None


def test_desktop_entry_is_replaced_only_when_it_is_a_symlink(tmp_path):
    first = tmp_path / "First.app"
    second = tmp_path / "Second.app"
    link = tmp_path / "Netfix.app"
    first.mkdir()
    second.mkdir()
    link.symlink_to(first)

    installer._atomic_desktop_link(link, second)

    assert link.is_symlink()
    assert link.resolve() == second


def test_real_desktop_entry_is_never_overwritten(tmp_path):
    destination = tmp_path / "Installed.app"
    destination.mkdir()
    entry = tmp_path / "Netfix.app"
    entry.mkdir()

    with pytest.raises(installer.InstallBlocked, match="not a symlink"):
        installer._atomic_desktop_link(entry, destination)


def test_installer_never_uses_forced_process_kill():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "signal.SIGINT" in source
    assert "signal.SIGKILL" not in source
    assert "kill -9" not in source


def test_launch_fails_when_bundled_backend_never_becomes_auditable(tmp_path, monkeypatch):
    destination = tmp_path / "Netfix.app"
    app = installer.ProcessInfo(
        pid=101,
        ppid=1,
        command=str(destination / installer.APP_EXECUTABLE_RELATIVE),
    )
    backend = installer.ProcessInfo(
        pid=102,
        ppid=101,
        command=str(destination / installer.BACKEND_RELATIVE),
    )
    clock = iter((0.0, 0.0, 2.0))

    monkeypatch.setattr(installer, "_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        installer,
        "discover_netfix_processes",
        lambda: ([app], [backend]),
    )
    monkeypatch.setattr(installer, "audit_running_backends", lambda backends: [])
    monkeypatch.setattr(installer.time, "time", lambda: next(clock))
    monkeypatch.setattr(installer.time, "sleep", lambda seconds: None)

    with pytest.raises(installer.InstallBlocked, match="did not become auditable"):
        installer.launch_and_verify(destination, {}, timeout=1)
