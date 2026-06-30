"""xray standalone core adapter."""
from __future__ import annotations

import logging
import os
from typing import Any

from netfix.cores.base import CoreBase
from netfix.utils import command_executable, run_command

logger = logging.getLogger(__name__)


class XrayCore(CoreBase):
    """Adapter for a standalone xray process.

    The active configuration is normally provided through a temporary file
    that is unlinked after startup, so this adapter only reports process and
    listening-port information.  It does not support API switching.
    """

    name = "xray"

    def detect(self) -> bool:
        """Return ``True`` if an xray process is running."""
        ps = run_command(["ps", "-axo", "pid,command"])
        if ps["ok"]:
            for line in ps["stdout"].splitlines()[1:]:
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                try:
                    pid = int(parts[0])
                except ValueError:
                    continue
                if pid == os.getpid():
                    continue
                exe = command_executable(parts[1])
                exe_str = str(exe).lower() if exe else ""
                if "xray" in exe_str and "v2rayN" not in parts[1]:
                    return True
        output = run_command(["pgrep", "-x", "xray"])
        if output["ok"] and output["stdout"].strip():
            return True
        return False

    def is_running(self) -> bool:
        """Return ``True`` if xray is running."""
        return self.detect()

    def get_inbound(self) -> dict[str, Any]:
        """Return the first listening port that belongs to xray."""
        for p in self.env.get("listening_ports", []):
            if "xray" in p.get("command", "").lower():
                return {
                    "port": p["port"],
                    "protocol": "mixed",
                    "host": p.get("host", "127.0.0.1"),
                }
        return {"port": None, "protocol": "mixed", "host": "127.0.0.1"}

    def get_active_profile(self) -> dict[str, Any] | None:
        """xray standalone configuration is not readable at runtime."""
        return None

    def list_profiles(self) -> list[dict[str, Any]]:
        """No profile list available for a running xray process."""
        return []

    def can_api_switch(self) -> bool:
        """xray has no built-in controller API for node switching."""
        return False

    def switch_profile(self, profile_id: str) -> bool:
        """Switching is not supported for standalone xray."""
        return False

    def get_api_info(self) -> dict[str, Any] | None:
        """No controller API for xray."""
        return None
