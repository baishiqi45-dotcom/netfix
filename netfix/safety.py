"""Safety classification, dangerous-pattern filtering and sudo audit.

All commands are classified into one of four tiers.  Tier 0 is read-only;
Tier 1 is safe to run automatically; Tier 2 requires explicit user
confirmation and a backup; Tier 3 is manual-only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List

from netfix.constants import JOURNAL_DIR
from netfix.utils import secure_append_text


class FixTier(Enum):
    READONLY = 0
    AUTO_SAFE = 1
    CONFIRM = 2
    MANUAL = 3


DANGEROUS_PATTERNS: List[str] = [
    r"\brm\s+-rf\s+/(?:\s|$)",
    r"\bmkfs\b",
    r"\bdd\s+if=/dev/zero\b",
    r">\s*/dev/sda\b",
    r"curl\s+.*\|\s*sh",
    r"curl\s+.*\|\s*bash",
    r"\bfork\s*bomb\b",
    r":\(\)\s*\{\s*:\|:\s*&&\s*\}",
    r"\bchmod\s+-R\s+777\s+/(?:\s|$)",
    r"\brm\s+-rf\s+~\b",
    r"\bsudo\s+rm\s+-rf\b",
    r"\bdd\s+of=/dev/[sh]d[a-z]\b",
    r">\s*/dev/null\s+2>&1\s*;\s*:\(\)\{\s*:",
    r"\bwget\s+.*\|\s*sh",
    r"\bwget\s+.*\|\s*bash",
]

_READONLY_KEYWORDS = (
    "ping", "dig", "scutil", "lsof", "netstat", "ifconfig",
    "route", "dscacheutil", "ps ", "pgrep", "pkill -0",
)
_SUDO_KEYWORDS = ("sudo", "networksetup", "pfctl", "socketfilterfw", "killall")


def is_dangerous(command: str) -> bool:
    """Return True if *command* matches a known dangerous pattern."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def classify_command(command: str) -> FixTier:
    """Return the default safety tier for *command* based on its content.

    The result is a hint; the rule file may override it with an explicit
    ``tier`` value.
    """
    if is_dangerous(command):
        return FixTier.MANUAL

    lower = command.lower()
    # Privileged commands (even read-only ones like `sudo lsof`) need confirmation.
    # Use \b word boundary to avoid false positives like "sudoMyScript" or "notnetworksetup".
    sudo_pattern = re.compile(r"\b(?:" + "|".join(re.escape(kw) for kw in _SUDO_KEYWORDS) + r")\b")
    if sudo_pattern.search(lower):
        return FixTier.CONFIRM

    readonly_pattern = re.compile(r"(?:^|\s)(?:" + "|".join(re.escape(kw) for kw in _READONLY_KEYWORDS) + r")\b")
    if readonly_pattern.search(lower):
        return FixTier.READONLY

    return FixTier.AUTO_SAFE


def audit_sudo(command: str, approved: bool) -> None:
    """Append a sudo/elevated command record to ``~/.netfix/audit.log``.

    Passwords or tokens are never written.
    """
    audit_file = JOURNAL_DIR / "audit.log"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "approved": approved,
    }
    secure_append_text(audit_file, json.dumps(entry, ensure_ascii=False) + "\n")


def tier_name(tier: FixTier) -> str:
    return tier.name.lower()
