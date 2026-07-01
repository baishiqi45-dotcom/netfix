"""Import DeepSeek sidecar credentials into Netfix Keychain."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from netfix import keychain, settings
from netfix.llm_provider import get_provider


CONFIRMATION = "IMPORT_DEEPSEEK_SIDECAR_KEY"
KEY_NAMES = ("DS_API_KEY", "DEEPSEEK_API_KEY")
MODEL_NAMES = ("DS_DEFAULT_MODEL", "DS_MODEL", "DS_MODEL_PREFERENCE")


def default_env_paths() -> list[Path]:
    """Return known local DeepSeek sidecar env locations."""
    paths: list[Path] = []
    explicit = os.environ.get("NETFIX_DS_SIDECAR_ENV") or os.environ.get("DS_SIDECAR_ENV")
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.append(Path.home() / "Desktop/mess/.env")
    deduped: list[Path] = []
    seen = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            deduped.append(path)
            seen.add(key)
    return deduped


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse simple KEY=value .env files without expanding shell syntax."""
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _strip_env_value(value)
    return values


def _first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def _sidecar_model(values: Dict[str, str]) -> str:
    provider = get_provider("deepseek") or {}
    fallback = str(provider.get("model") or "deepseek-v4-flash")
    for key in MODEL_NAMES:
        raw = values.get(key, "")
        if not raw:
            continue
        candidate = raw.split(",", 1)[0].strip()
        if candidate and candidate != "auto":
            return candidate
    return fallback


def import_sidecar_key(
    *,
    env_path: Optional[Path] = None,
    account: str = "deepseek",
    enable_llm: bool = True,
) -> Dict[str, Any]:
    """Copy a local DeepSeek sidecar API key into Netfix Keychain.

    The secret is never returned. Callers only receive source metadata and
    resulting readiness state.
    """
    source = env_path.expanduser() if env_path is not None else _first_existing(default_env_paths())
    if source is None:
        return {
            "ok": False,
            "reason_code": "sidecar_env_missing",
            "error": "DeepSeek sidecar .env file was not found.",
            "checked_paths": [str(path) for path in default_env_paths()],
        }
    values = parse_env_file(source)
    key_name = ""
    secret = ""
    for candidate in KEY_NAMES:
        if values.get(candidate):
            key_name = candidate
            secret = values[candidate]
            break
    if not secret:
        return {
            "ok": False,
            "reason_code": "sidecar_key_missing",
            "error": "DeepSeek sidecar .env does not contain DS_API_KEY or DEEPSEEK_API_KEY.",
            "env_path": str(source),
        }
    stored = keychain.set_secret(keychain.LLM_SERVICE, account, secret)
    if not stored.get("ok"):
        return {
            "ok": False,
            "reason_code": "keychain_write_failed",
            "error": stored.get("error", "failed to store API key"),
            "env_path": str(source),
            "key_name": key_name,
            "api_key_account": account,
        }

    provider = get_provider("deepseek") or {}
    saved = settings.update_llm_settings({
        "enabled": bool(enable_llm),
        "provider": "deepseek",
        "api_key_account": account,
        "api_key_set": True,
        "base_url": str(provider.get("base_url") or "https://api.deepseek.com"),
        "model": _sidecar_model(values),
    })
    return {
        "ok": True,
        "schema_version": "netfix_deepseek_sidecar_import.v1",
        "provider": "deepseek",
        "api_key_account": account,
        "key_name": key_name,
        "env_path": str(source),
        "model": saved.get("model"),
        "llm_enabled": bool(saved.get("enabled")),
        "api_key_set": bool(saved.get("api_key_set")),
        "settings": saved,
    }
