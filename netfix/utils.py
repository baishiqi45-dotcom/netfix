"""Utility helpers for netfix"""
import re
import shutil
import subprocess
import sys
import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def run_command(
    cmd: List[str],
    timeout: int = 30,
    check: bool = False,
    shell: bool = False,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
    stdin: Optional[int] = subprocess.DEVNULL,
) -> Dict[str, Any]:
    """Run a command and return a structured result."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            shell=shell,
            env=merged_env,
            cwd=cwd,
            stdin=stdin,
        )
        return {
            "cmd": " ".join(cmd) if not shell else cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": " ".join(cmd) if not shell else cmd,
            "returncode": -1,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "ok": False,
            "timeout": True,
        }
    except FileNotFoundError:
        return {
            "cmd": " ".join(cmd) if not shell else cmd,
            "returncode": -2,
            "stdout": "",
            "stderr": f"command not found: {cmd[0]}",
            "ok": False,
        }


def admin_command_script(command: str) -> str:
    """Return an AppleScript that runs *command* with administrator privileges.

    Leading ``sudo`` is stripped because the script itself already runs as root
    after the user authorizes via the macOS password dialog.
    """
    stripped = re.sub(r"^\s*sudo\s+", "", command)
    escaped = stripped.replace("\\", "\\\\").replace('"', '\\"')
    return f'do shell script "{escaped}" with administrator privileges'


def to_json(obj: Any, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    return json.dumps(obj, ensure_ascii=False, default=str)


def print_json(obj: Any) -> None:
    print(to_json(obj))


def human_time() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat()


def confirm(prompt: str, default: bool = False) -> bool:
    default_str = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{default_str}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_private_dir(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def secure_write_text(path: Path, text: str, mode: int = 0o600) -> Path:
    ensure_private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(path), flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return path


def secure_append_text(path: Path, text: str, mode: int = 0o600) -> Path:
    ensure_private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(str(path), flags, mode)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(text)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return path


def secure_write_json(path: Path, data: Any, *, sort_keys: bool = False, mode: int = 0o600) -> Path:
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=sort_keys, default=str)
    return secure_write_text(path, payload, mode=mode)


def find_first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def command_executable(command: str) -> Optional[Path]:
    """Return the executable Path for a ``ps`` command line.

    Handles absolute paths that contain spaces (e.g. ``/Users/x/Library/Application
    Support/.../xray``) by joining tokens until an existing file is found.
    Relative or bare executables are resolved with ``shutil.which``.
    """
    if not command:
        return None
    tokens = command.split()
    if not tokens:
        return None
    if tokens[0].startswith("/"):
        for i in range(1, len(tokens) + 1):
            candidate = Path(" ".join(tokens[:i]))
            if candidate.is_file():
                return candidate
        first = Path(tokens[0])
        return first if first.is_file() else None
    exe = shutil.which(tokens[0])
    return Path(exe) if exe else None
