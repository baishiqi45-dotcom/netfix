"""Tests for netfix.detect."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from netfix import detect
from netfix.utils import command_executable


SCUTIL_OUTPUT = """
<dictionary> {
  ProxyAutoDiscoveryEnable : 0
  HTTPEnable : 1
  HTTPProxy : 127.0.0.1
  HTTPPort : 10808
  HTTPSEnable : 1
  HTTPSProxy : 127.0.0.1
  HTTPSPort : 10808
  SOCKSEnable : 1
  SOCKSProxy : 127.0.0.1
  SOCKSPort : 10808
  ProxyAutoConfigEnable : 1
  ProxyAutoConfigURLString : http://wpad/wpad.dat
}
"""


def _fake_command_executable(command: str):
    """Return the first token as a Path so keyword matching works in tests."""
    if not command:
        return None
    token = command.split()[0]
    return Path(token)


class TestDetectSystemProxy(unittest.TestCase):
    def test_parses_scutil_output(self):
        def fake_run(cmd, **kwargs):
            return {
                "cmd": " ".join(cmd),
                "returncode": 0,
                "stdout": SCUTIL_OUTPUT if cmd[0] == "scutil" else "",
                "stderr": "",
                "ok": True,
            }

        with patch("netfix.detect.run_command", side_effect=fake_run):
            proxy = detect.detect_system_proxy()

        self.assertEqual(proxy["http"], "127.0.0.1:10808")
        self.assertEqual(proxy["https"], "127.0.0.1:10808")
        self.assertEqual(proxy["socks"], "127.0.0.1:10808")
        self.assertEqual(proxy["pac"], "http://wpad/wpad.dat")
        self.assertEqual(proxy["_detection_status"], "ok")

    def test_command_failure_is_unknown_not_an_empty_no_proxy_result(self):
        failed = {
            "cmd": "scutil --proxy",
            "returncode": 1,
            "stdout": "",
            "stderr": "not available",
            "ok": False,
        }
        with patch("netfix.detect.run_command", return_value=failed):
            proxy = detect.detect_system_proxy()

        self.assertEqual(proxy["_detection_status"], "unknown")
        self.assertIsNone(proxy["http"])


class TestDetectRunningProxies(unittest.TestCase):
    def test_finds_known_proxy_processes(self):
        ps_output = """
  PID COMMAND
 1234 /bin/bash
 5678 /Applications/v2rayN.app/Contents/MacOS/v2rayN
 9999 /usr/local/bin/xray -config config.json
"""

        def fake_run(cmd, **kwargs):
            return {
                "cmd": " ".join(cmd),
                "returncode": 0,
                "stdout": ps_output if cmd[0] == "ps" else "",
                "stderr": "",
                "ok": True,
            }

        with patch("netfix.detect.run_command", side_effect=fake_run), \
             patch("netfix.detect.command_executable", side_effect=_fake_command_executable):
            proxies = detect.detect_running_proxies()

        self.assertIn("v2rayn", proxies)
        self.assertIn("xray", proxies)
        self.assertNotIn("bash", proxies)

        v2rayn = proxies["v2rayn"]
        self.assertEqual(len(v2rayn), 1)
        self.assertEqual(v2rayn[0]["pid"], "5678")

    def test_command_executable_skips_unreadable_absolute_path(self):
        command = "/private/var/db/protected.app/Contents/MacOS/protected --flag"
        with patch("pathlib.Path.is_file", side_effect=PermissionError("denied")):
            self.assertIsNone(command_executable(command))


if __name__ == "__main__":
    unittest.main()
