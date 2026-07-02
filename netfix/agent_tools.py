"""Safe, read-only tools exposed to AI agents via MCP.

All functions return structured, redacted network state. Secrets such as
passwords, UUIDs, tokens and subscription URLs are masked before returning.
"""
from __future__ import annotations

import platform
import re
import socket
from typing import Any, Dict, List, Optional

from netfix import diagnose
from netfix.detect import detect_environment, detect_system_proxy, get_core
from netfix.ip_intel import current_ipv4, get_ip_info
from netfix.layers._helpers import (
    default_gateway,
    default_interface,
    has_ipv6_default_route,
    interface_ipv4,
    interface_ipv6s,
)
from netfix.redaction import redact_text
from netfix.utils import run_command


def _safe_text(value: Any, max_len: int = 500) -> str:
    """Return a short, redacted command-output snippet for agent-facing tools."""
    text = redact_text(str(value or ""))
    return text[:max_len]


def _redact_url(url: Optional[str]) -> Optional[str]:
    """Mask any user:pass credentials embedded in a proxy URL."""
    if not url or "://" not in url:
        return url
    try:
        # scheme://user:pass@host:port
        return re.sub(r"(://)[^@]+@", r"\1***@", url)
    except re.error:
        return url


def _parse_scutil_dns() -> Dict[str, Any]:
    res = run_command(["scutil", "--dns"], timeout=10)
    if not res["ok"]:
        return {"error": _safe_text(res["stderr"])}
    resolvers: List[str] = []
    search_domains: List[str] = []
    for line in res["stdout"].splitlines():
        ns = re.search(r"nameserver\[\d+\]\s*:\s*(\S+)", line)
        if ns:
            ip = ns.group(1)
            if ip not in resolvers:
                resolvers.append(ip)
        sd = re.search(r"search_domain\[\d+\]\s*:\s*(\S+)", line)
        if sd:
            domain = sd.group(1)
            if domain not in search_domains:
                search_domains.append(domain)
    return {"resolvers": resolvers, "search_domains": search_domains}


def _routes() -> List[Dict[str, Any]]:
    res = run_command(["netstat", "-rn", "-f", "inet"], timeout=10)
    if not res["ok"]:
        return []
    routes: List[Dict[str, Any]] = []
    for line in res["stdout"].splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            routes.append({
                "destination": parts[0],
                "gateway": parts[1],
                "flags": parts[2],
                "refs": parts[3],
                "use": parts[4],
                "interface": parts[5],
            })
        except Exception:
            continue
    return routes


def _listeners() -> List[Dict[str, Any]]:
    res = run_command(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=10)
    if not res["ok"]:
        return []
    out: List[Dict[str, Any]] = []
    for line in res["stdout"].splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        endpoint = parts[-2] if len(parts) >= 10 else parts[-1]
        match = re.search(r"(?:\[?([^\]]*)\]?):(\d+)", endpoint)
        if not match:
            continue
        host, port = match.groups()
        out.append({
            "command": parts[0],
            "pid": parts[1],
            "user": parts[2],
            "fd": parts[3],
            "type": parts[4],
            "device": parts[5],
            "size": parts[6],
            "node": parts[7],
            "host": host,
            "port": int(port),
            "name": endpoint,
        })
    return out


def get_global_state() -> Dict[str, Any]:
    """High-level network path summary."""
    iface = default_interface()
    return {
        "platform": platform.system().lower(),
        "primary_interface": iface,
        "gateway": default_gateway(),
        "self_ipv4": interface_ipv4(iface) if iface else None,
        "self_ipv6": interface_ipv6s(iface) if iface else [],
        "has_ipv6_default_route": has_ipv6_default_route(),
        "public_ipv4": current_ipv4(timeout=10),
    }


def get_interfaces() -> Dict[str, Any]:
    """List network interfaces and their states."""
    res = run_command(["ifconfig"], timeout=10)
    interfaces: List[Dict[str, Any]] = []
    if not res["ok"]:
        return {"interfaces": interfaces}

    current: Optional[Dict[str, Any]] = None
    for line in res["stdout"].splitlines():
        if line and not line.startswith("\t"):
            name = line.split(":", 1)[0]
            flags_match = re.search(r"flags=(\d+)<([^>]+)>", line)
            current = {
                "name": name,
                "flags": flags_match.group(2) if flags_match else "",
                "active": bool(flags_match and "UP" in flags_match.group(2)),
                "ipv4": [],
                "ipv6": [],
            }
            interfaces.append(current)
        elif current and "inet " in line:
            match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
            if match:
                current["ipv4"].append(match.group(1))
        elif current and "inet6 " in line:
            match = re.search(r"inet6\s+([0-9a-fA-F:]+)", line)
            if match:
                current["ipv6"].append(match.group(1))

    return {"interfaces": interfaces}


def get_dns_state() -> Dict[str, Any]:
    """Current DNS resolver configuration."""
    return _parse_scutil_dns()


def get_proxy_state() -> Dict[str, Any]:
    """System proxy configuration with credentials redacted."""
    sp = detect_system_proxy()
    return {
        "http": _redact_url(sp.get("http")),
        "https": _redact_url(sp.get("https")),
        "socks": _redact_url(sp.get("socks")),
        "pac": _redact_url(sp.get("pac")),
    }


def get_routes() -> Dict[str, Any]:
    """IPv4 routing table summary."""
    return {"routes": _routes()}


def get_listeners() -> Dict[str, Any]:
    """Local TCP listening ports."""
    return {"listeners": _listeners()}


def dns_resolve(target: str, resolver: Optional[str] = None) -> Dict[str, Any]:
    """Resolve *target* via system resolver or an explicit resolver."""
    if resolver:
        res = run_command(["dig", f"@{resolver}", f"+time=5", target], timeout=10)
    else:
        try:
            addrs = socket.getaddrinfo(target, None, proto=socket.IPPROTO_TCP)
            ips = list({record[4][0] for record in addrs})
            return {"target": target, "resolver": resolver, "ips": ips, "status": "ok"}
        except socket.gaierror as exc:
            return {"target": target, "resolver": resolver, "ips": [], "status": "fail", "error": str(exc)}

    ok = res["ok"] and "ANSWER SECTION" in res["stdout"]
    return {
        "target": target,
        "resolver": resolver,
        "status": "ok" if ok else "fail",
        "stdout_tail": _safe_text(res["stdout"], 500),
        "stderr": _safe_text(res["stderr"]),
    }


def test_proxy_for_url(url: str) -> Dict[str, Any]:
    """Fetch *url* through the system-configured proxy."""
    sp = detect_system_proxy()
    proxy = sp.get("https") or sp.get("http")
    if not proxy:
        return {"url": url, "status": "warn", "error": "no system proxy configured"}
    res = run_command(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", "-x", proxy, url],
        timeout=12,
    )
    try:
        code = int(res["stdout"].strip())
    except (ValueError, AttributeError):
        code = 0
    return {
        "url": url,
        "proxy": _redact_url(proxy),
        "http_code": code,
        "status": "ok" if code == 200 else ("fail" if code == 407 else "warn"),
        "error": _safe_text(res["stderr"]) if not res["ok"] else None,
    }


def test_direct_for_url(url: str) -> Dict[str, Any]:
    """Fetch *url* directly, bypassing proxies."""
    res = run_command(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", url],
        timeout=12,
    )
    try:
        code = int(res["stdout"].strip())
    except (ValueError, AttributeError):
        code = 0
    return {
        "url": url,
        "http_code": code,
        "status": "ok" if code == 200 else "warn",
        "error": _safe_text(res["stderr"]) if not res["ok"] else None,
    }


def check_proxy_auth() -> Dict[str, Any]:
    """Detect whether the system proxy requires authentication."""
    sp = detect_system_proxy()
    proxy = sp.get("https") or sp.get("http")
    if not proxy:
        return {"requires_auth": False, "status": "warn", "error": "no system proxy configured"}
    res = run_command(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "10", "-x", proxy,
         "https://www.google.com/generate_204"],
        timeout=12,
    )
    try:
        code = int(res["stdout"].strip())
    except (ValueError, AttributeError):
        code = 0
    requires = code == 407
    return {
        "proxy": _redact_url(proxy),
        "requires_auth": requires,
        "http_code": code,
        "status": "fail" if requires else ("ok" if code == 200 else "warn"),
    }


def get_ip_reputation() -> Dict[str, Any]:
    """Return redacted IP reputation summary."""
    info = get_ip_info(timeout=10)
    return {
        "ip": info.get("ip"),
        "country": info.get("country"),
        "isp": info.get("isp") or info.get("org"),
        "asn": info.get("asn"),
        "ip_type": info.get("ip_type"),
        "risk_score": info.get("risk_score"),
        "cached": info.get("cached", False),
        "status": info.get("status", "ok"),
        "error": info.get("error"),
    }


def trace_path(target: str = "8.8.8.8") -> Dict[str, Any]:
    """Return a structured traceroute for *target*."""
    return diagnose.run_diagnostic("path_trace", {"path_target": target}, None, timeout=20)


def flush_dns() -> Dict[str, Any]:
    """Flush the local DNS cache."""
    r1 = run_command(["sudo", "dscacheutil", "-flushcache"], timeout=10)
    r2 = run_command(["sudo", "killall", "-HUP", "mDNSResponder"], timeout=10)
    return {
        "flush": {"ok": r1["ok"], "stderr": _safe_text(r1["stderr"])},
        "signal": {"ok": r2["ok"], "stderr": _safe_text(r2["stderr"])},
        "status": "ok" if r1["ok"] and r2["ok"] else "warn",
    }


def renew_dhcp(interface: Optional[str] = None) -> Dict[str, Any]:
    """Force a DHCP renew on *interface* (defaults to primary)."""
    iface = interface or default_interface() or "en0"
    res = run_command(["sudo", "ipconfig", "set", iface, "DHCP"], timeout=15)
    return {"interface": iface, "status": "ok" if res["ok"] else "fail", "error": _safe_text(res["stderr"])}


def disable_ipv6(service: str = "Wi-Fi") -> Dict[str, Any]:
    """Temporarily disable IPv6 for a network service."""
    res = run_command(["networksetup", "-setv6off", service], timeout=10)
    return {"service": service, "status": "ok" if res["ok"] else "fail", "error": _safe_text(res["stderr"])}
