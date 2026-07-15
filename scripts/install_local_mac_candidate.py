#!/usr/bin/env python3
"""Safely install and launch the locally built Netfix macOS candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = REPO_ROOT / "gui" / "macos" / ".build" / "Netfix.app"
DEFAULT_INSTALL = Path.home() / "Applications" / "Netfix.app"
DEFAULT_DESKTOP_LINK = Path.home() / "Desktop" / "Netfix.app"
MANIFEST_RELATIVE = Path("Contents/Resources/release-manifest.json")
APP_EXECUTABLE_RELATIVE = Path("Contents/MacOS/Netfix")
BACKEND_RELATIVE = Path("Contents/MacOS/netfix-backend")


class InstallBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    command: str


def _run(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=check,
        capture_output=True,
        text=True,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_process_rows(text: str) -> List[ProcessInfo]:
    processes: List[ProcessInfo] = []
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            processes.append(ProcessInfo(pid=int(parts[0]), ppid=int(parts[1]), command=parts[2]))
        except ValueError:
            continue
    return processes


def list_processes() -> List[ProcessInfo]:
    return parse_process_rows(_run(["ps", "-axo", "pid=,ppid=,command="]).stdout)


def _is_netfix_app(process: ProcessInfo) -> bool:
    executable = process.command.split(None, 1)[0]
    return executable.endswith("/Netfix.app/Contents/MacOS/Netfix")


def _is_bundled_backend(process: ProcessInfo) -> bool:
    executable = process.command.split(None, 1)[0]
    return executable.endswith("/Netfix.app/Contents/MacOS/netfix-backend")


def _descendant_pids(processes: Iterable[ProcessInfo], roots: Iterable[int]) -> set[int]:
    descendants = set(roots)
    changed = True
    process_list = list(processes)
    while changed:
        changed = False
        for process in process_list:
            if process.ppid in descendants and process.pid not in descendants:
                descendants.add(process.pid)
                changed = True
    return descendants


def discover_netfix_processes() -> Tuple[List[ProcessInfo], List[ProcessInfo]]:
    processes = list_processes()
    apps = [process for process in processes if _is_netfix_app(process)]
    descendants = _descendant_pids(processes, [process.pid for process in apps])
    backends = [
        process
        for process in processes
        if _is_bundled_backend(process)
        or (
            process.pid in descendants
            and process.pid not in {item.pid for item in apps}
            and "netfix" in process.command.lower()
        )
    ]
    return apps, backends


def _listening_ports(pid: int) -> List[int]:
    completed = _run(
        ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN", "-Fn"],
        check=False,
    )
    ports: List[int] = []
    for line in completed.stdout.splitlines():
        if not line.startswith("n") or ":" not in line:
            continue
        endpoint = line[1:].rsplit("->", 1)[0]
        try:
            ports.append(int(endpoint.rsplit(":", 1)[1]))
        except (IndexError, ValueError):
            continue
    return sorted(set(ports))


def _token_for_pid(pid: int) -> Optional[str]:
    path = Path.home() / ".netfix" / f"api-token-{pid}.txt"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _get_json(port: int, token: str, path: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"X-Netfix-Token": token},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Netfix API returned a non-object payload")
    return payload


def bridge_payload_blocks_shutdown(
    dashboard: Dict[str, Any],
    bridge: Dict[str, Any],
) -> Optional[str]:
    proxy = dashboard.get("proxy") if isinstance(dashboard.get("proxy"), dict) else {}
    applied = proxy.get("applied") if isinstance(proxy.get("applied"), dict) else {}
    bridge_facts = proxy.get("bridge") if isinstance(proxy.get("bridge"), dict) else {}
    lifecycle = bridge.get("lifecycle") if isinstance(bridge.get("lifecycle"), dict) else {}
    status = str(lifecycle.get("status") or bridge_facts.get("lifecycle_status") or "")
    if applied.get("owner") == "netfix" and applied.get("active") is True:
        return "Netfix currently owns the active system proxy"
    if bridge_facts.get("in_use") is True or status == "running_system":
        return "the system proxy currently points to a Netfix bridge"
    if bridge_facts.get("needs_recovery") is True or status == "recovery_required":
        return "the system proxy must be restored before replacing the app"
    return None


def audit_running_backends(backends: Iterable[ProcessInfo]) -> List[Dict[str, Any]]:
    backend_list = list(backends)
    listener_count = 0
    evidence: List[Dict[str, Any]] = []
    for process in backend_list:
        ports = _listening_ports(process.pid)
        if not ports:
            continue
        listener_count += 1
        token = _token_for_pid(process.pid)
        if not token:
            raise InstallBlocked(f"cannot audit Netfix backend PID {process.pid}: token file is missing")
        audited = False
        errors: List[str] = []
        for port in ports:
            try:
                dashboard = _get_json(port, token, "/dashboard/state")
                bridge = _get_json(port, token, "/proxy/bridge")
            except Exception as exc:
                errors.append(f"{port}: {exc}")
                continue
            reason = bridge_payload_blocks_shutdown(dashboard, bridge)
            if reason:
                raise InstallBlocked(f"refusing to stop Netfix backend PID {process.pid}: {reason}")
            evidence.append({
                "pid": process.pid,
                "port": port,
                "command": process.command,
                "effective_route": (dashboard.get("decision") or {}).get("effective_route"),
                "applied_owner": ((dashboard.get("proxy") or {}).get("applied") or {}).get("owner"),
                "bridge_status": (bridge.get("lifecycle") or {}).get("status"),
                "safe_to_stop": True,
            })
            audited = True
            break
        if not audited:
            raise InstallBlocked(
                f"cannot audit Netfix backend PID {process.pid}: " + "; ".join(errors)
            )
    if backend_list and listener_count == 0:
        # PyInstaller parent processes have no listening socket. They are safe
        # only when another child process in the same set was audited.
        app_descendant_only = all(_is_bundled_backend(process) for process in backend_list)
        if not app_descendant_only:
            raise InstallBlocked("Netfix is running but no auditable local backend listener was found")
    return evidence


def _wait_for_exit(pids: Iterable[int], timeout: float) -> List[int]:
    remaining = set(pids)
    deadline = time.time() + timeout
    while remaining and time.time() < deadline:
        remaining = {pid for pid in remaining if _pid_exists(pid)}
        if remaining:
            time.sleep(0.2)
    return sorted(remaining)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def stop_audited_processes(apps: List[ProcessInfo], backends: List[ProcessInfo]) -> None:
    if apps:
        _run(
            ["osascript", "-e", 'tell application id "dev.netfix.Netfix" to quit'],
            check=False,
        )
        remaining = _wait_for_exit([process.pid for process in apps], 8)
        for pid in remaining:
            os.kill(pid, signal.SIGTERM)
        remaining = _wait_for_exit(remaining, 8)
        if remaining:
            raise InstallBlocked(f"Netfix app did not exit after SIGTERM: {remaining}")

    # Clean up audited orphaned bundle backends. Older bundled Python servers
    # may ignore SIGTERM; SIGINT reaches their KeyboardInterrupt shutdown path.
    # Never use SIGKILL here.
    live_backends = [process.pid for process in backends if _pid_exists(process.pid)]
    for pid in live_backends:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    remaining = _wait_for_exit(live_backends, 8)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    remaining = _wait_for_exit(remaining, 8)
    if remaining:
        raise InstallBlocked(f"Netfix backend did not exit after graceful signals: {remaining}")


def verify_candidate(app_bundle: Path) -> Dict[str, Any]:
    manifest_path = app_bundle / MANIFEST_RELATIVE
    if not app_bundle.is_dir():
        raise InstallBlocked(f"candidate app does not exist: {app_bundle}")
    for relative in (APP_EXECUTABLE_RELATIVE, BACKEND_RELATIVE, MANIFEST_RELATIVE):
        path = app_bundle / relative
        if not path.exists():
            raise InstallBlocked(f"candidate is missing {relative}")
    _run([
        sys.executable,
        str(REPO_ROOT / "scripts" / "release_manifest.py"),
        "verify",
        "--repo-root",
        str(REPO_ROOT),
        "--app-bundle",
        str(app_bundle),
        "--manifest",
        str(manifest_path),
    ])
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _atomic_desktop_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() and not link.is_symlink():
        raise InstallBlocked(f"desktop entry is not a symlink; refusing to replace it: {link}")
    temporary = link.with_name(f".{link.name}.tmp-{uuid.uuid4().hex}")
    temporary.symlink_to(target)
    os.replace(temporary, link)


def install_candidate(candidate: Path, destination: Path, desktop_link: Path) -> Optional[Path]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.install-{uuid.uuid4().hex}"
    backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
    _run(["ditto", str(candidate), str(temporary)])
    verify_candidate(temporary)
    had_existing = destination.exists()
    try:
        if had_existing:
            os.replace(destination, backup)
        os.replace(temporary, destination)
        _atomic_desktop_link(desktop_link, destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if had_existing and backup.exists():
            os.replace(backup, destination)
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return backup if had_existing else None


def _mapped_executable(pid: int) -> Dict[str, Any]:
    completed = _run(["lsof", "-a", "-p", str(pid), "-d", "txt", "-Fnfi"], check=False)
    result: Dict[str, Any] = {}
    for line in completed.stdout.splitlines():
        if line.startswith("n") and not result.get("path"):
            result["path"] = line[1:]
        elif line.startswith("i") and not result.get("inode"):
            result["inode"] = line[1:]
    return result


def launch_and_verify(destination: Path, manifest: Dict[str, Any], timeout: float = 45) -> Dict[str, Any]:
    _run(["open", str(destination)])
    deadline = time.time() + timeout
    apps: List[ProcessInfo] = []
    backends: List[ProcessInfo] = []
    destination_apps: List[ProcessInfo] = []
    backend_evidence: List[Dict[str, Any]] = []
    last_audit_error: Optional[str] = None
    while time.time() < deadline:
        apps, backends = discover_netfix_processes()
        destination_apps = [
            process for process in apps
            if process.command.split(None, 1)[0].startswith(str(destination))
        ]
        if len(apps) == 1 and len(destination_apps) == 1 and backends:
            try:
                backend_evidence = audit_running_backends(backends)
            except InstallBlocked as exc:
                backend_evidence = []
                last_audit_error = str(exc)
            if backend_evidence:
                apps = destination_apps
                break
        time.sleep(0.3)
    if len(apps) != 1:
        raise InstallBlocked(f"expected one running Netfix app, found {len(apps)}")
    if len(destination_apps) != 1:
        raise InstallBlocked("the running Netfix app is not the installed candidate")
    if not backend_evidence:
        detail = f": {last_audit_error}" if last_audit_error else ""
        raise InstallBlocked(
            "bundled backend did not become auditable before timeout" + detail
        )
    apps = destination_apps
    app_process = apps[0]
    expected_app = destination / APP_EXECUTABLE_RELATIVE
    expected_backend = destination / BACKEND_RELATIVE
    app_sha = sha256_file(expected_app)
    backend_sha = sha256_file(expected_backend)
    if app_sha != manifest.get("app_executable_sha256"):
        raise InstallBlocked("installed app executable hash does not match manifest")
    if backend_sha != manifest.get("backend_sha256"):
        raise InstallBlocked("installed backend hash does not match manifest")
    if not any(str(destination / BACKEND_RELATIVE) in process.command for process in backends):
        raise InstallBlocked("running backend is not the one bundled inside the installed app")
    mapped = _mapped_executable(app_process.pid)
    if mapped.get("path") and Path(str(mapped["path"])).resolve() != expected_app.resolve():
        raise InstallBlocked(f"running executable maps to {mapped.get('path')}, not {expected_app}")
    return {
        "app_pid": app_process.pid,
        "app_command": app_process.command,
        "mapped_executable": mapped,
        "app_executable_sha256": app_sha,
        "backend_sha256": backend_sha,
        "backend_processes": [process.pid for process in backends],
        "backend_audit": backend_evidence,
    }


def _remove_backup(path: Optional[Path]) -> None:
    if path and path.exists():
        shutil.rmtree(path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-bundle", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--install-target", type=Path, default=DEFAULT_INSTALL)
    parser.add_argument("--desktop-link", type=Path, default=DEFAULT_DESKTOP_LINK)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        raise InstallBlocked("local candidate installation requires macOS")
    candidate = args.app_bundle.expanduser().resolve()
    destination = args.install_target.expanduser().resolve()
    desktop_link = args.desktop_link.expanduser()
    manifest = verify_candidate(candidate)
    apps, backends = discover_netfix_processes()
    shutdown_audit = audit_running_backends(backends)
    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "candidate": str(candidate),
            "destination": str(destination),
            "desktop_link": str(desktop_link),
            "running_app_pids": [process.pid for process in apps],
            "shutdown_audit": shutdown_audit,
        }, ensure_ascii=False, indent=2))
        return 0

    stop_audited_processes(apps, backends)
    backup: Optional[Path] = None
    try:
        backup = install_candidate(candidate, destination, desktop_link)
        installed_manifest = verify_candidate(destination)
        runtime = launch_and_verify(destination, installed_manifest)
    except Exception:
        # Keep the previous hidden backup for manual recovery if launch-time
        # verification fails; do not silently replace a running candidate.
        raise
    _remove_backup(backup)

    if desktop_link.resolve() != destination:
        raise InstallBlocked("desktop link does not resolve to the installed candidate")
    evidence = {
        "schema_version": "netfix_local_install_evidence.v1",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(candidate),
        "installed_app": str(destination),
        "desktop_link": str(desktop_link),
        "desktop_resolves_to": str(desktop_link.resolve()),
        "manifest": {
            key: installed_manifest.get(key)
            for key in ("version", "build_id", "built_at", "git_sha", "dirty", "source_fingerprint")
        },
        "shutdown_audit": shutdown_audit,
        "runtime": runtime,
        "old_system_app_preserved": str(Path("/Applications/Netfix.app")),
    }
    if args.evidence:
        evidence_path = args.evidence.expanduser()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallBlocked as exc:
        print(f"install blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
