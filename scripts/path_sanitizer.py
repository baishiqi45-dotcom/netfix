"""Helpers for removing build-machine paths from exported metadata."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Tuple


Replacement = Tuple[str, str]

SENSITIVE_PUBLIC_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"iphone-v2rayn-package-\d{4}-\d{2}-\d{2}(?:\.zip)?", re.IGNORECASE),
        "<private-proxy-package>",
    ),
    (
        re.compile(r"cc-http(?:[-_.][A-Za-z0-9_-]+)*(?:\.[A-Za-z0-9_-]+)?", re.IGNORECASE),
        "<private-proxy-config>",
    ),
    (
        re.compile(r"(?:AIKB|CLAUDECODE|NEXT_DIALOGUE|PRODUCT_MACRO)[A-Z0-9_]*_\d{4}_\d{2}(?:_\d{2})?", re.IGNORECASE),
        "<internal-audit-doc>",
    ),
)


def path_forms(path: Path | str) -> list[str]:
    """Return common textual forms for a path, including macOS /private variants."""
    raw = str(path)
    forms = {raw}
    try:
        forms.add(str(Path(path).resolve()))
    except Exception:
        pass
    for item in list(forms):
        if item.startswith("/private/var/"):
            forms.add("/var/" + item[len("/private/var/"):])
        elif item.startswith("/var/"):
            forms.add("/private/var/" + item[len("/var/"):])
        elif item.startswith("/private/tmp/"):
            forms.add("/tmp/" + item[len("/private/tmp/"):])
        elif item.startswith("/tmp/") and not item.startswith("/tmp/.X"):
            # /tmp is a symlink to /private/tmp on macOS; keep the public form
            # alongside the resolved form so source-export manifests do not
            # leak build-machine paths to readers.
            forms.add("/private/tmp/" + item[len("/tmp/"):])
    return sorted(forms, key=len, reverse=True)


def build_replacements(items: Iterable[tuple[Path | str | None, str]]) -> list[Replacement]:
    replacements: list[Replacement] = []
    seen: set[str] = set()
    for path, replacement in items:
        if path is None:
            continue
        for form in path_forms(path):
            if form and form not in seen:
                replacements.append((form, replacement))
                seen.add(form)
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    return replacements


def sanitize_text(value: str, replacements: Iterable[Replacement]) -> str:
    result = value
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def sanitize_public_names_text(value: str) -> str:
    """Replace known private local artifact names in public metadata."""
    result = value
    for pattern, replacement in SENSITIVE_PUBLIC_NAME_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_public_names(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_public_names_text(value)
    if isinstance(value, list):
        return [sanitize_public_names(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_public_names(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_public_names(item) for key, item in value.items()}
    return value


def sanitize_json(value: Any, replacements: Iterable[Replacement]) -> Any:
    replacements = list(replacements)
    if isinstance(value, str):
        return sanitize_public_names_text(sanitize_text(value, replacements))
    if isinstance(value, list):
        return [sanitize_json(item, replacements) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json(item, replacements) for key, item in value.items()}
    return value
