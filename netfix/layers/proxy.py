"""Proxy layer diagnostics: system proxy, protocol tests, auth, PAC."""
from __future__ import annotations

import re
import shutil
from typing import Any, Dict, List, Optional

from netfix.diagnose import register
from netfix.layers._helpers import diagnostic, is_private_ip
from netfix.utils import run_command


_TEST_URL = "https://www.google.com/generate_204"


def _system_proxy_raw() -> Dict[str, Any]:
    """Parse `scutil --proxy` into a structured dict."""
    res = run_command(["scutil", "--proxy"], timeout=10)
    if not res["ok"]:
        return {"error": res["stderr"]}

    text = res["stdout"]
    parsed: Dict[str, Any] = {"raw": text}

    def enabled(proto: str) -> bool:
        key = f"{proto}Enable"
        return bool(re.search(rf"\b{re.escape(key)}\s*:\s*1\b", text))

    def endpoint(proto: str) -> Optional[str]:
        host_match = re.search(rf"\b{re.escape(proto)}Proxy\s*:\s*(\S+)", text)
        port_match = re.search(rf"\b{re.escape(proto)}Port\s*:\s*(\d+)", text)
        if host_match and port_match:
            return f"{host_match.group(1)}:{port_match.group(1)}"
        return None

    parsed["http"] = {"enabled": enabled("HTTP"), "endpoint": endpoint("HTTP")}
    parsed["https"] = {"enabled": enabled("HTTPS"), "endpoint": endpoint("HTTPS")}
    parsed["socks"] = {"enabled": enabled("SOCKS"), "endpoint": endpoint("SOCKS")}

    pac_match = re.search(r"\bProxyAutoConfigURLString\s*:\s*(\S+)", text)
    parsed["pac"] = {
        "enabled": enabled("ProxyAutoConfig"),
        "url": pac_match.group(1) if pac_match else None,
    }
    parsed["auto_discovery"] = enabled("ProxyAutoDiscovery")

    bypass_match = re.search(r"\bExceptionsList\s*:\s*\{([^}]*)\}", text, re.DOTALL)
    if bypass_match:
        parsed["bypass_domains"] = [
            x.strip().strip('"') for x in bypass_match.group(1).split(",") if x.strip()
        ]
    else:
        parsed["bypass_domains"] = []
    return parsed


def _listening_ports() -> List[int]:
    """Return TCP listening ports on localhost or all interfaces."""
    res = run_command(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=10)
    if not res["ok"]:
        return []
    ports: set[int] = set()
    for line in res["stdout"].splitlines()[1:]:
        # Match IPv4 listeners such as 127.0.0.1:10808, *:10808, 0.0.0.0:10808
        match = re.search(r"(?:127\.0\.0\.1|\*|0\.0\.0\.0):(\d+)\s+\(LISTEN\)", line)
        if match:
            ports.add(int(match.group(1)))
    return sorted(ports)


def _proxy_from_env(env: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Return HTTP/HTTPS/SOCKS endpoints inferred from system settings + env."""
    raw = _system_proxy_raw()
    http = raw.get("http", {}).get("endpoint") or env.get("HTTP_PROXY") or env.get("http_proxy")
    https = raw.get("https", {}).get("endpoint") or env.get("HTTPS_PROXY") or env.get("https_proxy")
    socks = raw.get("socks", {}).get("endpoint") or env.get("ALL_PROXY") or env.get("all_proxy")
    return {"http": http, "https": https, "socks": socks}


def _curl_code(cmd: List[str], timeout: int) -> Dict[str, Any]:
    """Run curl and return http_code / error / proxy_used."""
    full = [
        "curl",
        "-sS",
        "-o", "/dev/null",
        "-w", "%{http_code}|%{time_total}|%{redirect_url}",
        "--max-time", str(timeout),
    ] + cmd
    res = run_command(full, timeout=timeout + 2)
    if not res["ok"]:
        return {
            "ok": False,
            "http_code": 0,
            "stderr": res["stderr"],
            "stdout": res["stdout"],
        }
    parts = res["stdout"].split("|", 2)
    try:
        code = int(parts[0]) if parts[0] else 0
    except ValueError:
        code = 0
    return {
        "ok": True,
        "http_code": code,
        "time_total": parts[1] if len(parts) > 1 else None,
        "redirect_url": parts[2] if len(parts) > 2 else None,
    }


@register("system_proxy_state")
def system_proxy_state(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Inspect macOS system proxy settings and detect port mismatches."""
    raw = _system_proxy_raw()
    if "error" in raw:
        return diagnostic("system_proxy_state", "proxy", "fail", raw)

    listening = _listening_ports()
    checks: Dict[str, Any] = {}
    mismatches: List[str] = []

    for proto in ("http", "https", "socks"):
        entry = raw.get(proto, {})
        endpoint = entry.get("endpoint")
        enabled = entry.get("enabled", False)
        checks[proto] = {"enabled": enabled, "endpoint": endpoint}
        if enabled and endpoint:
            try:
                port = int(endpoint.rsplit(":", 1)[-1])
            except ValueError:
                port = None
            if port and port not in listening:
                mismatches.append(f"{proto} -> {endpoint} not listening")

    pac = raw.get("pac", {})
    if pac.get("enabled") and pac.get("url"):
        head = run_command(["curl", "-sSI", "--max-time", str(min(timeout, 5)), pac["url"]], timeout=min(timeout, 5) + 2)
        pac["reachable"] = head["ok"]

    manual_proxy_enabled = any(
        raw.get(proto, {}).get("enabled")
        for proto in ("http", "https", "socks")
    )
    auto_proxy_enabled = bool(raw.get("pac", {}).get("enabled") or raw.get("auto_discovery"))
    mixed_auto_and_manual = manual_proxy_enabled and auto_proxy_enabled

    status = "ok"
    if mismatches:
        status = "fail"
    elif mixed_auto_and_manual:
        status = "warn"
    elif manual_proxy_enabled:
        status = "ok"
    else:
        # No proxy configured is not necessarily a failure; mark warn if a proxy core is running.
        if env.get("mixed_port") or env.get("active_core"):
            status = "warn"

    return diagnostic(
        "system_proxy_state",
        "proxy",
        status,
        {
            "http": checks.get("http"),
            "https": checks.get("https"),
            "socks": checks.get("socks"),
            "pac": raw.get("pac"),
            "auto_discovery": raw.get("auto_discovery"),
            "mixed_auto_and_manual": mixed_auto_and_manual,
            "bypass_domains": raw.get("bypass_domains"),
            "listening_ports": listening,
            "mismatches": mismatches,
        },
    )


@register("proxy_http_test")
def proxy_http_test(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Probe the configured HTTP proxy with a real HTTPS request."""
    endpoints = _proxy_from_env(env)
    endpoint = endpoints.get("https") or endpoints.get("http")
    if not endpoint:
        return diagnostic(
            "proxy_http_test",
            "proxy",
            "warn",
            {"error": "no HTTP proxy configured"},
        )

    result = _curl_code(["-x", endpoint, _TEST_URL], timeout=min(timeout, 10))
    code = result.get("http_code", 0)
    if code in (200, 204):
        status = "ok"
    elif code == 407:
        status = "fail"
    elif code in (502, 503, 504):
        status = "fail"
    elif code > 0:
        status = "warn"
    else:
        status = "fail"

    return diagnostic(
        "proxy_http_test",
        "proxy",
        status,
        {
            "proxy": endpoint,
            "http_code": code,
            "time_total": result.get("time_total"),
            "error": result.get("stderr") if not result.get("ok") else None,
        },
    )


@register("proxy_socks_test")
def proxy_socks_test(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Probe the configured SOCKS5 proxy using remote DNS (socks5h)."""
    endpoints = _proxy_from_env(env)
    endpoint = endpoints.get("socks")
    if not endpoint and env.get("mixed_port"):
        endpoint = f"127.0.0.1:{env['mixed_port']}"
    if not endpoint:
        return diagnostic(
            "proxy_socks_test",
            "proxy",
            "warn",
            {"error": "no SOCKS proxy configured"},
        )

    # Prefer socks5h to avoid DNS leaks.
    proxy_url = endpoint if endpoint.startswith("socks5h://") else f"socks5h://{endpoint}"
    result = _curl_code(["--proxy", proxy_url, _TEST_URL], timeout=min(timeout, 10))
    code = result.get("http_code", 0)
    if code in (200, 204):
        status = "ok"
    elif code == 407:
        status = "fail"
    elif code > 0:
        status = "warn"
    else:
        status = "fail"

    return diagnostic(
        "proxy_socks_test",
        "proxy",
        status,
        {
            "proxy": proxy_url,
            "http_code": code,
            "time_total": result.get("time_total"),
            "error": result.get("stderr") if not result.get("ok") else None,
        },
    )


@register("proxy_auth_check")
def proxy_auth_check(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Detect whether the proxy requires authentication (HTTP 407)."""
    endpoints = _proxy_from_env(env)
    endpoint = endpoints.get("https") or endpoints.get("http") or endpoints.get("socks")
    if not endpoint and env.get("mixed_port"):
        endpoint = f"127.0.0.1:{env['mixed_port']}"
    if not endpoint:
        return diagnostic(
            "proxy_auth_check",
            "proxy",
            "warn",
            {"error": "no proxy configured"},
        )

    curl_args = ["-x", endpoint, _TEST_URL]
    if endpoint.startswith("socks5h://") or endpoint.startswith("socks5://"):
        curl_args = ["--proxy", endpoint, _TEST_URL]

    result = _curl_code(curl_args, timeout=min(timeout, 10))
    code = result.get("http_code", 0)
    requires_auth = code == 407
    return diagnostic(
        "proxy_auth_check",
        "proxy",
        "fail" if requires_auth else ("ok" if code in (200, 204) else "warn"),
        {
            "proxy": endpoint,
            "http_code": code,
            "requires_auth": requires_auth,
            "error": result.get("stderr") if not result.get("ok") else None,
        },
    )


@register("pac_state")
def pac_state(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Report PAC / WPAD auto-proxy configuration."""
    raw = _system_proxy_raw()
    pac = raw.get("pac", {})
    if not pac.get("enabled") and not raw.get("auto_discovery"):
        return diagnostic(
            "pac_state",
            "proxy",
            "ok",
            {"enabled": False, "url": None, "auto_discovery": False},
        )

    url = pac.get("url")
    reachable = False
    if url:
        head = run_command(
            ["curl", "-sSI", "--max-time", str(min(timeout, 5)), url],
            timeout=min(timeout, 5) + 2,
        )
        reachable = head["ok"]

    status = "ok" if reachable else "warn"
    return diagnostic(
        "pac_state",
        "proxy",
        status,
        {
            "enabled": True,
            "url": url,
            "auto_discovery": raw.get("auto_discovery", False),
            "reachable": reachable,
        },
    )
