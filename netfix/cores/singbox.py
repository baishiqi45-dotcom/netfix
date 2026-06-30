"""sing-box standalone core adapter."""
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

_GROUP_TYPES = {"Selector", "URLTest", "Fallback", "LoadBalance"}


def _safe_json_load(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning an empty dict on any error."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.debug("Failed to load %s: %s", path, exc)
        return {}


class SingBoxCore(CoreBase):
    """Adapter for a standalone sing-box process.

    When ``experimental.clash_api`` is configured, the Clash-compatible
    External Controller API is used for queries and switching.  Otherwise the
    adapter only reports process and port information.
    """

    name = "sing-box"

    def detect(self) -> bool:
        """Return ``True`` if a sing-box process is running."""
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
                if "sing-box" in exe_str and "v2rayN" not in parts[1]:
                    return True
        output = run_command(["pgrep", "-f", "sing-box"])
        return output["ok"] and bool(output["stdout"].strip())

    def is_running(self) -> bool:
        """Return ``True`` if sing-box is running."""
        return self.detect()

    def _config_path(self) -> Path | None:
        """Try to discover the active config path from process arguments."""
        ps = run_command(["ps", "-axo", "pid,command"])
        if not ps["ok"]:
            return None
        for line in ps["stdout"].splitlines()[1:]:
            if "sing-box" not in line:
                continue
            match = re.search(r"(?:-c|--config)\s+(\S+)", line)
            if match:
                path = Path(match.group(1)).expanduser()
                if path.exists():
                    return path
        return None

    def _config(self) -> dict[str, Any]:
        """Load the sing-box configuration if it can be found."""
        path = self._config_path()
        if path:
            return _safe_json_load(path)
        candidates = [
            Path.home() / ".config/sing-box/config.json",
            Path("/usr/local/etc/sing-box/config.json"),
            Path("/etc/sing-box/config.json"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return _safe_json_load(candidate)
        return {}

    def get_inbound(self) -> dict[str, Any]:
        """Return the first mixed/socks/http inbound from the config."""
        config = self._config()
        inbounds = config.get("inbounds", [])
        for item in inbounds:
            if item.get("type") in ("mixed", "socks", "http"):
                return {
                    "port": item.get("listen_port"),
                    "protocol": item.get("type"),
                    "host": item.get("listen", "127.0.0.1"),
                }
        # Fallback to listening ports discovered by the environment detector.
        for p in self.env.get("listening_ports", [])[:3]:
            return {
                "port": p["port"],
                "protocol": "mixed",
                "host": p.get("host", "127.0.0.1"),
            }
        return {"port": None, "protocol": "mixed", "host": "127.0.0.1"}

    def _clash_api(self) -> dict[str, Any] | None:
        """Return clash_api settings from ``experimental.clash_api``."""
        config = self._config()
        experimental = config.get("experimental", {})
        clash_api = experimental.get("clash_api")
        if isinstance(clash_api, dict) and clash_api.get("external_controller"):
            return clash_api
        return None

    def _api_request(
        self, path: str, method: str = "GET", data: bytes | None = None
    ) -> Any:
        """Make a request to the sing-box clash_api endpoint."""
        clash_api = self._clash_api()
        if not clash_api:
            return None
        controller = clash_api["external_controller"]
        secret = clash_api.get("secret")
        try:
            port = int(controller.rsplit(":", 1)[1])
        except (ValueError, IndexError):
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
            logger.debug("sing-box API %s %s failed: %s", method, url, exc)
            return None

    def get_api_info(self) -> dict[str, Any] | None:
        """Return clash_api reachability information when configured."""
        clash_api = self._clash_api()
        if not clash_api:
            return None
        controller = clash_api["external_controller"]
        try:
            port = int(controller.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            return None
        version_data = self._api_request("/version") or {}
        return {
            "port": port,
            "secret": clash_api.get("secret"),
            "reachable": bool(version_data),
            "version": version_data.get("version") or version_data.get("singbox") or True,
        }

    def get_active_profile(self) -> dict[str, Any] | None:
        """Return the active proxy node when clash_api is available."""
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
        """Return selectable proxy nodes when clash_api is available."""
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
        """Return ``True`` when clash_api is configured and reachable."""
        info = self.get_api_info()
        return bool(info and info.get("reachable"))

    def switch_profile(self, profile_id: str) -> bool:
        """Switch the GLOBAL selector to ``profile_id`` via clash_api.

        Returns:
            ``True`` if the API returned HTTP 204.
        """
        global_data = self._api_request("/proxies/GLOBAL")
        selector = "GLOBAL"
        if global_data and global_data.get("type") in _GROUP_TYPES:
            selector = global_data.get("name", "GLOBAL")
        data = json.dumps({"name": profile_id}).encode("utf-8")
        clash_api = self._clash_api()
        if not clash_api:
            return False
        controller = clash_api["external_controller"]
        secret = clash_api.get("secret")
        try:
            port = int(controller.rsplit(":", 1)[1])
        except (ValueError, IndexError):
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
            logger.debug("sing-box switch_profile failed: %s", exc)
            return False
