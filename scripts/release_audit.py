#!/usr/bin/env python3
"""Release artifact audit for netfix.

The workspace can contain private local cases or old proxy packages during
development.  Paid/downloadable artifacts cannot.  This script makes that
boundary explicit and machine-checkable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List


SENSITIVE_NAME_PATTERNS = [
    re.compile(r".*\.proxy-url$", re.IGNORECASE),
    re.compile(r".*shadowrocket.*", re.IGNORECASE),
    re.compile(r".*stash\.ya?ml$", re.IGNORECASE),
    re.compile(r".*proxy.*qr.*\.png$", re.IGNORECASE),
    re.compile(r".*v2rayn-package.*", re.IGNORECASE),
    re.compile(r".*proxy.*\.zip$", re.IGNORECASE),
]

SECRET_TEXT_PATTERNS = [
    re.compile(r"https?://[^/\s:@]+:[^/\s@]+@[^/\s]+", re.IGNORECASE),
    re.compile(r"socks5h?://[^/\s:@]+:[^/\s@]+@[^/\s]+", re.IGNORECASE),
    re.compile(r"\b(api[_-]?key|authorization|bearer|password|passwd|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}", re.IGNORECASE),
]

TEXT_SUFFIXES = {
    ".conf",
    ".json",
    ".md",
    ".plist",
    ".proxy-url",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    ".swiftpm",
    "node_modules",
    "__pycache__",
}


@dataclass
class Finding:
    severity: str
    kind: str
    path: str
    message: str


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.is_file():
            yield path


def _match_sensitive_name(rel: str) -> bool:
    return any(pattern.match(rel) for pattern in SENSITIVE_NAME_PATTERNS)


def _scan_text_file(path: Path, rel: str) -> List[Finding]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings: List[Finding] = []
    for pattern in SECRET_TEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            sample = match.group(0).lower()
            if "user:pass@" in sample or "proxy.example.com" in sample:
                continue
            findings.append(
                Finding(
                    severity="blocker",
                    kind="secret-like-text",
                    path=rel,
                    message="Secret-like proxy credential or token text found.",
                )
            )
            break
    return findings


def audit(root: Path, scope: str) -> List[Finding]:
    root = root.resolve()
    findings: List[Finding] = []
    for path in _iter_files(root):
        rel = str(path.relative_to(root))
        if _match_sensitive_name(rel):
            findings.append(
                Finding(
                    severity="blocker",
                    kind="sensitive-filename",
                    path=rel,
                    message="Proxy credential/config artifact must not be present in release scope.",
                )
            )
        # Bundle artifacts should be stricter. Workspace scans still look at
        # obvious text secrets, but filename blockers carry most of the signal.
        findings.extend(_scan_text_file(path, rel))

    if scope == "bundle":
        required = [
            "Contents/MacOS/Netfix",
            "Contents/Resources/netfix.py",
            "Contents/Resources/netfix",
            "Contents/Resources/rules",
            "Contents/Resources/gui/web/index.html",
            "Contents/Resources/PrivacyInfo.xcprivacy",
            "Contents/Resources/release-manifest.json",
        ]
        for item in required:
            if not (root / item).exists():
                findings.append(
                    Finding(
                        severity="blocker",
                        kind="missing-release-file",
                        path=item,
                        message="Required release bundle file is missing.",
                    )
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit netfix release/workspace artifacts.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Root path to audit.")
    parser.add_argument("--scope", choices=["workspace", "bundle"], default="workspace")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    parser.add_argument("--warn-only", action="store_true", help="Always exit 0.")
    args = parser.parse_args(argv)

    findings = audit(args.root, args.scope)
    result = {
        "ok": not findings,
        "scope": args.scope,
        "root": str(args.root),
        "findings": [asdict(item) for item in findings],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif findings:
        print(f"release audit failed: {len(findings)} finding(s)", file=sys.stderr)
        for item in findings:
            print(f"- [{item.severity}] {item.kind}: {item.path} - {item.message}", file=sys.stderr)
    else:
        print(f"release audit passed: {args.scope} {args.root}")

    if findings and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
