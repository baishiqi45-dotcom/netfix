"""Lightweight knowledge-base query over rules and runbook."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .constants import REPO_ROOT, RULES_DIR


def query(keyword: str) -> List[Dict[str, Any]]:
    """Search symptoms, fixes and final.md headings for ``keyword``."""
    keyword = keyword.lower()
    results: List[Dict[str, Any]] = []

    try:
        with open(RULES_DIR / "symptoms.json", "r", encoding="utf-8") as f:
            rules = json.load(f)
    except Exception:
        rules = {"symptoms": [], "fixes": {}}

    for symptom in rules.get("symptoms", []):
        text = " ".join(
            [symptom.get("id", "")] + symptom.get("keywords", [])
        ).lower()
        if keyword in text:
            results.append({"type": "symptom", **symptom})

    for fix_id, fix in rules.get("fixes", {}).items():
        text = f"{fix_id} {fix.get('description', '')}".lower()
        if keyword in text:
            results.append({"type": "fix", "id": fix_id, **fix})

    final = REPO_ROOT / "final.md"
    if final.exists():
        for lineno, line in enumerate(final.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("#") and keyword in line.lower():
                results.append(
                    {"type": "runbook", "line": lineno, "heading": line.strip()}
                )

    return results
