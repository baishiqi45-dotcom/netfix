"""Tests for netfix layered diagnostics."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from netfix import diagnose
from netfix.agent_tools import _redact_url
from netfix.ip_intel import _cache_get, _cache_set, _cache_load
from netfix.layers import egress, local, path, proxy


class TestLocalHelpers(unittest.TestCase):
    def test_status_from_rssi(self):
        self.assertEqual(local.status_from_rssi(-30), "ok")
        self.assertEqual(local.status_from_rssi(-65), "warn")
        self.assertEqual(local.status_from_rssi(-75), "fail")
        self.assertEqual(local.status_from_rssi(None), "warn")


class TestLocalDiagnostics(unittest.TestCase):
    def _fake_run(self, outputs):
        def runner(cmd, **kwargs):
            key = " ".join(cmd[:3])
            stdout = outputs.get(key, "")
            return {"cmd": " ".join(cmd), "returncode": 0, "stdout": stdout, "stderr": "", "ok": True}
        return runner

    def test_interface_state_ok(self):
        outputs = {
            "route -n get": "interface: en0\ngateway: 192.168.1.1",
            "ipconfig getifaddr en0": "192.168.1.42",
            "ifconfig en0": "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n\tinet 192.168.1.42 netmask 0xffffff00 broadcast 192.168.1.255\n\tinet6 fe80::1 prefixlen 64",
        }
        fake = self._fake_run(outputs)
        with patch("netfix.layers._helpers.run_command", side_effect=fake), \
             patch("netfix.layers.local.run_command", side_effect=fake):
            result = diagnose.run_diagnostic("interface_state", {}, None, 10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["layer"], "network")
        self.assertEqual(result["details"]["ipv4"], "192.168.1.42")

    def test_dhcp_state_ok(self):
        outputs = {
            "route -n get": "interface: en0",
            "ipconfig getpacket en0": "yiaddr = 192.168.1.42\nserver_identifier (ip): 192.168.1.1\nrouter (ip_mult): {192.168.1.1}\ndomain_name_server (ip_mult): {192.168.1.1}",
        }
        fake = self._fake_run(outputs)
        with patch("netfix.layers._helpers.run_command", side_effect=fake), \
             patch("netfix.layers.local.run_command", side_effect=fake):
            result = diagnose.run_diagnostic("dhcp_state", {}, None, 10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["yiaddr"], "192.168.1.42")

    def test_dhcp_state_fail_self_assigned(self):
        outputs = {
            "route -n get": "interface: en0",
            "ipconfig getpacket en0": "yiaddr = 169.254.1.2",
        }
        fake = self._fake_run(outputs)
        with patch("netfix.layers._helpers.run_command", side_effect=fake), \
             patch("netfix.layers.local.run_command", side_effect=fake):
            result = diagnose.run_diagnostic("dhcp_state", {}, None, 10)
        self.assertEqual(result["status"], "fail")

    def test_gateway_ok(self):
        outputs = {
            "route -n get": "gateway: 192.168.1.1",
            "ping -c 3 -W 2000 192.168.1.1": "3 packets transmitted, 3 packets received, 0.0% packet loss",
        }
        with patch("netfix.layers._helpers.run_command", side_effect=self._fake_run(outputs)):
            result = diagnose.run_diagnostic("gateway", {}, None, 10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["packet_loss"], 0.0)

    def test_ipv4_route_ok(self):
        outputs = {"route -n get": "interface: en0\ngateway: 192.168.1.1"}
        with patch("netfix.layers._helpers.run_command", side_effect=self._fake_run(outputs)):
            result = diagnose.run_diagnostic("ipv4_route", {}, None, 10)
        self.assertEqual(result["status"], "ok")

    def test_dns_resolvers(self):
        outputs = {
            "scutil --dns": "resolver #1\n  nameserver[0] : 1.1.1.1\n  nameserver[1] : 8.8.8.8",
        }
        fake = self._fake_run(outputs)
        with patch("netfix.layers._helpers.run_command", side_effect=fake), \
             patch("netfix.layers.local.run_command", side_effect=fake):
            result = diagnose.run_diagnostic("dns_resolvers", {}, None, 10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["resolvers"], ["1.1.1.1", "8.8.8.8"])


class TestProxyDiagnostics(unittest.TestCase):
    SCUTIL = """
<dictionary> {
  HTTPEnable : 1
  HTTPProxy : 127.0.0.1
  HTTPPort : 10808
  HTTPSEnable : 1
  HTTPSProxy : 127.0.0.1
  HTTPSPort : 10808
  SOCKSEnable : 1
  SOCKSProxy : 127.0.0.1
  SOCKSPort : 10808
  ProxyAutoDiscoveryEnable : 0
}
"""

    def _fake_run(self, outputs):
        def runner(cmd, **kwargs):
            key = " ".join(cmd[:3])
            stdout = outputs.get(key, "")
            return {"cmd": " ".join(cmd), "returncode": 0, "stdout": stdout, "stderr": "", "ok": True}
        return runner

    def test_system_proxy_state_ok(self):
        outputs = {
            "scutil --proxy": self.SCUTIL,
            "lsof -nP -iTCP": "COMMAND PID USER FD TYPE DEVICE SIZE NODE NAME\nxray 1234 user 3u IPv4 0x0 0t0 TCP *:10808 (LISTEN)",
        }
        with patch("netfix.layers.proxy.run_command", side_effect=self._fake_run(outputs)):
            result = diagnose.run_diagnostic("system_proxy_state", {}, None, 10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["details"]["http"]["endpoint"], "127.0.0.1:10808")
        self.assertEqual(result["details"]["mismatches"], [])

    def test_system_proxy_state_warn_when_manual_and_pac_enabled(self):
        scutil = self.SCUTIL.replace(
            "ProxyAutoDiscoveryEnable : 0",
            "ProxyAutoConfigEnable : 1\n  ProxyAutoConfigURLString : http://wpad/wpad.dat\n  ProxyAutoDiscoveryEnable : 1",
        )
        outputs = {
            "scutil --proxy": scutil,
            "lsof -nP -iTCP": "COMMAND PID USER FD TYPE DEVICE SIZE NODE NAME\nxray 1234 user 3u IPv4 0x0 0t0 TCP *:10808 (LISTEN)",
        }
        with patch("netfix.layers.proxy.run_command", side_effect=self._fake_run(outputs)):
            result = diagnose.run_diagnostic("system_proxy_state", {}, None, 10)
        self.assertEqual(result["status"], "warn")
        self.assertTrue(result["details"]["mixed_auto_and_manual"])

    def test_system_proxy_state_mismatch(self):
        outputs = {
            "scutil --proxy": self.SCUTIL,
            "lsof -nP -iTCP": "COMMAND PID USER FD TYPE DEVICE SIZE NODE NAME\nfoo 1234 user 3u IPv4 0x0 0t0 TCP *:7890 (LISTEN)",
        }
        with patch("netfix.layers.proxy.run_command", side_effect=self._fake_run(outputs)):
            result = diagnose.run_diagnostic("system_proxy_state", {}, None, 10)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("10808" in m for m in result["details"]["mismatches"]))

    def test_proxy_auth_check_requires_auth(self):
        outputs = {
            "scutil --proxy": self.SCUTIL,
            "lsof -nP -iTCP": "xray 1234 user 3u IPv4 0x0 0t0 TCP *:10808 (LISTEN)",
        }

        def curl_runner(cmd, **kwargs):
            if cmd[0] == "curl" and "-x" in cmd:
                return {"cmd": " ".join(cmd), "returncode": 0, "stdout": "407", "stderr": "", "ok": True}
            return self._fake_run(outputs)(cmd, **kwargs)

        with patch("netfix.layers.proxy.run_command", side_effect=curl_runner):
            result = diagnose.run_diagnostic("proxy_auth_check", {"mixed_port": 10808}, None, 10)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["details"]["requires_auth"])

    def test_proxy_http_test_accepts_generate_204(self):
        def curl_runner(cmd, **kwargs):
            if cmd[0] == "curl" and "-x" in cmd:
                return {"cmd": " ".join(cmd), "returncode": 0, "stdout": "204|0.100|", "stderr": "", "ok": True}
            return self._fake_run({"scutil --proxy": self.SCUTIL})(cmd, **kwargs)

        with patch("netfix.layers.proxy.run_command", side_effect=curl_runner):
            result = diagnose.run_diagnostic("proxy_http_test", {}, None, 10)
        self.assertEqual(result["status"], "ok")


class TestEgressDiagnostics(unittest.TestCase):
    def test_dns_leak_warn_when_local_and_proxy(self):
        outputs = {
            "scutil --dns": "resolver #1\n  nameserver[0] : 192.168.1.1",
        }
        with patch("netfix.layers.egress.run_command", side_effect=lambda cmd, **kw: {
            "cmd": " ".join(cmd), "returncode": 0, "stdout": outputs.get("scutil --dns", ""), "stderr": "", "ok": True,
        }):
            result = diagnose.run_diagnostic("dns_leak", {"active_core": "v2rayN"}, None, 10)
        self.assertEqual(result["status"], "warn")
        self.assertIn("192.168.1.1", result["details"]["private_resolvers"])

    def test_ipv6_leak_warn(self):
        with patch("netfix.layers.egress.current_ipv6", return_value="2400:1234::1"):
            result = diagnose.run_diagnostic("ipv6_leak", {"active_core": "v2rayN"}, None, 10)
        self.assertEqual(result["status"], "warn")
        self.assertEqual(result["details"]["public_ipv6"], "2400:1234::1")
        self.assertTrue(result["details"]["leak_confirmed"])

    def test_ipv6_route_without_public_ipv6_is_fallback_risk(self):
        with patch("netfix.layers.egress.current_ipv6", return_value=None), \
             patch("netfix.layers.egress.has_ipv6_default_route", return_value=True):
            result = diagnose.run_diagnostic("ipv6_leak", {"active_core": "v2rayN"}, None, 10)
        self.assertEqual(result["status"], "warn")
        self.assertFalse(result["details"]["leak_confirmed"])
        self.assertTrue(result["details"]["fallback_risk"])


class TestPathDiagnostics(unittest.TestCase):
    TRACEROUTE = """traceroute to 8.8.8.8 (8.8.8.8), 64 hops max, 52 byte packets
 1  192.168.1.1 (192.168.1.1)  2.123 ms  1.987 ms  2.045 ms
 2  10.0.0.1 (10.0.0.1)  5.123 ms  4.987 ms  5.045 ms
 3  * * *
"""

    def test_parse_traceroute(self):
        hops = path._parse_traceroute(self.TRACEROUTE)
        self.assertEqual(len(hops), 3)
        self.assertEqual(hops[0]["host"], "192.168.1.1")
        self.assertEqual(hops[0]["rtt_ms"], 2.123)
        self.assertIsNone(hops[2]["host"])

    def test_path_trace_status(self):
        hops = [
            {"hop": 1, "host": "192.168.1.1", "ip": "192.168.1.1", "loss_percent": 0.0, "rtt_ms": 2.0},
            {"hop": 2, "host": "10.0.0.1", "ip": "10.0.0.1", "loss_percent": 0.0, "rtt_ms": 5.0},
        ]
        self.assertEqual(path._path_status(hops), "ok")
        hops[0]["loss_percent"] = 12.0
        self.assertEqual(path._path_status(hops), "fail")


class TestIpIntel(unittest.TestCase):
    def test_cache_roundtrip(self):
        _cache_set("1.2.3.4", {"ip": "1.2.3.4", "country": "US"})
        cached = _cache_get("1.2.3.4")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["country"], "US")

    def test_cache_expires(self):
        import time
        _cache_set("9.9.9.9", {"ip": "9.9.9.9"})
        # Simulate an expired entry by manipulating the timestamp.
        data = _cache_load()
        data["9.9.9.9"]["ts"] = time.time() - 7200
        from pathlib import Path
        from netfix.constants import JOURNAL_DIR
        cache_file = Path(JOURNAL_DIR) / "ip_cache.json"
        cache_file.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(_cache_get("9.9.9.9"))


class TestAgentTools(unittest.TestCase):
    def test_redact_url_masks_credentials(self):
        self.assertEqual(_redact_url("http://user:pass@proxy:8080"), "http://***@proxy:8080")
        self.assertEqual(_redact_url("socks5h://user:pass@127.0.0.1:1080"), "socks5h://***@127.0.0.1:1080")
        self.assertIsNone(_redact_url(None))


if __name__ == "__main__":
    unittest.main()
