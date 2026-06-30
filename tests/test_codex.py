"""Tests for netfix.codex with local HTTP servers."""
from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from netfix import codex


class _DirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"direct")

    def log_message(self, format, *args):
        pass


class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"proxy")

    def log_message(self, format, *args):
        pass


class TestCheckEndpoint(unittest.TestCase):
    def setUp(self):
        self.target_server = ThreadingHTTPServer(("127.0.0.1", 0), _DirectHandler)
        self.proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHandler)
        self.target_port = self.target_server.server_address[1]
        self.proxy_port = self.proxy_server.server_address[1]
        self.target_thread = threading.Thread(target=self.target_server.serve_forever, daemon=True)
        self.proxy_thread = threading.Thread(target=self.proxy_server.serve_forever, daemon=True)
        self.target_thread.start()
        self.proxy_thread.start()

    def tearDown(self):
        self.target_server.shutdown()
        self.proxy_server.shutdown()
        self.target_server.server_close()
        self.proxy_server.server_close()
        self.target_thread.join(timeout=2)
        self.proxy_thread.join(timeout=2)

    def test_direct_request(self):
        url = f"http://127.0.0.1:{self.target_port}/"
        result = codex.check_endpoint("direct", url, "/", timeout=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["http_code"], 200)
        self.assertEqual(result["proxy_used"], "direct")

    def test_via_proxy_routes_through_proxy(self):
        target = f"http://127.0.0.1:{self.target_port}/"
        proxy = f"http://127.0.0.1:{self.proxy_port}/"
        result = codex.check_endpoint("via_proxy", target, "/", proxy_url=proxy, timeout=5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["http_code"], 200)
        self.assertEqual(result["proxy_used"], proxy)

    def test_unreachable_endpoint(self):
        result = codex.check_endpoint("unreachable", "http://127.0.0.1:1", "/", timeout=1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["http_code"], 0)
        self.assertIsNotNone(result["error"])


class TestCodexHelpers(unittest.TestCase):
    def test_check_codex_direct_labels_direct(self):
        result = codex.check_codex_direct(timeout=1)
        self.assertEqual(result["name"], "codex_api_direct")
        self.assertEqual(result["proxy_used"], "direct")


if __name__ == "__main__":
    unittest.main()
