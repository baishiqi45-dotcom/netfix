import time
import unittest
from unittest.mock import patch

from netfix import service_runner


class SlowProcess:
    def __init__(self, *args, **kwargs):
        self.returncode = None
        self.terminated = False
        self.killed = False

    def communicate(self, timeout=None):
        time.sleep(0.2)
        if self.terminated:
            self.returncode = -15
            return "", "terminated"
        self.returncode = 0
        return '{"ok": true, "diagnostics": []}', ""

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9

    def poll(self):
        return self.returncode


class TestServiceRunnerJobs(unittest.TestCase):
    def test_source_cli_command_uses_python_module_entry(self):
        with patch.object(service_runner.sys, "executable", "/usr/bin/python3"):
            if hasattr(service_runner.sys, "frozen"):
                with patch.object(service_runner.sys, "frozen", False):
                    command = service_runner._cli_command(["codex", "--json"])
            else:
                command = service_runner._cli_command(["codex", "--json"])

        self.assertEqual(command, ["/usr/bin/python3", "-m", "netfix.cli", "codex", "--json"])

    def test_frozen_cli_command_calls_bundled_backend_directly(self):
        with patch.object(service_runner.sys, "executable", "/Applications/Netfix.app/Contents/MacOS/netfix-backend"), \
                patch.object(service_runner.sys, "frozen", True, create=True):
            command = service_runner._cli_command(["codex", "--json"])

        self.assertEqual(command, ["/Applications/Netfix.app/Contents/MacOS/netfix-backend", "codex", "--json"])
        self.assertNotIn("netfix.cli", command)

    def test_cancel_job_terminates_process_and_preserves_cancelled_status(self):
        created = []

        def fake_popen(*args, **kwargs):
            proc = SlowProcess(*args, **kwargs)
            created.append(proc)
            return proc

        with patch("netfix.service_runner.subprocess.Popen", side_effect=fake_popen):
            job_id = service_runner.start_job(["codex", "--json"], timeout=5)
            deadline = time.time() + 2
            while time.time() < deadline and not created:
                time.sleep(0.01)

            cancelled = service_runner.cancel_job(job_id)
            self.assertIsNotNone(cancelled)
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["error"], "job cancelled")
            self.assertTrue(created[0].terminated)

            time.sleep(0.3)
            final = service_runner.get_job(job_id)
            self.assertIsNotNone(final)
            self.assertEqual(final["status"], "cancelled")
            self.assertNotIn("_process", final)


if __name__ == "__main__":
    unittest.main()
