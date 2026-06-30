"""WireGuard App / command-line core adapter."""
from __future__ import annotations

import logging
import re
from typing import Any

from netfix.cores.base import CoreBase
from netfix.utils import run_command

logger = logging.getLogger(__name__)


class WireGuardCore(CoreBase):
    """Adapter for WireGuard tunnels on macOS.

    Detection relies on the ``wg`` utility and/or active ``utun`` interfaces.
    Switching tunnels is not supported programmatically; the user must use the
    WireGuard app or ``wg-quick`` manually.
    """

    name = "wireguard"

    def _wg_available(self) -> bool:
        """Return ``True`` if the ``wg`` command is on PATH."""
        return run_command(["wg", "show", "interfaces"])["ok"]

    def _utun_interfaces(self) -> list[dict[str, str | None]]:
        """Return active ``utun`` interfaces with their IPv4 addresses."""
        interfaces: list[dict[str, str | None]] = []
        output = run_command(["ifconfig"])
        if not output["ok"]:
            return interfaces
        current: dict[str, str | None] | None = None
        for line in output["stdout"].splitlines():
            iface_match = re.match(r"^(utun\d+):", line)
            if iface_match:
                if current:
                    interfaces.append(current)
                current = {"id": iface_match.group(1), "address": None}
                continue
            if current is None:
                continue
            if re.search(r"status:\s+active", line, re.IGNORECASE):
                current["active"] = "true"
            inet_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
            if inet_match and not current.get("address"):
                current["address"] = inet_match.group(1)
        if current:
            interfaces.append(current)
        return [i for i in interfaces if i.get("active") == "true"]

    def detect(self) -> bool:
        """Return ``True`` if WireGuard appears to be active."""
        if self._wg_available():
            output = run_command(["wg", "show", "interfaces"])
            if output["ok"] and output["stdout"].strip():
                return True
        return bool(self._utun_interfaces())

    def is_running(self) -> bool:
        """Return ``True`` if a WireGuard tunnel is up."""
        return self.detect()

    def get_inbound(self) -> dict[str, Any]:
        """WireGuard does not expose a local SOCKS/HTTP inbound."""
        return {}

    def _first_active_interface(self) -> dict[str, str | None] | None:
        """Return the first active ``utun`` interface, if any."""
        interfaces = self._utun_interfaces()
        return interfaces[0] if interfaces else None

    def get_active_profile(self) -> dict[str, Any] | None:
        """Return the first active WireGuard tunnel interface."""
        iface = self._first_active_interface()
        if not iface:
            return None
        return {
            "id": iface["id"],
            "remarks": f"WireGuard {iface['id']}",
            "address": iface.get("address"),
            "port": None,
            "type": "wireguard",
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return active WireGuard tunnel interfaces."""
        return [
            {
                "id": i["id"],
                "remarks": f"WireGuard {i['id']}",
                "address": i.get("address"),
                "port": None,
                "type": "wireguard",
            }
            for i in self._utun_interfaces()
        ]

    def can_api_switch(self) -> bool:
        """WireGuard has no runtime node-switching API."""
        return False

    def switch_profile(self, profile_id: str) -> bool:
        """Switching is not supported; use the WireGuard app or ``wg-quick``."""
        return False

    def get_api_info(self) -> dict[str, Any] | None:
        """No controller API for WireGuard."""
        return None
