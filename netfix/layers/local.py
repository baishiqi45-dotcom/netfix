"""Local network layer diagnostics: Wi-Fi, DHCP, gateway, IPv4/IPv6."""
from __future__ import annotations

import re
import shutil
from typing import Any, Dict, List, Optional

from netfix.diagnose import register
from netfix.layers._helpers import (
    default_gateway,
    default_interface,
    diagnostic,
    has_ipv6_default_route,
    interface_ipv4,
    interface_ipv6s,
    ipv6_default_gateway,
    packet_loss_percent,
    status_from_loss,
    status_from_rssi,
)
from netfix.utils import run_command


_AIRPORT = (
    "/System/Library/PrivateFrameworks/Apple80211.framework"
    "/Versions/Current/Resources/airport"
)


def _wdutil_available() -> bool:
    return shutil.which("wdutil") is not None and run_command(["wdutil", "info"], timeout=5)["ok"]


def _wifi_from_wdutil() -> Dict[str, Any]:
    """Parse `wdutil info` for Wi-Fi signal and state."""
    res = run_command(["wdutil", "info"], timeout=10)
    out = {"available": False}
    if not res["ok"]:
        return out
    text = res["stdout"]
    out["available"] = True
    out["ssid"] = _re_search(r"SSID\s*:\s*(.+)", text)
    out["bssid"] = _re_search(r"BSSID\s*:\s*(\S+)", text)
    rssi = _re_search(r"RSSI\s*:\s*(-?\d+)", text)
    out["rssi"] = int(rssi) if rssi is not None else None
    noise = _re_search(r"Noise\s*:\s*(-?\d+)", text)
    out["noise"] = int(noise) if noise is not None else None
    tx_rate = _re_search(r"Tx Rate\s*:\s*(\S+)", text)
    out["tx_rate"] = tx_rate
    channel = _re_search(r"Channel\s*:\s*(\S+)", text)
    out["channel"] = channel
    return out


def _wifi_from_airport() -> Dict[str, Any]:
    """Parse the legacy `airport -I` output."""
    res = run_command([_AIRPORT, "-I"], timeout=10)
    out: Dict[str, Any] = {"available": False}
    if not res["ok"]:
        return out
    text = res["stdout"]
    out["available"] = True
    out["ssid"] = _re_search(r"\bSSID\s*:\s*(.+)", text)
    out["bssid"] = _re_search(r"\bBSSID\s*:\s*(\S+)", text)
    rssi = _re_search(r"agrCtlRSSI\s*:\s*(-?\d+)", text)
    out["rssi"] = int(rssi) if rssi is not None else None
    noise = _re_search(r"agrCtlNoise\s*:\s*(-?\d+)", text)
    out["noise"] = int(noise) if noise is not None else None
    out["tx_rate"] = _re_search(r"lastTxRate\s*:\s*(\S+)", text)
    out["channel"] = _re_search(r"channel\s*:\s*(\S+)", text)
    return out


def _wifi_fallback_ssid() -> Optional[str]:
    res = run_command(["networksetup", "-getairportnetwork", "en0"], timeout=10)
    if not res["ok"]:
        return None
    match = re.search(r"Current Wi-Fi Network:\s*(.+)", res["stdout"])
    return match.group(1).strip() if match else None


def _re_search(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None


@register("wifi_signal")
def wifi_signal(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Inspect Wi-Fi association and signal quality."""
    info: Dict[str, Any]
    source = "wdutil"
    if _wdutil_available():
        info = _wifi_from_wdutil()
    elif shutil.which(_AIRPORT):
        info = _wifi_from_airport()
        source = "airport"
    else:
        source = "networksetup"
        ssid = _wifi_fallback_ssid()
        info = {"available": bool(ssid), "ssid": ssid}

    if not info.get("available"):
        return diagnostic(
            "wifi_signal",
            "network",
            "warn",
            {"source": source, "error": "Wi-Fi information unavailable"},
        )

    rssi = info.get("rssi")
    noise = info.get("noise")
    snr = None
    if isinstance(rssi, int) and isinstance(noise, int):
        snr = rssi - noise
    status = status_from_rssi(rssi)
    details = {
        "source": source,
        "ssid": info.get("ssid"),
        "bssid": info.get("bssid"),
        "rssi": rssi,
        "noise": noise,
        "snr": snr,
        "tx_rate": info.get("tx_rate"),
        "channel": info.get("channel"),
    }
    return diagnostic("wifi_signal", "network", status, details)


@register("interface_state")
def interface_state(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Report the default outbound interface state (IPv4, IPv6, flags)."""
    iface = default_interface()
    if not iface:
        return diagnostic(
            "interface_state",
            "network",
            "fail",
            {"error": "no default interface found"},
        )

    ipv4 = interface_ipv4(iface)
    ipv6s = [ip for ip in interface_ipv6s(iface) if not ip.startswith("fe80:")]
    res = run_command(["ifconfig", iface], timeout=10)
    flags = ""
    mtu: Optional[int] = None
    active = False
    if res["ok"]:
        flags_match = re.search(r"flags=(\d+)<([^>]+)>", res["stdout"])
        if flags_match:
            flags = flags_match.group(2)
            active = "UP" in flags and "RUNNING" in flags
        mtu_match = re.search(r"mtu\s+(\d+)", res["stdout"])
        if mtu_match:
            mtu = int(mtu_match.group(1))

    if not ipv4 and not ipv6s:
        status = "fail"
    elif not active:
        status = "warn"
    else:
        status = "ok"

    return diagnostic(
        "interface_state",
        "network",
        status,
        {
            "interface": iface,
            "ipv4": ipv4,
            "ipv6": ipv6s,
            "active": active,
            "flags": flags,
            "mtu": mtu,
        },
    )


@register("dhcp_state")
def dhcp_state(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Inspect the DHCP lease for the default interface."""
    iface = default_interface() or "en0"
    res = run_command(["ipconfig", "getpacket", iface], timeout=10)
    if not res["ok"] or not res["stdout"].strip():
        return diagnostic(
            "dhcp_state",
            "network",
            "warn",
            {"interface": iface, "error": "no DHCP packet returned"},
        )

    text = res["stdout"]
    yiaddr = _re_search(r"yiaddr\s*=\s*(\S+)", text)
    router = _re_search(r"router\s*\(ip_mult\)\s*:\s*\{([^}]+)\}", text)
    dns = _re_search(r"domain_name_server\s*\(ip_mult\)\s*:\s*\{([^}]+)\}", text)
    server = _re_search(r"server_identifier\s*\(ip\)\s*:\s*(\S+)", text)
    lease_time = _re_search(r"lease_time\s*\(uint32\)\s*:\s*(\S+)", text)

    status = "ok"
    if not yiaddr or yiaddr.startswith("169.254."):
        status = "fail"
    elif not router or not dns:
        status = "warn"

    return diagnostic(
        "dhcp_state",
        "network",
        status,
        {
            "interface": iface,
            "yiaddr": yiaddr,
            "router": router,
            "dns": dns,
            "server": server,
            "lease_time": lease_time,
        },
    )


@register("gateway")
def gateway(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Ping the IPv4 default gateway."""
    gw = default_gateway()
    if not gw:
        return diagnostic(
            "gateway",
            "network",
            "fail",
            {"error": "default gateway not found"},
        )

    ping = run_command(["ping", "-c", "3", "-W", "2000", gw], timeout=timeout)
    loss = packet_loss_percent(ping["stdout"])
    status = status_from_loss(loss)
    return diagnostic(
        "gateway",
        "network",
        status,
        {"gateway": gw, "packet_loss": loss, "ping_ok": ping["ok"]},
    )


@register("ipv4_route")
def ipv4_route(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Verify that a usable IPv4 default route exists."""
    gw = default_gateway()
    iface = default_interface()
    if gw and iface:
        return diagnostic(
            "ipv4_route",
            "network",
            "ok",
            {"gateway": gw, "interface": iface},
        )
    if iface:
        return diagnostic(
            "ipv4_route",
            "network",
            "warn",
            {"interface": iface, "error": "no default gateway"},
        )
    return diagnostic(
        "ipv4_route",
        "network",
        "fail",
        {"error": "no default IPv4 route"},
    )


@register("ipv6_route")
def ipv6_route(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Verify that a usable IPv6 default route exists."""
    has_route = has_ipv6_default_route()
    gw = ipv6_default_gateway()
    if has_route and gw:
        return diagnostic(
            "ipv6_route",
            "network",
            "ok",
            {"gateway": gw, "has_default_route": True},
        )
    if has_route:
        return diagnostic(
            "ipv6_route",
            "network",
            "warn",
            {"has_default_route": True, "gateway": None, "error": "no gateway parsed"},
        )
    return diagnostic(
        "ipv6_route",
        "network",
        "warn",
        {"has_default_route": False, "error": "no IPv6 default route"},
    )


@register("dns_resolvers")
def dns_resolvers(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """List the active DNS resolvers from `scutil --dns`."""
    res = run_command(["scutil", "--dns"], timeout=10)
    if not res["ok"]:
        return diagnostic(
            "dns_resolvers",
            "dns",
            "warn",
            {"error": res["stderr"]},
        )

    text = res["stdout"]
    resolvers: List[str] = []
    for line in text.splitlines():
        match = re.search(r"nameserver\[\d+\]\s*:\s*(\S+)", line)
        if match:
            ip = match.group(1)
            if ip not in resolvers:
                resolvers.append(ip)

    return diagnostic(
        "dns_resolvers",
        "dns",
        "ok" if resolvers else "warn",
        {"resolvers": resolvers, "count": len(resolvers)},
    )
