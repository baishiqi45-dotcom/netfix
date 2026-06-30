"""Diagnostic registry and dispatcher for netfix.

Diagnostics can be pure Python functions or thin wrappers around
``bin/*.sh`` scripts.  Every diagnostic returns a dict with:

    {
        "name": str,
        "status": "ok" | "warn" | "fail",
        "duration_ms": int,
        "details": dict,
    }
"""
from __future__ import annotations

import json as _json
import shlex
import socket
import time
from typing import Any, Callable, Dict, Optional

from netfix.constants import BIN_DIR
from netfix.utils import run_command

DIAGNOSTICS: Dict[str, Callable] = {}


def register(name: str) -> Callable:
    """Decorator that registers a diagnostic under *name*."""
    def decorator(func: Callable) -> Callable:
        DIAGNOSTICS[name] = func
        return func
    return decorator


def run_diagnostic(name: str, env: dict, core, timeout: int = 30) -> dict:
    """Run the diagnostic registered as *name*.

    *env* is a shared dict with runtime facts (mixed_port, dns_target, ...).
    *core* is an optional core adapter object (reserved for future use).
    """
    if name not in DIAGNOSTICS:
        return {
            "name": name,
            "status": "fail",
            "duration_ms": 0,
            "details": {"error": f"diagnostic '{name}' not registered"},
        }

    start = time.time()
    try:
        result = DIAGNOSTICS[name](env, core, timeout)
    except Exception as exc:  # pragma: no cover - defensive
        result = {
            "name": name,
            "status": "fail",
            "details": {"error": type(exc).__name__, "message": str(exc)},
        }

    result.setdefault("name", name)
    result.setdefault("duration_ms", int((time.time() - start) * 1000))
    result.setdefault("layer", _LAYER_FALLBACK.get(name, "service"))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_packet_loss(stdout: str) -> Optional[str]:
    for line in stdout.splitlines():
        if "packet loss" in line.lower():
            return line.strip()
    return None


def _default_gateway() -> Optional[str]:
    res = run_command(["route", "-n", "get", "default"], timeout=10)
    if not res["ok"]:
        return None
    for line in res["stdout"].splitlines():
        if "gateway:" in line.lower():
            return line.split(":", 1)[-1].strip()
    return None


def _run_json_script(script_name: str, env: dict, timeout: int) -> Dict[str, Any]:
    script = BIN_DIR / script_name
    if not script.exists():
        return {
            "status": "warn",
            "details": {"error": f"{script} not found"},
        }
    res = run_command(["bash", str(script), "--json"], timeout=timeout)
    details: Dict[str, Any] = {
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "returncode": res["returncode"],
    }
    try:
        data = _json.loads(res["stdout"])
        details.update(data)
        status = data.get("status", "ok" if res["ok"] else "warn")
    except _json.JSONDecodeError:
        status = "warn" if res["ok"] else "fail"
    return {"status": status, "details": details}


# ---------------------------------------------------------------------------
# Built-in diagnostics
# ---------------------------------------------------------------------------

@register("proxy_core_status")
def _proxy_core_status(env: dict, core, timeout: int = 30) -> dict:
    """Detect whether the proxy core is running and the mixed port is listening."""
    mixed_port = env.get("mixed_port", 10808)
    expected = env.get("proxy_processes", ["xray", "sing-box", "clash", "mihomo", "v2ray"])

    procs_running = False
    for proc in expected:
        r = run_command(["pgrep", "-x", proc], timeout=10)
        if r["ok"] and r["stdout"].strip():
            procs_running = True
            break

    port_res = run_command(
        ["lsof", "-nP", "-iTCP:%s" % mixed_port, "-sTCP:LISTEN"],
        timeout=10,
    )
    port_listening = port_res["ok"] and str(mixed_port) in port_res["stdout"]

    if procs_running and port_listening:
        status = "ok"
    elif procs_running:
        status = "warn"
    else:
        status = "fail"

    return {
        "status": status,
        "details": {
            "mixed_port": mixed_port,
            "processes_checked": expected,
            "processes_running": procs_running,
            "port_listening": port_listening,
        },
    }


@register("dns_local")
def _dns_local(env: dict, core, timeout: int = 30) -> dict:
    """Resolve a target through the local macOS resolver."""
    target = env.get("dns_target", "example.com")
    try:
        addrs = socket.getaddrinfo(target, None, proto=socket.IPPROTO_TCP)
        ips = list({record[4][0] for record in addrs})
        return {"status": "ok", "details": {"target": target, "ips": ips}}
    except socket.gaierror as exc:
        return {"status": "fail", "details": {"target": target, "error": str(exc)}}


@register("dns_public")
def _dns_public(env: dict, core, timeout: int = 30) -> dict:
    """Resolve a target via a public DNS server (8.8.8.8)."""
    target = env.get("dns_target", "example.com")
    dig_timeout = min(timeout, 5)
    res = run_command(
        ["dig", "@8.8.8.8", f"+time={dig_timeout}", target],
        timeout=timeout,
    )
    ok = res["ok"] and "ANSWER SECTION" in res["stdout"]
    return {
        "status": "ok" if ok else "fail",
        "details": {
            "target": target,
            "has_answer": ok,
            "stdout_tail": res["stdout"][-500:],
            "stderr": res["stderr"],
        },
    }


@register("dns_cache")
def _dns_cache(env: dict, core, timeout: int = 30) -> dict:
    """Read local DNS cache statistics."""
    res = run_command(["dscacheutil", "-statistics"], timeout=10)
    return {
        "status": "ok" if res["ok"] else "warn",
        "details": {"stdout": res["stdout"], "stderr": res["stderr"]},
    }


@register("gateway")
def _gateway(env: dict, core, timeout: int = 30) -> dict:
    """Ping the default gateway."""
    gateway = _default_gateway()
    if not gateway:
        return {
            "status": "fail",
            "details": {"error": "default gateway not found"},
        }

    ping = run_command(
        ["ping", "-c", "3", "-W", "2000", gateway],
        timeout=timeout,
    )
    loss_text = _parse_packet_loss(ping["stdout"]) or ""
    ok = ping["ok"] and ("0.0% packet loss" in loss_text or " 0% packet loss" in loss_text)
    return {
        "status": "ok" if ok else "fail",
        "details": {
            "gateway": gateway,
            "packet_loss": loss_text,
            "ok": ping["ok"],
        },
    }


@register("codex_api_direct")
def _codex_api_direct(env: dict, core, timeout: int = 30) -> dict:
    """Check Codex/OpenAI reachability without proxy."""
    try:
        from netfix.codex import check_codex_direct
        result = check_codex_direct(timeout=min(timeout, 10))
    except Exception:
        result = _fallback_codex_direct(timeout=min(timeout, 10))
    return {
        "status": result.get("status", "fail"),
        "details": {k: v for k, v in result.items() if k != "status"},
    }


def _fallback_codex_direct(timeout: int = 10) -> Dict[str, Any]:
    res = run_command(
        ["curl", "-sS", "--max-time", str(timeout), "-o", "/dev/null", "-w", "%{http_code}",
         "https://api.openai.com/v1/models"],
        timeout=timeout + 2,
    )
    try:
        code = int(res["stdout"].strip())
    except (ValueError, AttributeError):
        code = 0
    return {
        "status": "ok" if code == 200 else "fail",
        "http_code": code,
        "fallback": True,
    }


@register("codex_api_via_proxy")
def _codex_api_via_proxy(env: dict, core, timeout: int = 30) -> dict:
    """Check Codex/OpenAI reachability through the local mixed proxy."""
    proxy = env.get("mixed_proxy", "http://127.0.0.1:10808")
    try:
        from netfix.codex import check_codex_via_proxy
        result = check_codex_via_proxy(proxy=proxy, timeout=min(timeout, 10))
    except Exception:
        result = _fallback_codex_via_proxy(proxy, timeout=min(timeout, 10))
    return {
        "status": result.get("status", "fail"),
        "details": {k: v for k, v in result.items() if k != "status"},
    }


def _fallback_codex_via_proxy(proxy: str, timeout: int = 10) -> Dict[str, Any]:
    res = run_command(
        ["curl", "-sS", "--max-time", str(timeout), "--proxy", proxy,
         "-o", "/dev/null", "-w", "%{http_code}",
         "https://api.openai.com/v1/models"],
        timeout=timeout + 2,
    )
    try:
        code = int(res["stdout"].strip())
    except (ValueError, AttributeError):
        code = 0
    return {
        "status": "ok" if code == 200 else "fail",
        "http_code": code,
        "proxy": proxy,
        "fallback": True,
    }


@register("mtu_probe")
def _mtu_probe(env: dict, core, timeout: int = 30) -> dict:
    """Run ``bin/mtu-tune.sh --json`` if it exists."""
    result = _run_json_script("mtu-tune.sh", env, timeout)
    return {"status": result["status"], "details": result["details"]}


@register("ipv6_leak")
def _ipv6_leak(env: dict, core, timeout: int = 30) -> dict:
    """Run ``bin/ipv6-leak-check.sh --json`` if it exists."""
    result = _run_json_script("ipv6-leak-check.sh", env, timeout)
    return {"status": result["status"], "details": result["details"]}


@register("wifi_signal")
def _wifi_signal(env: dict, core, timeout: int = 30) -> dict:
    """Read macOS Wi-Fi signal info via the airport utility."""
    airport = (
        "/System/Library/PrivateFrameworks/Apple80211.framework"
        "/Versions/Current/Resources/airport"
    )
    res = run_command([airport, "-I"], timeout=timeout)
    return {
        "status": "ok" if res["ok"] else "fail",
        "details": {
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "returncode": res["returncode"],
        },
    }


@register("ssl_cert")
def _ssl_cert(env: dict, core, timeout: int = 30) -> dict:
    """Check TLS certificate validity for a target host."""
    target = env.get("ssl_target", "cloudflare.com")
    res = run_command(
        ["openssl", "s_client", "-connect", f"{target}:443", "-servername", target],
        timeout=timeout,
    )
    ok = res["ok"] or "verify return:1" in res.get("stderr", "")
    return {
        "status": "ok" if ok else "fail",
        "details": {
            "target": target,
            "stdout_tail": res["stdout"][-500:],
            "stderr_tail": res["stderr"][-500:],
            "returncode": res["returncode"],
        },
    }


@register("connectivity")
def _connectivity(env: dict, core, timeout: int = 30) -> dict:
    """TCP connect to a host:port target."""
    target = env.get("connectivity_target", "8.8.8.8:443")
    host, port_str = target.rsplit(":", 1)
    port = int(port_str)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {
                "status": "ok",
                "details": {"target": target, "host": host, "port": port},
            }
    except Exception as exc:
        return {
            "status": "fail",
            "details": {"target": target, "host": host, "port": port, "error": str(exc)},
        }


@register("node_reachability")
def _node_reachability(env: dict, core, timeout: int = 30) -> dict:
    """TCP reachability test for each configured proxy/VPN node.

    This does not test the full proxy protocol (auth, encryption), only whether
    the node's endpoint is reachable at the TCP layer.  It is enough to spot a
    dead node quickly without relying on a controller API.
    """
    profiles = []
    active = None
    if core is not None:
        try:
            profiles = core.list_profiles() or []
            active = core.get_active_profile()
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "status": "warn",
                "details": {"error": str(exc)},
            }

    if not profiles:
        return {
            "status": "ok",
            "details": {"profiles": [], "reason": "no profiles discovered"},
        }

    per_profile_timeout = max(2, min(5, timeout // max(len(profiles), 1)))
    results = []
    active_reachable = None
    for p in profiles:
        address = p.get("address")
        port = p.get("port")
        remark = p.get("remarks") or p.get("id")
        if not address or not port:
            results.append({"remarks": remark, "address": address, "port": port, "reachable": None})
            continue
        reachable = False
        try:
            with socket.create_connection((address, int(port)), timeout=per_profile_timeout):
                reachable = True
        except Exception:
            reachable = False
        entry = {"remarks": remark, "address": address, "port": port, "reachable": reachable}
        results.append(entry)
        if active and (p.get("id") == active.get("id") or p.get("remarks") == active.get("remarks")):
            active_reachable = reachable

    if active_reachable is False:
        status = "fail"
    elif any(r.get("reachable") is False for r in results):
        status = "warn"
    else:
        status = "ok"

    return {
        "status": status,
        "details": {
            "active_reachable": active_reachable,
            "profiles": results,
        },
    }


# Convenience to run every registered diagnostic.
BUILTIN_DIAGNOSTICS = list(DIAGNOSTICS.keys())

# Register layered diagnostics implemented in netfix.layers.*.
# The import has side effects (registrations) and must happen after DIAGNOSTICS
# is defined above.
from netfix import layers  # noqa: E402,F401


# Fallback layer mapping for legacy diagnostics that do not set ``layer``.
_LAYER_FALLBACK: Dict[str, str] = {
    "proxy_core_status": "proxy",
    "system_proxy_state": "proxy",
    "dns_local": "dns",
    "dns_public": "dns",
    "dns_cache": "dns",
    "gateway": "network",
    "codex_api_direct": "service",
    "codex_api_via_proxy": "service",
    "mtu_probe": "network",
    "ipv6_leak": "egress",
    "wifi_signal": "network",
    "ssl_cert": "service",
    "connectivity": "network",
    "node_reachability": "proxy",
}
