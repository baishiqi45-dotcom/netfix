"""netfix core adapters."""
from __future__ import annotations

from typing import Any

from netfix.cores.base import CoreBase
from netfix.cores.mihomo import MihomoCore
from netfix.cores.singbox import SingBoxCore
from netfix.cores.v2rayn import V2RayNCore
from netfix.cores.wireguard import WireGuardCore
from netfix.cores.xray import XrayCore

__all__ = [
    "CoreBase",
    "V2RayNCore",
    "MihomoCore",
    "SingBoxCore",
    "XrayCore",
    "WireGuardCore",
    "get_core",
]


def get_core(env: dict[str, Any] | None = None) -> CoreBase | None:
    """Pick the most appropriate core adapter for the detected environment.

    The selection follows the priority defined in the netfix design document:
    v2rayN first, then mihomo/Clash, sing-box, xray and finally WireGuard.

    Args:
        env: The environment dict from :func:`netfix.detect.detect_environment`.

    Returns:
        An initialized :class:`CoreBase` subclass instance, or ``None`` if no
        supported proxy/VPN client is detected.
    """
    env = env or {}
    running = env.get("running_proxies", {})

    candidates: list[tuple[str, type[CoreBase]]] = [
        ("v2rayn", V2RayNCore),
        ("mihomo", MihomoCore),
        ("clash", MihomoCore),
        ("singbox", SingBoxCore),
        ("xray", XrayCore),
        ("wireguard", WireGuardCore),
    ]
    for key, cls in candidates:
        if running.get(key):
            core = cls(env)
            if core.detect():
                return core

    # Fallback: infer the core from listening ports when no process matched.
    for port_info in env.get("listening_ports", []):
        command = (port_info.get("command") or "").lower()
        if "xray" in command:
            return XrayCore(env)
        if "sing-box" in command or "singbox" in command:
            return SingBoxCore(env)
        if any(k in command for k in ("mihomo", "clash")):
            return MihomoCore(env)
        if "wireguard" in command:
            return WireGuardCore(env)

    return None
