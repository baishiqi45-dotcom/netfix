import socket
import socketserver
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler

from netfix import proxy_bridge


class _UpstreamProxyHandler(BaseHTTPRequestHandler):
    auth_header = ""
    received_path = ""

    def log_message(self, _format, *_args):
        return

    def do_GET(self):  # noqa: N802
        type(self).auth_header = self.headers.get("Proxy-Authorization", "")
        type(self).received_path = self.path
        body = b"bridge-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Socks5UpstreamHandler(socketserver.BaseRequestHandler):
    username = ""
    password = ""
    target = ("", 0)
    request_line = b""

    def handle(self):
        first = self.request.recv(2)
        if len(first) != 2 or first[0] != 5:
            return
        methods = self.request.recv(first[1])
        self.request.sendall(b"\x05\x02" if b"\x02" in methods else b"\x05\x00")
        if b"\x02" in methods:
            auth_head = self.request.recv(2)
            if len(auth_head) != 2 or auth_head[0] != 1:
                return
            username = self.request.recv(auth_head[1]).decode("utf-8")
            plen = self.request.recv(1)[0]
            password = self.request.recv(plen).decode("utf-8")
            type(self).username = username
            type(self).password = password
            self.request.sendall(b"\x01\x00")
        req_head = self.request.recv(4)
        if len(req_head) != 4 or req_head[0] != 5 or req_head[1] != 1:
            return
        atyp = req_head[3]
        if atyp == 1:
            host = socket.inet_ntoa(self.request.recv(4))
        elif atyp == 3:
            size = self.request.recv(1)[0]
            host = self.request.recv(size).decode("utf-8")
        else:
            return
        port = int.from_bytes(self.request.recv(2), "big")
        type(self).target = (host, port)
        self.request.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 4096:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data += chunk
        type(self).request_line = data.split(b"\r\n", 1)[0]
        body = b"socks-bridge-ok"
        self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)


class TestProxyBridge(unittest.TestCase):
    def setUp(self):
        _UpstreamProxyHandler.auth_header = ""
        _UpstreamProxyHandler.received_path = ""
        _Socks5UpstreamHandler.username = ""
        _Socks5UpstreamHandler.password = ""
        _Socks5UpstreamHandler.target = ("", 0)
        _Socks5UpstreamHandler.request_line = b""
        self.upstream = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _UpstreamProxyHandler)
        self.upstream.daemon_threads = True
        self.thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.upstream.shutdown()
        self.upstream.server_close()
        self.thread.join(timeout=3)

    def test_bridge_injects_proxy_authorization_without_public_secret(self):
        host, port = self.upstream.server_address
        profile = {
            "id": "p1",
            "name": "upstream",
            "protocol": "http",
            "host": host,
            "port": port,
            "username": "user",
        }
        started = proxy_bridge.start_http_bridge(profile, password="pass")
        self.assertTrue(started["ok"])
        bridge = started["bridge"]
        try:
            encoded = str(started)
            self.assertNotIn("pass", encoded)
            with socket.create_connection((bridge["listen_host"], bridge["listen_port"]), timeout=5) as sock:
                sock.sendall(
                    b"GET http://example.com/health HTTP/1.1\r\n"
                    b"Host: example.com\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                response = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            self.assertIn(b"bridge-ok", response)
            self.assertEqual(_UpstreamProxyHandler.received_path, "http://example.com/health")
            self.assertEqual(_UpstreamProxyHandler.auth_header, "Basic dXNlcjpwYXNz")
        finally:
            stopped = proxy_bridge.stop_bridge(bridge["id"])
            self.assertTrue(stopped["ok"])
            self.assertTrue(stopped["stopped"])

    def test_bridge_status_records_client_audit_without_target_url(self):
        host, port = self.upstream.server_address
        profile = {
            "id": "p1",
            "name": "upstream",
            "protocol": "http",
            "host": host,
            "port": port,
            "username": "user",
        }
        started = proxy_bridge.start_http_bridge(profile, password="pass")
        self.assertTrue(started["ok"])
        bridge = started["bridge"]
        try:
            with socket.create_connection((bridge["listen_host"], bridge["listen_port"]), timeout=5) as sock:
                sock.sendall(
                    b"GET http://example.com/health HTTP/1.1\r\n"
                    b"Host: example.com\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                while sock.recv(4096):
                    pass
            status = proxy_bridge.status()
            current = next(item for item in status["bridges"] if item["id"] == bridge["id"])
            self.assertEqual(current["request_count"], 1)
            self.assertEqual(current["active_connections"], 0)
            self.assertEqual(current["recent_clients"][0]["host"], "127.0.0.1")
            self.assertEqual(current["recent_clients"][0]["count"], 1)
            self.assertIn("last_activity_at", current)
            self.assertNotIn("example.com/health", str(current))
        finally:
            proxy_bridge.stop_bridge(bridge["id"])

    def test_bridge_auto_stops_after_idle_timeout(self):
        host, port = self.upstream.server_address
        profile = {"id": "p1", "name": "upstream", "protocol": "http", "host": host, "port": port}
        started = proxy_bridge.start_http_bridge(profile, idle_timeout_s=0.2)
        self.assertTrue(started["ok"])
        bridge_id = started["bridge"]["id"]
        deadline = time.time() + 3
        try:
            while time.time() < deadline:
                bridges = proxy_bridge.status()["bridges"]
                if not any(item["id"] == bridge_id for item in bridges):
                    return
                time.sleep(0.05)
            self.fail("bridge did not auto-stop after idle timeout")
        finally:
            proxy_bridge.stop_bridge(bridge_id)

    def test_bridge_authenticates_to_socks5_upstream_without_public_secret(self):
        socks = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Socks5UpstreamHandler)
        socks.daemon_threads = True
        thread = threading.Thread(target=socks.serve_forever, daemon=True)
        thread.start()
        host, port = socks.server_address
        profile = {
            "id": "p-socks",
            "name": "socks upstream",
            "protocol": "socks5",
            "host": host,
            "port": port,
            "username": "user",
        }
        started = proxy_bridge.start_http_bridge(profile, password="pass")
        self.assertTrue(started["ok"])
        bridge = started["bridge"]
        try:
            self.assertNotIn("pass", str(started))
            with socket.create_connection((bridge["listen_host"], bridge["listen_port"]), timeout=5) as sock:
                sock.sendall(
                    b"GET http://example.com/health HTTP/1.1\r\n"
                    b"Host: example.com\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                )
                response = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            self.assertIn(b"socks-bridge-ok", response)
            self.assertEqual(_Socks5UpstreamHandler.username, "user")
            self.assertEqual(_Socks5UpstreamHandler.password, "pass")
            self.assertEqual(_Socks5UpstreamHandler.target, ("example.com", 80))
            self.assertEqual(_Socks5UpstreamHandler.request_line, b"GET /health HTTP/1.1")
        finally:
            proxy_bridge.stop_bridge(bridge["id"])
            socks.shutdown()
            socks.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
