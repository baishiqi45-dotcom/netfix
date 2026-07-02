"""In-process loopback HTTP proxy bridge for authenticated upstream proxies."""
from __future__ import annotations

import base64
import select
import socket
import socketserver
import ssl
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit


_BRIDGES: Dict[str, "_BridgeRecord"] = {}
_LOCK = threading.RLock()
TUNNEL_MAX_SECONDS = 60.0


class _BridgeRecord:
    def __init__(self, bridge_id: str, server: "_BridgeServer", thread: threading.Thread, profile: Dict[str, Any]):
        self.bridge_id = bridge_id
        self.server = server
        self.thread = thread
        self.profile = profile
        self.started_at = time.time()

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.bridge_id,
            "listen_host": self.server.server_address[0],
            "listen_port": self.server.server_address[1],
            "profile_id": self.profile.get("id"),
            "profile_name": self.profile.get("name"),
            "upstream_protocol": self.profile.get("protocol"),
            "upstream_host": self.profile.get("host"),
            "upstream_port": self.profile.get("port"),
            "running": self.thread.is_alive(),
            "started_at": self.started_at,
            **self.server.audit_public(),
        }


class _BridgeServer(socketserver.ThreadingTCPServer):
    address_family = socket.AF_INET
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], profile: Dict[str, Any], password: str, idle_timeout_s: float = 0):
        self.profile = dict(profile)
        self.password = password
        self.idle_timeout_s = max(0.0, float(idle_timeout_s or 0))
        self._audit_lock = threading.RLock()
        self._active_connections = 0
        self._request_count = 0
        self._last_activity_at = time.time()
        self._clients: Dict[str, Dict[str, Any]] = {}
        super().__init__(server_address, _BridgeHandler)

    def note_connection_open(self) -> None:
        with self._audit_lock:
            self._active_connections += 1
            self._last_activity_at = time.time()

    def note_connection_close(self) -> None:
        with self._audit_lock:
            self._active_connections = max(0, self._active_connections - 1)
            self._last_activity_at = time.time()

    def note_request(self, client_host: str) -> None:
        now = time.time()
        host = client_host or "unknown"
        with self._audit_lock:
            self._request_count += 1
            self._last_activity_at = now
            client = self._clients.setdefault(host, {"host": host, "count": 0, "first_seen": now})
            client["count"] = int(client.get("count") or 0) + 1
            client["last_seen"] = now

    def audit_public(self) -> Dict[str, Any]:
        with self._audit_lock:
            clients = sorted(self._clients.values(), key=lambda item: float(item.get("last_seen") or 0), reverse=True)
            return {
                "request_count": self._request_count,
                "active_connections": self._active_connections,
                "last_activity_at": self._last_activity_at,
                "idle_timeout_s": self.idle_timeout_s,
                "recent_clients": [dict(item) for item in clients[:5]],
            }

    def idle_snapshot(self) -> Tuple[int, float, float]:
        with self._audit_lock:
            return self._active_connections, self._last_activity_at, self.idle_timeout_s


class _BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def setup(self) -> None:
        super().setup()
        self.server.note_connection_open()  # type: ignore[attr-defined]

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            self.server.note_connection_close()  # type: ignore[attr-defined]

    def do_CONNECT(self) -> None:  # noqa: N802
        self._record_request()
        protocol = self._upstream_protocol()
        if protocol in {"socks5", "socks5h"}:
            target = self._connect_target_from_connect_path()
            if target is None:
                return
            upstream = self._connect_socks_target(*target)
            if upstream is None:
                return
            try:
                self.connection.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self._tunnel(self.connection, upstream)
            finally:
                upstream.close()
            return

        upstream = self._connect_http_upstream()
        if upstream is None:
            return
        try:
            request = (
                f"CONNECT {self.path} HTTP/1.1\r\n"
                f"Host: {self.path}\r\n"
                f"{self._proxy_authorization_header()}"
                "Proxy-Connection: Keep-Alive\r\n"
                "\r\n"
            ).encode("utf-8")
            upstream.sendall(request)
            response = self._read_headers(upstream)
            if not response.startswith(b"HTTP/"):
                self.send_error(502, "bad upstream proxy response")
                return
            status = response.split(None, 2)[1:2]
            if status != [b"200"]:
                self.connection.sendall(response)
                return
            self.connection.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self._tunnel(self.connection, upstream)
        finally:
            upstream.close()

    def do_GET(self) -> None:  # noqa: N802
        self._forward_plain_http()

    def do_POST(self) -> None:  # noqa: N802
        self._forward_plain_http()

    def do_PUT(self) -> None:  # noqa: N802
        self._forward_plain_http()

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward_plain_http()

    def do_HEAD(self) -> None:  # noqa: N802
        self._forward_plain_http()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._forward_plain_http()

    def _forward_plain_http(self) -> None:
        self._record_request()
        protocol = self._upstream_protocol()
        target_host = ""
        target_port = 80
        request_path = self.path or "/"
        if protocol in {"socks5", "socks5h"}:
            parsed = self._plain_http_target()
            if parsed is None:
                return
            target_host, target_port, request_path = parsed
            upstream = self._connect_socks_target(target_host, target_port)
        else:
            upstream = self._connect_http_upstream()
        if upstream is None:
            return
        try:
            body_len = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(body_len) if body_len > 0 else b""
            lines = [f"{self.command} {request_path} {self.request_version}\r\n"]
            for key, value in self.headers.items():
                lower = key.lower()
                if lower in {"connection", "proxy-authorization", "proxy-connection"}:
                    continue
                lines.append(f"{key}: {value}\r\n")
            if protocol not in {"socks5", "socks5h"}:
                lines.append(self._proxy_authorization_header())
            lines.append("Connection: close\r\n")
            if protocol not in {"socks5", "socks5h"}:
                lines.append("Proxy-Connection: close\r\n")
            lines.append("\r\n")
            upstream.sendall("".join(lines).encode("iso-8859-1", errors="replace") + body)
            self._relay_until_close(upstream, self.connection)
        finally:
            upstream.close()

    def _record_request(self) -> None:
        client_host = self.client_address[0] if self.client_address else ""
        self.server.note_request(client_host)  # type: ignore[attr-defined]

    def _upstream_protocol(self) -> str:
        profile = self.server.profile  # type: ignore[attr-defined]
        return str(profile.get("protocol") or "http")

    def _connect_http_upstream(self) -> Optional[socket.socket]:
        profile = self.server.profile  # type: ignore[attr-defined]
        protocol = str(profile.get("protocol") or "http")
        host = str(profile.get("host") or "")
        port = int(profile.get("port") or 0)
        try:
            sock = socket.create_connection((host, port), timeout=15)
            if protocol == "https":
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=host)
            return sock
        except Exception:
            self.send_error(502, "failed to connect upstream proxy")
            return None

    def _connect_target_from_connect_path(self) -> Optional[Tuple[str, int]]:
        host, sep, port_text = str(self.path or "").rpartition(":")
        if not sep or not host:
            self.send_error(400, "CONNECT target must be host:port")
            return None
        try:
            port = int(port_text)
        except ValueError:
            self.send_error(400, "CONNECT target port is invalid")
            return None
        if port <= 0 or port > 65535:
            self.send_error(400, "CONNECT target port is invalid")
            return None
        return host.strip("[]"), port

    def _plain_http_target(self) -> Optional[Tuple[str, int, str]]:
        parsed = urlsplit(self.path or "")
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname or ""
            port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
            path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            return host, port, path
        host_header = str(self.headers.get("Host") or "")
        if not host_header:
            self.send_error(400, "Host header is required")
            return None
        host, sep, port_text = host_header.rpartition(":")
        if sep and port_text.isdigit():
            return host.strip("[]"), int(port_text), self.path or "/"
        return host_header.strip("[]"), 80, self.path or "/"

    def _connect_socks_target(self, target_host: str, target_port: int) -> Optional[socket.socket]:
        profile = self.server.profile  # type: ignore[attr-defined]
        upstream_host = str(profile.get("host") or "")
        upstream_port = int(profile.get("port") or 0)
        username = str(profile.get("username") or "")
        password = self.server.password  # type: ignore[attr-defined]
        sock: Optional[socket.socket] = None
        try:
            sock = socket.create_connection((upstream_host, upstream_port), timeout=15)
            methods = [0]
            if username:
                methods.append(2)
            sock.sendall(bytes([5, len(methods), *methods]))
            selected = self._read_exact(sock, 2)
            if len(selected) != 2 or selected[0] != 5 or selected[1] == 0xFF:
                raise RuntimeError("SOCKS5 upstream did not accept an authentication method")
            if selected[1] == 2:
                username_bytes = username.encode("utf-8")
                password_bytes = str(password or "").encode("utf-8")
                if len(username_bytes) > 255 or len(password_bytes) > 255:
                    raise RuntimeError("SOCKS5 username/password is too long")
                sock.sendall(bytes([1, len(username_bytes)]) + username_bytes + bytes([len(password_bytes)]) + password_bytes)
                auth = self._read_exact(sock, 2)
                if len(auth) != 2 or auth[1] != 0:
                    raise RuntimeError("SOCKS5 upstream authentication failed")
            elif selected[1] != 0:
                raise RuntimeError("SOCKS5 upstream selected an unsupported authentication method")

            host_bytes = str(target_host).encode("idna")
            if len(host_bytes) > 255:
                raise RuntimeError("SOCKS5 target host is too long")
            request = bytes([5, 1, 0, 3, len(host_bytes)]) + host_bytes + int(target_port).to_bytes(2, "big")
            sock.sendall(request)
            head = self._read_exact(sock, 4)
            if len(head) != 4 or head[0] != 5:
                raise RuntimeError("bad SOCKS5 upstream response")
            if head[1] != 0:
                raise RuntimeError(f"SOCKS5 upstream connect failed: {head[1]}")
            atyp = head[3]
            if atyp == 1:
                self._read_exact(sock, 4)
            elif atyp == 3:
                length = self._read_exact(sock, 1)
                self._read_exact(sock, length[0] if length else 0)
            elif atyp == 4:
                self._read_exact(sock, 16)
            else:
                raise RuntimeError("bad SOCKS5 bind address type")
            self._read_exact(sock, 2)
            return sock
        except Exception:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            self.send_error(502, "failed to connect through SOCKS5 upstream")
            return None

    def _proxy_authorization_header(self) -> str:
        profile = self.server.profile  # type: ignore[attr-defined]
        username = str(profile.get("username") or "")
        password = self.server.password  # type: ignore[attr-defined]
        if not username:
            return ""
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return f"Proxy-Authorization: Basic {token}\r\n"

    @staticmethod
    def _read_headers(sock: socket.socket) -> bytes:
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    @staticmethod
    def _read_exact(sock: socket.socket, size: int) -> bytes:
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                break
            data += chunk
        return data

    @staticmethod
    def _relay_until_close(src: socket.socket, dst: socket.socket) -> None:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                return
            dst.sendall(chunk)

    @staticmethod
    def _tunnel(left: socket.socket, right: socket.socket) -> None:
        sockets = [left, right]
        deadline = time.monotonic() + TUNNEL_MAX_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            readable, _writable, errored = select.select(sockets, [], sockets, min(5.0, remaining))
            if errored or not readable:
                return
            for src in readable:
                dst = right if src is left else left
                data = src.recv(65536)
                if not data:
                    return
                dst.sendall(data)


def _auto_stop_after_idle(bridge_id: str) -> None:
    while True:
        with _LOCK:
            record = _BRIDGES.get(bridge_id)
        if record is None:
            return
        active, last_activity, idle_timeout = record.server.idle_snapshot()
        if idle_timeout <= 0:
            return
        if active == 0 and time.time() - last_activity >= idle_timeout:
            stop_bridge(bridge_id)
            return
        time.sleep(min(1.0, max(0.05, idle_timeout / 4)))


def start_http_bridge(
    profile: Dict[str, Any],
    password: str = "",
    bind_host: str = "127.0.0.1",
    bind_port: int = 0,
    idle_timeout_s: float = 0,
) -> Dict[str, Any]:
    """Start a local unauthenticated HTTP proxy that authenticates upstream."""
    protocol = str(profile.get("protocol") or "")
    if protocol not in {"http", "https", "socks5", "socks5h"}:
        return {
            "ok": False,
            "error": "loopback bridge supports HTTP/HTTPS or SOCKS5 upstream proxies",
            "reason_code": "bridge_unsupported_upstream_protocol",
        }
    bridge_id = str(uuid.uuid4())
    try:
        server = _BridgeServer((bind_host, bind_port), profile, password, idle_timeout_s=idle_timeout_s)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "reason_code": "bridge_start_failed"}
    thread = threading.Thread(target=server.serve_forever, name=f"netfix-proxy-bridge-{bridge_id[:8]}", daemon=True)
    record = _BridgeRecord(bridge_id, server, thread, profile)
    with _LOCK:
        _BRIDGES[bridge_id] = record
    thread.start()
    if server.idle_timeout_s > 0:
        monitor = threading.Thread(target=_auto_stop_after_idle, args=(bridge_id,), name=f"netfix-proxy-bridge-idle-{bridge_id[:8]}", daemon=True)
        monitor.start()
    return {"ok": True, "bridge": record.to_public()}


def stop_bridge(bridge_id: str) -> Dict[str, Any]:
    """Stop a running bridge by id."""
    with _LOCK:
        record = _BRIDGES.pop(bridge_id, None)
    if record is None:
        return {"ok": True, "stopped": False, "missing": True, "bridge_id": bridge_id}
    record.server.shutdown()
    record.server.server_close()
    record.thread.join(timeout=3)
    return {"ok": True, "stopped": True, "bridge_id": bridge_id}


def status() -> Dict[str, Any]:
    with _LOCK:
        bridges = [record.to_public() for record in _BRIDGES.values()]
    return {"ok": True, "bridges": bridges}
