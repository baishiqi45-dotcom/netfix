"""mihomo / Clash / Clash Verge core adapter (External Controller API)."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from netfix.cores.base import CoreBase
from netfix.utils import command_executable, run_command

logger = logging.getLogger(__name__)

_COMMON_API_PORTS = [9090, 9097, 9093, 7892]
_MIHOMO_CONFIG_PATHS = [
    Path.home() / ".config/mihomo/config.yaml",
    Path.home() / ".config/clash/config.yaml",
    Path.home() / ".config/clash.meta/config.yaml",
]
_GROUP_TYPES = {"Selector", "URLTest", "Fallback", "LoadBalance"}


def _parse_yaml_controller(text: str) -> tuple[str | None, str | None]:
    """Extract ``external-controller`` and ``secret`` from a YAML config."""
    controller: str | None = None
    secret: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = re.match(r"external-controller\s*:\s*(.+)", stripped)
        if match:
            controller = match.group(1).strip().strip('"').strip("'")
        match = re.match(r"secret\s*:\s*(.+)", stripped)
        if match:
            secret = match.group(1).strip().strip('"').strip("'")
    return controller, secret


class MihomoCore(CoreBase):
    """Adapter for mihomo / Clash / Clash Verge cores.

    Uses the External Controller REST API to query the active node and switch
    selectors when the API is reachable.
    """

    name = "mihomo"

    def detect(self) -> bool:
        """Return ``True`` if a mihomo or Clash process is running."""
        ps = run_command(["ps", "-axo", "pid,command"])
        if not ps["ok"]:
            return False
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
            if (
                "mihomo" in exe_str
                or "clash.meta" in exe_str
                or "clash-meta" in exe_str
            ):
                return True
            if "clash" in exe_str and "v2ray" not in exe_str:
                return True
        return False

    def is_running(self) -> bool:
        """Return ``True`` if the core process is running."""
        return self.detect()

    def _controller_and_secret(self) -> tuple[str | None, str | None]:
        """Discover controller endpoint and secret from config and process args."""
        controller: str | None = None
        secret: str | None = None

        for path in _MIHOMO_CONFIG_PATHS:
            if path.exists():
                try:
                    text = path.read_text(encoding="utf-8")
                    c, s = _parse_yaml_controller(text)
                    if c:
                        controller = c
                    if s:
                        secret = s
                except Exception as exc:
                    logger.debug("Failed to read %s: %s", path, exc)

        ps = run_command(["ps", "-axo", "pid,command"])
        if ps["ok"]:
            for line in ps["stdout"].splitlines()[1:]:
                if not any(k in line.lower() for k in ("mihomo", "clash")):
                    continue
                ctl_match = re.search(r"-ext-ctl\s+(\S+)", line)
                if ctl_match:
                    controller = ctl_match.group(1)
                secret_match = re.search(r"-secret\s+(\S+)", line)
                if secret_match:
                    secret = secret_match.group(1)

        return controller, secret

    def _api_port_secret(self) -> tuple[int | None, str | None]:
        """Return the resolved API port and secret."""
        controller, secret = self._controller_and_secret()
        port: int | None = None
        if controller and ":" in controller:
            try:
                port = int(controller.rsplit(":", 1)[1])
            except (ValueError, IndexError):
                port = None
        if port is None:
            port = self._resolve_port()
        return port, secret

    def _api_request(
        self, path: str, method: str = "GET", data: bytes | None = None
    ) -> Any:
        """Perform an authorized API request and return the parsed JSON body."""
        port, secret = self._api_port_secret()
        if port is None:
            return None
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url, method=method, data=data)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if secret:
            req.add_header("Authorization", f"Bearer {secret}")
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug("mihomo API %s %s failed: %s", method, url, exc)
            return None

    def _resolve_port(self) -> int | None:
        """Return the first reachable API port from the common list, or ``None``."""
        _, secret = self._controller_and_secret()
        for port in _COMMON_API_PORTS:
            url = f"http://127.0.0.1:{port}/version"
            req = urllib.request.Request(url)
            if secret:
                req.add_header("Authorization", f"Bearer {secret}")
            try:
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        return port
            except Exception:
                continue
        return None

    def get_api_info(self) -> dict[str, Any] | None:
        """Return API port, secret, reachability status and version."""
        port, secret = self._api_port_secret()
        if port is None:
            return None
        version_data = self._api_request("/version") or {}
        reachable = bool(version_data)
        return {
            "port": port,
            "secret": secret,
            "reachable": reachable,
            "version": version_data.get("version") or version_data.get("meta") or True,
        }

    def get_inbound(self) -> dict[str, Any]:
        """Return the mixed inbound port from the environment or config."""
        for p in self.env.get("listening_ports", []):
            if p.get("port") in (7890, 7891, 7892, 10808):
                return {
                    "port": p["port"],
                    "protocol": "mixed",
                    "host": p.get("host", "127.0.0.1"),
                }
        return {"port": None, "protocol": "mixed", "host": "127.0.0.1"}

    def _global_selector(self) -> str:
        """Return the name of the active selector, defaulting to GLOBAL."""
        data = self._api_request("/proxies/GLOBAL")
        if data and data.get("type") in _GROUP_TYPES:
            return data.get("now", "GLOBAL")
        return "GLOBAL"

    def get_active_profile(self) -> dict[str, Any] | None:
        """Return the currently selected proxy node."""
        global_data = self._api_request("/proxies/GLOBAL")
        if not global_data:
            return None
        selected = global_data.get("now")
        if not selected:
            return None
        detail = self._api_request(f"/proxies/{urllib.request.quote(selected)}")
        return {
            "id": selected,
            "remarks": selected,
            "address": None,
            "port": None,
            "type": detail.get("type") if detail else None,
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return all selectable proxy nodes reported by the API."""
        proxies = self._api_request("/proxies")
        if not isinstance(proxies, dict):
            return []
        results: list[dict[str, Any]] = []
        for name, info in proxies.get("proxies", proxies).items():
            if not isinstance(info, dict):
                continue
            if info.get("type") in _GROUP_TYPES:
                continue
            results.append(
                {
                    "id": name,
                    "remarks": name,
                    "address": None,
                    "port": None,
                    "type": info.get("type"),
                }
            )
        return results

    def can_api_switch(self) -> bool:
        """Return ``True`` when the External Controller API is reachable."""
        info = self.get_api_info()
        return bool(info and info.get("reachable"))

    def switch_profile(self, profile_id: str) -> bool:
        """Switch the GLOBAL selector (or active selector) to ``profile_id``.

        Args:
            profile_id: The name of the proxy node to select.

        Returns:
            ``True`` if the API returned HTTP 204.
        """
        selector = "GLOBAL"
        global_data = self._api_request("/proxies/GLOBAL")
        if global_data and global_data.get("type") in _GROUP_TYPES:
            selector = global_data.get("name", "GLOBAL")
        data = json.dumps({"name": profile_id}).encode("utf-8")
        port, secret = self._api_port_secret()
        if port is None:
            return False
        url = f"http://127.0.0.1:{port}/proxies/{urllib.request.quote(selector)}"
        req = urllib.request.Request(url, method="PUT", data=data)
        req.add_header("Content-Type", "application/json")
        if secret:
            req.add_header("Authorization", f"Bearer {secret}")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 204
        except Exception as exc:
            logger.debug("mihomo switch_profile failed: %s", exc)
            return False
