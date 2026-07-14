"""Platform, process, port and proxy-client detection for netfix."""
from __future__ import annotations

import logging
import os
import platform
import re
from pathlib import Path
from typing import Any

from netfix.constants import COMMON_PROXY_PORTS
from netfix.utils import command_executable, run_command

logger = logging.getLogger(__name__)

# Ordered so that more specific names are checked before generic substrings.
# xray/sing-box are placed before v2rayN because v2rayN launches them with
# bundle paths that contain the string "v2rayN".
_PROXY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("xray", ["xray"]),
    ("singbox", ["sing-box", "singbox"]),
    ("mihomo", ["mihomo", "clash.meta", "clash-meta"]),
    ("clash", ["clash"]),
    ("v2rayn", ["v2rayN", "v2rayn.app"]),
    ("v2ray", ["v2ray"]),
    ("wireguard", ["wireguard-go", "wireguard"]),
]


def _coerce_scutil_value(value: str) -> str | int:
    """Convert an scutil scalar string to int when possible."""
    try:
        return int(value)
    except ValueError:
        return value


def _parse_scutil_dict(text: str) -> dict[str, Any]:
    """Parse the nested dictionary printed by ``scutil --proxy``."""
    stack: list[dict[str, Any]] = [{}]
    current_key: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped == "{":
            new_dict: dict[str, Any] = {}
            if current_key is not None:
                stack[-1][current_key] = new_dict
                current_key = None
            stack.append(new_dict)
        elif stripped == "}":
            if len(stack) > 1:
                stack.pop()
            current_key = None
        elif ":" in stripped:
            key, _, rest = stripped.partition(":")
            key = key.strip()
            value = rest.strip()
            if value == "{":
                new_dict = {}
                stack[-1][key] = new_dict
                stack.append(new_dict)
                current_key = None
            else:
                stack[-1][key] = _coerce_scutil_value(value)
                current_key = key
    return stack[0]


def detect_platform() -> dict[str, str | None]:
    """Detect the current platform, default interface, gateway and local IP.

    Returns:
        A dict with keys ``platform``, ``interface``, ``gateway`` and ``self_ip``.
        Missing values are returned as ``None``.
    """
    result: dict[str, str | None] = {
        "platform": platform.system().lower(),
        "interface": None,
        "gateway": None,
        "self_ip": None,
    }

    route = run_command(["route", "-n", "get", "default"])
    if route["ok"]:
        stdout = route["stdout"]
        iface_match = re.search(r"interface:\s*(\S+)", stdout)
        gateway_match = re.search(r"gateway:\s*(\S+)", stdout)
        if iface_match:
            result["interface"] = iface_match.group(1)
        if gateway_match:
            result["gateway"] = gateway_match.group(1)

    interface = result["interface"]
    if interface:
        ipconfig = run_command(["ipconfig", "getifaddr", interface])
        if ipconfig["ok"]:
            result["self_ip"] = ipconfig["stdout"].strip() or None
        if not result["self_ip"]:
            ifconfig = run_command(["ifconfig", interface])
            if ifconfig["ok"]:
                inet_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ifconfig["stdout"])
                if inet_match:
                    result["self_ip"] = inet_match.group(1)

    return result


def detect_system_proxy() -> dict[str, Any]:
    """Parse ``scutil --proxy`` and return enabled proxy endpoints.

    Returns:
        A dict with keys ``http``, ``https``, ``socks`` and ``pac``.
        Disabled entries are ``None``.
    """
    result: dict[str, str | None] = {
        "http": None,
        "https": None,
        "socks": None,
        "pac": None,
        "_detection_status": "unknown",
    }
    try:
        output = run_command(["scutil", "--proxy"])
        if not output["ok"]:
            return result
        parsed = _parse_scutil_dict(output["stdout"])
        proxies = parsed.get("Proxies") or parsed

        def _endpoint(host_key: str, port_key: str) -> str | None:
            host = proxies.get(host_key)
            port = proxies.get(port_key)
            if host and port:
                return f"{host}:{port}"
            return None

        if proxies.get("HTTPEnable"):
            result["http"] = _endpoint("HTTPProxy", "HTTPPort")
        if proxies.get("HTTPSEnable"):
            result["https"] = _endpoint("HTTPSProxy", "HTTPSPort")
        if proxies.get("SOCKSEnable"):
            result["socks"] = _endpoint("SOCKSProxy", "SOCKSPort")
        if proxies.get("ProxyAutoConfigEnable"):
            result["pac"] = proxies.get("ProxyAutoConfigURLString")
        result["_detection_status"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("detect_system_proxy failed: %s", exc)
    return result


def detect_listening_ports() -> list[dict[str, Any]]:
    """List TCP listening ports associated with common proxy ports.

    Uses ``lsof -nP -iTCP -sTCP:LISTEN``.  Returns a list of dicts with
    ``command``, ``pid``, ``host``, ``port``, ``protocol`` and ``name``.
    """
    results: list[dict[str, Any]] = []
    output = run_command(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
    if not output["ok"]:
        return results

    lines = output["stdout"].splitlines()
    if not lines:
        return results

    for line in lines[1:]:
        # lsof network lines end with "TCP <endpoint> (LISTEN)"; the endpoint
        # can contain spaces when IPv6 or additional state is printed, so use
        # a regex anchored at the end of the line.
        listen_match = re.search(r"(\S+:\d+)\s+\(LISTEN\)\s*$", line)
        if not listen_match:
            continue
        raw_name = listen_match.group(1)
        parts = line.split()
        if len(parts) < 2:
            continue
        command = parts[0]
        pid = parts[1]
        match = re.match(r"(?:\[?([^\]]*)\]?):(\d+)", raw_name)
        if not match:
            continue
        host, port_str = match.groups()
        try:
            port = int(port_str)
        except ValueError:
            continue
        if port not in COMMON_PROXY_PORTS:
            continue
        results.append(
            {
                "command": command,
                "pid": pid,
                "host": host or "*",
                "port": port,
                "protocol": "tcp",
                "name": raw_name,
            }
        )
    return results


def detect_running_proxies() -> dict[str, list[dict[str, str]]]:
    """Detect known proxy/VPN processes from ``ps -axo pid,command``.

    Returns:
        A mapping from canonical core name to a list of process records.
        Each record contains ``pid`` and ``command``.
    """
    found: dict[str, list[dict[str, str]]] = {}
    output = run_command(["ps", "-axo", "pid,command"])
    if not output["ok"]:
        return found

    used: set[int] = set()
    for line in output["stdout"].splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        command = parts[1]
        exe = command_executable(command)
        exe_str = str(exe).lower() if exe else ""
        exe_name = exe.name.lower() if exe else ""

        for core_name, keywords in _PROXY_KEYWORDS:
            if pid in used:
                break
            for keyword in keywords:
                key_lower = keyword.lower()
                if key_lower in exe_name or key_lower in exe_str:
                    found.setdefault(core_name, []).append(
                        {"pid": str(pid), "command": command}
                    )
                    used.add(pid)
                    break
    return found


def detect_environment() -> dict[str, Any]:
    """Aggregate platform, system proxy, listening ports and running proxies."""
    return {
        "platform": detect_platform(),
        "system_proxy": detect_system_proxy(),
        "listening_ports": detect_listening_ports(),
        "running_proxies": detect_running_proxies(),
    }


def get_core(env: dict[str, Any] | None = None) -> Any:
    """Return the best matching core adapter for the current environment.

    Args:
        env: The environment dict returned by :func:`detect_environment`.
             If ``None``, a fresh detection is performed.

    Returns:
        An instance of a :class:`netfix.cores.base.CoreBase` subclass, or
        ``None`` when no supported client is detected.
    """
    # Local import avoids circular dependencies between detect and cores.
    from netfix.cores import get_core as _get_core

    if env is None:
        env = detect_environment()
    return _get_core(env)
