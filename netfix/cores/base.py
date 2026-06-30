"""Abstract base class for proxy/VPN core adapters."""
from __future__ import annotations

from typing import Any


class CoreBase:
    """Common interface implemented by every netfix core adapter.

    Subclasses must set :attr:`name` and implement the detection/query methods
    relevant to the client they wrap.  Methods that are not supported should
    return ``False``, ``None`` or an empty container rather than raising.
    """

    name: str = ""

    def __init__(self, env: dict[str, Any] | None = None) -> None:
        """Initialize the adapter with an optional environment snapshot."""
        self.env = env or {}

    def detect(self) -> bool:
        """Return ``True`` if this core/client is present on the system."""
        raise NotImplementedError

    def is_running(self) -> bool:
        """Return ``True`` if the core process is currently running."""
        return self.detect()

    def get_inbound(self) -> dict[str, Any]:
        """Return the local inbound configuration.

        Typical keys: ``port``, ``protocol`` and ``host``.
        """
        raise NotImplementedError

    def get_active_profile(self) -> dict[str, Any] | None:
        """Return the currently active outbound profile, if discoverable."""
        raise NotImplementedError

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return the list of known outbound profiles."""
        raise NotImplementedError

    def can_api_switch(self) -> bool:
        """Return ``True`` if the core supports switching profiles via an API."""
        return False

    def switch_profile(self, profile_id: str) -> bool:
        """Switch to ``profile_id`` when supported.

        Returns:
            ``True`` on success, ``False`` if unsupported or on failure.
        """
        return False

    def get_api_info(self) -> dict[str, Any] | None:
        """Return API reachability information when available.

        Typical keys: ``port``, ``secret``, ``reachable`` and ``version``.
        Sensitive values are masked before exposure in :meth:`to_dict`.
        """
        return None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary of the core state.

        Subclasses may override this to add client-specific fields, but they
        must never include passwords, UUIDs or private keys.
        """
        api_info = self.get_api_info()
        if api_info and api_info.get("secret"):
            api_info = {**api_info, "secret": "***"}
        return {
            "name": self.name,
            "running": self.is_running(),
            "inbound": self.get_inbound(),
            "active_profile": self.get_active_profile(),
            "profiles_count": len(self.list_profiles()),
            "can_api_switch": self.can_api_switch(),
            "api_info": api_info,
        }
