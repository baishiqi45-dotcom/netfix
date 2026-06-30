#!/usr/bin/env python3
"""netfix CLI wrapper.

Usage:
    python3 netfix.py codex [--json]
    python3 netfix.py triage [--json]
    python3 netfix.py fix --issue <id> [--dry-run]
    python3 netfix.py report [--json]
    python3 netfix.py rollback
"""
import sys
import encodings.idna  # noqa: F401 - required by bundled HTTPS hostname handling.
from pathlib import Path

# Ensure repo-local netfix package is importable even when run from anywhere
REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from netfix.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
