"""Shared helpers for layered diagnostics."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from netfix.utils import run_command


def default_interface() -> Optional[str]:
    """Return the BSD name of the default outbound interface."""
    res = run_command(["route", "-n", "get", "default"], timeout=10)
    if not res["ok"]:
        return None
    match = re.search(r"interface:\s*(\S+)", res["stdout"])
    return match.group(1) if match else None


def interface_ipv4(iface: str) -> Optional[str]:
    """Return the IPv4 address assigned to *iface*."""
    res = run_command(["ipconfig", "getifaddr", iface], timeout=10)
    if res["ok"] and res["stdout"].strip():
        return res["stdout"].strip()
    res = run_command(["ifconfig", iface], timeout=10)
    if not res["ok"]:
        return None
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", res["stdout"])
    return match.group(1) if match else None


def interface_ipv6s(iface: str) -> List[str]:
    """Return the global IPv6 addresses assigned to *iface*."""
    res = run_command(["ifconfig", iface], timeout=10)
    if not res["ok"]:
        return []
    return re.findall(r"inet6\s+([0-9a-fA-F:]+)", res["stdout"])


def default_gateway() -> Optional[str]:
    """Return the IPv4 default gateway."""
    res = run_command(["route", "-n", "get", "default"], timeout=10)
    if not res["ok"]:
        return None
    match = re.search(r"gateway:\s*(\S+)", res["stdout"])
    return match.group(1) if match else None


def ipv6_default_gateway() -> Optional[str]:
    """Return the IPv6 default gateway if one exists."""
    res = run_command(["route", "-n", "get", "-inet6", "default"], timeout=10)
    if not res["ok"]:
        return None
    match = re.search(r"gateway:\s*(\S+)", res["stdout"])
    return match.group(1) if match else None


def has_ipv6_default_route() -> bool:
    """Return True if an IPv6 default route is present."""
    res = run_command(["netstat", "-rn", "-f", "inet6"], timeout=10)
    if not res["ok"]:
        return False
    return "default" in res["stdout"]


def parse_packet_loss(stdout: str) -> Optional[str]:
    """Extract the packet loss line from a ping summary."""
    for line in stdout.splitlines():
        if "packet loss" in line.lower():
            return line.strip()
    return None


def packet_loss_percent(stdout: str) -> Optional[float]:
    """Return packet loss percentage from ping output, or None."""
    text = parse_packet_loss(stdout) or ""
    match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", text)
    if match:
        return float(match.group(1))
    return None


def status_from_rssi(rssi: Optional[int]) -> str:
    """Map Wi-Fi RSSI in dBm to ok/warn/fail."""
    if rssi is None:
        return "warn"
    if rssi >= -55:
        return "ok"
    if rssi >= -70:
        return "warn"
    return "fail"


def status_from_loss(loss: Optional[float]) -> str:
    """Map packet loss percentage to ok/warn/fail."""
    if loss is None:
        return "warn"
    if loss == 0:
        return "ok"
    if loss <= 5:
        return "warn"
    return "fail"


def is_private_ip(ip: str) -> bool:
    """Return True for RFC1918 / typical LAN IPs."""
    return bool(re.match(r"^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|169\.254\.|127\.)", ip))


def diagnostic(
    name: str,
    layer: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standardized diagnostic result dict."""
    return {
        "name": name,
        "layer": layer,
        "status": status,
        "details": details or {},
    }
