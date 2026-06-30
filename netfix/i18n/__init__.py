"""Simple i18n helper for netfix.

Only Chinese (zh_CN) is shipped for now; the helper falls back to the key name
when a translation is missing so the UI never crashes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent


class I18n:
    """Minimal gettext-like helper."""

    def __init__(self, locale: str = "zh_CN") -> None:
        self.locale = locale
        self._catalog: Mapping[str, str] = {}
        self._load(locale)

    def _load(self, locale: str) -> None:
        path = _PACKAGE_DIR / f"{locale}.json"
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    self._catalog = json.load(fh)
            except Exception as exc:
                logger.warning("Failed to load i18n catalog %s: %s", path, exc)
        else:
            logger.debug("i18n catalog not found: %s", path)

    def get(self, key: str, default: Optional[str] = None) -> str:
        return self._catalog.get(key, default if default is not None else key)

    def fmt(self, key: str, **kwargs: Any) -> str:
        try:
            return self.get(key).format(**kwargs)
        except Exception as exc:
            logger.debug("i18n fmt failed for %s: %s", key, exc)
            return self.get(key)


_DEFAULT = I18n()


def t(key: str, default: Optional[str] = None) -> str:
    return _DEFAULT.get(key, default)


def fmt(key: str, **kwargs: Any) -> str:
    return _DEFAULT.fmt(key, **kwargs)
