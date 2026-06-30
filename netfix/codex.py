"""Codex / OpenAI / GitHub reachability diagnostics.

Uses only the Python standard library (urllib.request / socket / ssl) so that
netfix remains usable offline without installing third-party packages.
"""

from __future__ import annotations

import os
import re
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Allow running this file directly: python3 netfix/codex.py
if __name__ == "__main__" and __package__ is None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from netfix.constants import CODEX_ENDPOINTS


# A very loose IPv4/IPv6 matcher for "the response body is just an IP" services.
IP_RE = re.compile(r"^\s*(?:\d{1,3}\.){3}\d{1,3}\s*$")
IPV6_RE = re.compile(r"^\s*(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\s*$")


def _extract_exit_ip(body: bytes) -> str | None:
    """Return the body if it looks like a plain IP address, else None."""
    text = body.decode("utf-8", errors="ignore").strip()
    if len(text) > 100:
        return None
    if IP_RE.match(text) or IPV6_RE.match(text):
        return text
    return None


def _detect_system_proxy() -> tuple[str | None, str | None]:
    """Detect the system proxy URL and its source.

    Returns (proxy_url, source) where source is one of:
      - "env:<varname>"      (from http_proxy / https_proxy / all_proxy)
      - "scutil"             (parsed from macOS scutil --proxy)
      - None                 (no system proxy detected)
    """
    # 1. Environment variables (common on Linux and many CI environments).
    for key in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        value = os.environ.get(key)
        if value:
            return value, f"env:{key}"

    # 2. macOS system dynamic store (scutil --proxy).
    try:
        proc = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            text = proc.stdout
            enable_re = re.compile(r"(\w+)Enable\s*:\s*(\d+)")
            host_re = re.compile(r"(\w+)Proxy\s*:\s*([\w.]+)")
            port_re = re.compile(r"(\w+)Port\s*:\s*(\d+)")

            enables = {m.group(1): m.group(2) == "1" for m in enable_re.finditer(text)}
            hosts = {m.group(1): m.group(2) for m in host_re.finditer(text)}
            ports = {m.group(1): int(m.group(2)) for m in port_re.finditer(text)}

            # Prefer HTTPS > HTTP > SOCKS.  For HTTP/HTTPS proxies the URL scheme
            # is still "http://" because the proxy itself speaks HTTP CONNECT.
            # For SOCKS we return a real socks5:// URL and fall back to our
            # minimal SOCKS5 connector in check_endpoint().
            if enables.get("HTTPS") and "HTTPS" in hosts and "HTTPS" in ports:
                return f"http://{hosts['HTTPS']}:{ports['HTTPS']}", "scutil"
            if enables.get("HTTP") and "HTTP" in hosts and "HTTP" in ports:
                return f"http://{hosts['HTTP']}:{ports['HTTP']}", "scutil"
            if enables.get("SOCKS") and "SOCKS" in hosts and "SOCKS" in ports:
                return f"socks5://{hosts['SOCKS']}:{ports['SOCKS']}", "scutil"
    except Exception:
        pass

    return None, None


def _status_from_code(code: int, expect: int) -> str:
    """Map an HTTP status code to ok / warn."""
    if code == expect or 200 <= code < 300:
        return "ok"
    # Reachable but something is off (auth, proxy auth, blocked).
    return "warn"


def _classify_error(exc: Exception) -> str:
    """Convert an exception into a short, stable error label."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"

    msg = str(exc).lower()
    if "proxy authentication" in msg or msg.startswith("407") or "407 proxy" in msg:
        return "proxy authentication required"
    if "ssl" in msg or "tls" in msg or "certificate" in msg:
        return "ssl error"
    if "connection refused" in msg or "refused" in msg:
        return "connection refused"
    if "name or service not known" in msg or "getaddrinfo" in msg or "nxdomain" in msg:
        return "dns resolution failed"
    if "unsupported proxy" in msg:
        return "unsupported proxy scheme"
    if "network is unreachable" in msg:
        return "network unreachable"
    if "authentication failed" in msg:
        return "proxy authentication failed"
    return msg or "unknown error"


def _request_http_proxy(full_url: str, proxy_url: str | None, timeout: int) -> tuple[int, bytes, float]:
    """Make a request directly or through an HTTP/HTTPS proxy via urllib."""
    start = time.perf_counter()
    handlers = []
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "netfix/0.1.0",
            "Accept": "*/*",
        },
        method="GET",
    )
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read()
        code = resp.getcode()
    duration_ms = (time.perf_counter() - start) * 1000
    return code, body, duration_ms


def _request_socks5_proxy(full_url: str, proxy_url: str, timeout: int) -> tuple[int, bytes, float]:
    """Minimal SOCKS5 CONNECT + HTTP GET (over TLS when target is https).

    This is intentionally small and self-contained: urllib.request has no native
    SOCKS support, but many mixed inbound ports (xray, v2rayN, Clash) expose both
    HTTP and SOCKS on the same address.  We use this only when the caller passes
    a socks5:// URL.
    """
    target = urlparse(full_url)
    proxy = urlparse(proxy_url)
    phost = proxy.hostname
    pport = proxy.port or 1080
    if not phost:
        raise ValueError("invalid socks5 proxy URL")

    start = time.perf_counter()
    sock = socket.create_connection((phost, pport), timeout=timeout)
    try:
        # Greeting: SOCKS5, offer username/password auth if credentials present.
        has_auth = bool(proxy.username)
        methods = b"\x02\x00" if has_auth else b"\x00"
        sock.sendall(bytes([5, len(methods)]) + methods)
        resp = sock.recv(2)
        if resp[0] != 5:
            raise ConnectionError("invalid socks5 response")
        if resp[1] == 0xFF:
            raise ConnectionError("no acceptable socks5 auth method")
        if resp[1] == 0x02:
            user = (proxy.username or "").encode()
            passwd = (proxy.password or "").encode()
            auth = bytes([1, len(user)]) + user + bytes([len(passwd)]) + passwd
            sock.sendall(auth)
            aresp = sock.recv(2)
            if aresp[1] != 0:
                raise ConnectionError("socks5 authentication failed")

        # CONNECT request (domain name address type).
        thost = target.hostname
        tport = target.port or (443 if target.scheme == "https" else 80)
        if not thost:
            raise ValueError("invalid target URL")
        addr_bytes = bytes([len(thost)]) + thost.encode()
        connect_req = (
            bytes([5, 1, 0, 3])
            + addr_bytes
            + bytes([(tport >> 8) & 0xFF, tport & 0xFF])
        )
        sock.sendall(connect_req)

        resp = sock.recv(4)
        if resp[0] != 5:
            raise ConnectionError("invalid socks5 connect response")
        if resp[1] != 0:
            errors = {
                1: "general failure",
                2: "connection not allowed",
                3: "network unreachable",
                4: "host unreachable",
                5: "connection refused",
                6: "ttl expired",
                7: "command not supported",
                8: "address type not supported",
            }
            raise ConnectionError(f"socks5 connect failed: {errors.get(resp[1], resp[1])}")

        # Consume the bind address returned by the proxy.
        atyp = resp[3]
        if atyp == 1:
            sock.recv(4 + 2)
        elif atyp == 3:
            alen = sock.recv(1)[0]
            sock.recv(alen + 2)
        elif atyp == 4:
            sock.recv(16 + 2)

        # TLS wrap for HTTPS targets.
        if target.scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=thost)

        # HTTP GET.
        path = target.path or "/"
        if target.query:
            path += "?" + target.query
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {thost}\r\n"
            f"User-Agent: netfix/0.1.0\r\n"
            f"Accept: */*\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        sock.sendall(request)

        response = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            response += chunk

        header_end = response.find(b"\r\n\r\n")
        if header_end == -1:
            raise ConnectionError("invalid http response from proxy")
        header = response[:header_end].decode("utf-8", errors="ignore")
        body = response[header_end + 4 :]
        status_line = header.splitlines()[0]
        code = int(status_line.split()[1])
    finally:
        try:
            sock.close()
        except Exception:
            pass

    duration_ms = (time.perf_counter() - start) * 1000
    return code, body, duration_ms


def check_endpoint(
    name: str,
    url: str,
    path: str,
    proxy_url: str | None = None,
    proxy_used: str | None = None,
    timeout: int = 10,
    expect: int = 200,
) -> dict[str, Any]:
    """Probe a single endpoint and return a structured result.

    Args:
        name: Human-readable identifier for this probe.
        url: Base URL of the endpoint (e.g. https://api.openai.com).
        path: Path to request (e.g. /v1/models).
        proxy_url: Actual proxy URL to use, or None for a direct connection.
        proxy_used: Label recorded in the result (e.g. "direct", "system").
        timeout: Network timeout in seconds.
        expect: Expected HTTP status code.

    Returns:
        A dict matching the DESIGN.md diagnostic item contract.
    """
    full_url = url.rstrip("/") + path
    status = "fail"
    http_code = 0
    exit_ip = None
    error = None
    duration_ms = 0.0

    if proxy_used is None:
        proxy_used = proxy_url or "direct"

    start = time.perf_counter()
    try:
        if proxy_url and proxy_url.startswith(("socks5://", "socks5h://")):
            code, body, _ = _request_socks5_proxy(full_url, proxy_url, timeout)
        else:
            code, body, _ = _request_http_proxy(full_url, proxy_url, timeout)
        http_code = code
        exit_ip = _extract_exit_ip(body)
        status = _status_from_code(code, expect)
    except urllib.error.HTTPError as exc:
        http_code = exc.code
        status = _status_from_code(exc.code, expect)
        if exc.code == 407:
            status = "warn"
            error = "proxy authentication required"
        else:
            error = _classify_error(exc)
        try:
            exit_ip = _extract_exit_ip(exc.read())
        except Exception:
            pass
    except Exception as exc:
        error = _classify_error(exc)
        status = "fail"
    finally:
        duration_ms = (time.perf_counter() - start) * 1000

    return {
        "name": name,
        "target": full_url,
        "proxy_used": proxy_used,
        "status": status,
        "http_code": http_code,
        "duration_ms": round(duration_ms),
        "exit_ip": exit_ip,
        "error": error,
    }


def check_codex(
    proxy_url: str | None = None,
    use_system_proxy: bool = True,
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """Probe all Codex endpoints through direct, system, local and optional proxy.

    Test matrix per endpoint:
      1. direct (no proxy)
      2. system proxy (from env or scutil --proxy)
      3. 127.0.0.1:10808 (common mixed inbound)
      4. user-provided proxy_url, if any
    """
    results: list[dict[str, Any]] = []
    system_proxy, _ = _detect_system_proxy() if use_system_proxy else (None, None)

    proxy_modes: list[tuple[str, str | None]] = [("direct", None)]
    if system_proxy:
        proxy_modes.append(("system", system_proxy))
    proxy_modes.append(("127.0.0.1:10808", "http://127.0.0.1:10808"))
    if proxy_url:
        proxy_modes.append((proxy_url, proxy_url))

    for endpoint in CODEX_ENDPOINTS:
        expect = endpoint.get("expect", 200)
        for label, purl in proxy_modes:
            results.append(
                check_endpoint(
                    name=endpoint["name"],
                    url=endpoint["url"],
                    path=endpoint["path"],
                    proxy_url=purl,
                    proxy_used=label,
                    timeout=timeout,
                    expect=expect,
                )
            )
    return results


def summarize_codex(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize reachability test results into a short conclusion.

    A probe is considered "reachable" when we got any HTTP response from the
    server (status != fail and http_code > 0).  This treats auth responses such
    as OpenAI's 401 as a successful network path, which is what a reachability
    diagnostic cares about.
    """
    def reachable(r: dict[str, Any]) -> bool:
        return r["status"] != "fail" and r["http_code"] > 0

    direct_ok = any(reachable(r) and r["proxy_used"] == "direct" for r in results)
    proxy_ok = any(reachable(r) and r["proxy_used"] != "direct" for r in results)

    # Pick the best active proxy.  Priority mirrors the test order.
    active_proxy = None
    for preferred in ("system", "127.0.0.1:10808"):
        if any(reachable(r) and r["proxy_used"] == preferred for r in results):
            active_proxy = preferred
            break
    if active_proxy is None:
        for r in results:
            if reachable(r) and r["proxy_used"] not in ("direct", "system", "127.0.0.1:10808"):
                active_proxy = r["proxy_used"]
                break
    if active_proxy is None and direct_ok:
        active_proxy = "direct"

    if direct_ok and proxy_ok:
        root_cause = "Codex/OpenAI/GitHub reachable both directly and via proxy."
    elif not direct_ok and proxy_ok:
        root_cause = "Direct access to Codex/OpenAI/GitHub is blocked; proxy is working."
    elif direct_ok and not proxy_ok:
        root_cause = "Direct access works but proxy test failed; check proxy settings."
    else:
        root_cause = "Both direct and proxy access failed; check network/proxy core."

    return {
        "direct_ok": direct_ok,
        "proxy_ok": proxy_ok,
        "active_proxy": active_proxy,
        "root_cause": root_cause,
    }


def check_codex_direct(timeout: int = 10) -> dict[str, Any]:
    """Check OpenAI API reachability without a proxy."""
    return check_endpoint(
        name="codex_api_direct",
        url="https://api.openai.com",
        path="/v1/models",
        proxy_url=None,
        proxy_used="direct",
        timeout=timeout,
        expect=200,
    )


def check_codex_via_proxy(proxy: str = "http://127.0.0.1:10808", timeout: int = 10) -> dict[str, Any]:
    """Check OpenAI API reachability through the given proxy."""
    return check_endpoint(
        name="codex_api_via_proxy",
        url="https://api.openai.com",
        path="/v1/models",
        proxy_url=proxy,
        proxy_used="proxy",
        timeout=timeout,
        expect=200,
    )


if __name__ == "__main__":
    # Simple self-test when invoked directly.
    import json

    res = check_codex()
    print(json.dumps({"tests": res, "summary": summarize_codex(res)}, ensure_ascii=False, indent=2))
