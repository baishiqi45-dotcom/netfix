import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_TOOL = ROOT / "scripts" / "release_manifest.py"
BUILD_APP = ROOT / "gui" / "macos" / "build_app.sh"


def _write_executable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(path.stat().st_mode | 0o111)


def _candidate_bundle(tmp_path: Path, *, include_backend: bool = True) -> tuple[Path, Path]:
    bundle = tmp_path / "Netfix.app"
    executable = bundle / "Contents" / "MacOS" / "Netfix"
    backend = bundle / "Contents" / "MacOS" / "netfix-backend"
    _write_executable(executable, b"netfix-app-executable\n")
    if include_backend:
        _write_executable(backend, b"self-contained-backend\n")
    return bundle, bundle / "Contents" / "Resources" / "release-manifest.json"


def _run_manifest(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_TOOL), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _create_manifest(bundle: Path, manifest: Path) -> subprocess.CompletedProcess[str]:
    return _run_manifest(
        "create",
        "--repo-root",
        str(ROOT),
        "--app-bundle",
        str(bundle),
        "--output",
        str(manifest),
        "--release-candidate",
        "--workspace-audit-findings",
        "0",
    )


def test_release_manifest_records_version_provenance_and_artifact_hashes(tmp_path: Path):
    bundle, manifest_path = _candidate_bundle(tmp_path)

    result = _create_manifest(bundle, manifest_path)

    assert result.returncode == 0, result.stderr
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    expected_version = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)
    assert manifest["schema_version"] == "netfix_release_manifest.v1"
    assert manifest["version"] == expected_version
    assert re.fullmatch(r"[0-9a-f]{40,64}", manifest["git_sha"])
    assert isinstance(manifest["dirty"], bool)
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_fingerprint"])
    assert manifest["backend_sha256"] == hashlib.sha256(
        (bundle / "Contents" / "MacOS" / "netfix-backend").read_bytes()
    ).hexdigest()
    assert manifest["app_executable_sha256"] == hashlib.sha256(
        (bundle / "Contents" / "MacOS" / "Netfix").read_bytes()
    ).hexdigest()
    assert manifest["build_id"]
    assert datetime.fromisoformat(manifest["built_at"].replace("Z", "+00:00")).tzinfo is not None
    assert manifest["backend_runtime"]["bundled_backend"] is True
    assert manifest["backend_runtime"]["system_python_required"] is False
    assert manifest["distribution"]["developer_id_signed"] is False
    assert manifest["distribution"]["notarized"] is False


def test_release_manifest_creation_fails_when_bundled_backend_is_missing(tmp_path: Path):
    bundle, manifest_path = _candidate_bundle(tmp_path, include_backend=False)

    result = _create_manifest(bundle, manifest_path)

    assert result.returncode != 0
    assert "missing bundled backend" in result.stderr.lower()
    assert not manifest_path.exists()


def test_release_manifest_verification_fails_after_backend_hash_changes(tmp_path: Path):
    bundle, manifest_path = _candidate_bundle(tmp_path)
    created = _create_manifest(bundle, manifest_path)
    assert created.returncode == 0, created.stderr
    backend = bundle / "Contents" / "MacOS" / "netfix-backend"
    backend.write_bytes(backend.read_bytes() + b"tampered")

    result = _run_manifest(
        "verify", "--app-bundle", str(bundle), "--manifest", str(manifest_path)
    )

    assert result.returncode != 0
    assert "backend sha256 mismatch" in result.stderr.lower()


def test_release_manifest_verification_fails_after_app_hash_changes(tmp_path: Path):
    bundle, manifest_path = _candidate_bundle(tmp_path)
    created = _create_manifest(bundle, manifest_path)
    assert created.returncode == 0, created.stderr
    executable = bundle / "Contents" / "MacOS" / "Netfix"
    executable.write_bytes(executable.read_bytes() + b"tampered")

    result = _run_manifest(
        "verify", "--app-bundle", str(bundle), "--manifest", str(manifest_path)
    )

    assert result.returncode != 0
    assert "app executable sha256 mismatch" in result.stderr.lower()


def test_app_build_forces_fresh_bundled_backend_and_manifest_verification():
    script = BUILD_APP.read_text(encoding="utf-8")

    assert "scripts/build_backend_binary.sh" in script
    assert "scripts/release_manifest.py" in script
    assert re.search(r"MANIFEST_ARGS=\(\s*create\b", script)
    assert re.search(r'python3 "\$\{MANIFEST_TOOL\}" verify\b', script)
    assert "NETFIX_BACKEND_BIN" not in script
    assert "NETFIX_REQUIRE_BUNDLED_RUNTIME" not in script
    assert "0.2.0" not in script
    assert "system_python_fallback\": True" not in script
    assert script.count('fingerprint --repo-root "${REPO_ROOT}"') >= 2
    assert "SOURCE_FINGERPRINT_BEFORE" in script
    assert "SOURCE_FINGERPRINT_AFTER" in script
    assert "GIT_SHA_BEFORE" in script
    assert "GIT_SHA_AFTER" in script
    assert 'if [[ "${SOURCE_FINGERPRINT_BEFORE}" != "${SOURCE_FINGERPRINT_AFTER}"' in script
    assert not re.search(r"^\s*(open|killall|pkill|osascript)\b", script, re.MULTILINE)
    assert "Desktop/Netfix" not in script


def test_backend_builder_uses_absolute_data_sources_with_isolated_spec_directory():
    script = (ROOT / "scripts" / "build_backend_binary.sh").read_text(encoding="utf-8")

    assert '--specpath "${SPEC_DIR}"' in script
    for relative in ["rules", "bin", "gui/web"]:
        assert f'--add-data "${{REPO_ROOT}}/{relative}:{relative}"' in script


def test_macos_runtime_prefers_bundled_backend_before_python_fallbacks():
    source = (ROOT / "gui" / "macos" / "Sources" / "Backend.swift").read_text(encoding="utf-8")

    bundled = source.index("if let path = bundledBackendPath")
    bundled_python = source.index("if let python = bundledPythonPath")
    system_python = source.index('executableURL: URL(fileURLWithPath: "/usr/bin/env")')
    assert bundled < bundled_python < system_python
    assert 'label: "bundled backend binary"' in source
