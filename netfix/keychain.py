"""Small macOS Keychain wrapper for netfix secrets."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import re
import sys
from typing import Any, Dict, Optional


LLM_SERVICE = "netfix.llm"
PROXY_SERVICE = "netfix.proxy"


def is_available() -> bool:
    """Return True when the macOS security CLI is available."""
    return platform.system() == "Darwin" and shutil.which("security") is not None


def _trusted_app_path() -> str:
    candidate = (os.environ.get("NETFIX_KEYCHAIN_TRUSTED_APP") or sys.executable or "").strip()
    if candidate and os.path.exists(candidate):
        return candidate
    return ""


def set_secret(service: str, account: str, secret: str) -> Dict[str, Any]:
    """Store or update a secret in Keychain."""
    if not secret:
        return {"ok": False, "error": "empty secret"}
    if not is_available():
        return {"ok": False, "error": "macOS Keychain is unavailable"}
    # Put -w last without a value so security prompts on stdin. Passing the
    # secret as the -w argument exposes it in process lists.
    cmd = [
        "security",
        "add-generic-password",
        "-a",
        account,
        "-s",
        service,
        "-U",
    ]
    trusted_app = _trusted_app_path()
    if trusted_app:
        cmd.extend(["-T", trusted_app])
    cmd.append("-w")
    proc = subprocess.run(cmd, input=f"{secret}\n", capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    return {"ok": True, "service": service, "account": account}


def _env_key_for_account(account: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", account).strip("_").upper() or "DEFAULT"
    return f"NETFIX_LLM_API_KEY_{suffix}"


def get_secret(service: str, account: str, *, allow_generic_llm_override: bool = False) -> Optional[str]:
    """Read a secret from Keychain.

    Provider-scoped LLM environment variables are accepted as temporary
    overrides so tests and one-off CLI sessions can avoid writing a key to disk.
    The legacy generic ``NETFIX_LLM_API_KEY`` override is opt-in so fallback
    providers do not accidentally receive the active provider's token.
    """
    if service == LLM_SERVICE:
        override = os.environ.get(_env_key_for_account(account))
        if override:
            return override
        override = os.environ.get("NETFIX_LLM_API_KEY") if allow_generic_llm_override else None
        if override:
            return override
    if not is_available():
        return None
    cmd = ["security", "find-generic-password", "-a", account, "-s", service, "-w"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def has_secret(service: str, account: str, *, allow_generic_llm_override: bool = False) -> bool:
    """Return whether a secret exists without reading the secret value."""
    if service == LLM_SERVICE:
        if os.environ.get(_env_key_for_account(account)):
            return True
        if allow_generic_llm_override and os.environ.get("NETFIX_LLM_API_KEY"):
            return True
        return bool(get_secret(service, account, allow_generic_llm_override=allow_generic_llm_override))
    if not is_available():
        return False
    cmd = ["security", "find-generic-password", "-a", account, "-s", service]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return proc.returncode == 0


def delete_secret(service: str, account: str, missing_ok: bool = False) -> Dict[str, Any]:
    """Delete a Keychain item if present."""
    if not is_available():
        return {"ok": False, "error": "macOS Keychain is unavailable"}
    cmd = ["security", "delete-generic-password", "-a", account, "-s", service]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        if missing_ok and ("could not be found" in detail.lower() or "not found" in detail.lower()):
            return {"ok": True, "service": service, "account": account, "missing": True}
        return {"ok": False, "error": detail}
    return {"ok": True, "service": service, "account": account}


def _account_from_ref(ref: str) -> Optional[str]:
    prefix = "keychain://"
    if not ref.startswith(prefix):
        return None
    path = ref[len(prefix):]
    parts = path.split("/", 1)
    if len(parts) != 2:
        return None
    return parts[1] or None


def delete_known_netfix_secrets(settings_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Delete known netfix LLM/proxy Keychain items from a settings snapshot."""
    targets = set()
    llm = settings_snapshot.get("llm", {}) if isinstance(settings_snapshot, dict) else {}
    if isinstance(llm, dict):
        for key in ("api_key_account", "provider"):
            value = str(llm.get(key) or "")
            if value:
                targets.add((LLM_SERVICE, value))
    for provider_id in ("deepseek", "moonshot_kimi", "minimax", "qwen", "custom_openai_compatible", "openai"):
        targets.add((LLM_SERVICE, provider_id))

    profiles = settings_snapshot.get("proxy_profiles", []) if isinstance(settings_snapshot, dict) else []
    if isinstance(profiles, list):
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            account = _account_from_ref(str(profile.get("credential_ref") or "")) or str(profile.get("id") or "")
            if account:
                targets.add((PROXY_SERVICE, account))

    deleted = []
    missing = []
    errors = {}
    for service, account in sorted(targets):
        result = delete_secret(service, account, missing_ok=True)
        if result.get("ok") and result.get("missing"):
            missing.append({"service": service, "account": account})
        elif result.get("ok"):
            deleted.append({"service": service, "account": account})
        else:
            errors[f"{service}/{account}"] = result.get("error", "delete failed")
    return {"ok": not errors, "deleted": deleted, "missing": missing, "errors": errors}
