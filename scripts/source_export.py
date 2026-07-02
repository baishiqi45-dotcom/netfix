#!/usr/bin/env python3
"""Create a clean source export without local private artifacts."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.path_sanitizer import build_replacements, sanitize_json  # noqa: E402
from scripts.release_audit import audit, _match_sensitive_name  # noqa: E402


DEFAULT_OUT = ROOT / "open-source-export"

EXCLUDE_DIR_NAMES = {
    ".git",
    ".harness",
    ".netfix",
    ".opencode",
    ".playwright-cli",
    ".pytest_cache",
    ".swiftpm",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "open-source-export",
    "output",
    "release-export",
}

EXCLUDE_FILE_PATTERNS = {
    "*.pyc",
    "*.pyo",
    "*.spec",
    ".DS_Store",
    "Netfix-*.dmg",
    "Netfix-*.zip",
}

PUBLIC_DOC_PATHS = {
    "docs/EULA_DRAFT.md",
    "docs/PRIVACY_POLICY_DRAFT.md",
    "docs/PRODUCTIZATION_PLAN_2026_06_24.md",
}

PUBLIC_DOC_PREFIXES = (
    "docs/github/",
)

PUBLIC_CASE_PATHS = {
    "cases/.gitkeep",
    "cases/TEMPLATE.md",
}

INTERNAL_TOP_LEVEL_FILES = {
    "DESIGN.md",
    "HANDOFF.md",
    "PRODUCT_DESIGN.md",
    "PRODUCT_STRATEGY.md",
    "PRODUCT_STRATEGY_V2.md",
    "document.md",
    "final.md",
}


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path, *, excluded_roots: Iterable[Path]) -> Iterable[Path]:
    excluded_roots = [path.resolve() for path in excluded_roots]
    for path in sorted(root.rglob("*")):
        resolved = path.resolve()
        if any(_is_relative_to(resolved, excluded) for excluded in excluded_roots):
            continue
        if path.is_dir():
            continue
        yield path


def _exclude_reason(path: Path, root: Path) -> Optional[str]:
    rel = path.relative_to(root).as_posix()
    parts = path.relative_to(root).parts
    if rel in INTERNAL_TOP_LEVEL_FILES:
        return "internal_docs"
    if rel.startswith("docs/") and rel not in PUBLIC_DOC_PATHS and not any(
        rel.startswith(prefix) for prefix in PUBLIC_DOC_PREFIXES
    ):
        return "internal_docs"
    if rel.startswith("cases/") and rel not in PUBLIC_CASE_PATHS:
        return "local_cases"
    if any(fnmatch.fnmatch(path.name, pattern) for pattern in {"Netfix-*.dmg", "Netfix-*.zip"}):
        return "generated_release_artifact"
    if any(part in EXCLUDE_DIR_NAMES or part == ".build" for part in parts):
        return "build_or_runtime_directory"
    if path.is_symlink():
        return "symlink"
    if _match_sensitive_name(rel):
        return "sensitive_name"
    if any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDE_FILE_PATTERNS):
        return "tooling_artifact"
    return None


def _should_exclude(path: Path, root: Path) -> bool:
    return _exclude_reason(path, root) is not None


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_checksums(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            lines.append(f"{_sha256(path)}  {_relative(root, path)}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_source_export(
    *,
    root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT,
    version: str = "0.2.0",
    make_zip: bool = False,
) -> Dict[str, Any]:
    root = root.resolve()
    out_dir = out_dir.resolve()
    export_root = out_dir / f"Netfix-{version}-source"
    zip_path = out_dir / f"Netfix-{version}-source.zip"

    if export_root.exists():
        shutil.rmtree(export_root)
    export_root.mkdir(parents=True)
    if zip_path.exists():
        zip_path.unlink()

    copied: list[str] = []
    excluded_count = 0
    excluded_counts_by_reason: Dict[str, int] = {}
    for source in _iter_files(root, excluded_roots=[out_dir, export_root]):
        rel = _relative(root, source)
        exclude_reason = _exclude_reason(source, root)
        if exclude_reason is not None:
            excluded_count += 1
            excluded_counts_by_reason[exclude_reason] = excluded_counts_by_reason.get(exclude_reason, 0) + 1
            continue
        target = export_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(rel)

    audit_findings = audit(export_root, "workspace")
    replacements = build_replacements([
        (root, "<source-workspace>"),
        (out_dir, "<source-export-output>"),
        (export_root, "<source-export-root>"),
    ])
    manifest = {
        "schema_version": "netfix_source_export.v1",
        "name": "Netfix",
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact_scope": "open-source-worktree-snapshot",
        "source_root": "<source-workspace>",
        "source_workspace_included_private_artifacts": False,
        "audit_passed": not audit_findings,
        "file_count": len(copied),
        "excluded_count": excluded_count,
        "excluded_counts_by_reason": dict(sorted(excluded_counts_by_reason.items())),
        "files": copied,
        "audit_findings": [
            {
                "severity": item.severity,
                "kind": item.kind,
                "path": item.path,
                "message": item.message,
                "next_steps": item.next_steps,
            }
            for item in audit_findings
        ],
        "notes": [
            "This source export is a sanitized snapshot, not a mutation of the developer workspace.",
            "Local proxy credential packages, generated DMG/ZIP artifacts, build outputs, and runtime state are excluded.",
            "Publish only if audit_passed is true and the owner has approved source publication.",
        ],
    }
    manifest = sanitize_json(manifest, replacements)
    manifest_path = export_root / "SOURCE-EXPORT-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _write_checksums(export_root)

    if make_zip:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(export_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(out_dir))

    return {
        "ok": not audit_findings,
        "export_root": str(export_root),
        "zip": str(zip_path) if make_zip else None,
        "file_count": len(copied),
        "excluded_count": excluded_count,
        "audit_findings": manifest["audit_findings"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create a clean Netfix source export.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--zip", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = create_source_export(
            root=args.root,
            out_dir=args.out_dir,
            version=args.version,
            make_zip=args.zip,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"source export failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Created source export: {result['export_root']}")
        if result.get("zip"):
            print(f"Zip: {result['zip']}")
        if not result["ok"]:
            print(f"Audit findings: {len(result.get('audit_findings', []))}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
