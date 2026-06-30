"""v2rayN (xray + sing-box) core adapter for macOS."""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from netfix.constants import V2RAYN_CONFIG_TYPES
from netfix.cores.base import CoreBase
from netfix.utils import command_executable, run_command

logger = logging.getLogger(__name__)

_V2RAYN_APP = Path("/Applications/v2rayN.app/Contents/MacOS/v2rayN")
_V2RAYN_SUPPORT = Path.home() / "Library/Application Support/v2rayN"
_V2RAYN_GUI_CONFIGS = _V2RAYN_SUPPORT / "guiConfigs"
_V2RAYN_CONFIG = _V2RAYN_GUI_CONFIGS / "guiNConfig.json"
_V2RAYN_DB = _V2RAYN_GUI_CONFIGS / "guiNDB.db"


def _safe_json_load(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning an empty dict on any error."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.debug("Failed to load %s: %s", path, exc)
        return {}


class V2RayNCore(CoreBase):
    """Adapter for the v2rayN GUI client on macOS.

    v2rayN itself does not expose an external API, so node switching is done by
    rewriting ``guiNConfig.json`` after making a backup.
    """

    name = "v2rayN"

    def detect(self) -> bool:
        """Return ``True`` if a v2rayN process is running."""
        if _V2RAYN_APP.exists():
            output = run_command(["pgrep", "-f", str(_V2RAYN_APP)])
            if output["ok"] and output["stdout"].strip():
                return True
        # Fallback to a broad command match.
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
                if "v2rayn" in exe_str or "v2rayn.app" in exe_str:
                    return True
        return False

    def is_running(self) -> bool:
        """Return ``True`` if v2rayN is running."""
        return self.detect()

    def _config(self) -> dict[str, Any]:
        """Return the parsed ``guiNConfig.json`` content."""
        return _safe_json_load(_V2RAYN_CONFIG)

    def get_inbound(self) -> dict[str, Any]:
        """Return the local mixed inbound configuration.

        Defaults to ``127.0.0.1:10808`` when the config cannot be read.
        """
        config = self._config()
        inbounds = config.get("Inbound", [])
        if isinstance(inbounds, dict):
            inbounds = [inbounds]
        for item in inbounds:
            if not isinstance(item, dict):
                continue
            protocol = item.get("protocol", "mixed")
            port = item.get("port", 10808)
            host = item.get("listen", "127.0.0.1")
            if protocol == "mixed":
                return {"port": port, "protocol": protocol, "host": host}
        if inbounds:
            first = inbounds[0]
            return {
                "port": first.get("port", 10808),
                "protocol": first.get("protocol", "mixed"),
                "host": first.get("listen", "127.0.0.1"),
            }
        return {"port": 10808, "protocol": "mixed", "host": "127.0.0.1"}

    def _read_profiles(self) -> list[dict[str, Any]]:
        """Read all profiles from the ``ProfileItem`` SQLite table."""
        if not _V2RAYN_DB.exists():
            return []
        try:
            conn = sqlite3.connect(f"file:{_V2RAYN_DB}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT IndexId, ConfigType, Address, Port, Remarks, CoreType "
                "FROM ProfileItem"
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "id": str(row["IndexId"]),
                    "type": V2RAYN_CONFIG_TYPES.get(row["ConfigType"], "unknown"),
                    "address": row["Address"],
                    "port": row["Port"],
                    "remarks": row["Remarks"],
                    "core_type": row["CoreType"],
                }
                for row in rows
            ]
        except Exception as exc:
            logger.debug("Failed to read v2rayN profile database: %s", exc)
            return []

    def get_active_profile(self) -> dict[str, Any] | None:
        """Return the currently selected v2rayN profile."""
        config = self._config()
        index_id = config.get("IndexId")
        if index_id is None:
            return None
        for profile in self._read_profiles():
            if profile["id"] == str(index_id):
                return {
                    "id": profile["id"],
                    "remarks": profile["remarks"],
                    "address": profile["address"],
                    "port": profile["port"],
                    "type": profile["type"],
                }
        return None

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return all v2rayN profiles from the local database."""
        return [
            {
                "id": p["id"],
                "remarks": p["remarks"],
                "address": p["address"],
                "port": p["port"],
                "type": p["type"],
            }
            for p in self._read_profiles()
        ]

    def tun_enabled(self) -> bool:
        """Return ``True`` if v2rayN TUN mode is enabled in the config."""
        config = self._config()
        tun = config.get("TunModeItem", {})
        if isinstance(tun, dict):
            return bool(tun.get("EnableTun", tun.get("Enable", False)))
        return False

    def can_api_switch(self) -> bool:
        """v2rayN does not expose an external controller API."""
        return False

    def switch_profile(self, profile_id: str) -> bool:
        """Rewrite ``guiNConfig.json`` to select ``profile_id``.

        A timestamped backup is created next to the original file.  The GUI
        must be restarted by the user for the change to take effect.

        Args:
            profile_id: The ``IndexId`` of the target profile.

        Returns:
            ``True`` if the file was updated successfully.
        """
        if not _V2RAYN_CONFIG.exists():
            return False
        try:
            config = self._config()
            config["IndexId"] = profile_id
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            backup = _V2RAYN_CONFIG.with_suffix(f".json.bak-{timestamp}")
            shutil.copy2(_V2RAYN_CONFIG, backup)
            with _V2RAYN_CONFIG.open("w", encoding="utf-8") as fh:
                json.dump(config, fh, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            logger.debug("Failed to switch v2rayN profile: %s", exc)
            return False

    def get_api_info(self) -> dict[str, Any] | None:
        """v2rayN has no external API; returns ``None``."""
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary including TUN state."""
        base = super().to_dict()
        base["tun_enabled"] = self.tun_enabled()
        return base
