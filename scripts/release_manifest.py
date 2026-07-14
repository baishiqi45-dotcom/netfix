#!/usr/bin/env python3
"""Create and verify the provenance manifest embedded in Netfix.app."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "netfix_release_manifest.v1"
BACKEND_RELATIVE_PATH = Path("Contents/MacOS/netfix-backend")
APP_EXECUTABLE_RELATIVE_PATH = Path("Contents/MacOS/Netfix")
SOURCE_INPUTS = (
    "pyproject.toml",
    "netfix.py",
    "netfix",
    "rules",
    "bin",
    "gui/web",
    "gui/macos/Package.swift",
    "gui/macos/Sources",
    "gui/macos/PrivacyInfo.xcprivacy",
    "gui/macos/build_app.sh",
    "scripts/build_backend_binary.sh",
    "scripts/release_manifest.py",
)
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")


class ManifestError(RuntimeError):
    """The candidate cannot produce or satisfy its release manifest."""


def _read_project_table_with_stdlib(pyproject_path: Path) -> Optional[Dict[str, Any]]:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return None
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project")
    return project if isinstance(project, dict) else None


def _read_project_table_fallback(pyproject_path: Path) -> Dict[str, Any]:
    project: Dict[str, Any] = {}
    in_project = False
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if not in_project:
            continue
        match = re.fullmatch(r'version\s*=\s*"([A-Za-z0-9][A-Za-z0-9._+\-]*)"\s*', line)
        if match:
            project["version"] = match.group(1)
            break
    return project


def project_version(repo_root: Path) -> str:
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        raise ManifestError(f"missing pyproject.toml: {pyproject_path}")
    project = _read_project_table_with_stdlib(pyproject_path)
    if project is None:
        project = _read_project_table_fallback(pyproject_path)
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ManifestError("pyproject.toml [project].version is missing or invalid")
    return version.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_ignored_source(path: Path) -> bool:
    return any(part in IGNORED_NAMES for part in path.parts) or path.suffix in IGNORED_SUFFIXES


def _source_files(repo_root: Path) -> List[Path]:
    files: List[Path] = []
    seen = set()
    for relative in SOURCE_INPUTS:
        source = repo_root / relative
        candidates: Iterable[Path]
        if source.is_file() or source.is_symlink():
            candidates = (source,)
        elif source.is_dir():
            candidates = source.rglob("*")
        else:
            raise ManifestError(f"missing release source input: {relative}")
        for candidate in candidates:
            if _is_ignored_source(candidate.relative_to(repo_root)):
                continue
            if not candidate.is_file() and not candidate.is_symlink():
                continue
            relative_path = candidate.relative_to(repo_root)
            if relative_path in seen:
                continue
            seen.add(relative_path)
            files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(repo_root).as_posix())


def source_fingerprint(repo_root: Path) -> str:
    digest = hashlib.sha256(b"netfix-release-source.v1\0")
    files = _source_files(repo_root)
    if not files:
        raise ManifestError("release source fingerprint has no inputs")
    for path in files:
        relative = path.relative_to(repo_root).as_posix().encode("utf-8")
        executable = b"x" if os.access(path, os.X_OK) else b"-"
        digest.update(relative)
        digest.update(b"\0")
        digest.update(executable)
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8"))
        else:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise ManifestError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def git_provenance(repo_root: Path) -> Tuple[str, bool]:
    git_sha = _git(repo_root, "rev-parse", "--verify", "HEAD")
    if not GIT_SHA_RE.fullmatch(git_sha):
        raise ManifestError(f"invalid git SHA: {git_sha!r}")
    dirty = bool(_git(repo_root, "status", "--porcelain", "--untracked-files=all"))
    return git_sha, dirty


def _built_at() -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        try:
            instant = datetime.fromtimestamp(int(source_date_epoch), tz=timezone.utc)
        except (ValueError, OverflowError) as exc:
            raise ManifestError("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    else:
        instant = datetime.now(timezone.utc)
    return instant.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_executable(path: Path, label: str) -> None:
    if not path.is_file():
        raise ManifestError(f"missing {label}: {path}")
    if not os.access(path, os.X_OK):
        raise ManifestError(f"{label} is not executable: {path}")


def create_manifest(
    repo_root: Path,
    app_bundle: Path,
    output: Path,
    *,
    release_candidate: bool,
    workspace_audit_findings: int,
) -> Dict[str, Any]:
    repo_root = repo_root.resolve()
    app_bundle = app_bundle.resolve()
    backend = app_bundle / BACKEND_RELATIVE_PATH
    app_executable = app_bundle / APP_EXECUTABLE_RELATIVE_PATH
    _require_executable(backend, "bundled backend")
    _require_executable(app_executable, "app executable")

    version = project_version(repo_root)
    git_sha, dirty = git_provenance(repo_root)
    fingerprint = source_fingerprint(repo_root)
    build_id_parts = ["netfix", version, git_sha[:12], fingerprint[:12]]
    if dirty:
        build_id_parts.append("dirty")

    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "name": "Netfix",
        "version": version,
        "build_id": "-".join(build_id_parts),
        "built_at": _built_at(),
        "git_sha": git_sha,
        "dirty": dirty,
        "source_fingerprint": fingerprint,
        "backend_sha256": sha256_file(backend),
        "app_executable_sha256": sha256_file(app_executable),
        "release_candidate": release_candidate,
        "artifact_scope": "self-contained-macos-app",
        "workspace_audit_findings": workspace_audit_findings,
        "workspace_audit_note": (
            "Workspace findings are excluded from the app by the allowlisted bundle copy; "
            "use --strict-workspace to gate a source release."
        ),
        "backend_runtime": {
            "bundled_backend": True,
            "bundled_backend_path": BACKEND_RELATIVE_PATH.as_posix(),
            "bundled_python": False,
            "bundled_runtime_required": True,
            "system_python_required": False,
            "system_python_fallback": False,
        },
        "distribution": {
            "candidate_status": "unsigned-unnotarized",
            "developer_id_signed": False,
            "notarization_requested": False,
            "notarized": False,
            "notarization_receipt": None,
            "dmg_created": release_candidate,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    verify_manifest(app_bundle, output, repo_root=repo_root)
    return manifest


def _required_string(manifest: Dict[str, Any], name: str) -> str:
    value = manifest.get(name)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"manifest field {name} is missing or invalid")
    return value


def verify_manifest(
    app_bundle: Path, manifest_path: Path, *, repo_root: Optional[Path] = None
) -> Dict[str, Any]:
    backend = app_bundle / BACKEND_RELATIVE_PATH
    app_executable = app_bundle / APP_EXECUTABLE_RELATIVE_PATH
    _require_executable(backend, "bundled backend")
    _require_executable(app_executable, "app executable")
    if not manifest_path.is_file():
        raise ManifestError(f"missing release manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"release manifest is not readable JSON: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("release manifest root must be an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"release manifest schema must be {SCHEMA_VERSION}")

    git_sha = _required_string(manifest, "git_sha")
    fingerprint = _required_string(manifest, "source_fingerprint")
    backend_sha = _required_string(manifest, "backend_sha256")
    app_sha = _required_string(manifest, "app_executable_sha256")
    for field in ("version", "build_id", "built_at"):
        _required_string(manifest, field)
    if not GIT_SHA_RE.fullmatch(git_sha):
        raise ManifestError("manifest git_sha is invalid")
    if not SHA256_RE.fullmatch(fingerprint):
        raise ManifestError("manifest source_fingerprint is invalid")
    if type(manifest.get("dirty")) is not bool:
        raise ManifestError("manifest dirty must be a boolean")
    if sha256_file(backend) != backend_sha:
        raise ManifestError("backend SHA256 mismatch")
    if sha256_file(app_executable) != app_sha:
        raise ManifestError("app executable SHA256 mismatch")

    runtime = manifest.get("backend_runtime")
    if not isinstance(runtime, dict):
        raise ManifestError("manifest backend_runtime is missing")
    if runtime.get("bundled_backend") is not True:
        raise ManifestError("manifest must require the bundled backend")
    if runtime.get("bundled_runtime_required") is not True:
        raise ManifestError("manifest must record bundled_runtime_required=true")
    if runtime.get("system_python_required") is not False:
        raise ManifestError("manifest must record system_python_required=false")
    if runtime.get("system_python_fallback") is not False:
        raise ManifestError("manifest must record system_python_fallback=false")

    distribution = manifest.get("distribution")
    if not isinstance(distribution, dict):
        raise ManifestError("manifest distribution is missing")
    if distribution.get("developer_id_signed") is not False:
        raise ManifestError("P0 candidate must not claim Developer ID signing")
    if distribution.get("notarized") is not False:
        raise ManifestError("P0 candidate must not claim notarization")

    if repo_root is not None:
        repo_root = repo_root.resolve()
        if manifest["version"] != project_version(repo_root):
            raise ManifestError("manifest version does not match pyproject.toml")
        if git_sha != git_provenance(repo_root)[0]:
            raise ManifestError("manifest git_sha does not match the source checkout")
        if fingerprint != source_fingerprint(repo_root):
            raise ManifestError("manifest source_fingerprint does not match release inputs")
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    version_parser = subparsers.add_parser("version", help="Print [project].version")
    version_parser.add_argument("--repo-root", type=Path, default=Path.cwd())

    fingerprint_parser = subparsers.add_parser("fingerprint", help="Print the release source fingerprint")
    fingerprint_parser.add_argument("--repo-root", type=Path, default=Path.cwd())

    create_parser = subparsers.add_parser("create", help="Create and immediately verify a manifest")
    create_parser.add_argument("--repo-root", type=Path, required=True)
    create_parser.add_argument("--app-bundle", type=Path, required=True)
    create_parser.add_argument("--output", type=Path, required=True)
    create_parser.add_argument("--release-candidate", action="store_true")
    create_parser.add_argument("--workspace-audit-findings", type=int, default=0)

    verify_parser = subparsers.add_parser("verify", help="Verify manifest fields and artifact hashes")
    verify_parser.add_argument("--app-bundle", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--repo-root", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "version":
            print(project_version(args.repo_root.resolve()))
            return 0
        if args.command == "fingerprint":
            print(source_fingerprint(args.repo_root.resolve()))
            return 0
        if args.command == "create":
            manifest = create_manifest(
                args.repo_root,
                args.app_bundle,
                args.output,
                release_candidate=args.release_candidate,
                workspace_audit_findings=args.workspace_audit_findings,
            )
        else:
            manifest = verify_manifest(
                args.app_bundle.resolve(),
                args.manifest.resolve(),
                repo_root=args.repo_root,
            )
        print(
            json.dumps(
                {
                    "ok": True,
                    "schema_version": manifest["schema_version"],
                    "version": manifest["version"],
                    "build_id": manifest["build_id"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (ManifestError, OSError) as exc:
        print(f"release manifest error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
