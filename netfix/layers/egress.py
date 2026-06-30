"""Egress identity and leak diagnostics."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from netfix.diagnose import register
from netfix.ip_intel import current_ipv4, current_ipv6, get_ip_info
from netfix.layers._helpers import (
    default_interface,
    diagnostic,
    has_ipv6_default_route,
    interface_ipv4,
    is_private_ip,
)
from netfix.utils import run_command


def _dns_resolvers() -> List[str]:
    """Return the list of active DNS resolver IPs."""
    res = run_command(["scutil", "--dns"], timeout=10)
    if not res["ok"]:
        return []
    out: List[str] = []
    for line in res["stdout"].splitlines():
        match = re.search(r"nameserver\[\d+\]\s*:\s*(\S+)", line)
        if match:
            ip = match.group(1)
            if ip not in out:
                out.append(ip)
    return out


def _proxy_active(env: Dict[str, Any]) -> bool:
    """Return True if a proxy core or system proxy appears active."""
    if env.get("active_core") or env.get("mixed_port"):
        return True
    sp = env.get("system_proxy") or {}
    if sp.get("http") or sp.get("https") or sp.get("socks"):
        return True
    return False


@register("ip_reputation")
def ip_reputation(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Check public IPv4 identity, ISP/ASN and reputation."""
    probe_timeout = min(timeout, 10)
    info = get_ip_info(timeout=probe_timeout)
    if info.get("status") != "ok":
        return diagnostic(
            "ip_reputation",
            "egress",
            "warn",
            info,
        )

    local_ip = interface_ipv4(default_interface() or "en0")
    egress_ip = info.get("ip")
    same_as_local = bool(local_ip and egress_ip and local_ip == egress_ip)

    ip_type = info.get("ip_type", "unknown")
    risk = info.get("risk_score")

    status = "ok"
    if same_as_local and _proxy_active(env):
        status = "warn"
    elif ip_type in ("hosting/datacenter", "proxy/vpn"):
        status = "warn"
    elif risk is not None and risk >= 66:
        status = "fail"
    elif risk is not None and risk >= 33:
        status = "warn"

    details = {
        "ip": egress_ip,
        "local_ip": local_ip,
        "same_as_local": same_as_local,
        "country": info.get("country"),
        "isp": info.get("isp") or info.get("org"),
        "asn": info.get("asn"),
        "ip_type": ip_type,
        "risk_score": risk,
        "cached": info.get("cached", False),
        "source": info.get("source"),
    }
    if info.get("risk_info"):
        details["risk_info"] = info["risk_info"]

    return diagnostic("ip_reputation", "egress", status, details)


@register("dns_leak")
def dns_leak(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Detect potential DNS leaks when a proxy/VPN is active."""
    resolvers = _dns_resolvers()
    if not resolvers:
        return diagnostic(
            "dns_leak",
            "dns",
            "warn",
            {"error": "unable to read DNS resolvers"},
        )

    private_resolvers = [ip for ip in resolvers if is_private_ip(ip)]
    proxy_on = _proxy_active(env)

    # Heuristic: if a proxy is active but DNS still points at a local router,
    # queries may bypass the tunnel.
    if proxy_on and private_resolvers:
        status = "warn"
        reason = "proxy active but DNS resolvers are local"
    elif proxy_on and not private_resolvers:
        status = "ok"
        reason = "proxy active and DNS resolvers are non-local"
    else:
        status = "ok"
        reason = "no proxy active; local DNS is expected"

    return diagnostic(
        "dns_leak",
        "dns",
        status,
        {
            "resolvers": resolvers,
            "private_resolvers": private_resolvers,
            "proxy_active": proxy_on,
            "reason": reason,
        },
    )


@register("ipv6_leak")
def ipv6_leak(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Detect whether IPv6 is leaking around a proxy/VPN."""
    probe_timeout = min(timeout, 10)
    ipv6_addr = current_ipv6(timeout=probe_timeout)
    has_route = has_ipv6_default_route()
    proxy_on = _proxy_active(env)

    if ipv6_addr and proxy_on:
        status = "warn"
        reason = "proxy active but public IPv6 address still reachable"
    elif ipv6_addr and has_route:
        status = "warn"
        reason = "public IPv6 address present and default route exists"
    elif has_route and proxy_on:
        status = "warn"
        reason = "proxy active and IPv6 default route present; no public IPv6 observed"
    else:
        status = "ok"
        reason = "no public IPv6 leak detected"

    return diagnostic(
        "ipv6_leak",
        "egress",
        status,
        {
            "public_ipv6": ipv6_addr,
            "ipv6_default_route": has_route,
            "proxy_active": proxy_on,
            "leak_confirmed": bool(ipv6_addr),
            "fallback_risk": bool(has_route and proxy_on and not ipv6_addr),
            "reason": reason,
        },
    )
