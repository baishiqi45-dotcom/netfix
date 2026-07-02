#!/usr/bin/env python3
"""Create a clean downloadable Netfix release export directory.

This script deliberately exports only the distributable DMG plus release
metadata. It never copies the source workspace, local cases, or proxy packages.
"""
from __future__ import annotations

import argparse
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

from scripts.release_audit import audit  # noqa: E402
from scripts.path_sanitizer import build_replacements, sanitize_json, sanitize_public_names  # noqa: E402
from scripts.release_readiness import evaluate  # noqa: E402


DEFAULT_BUNDLE = ROOT / "gui/macos/.build/Netfix.app"
DEFAULT_DMG = ROOT / "gui/macos/.build/Netfix-0.2.0.dmg"
DEFAULT_OUT = ROOT / "gui/macos/.build/release-export"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _is_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _resolve_evidence_record(record: str, *, root: Path, evidence_file: Path) -> Optional[Path]:
    if not record or _is_url(record):
        return None
    candidate = Path(record)
    candidates = [candidate] if candidate.is_absolute() else [evidence_file.parent / candidate, root / candidate]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _copy_clean_machine_qa_dependencies(record_path: Path, target: Path, evidence_dir: Path) -> list[Path]:
    data = _load_json(record_path)
    screenshots = data.get("screenshots") if isinstance(data.get("screenshots"), list) else []
    copied: list[Path] = []
    rewritten: list[str] = []
    for index, item in enumerate(screenshots, start=1):
        if not isinstance(item, str) or not item.strip() or item.startswith("http://") or item.startswith("https://"):
            continue
        source = Path(item)
        if not source.is_absolute():
            source = record_path.parent / source
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix or ".png"
        screenshot_target = evidence_dir / f"clean_machine_qa_screenshot_{index}{suffix}"
        shutil.copy2(source, screenshot_target)
        copied.append(screenshot_target)
        rewritten.append(screenshot_target.name)
    if copied:
        data["screenshots"] = rewritten
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return copied


def _copy_legal_review_dependencies(record_path: Path, target: Path, evidence_dir: Path) -> list[Path]:
    data = _load_json(record_path)
    copied: list[Path] = []
    for field in ("privacy_policy_artifact", "eula_artifact"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip() or _is_url(value.strip()):
            continue
        source = Path(value.strip())
        if not source.is_absolute():
            source = record_path.parent / source
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix or ".md"
        artifact_target = evidence_dir / f"legal_review_{field}{suffix}"
        shutil.copy2(source, artifact_target)
        copied.append(artifact_target)
        data[field] = artifact_target.name
    if copied:
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return copied


def _copy_release_evidence(source: Path, *, root: Path, export_root: Path) -> tuple[Optional[Path], list[Path]]:
    if not source.exists():
        return None, []
    data = _load_json(source)
    if not data:
        return None, []
    copied_records: list[Path] = []
    evidence_dir = export_root / "evidence"
    for key, value in list(data.items()):
        if not key.endswith("_record") or not isinstance(value, str) or _is_url(value):
            continue
        record_path = _resolve_evidence_record(value, root=root, evidence_file=source)
        if record_path is None:
            continue
        evidence_dir.mkdir(exist_ok=True)
        suffix = record_path.suffix or ".txt"
        target = evidence_dir / f"{key}{suffix}"
        shutil.copy2(record_path, target)
        data[key] = target.relative_to(export_root).as_posix()
        copied_records.append(target)
        if key == "clean_machine_qa_record":
            copied_records.extend(_copy_clean_machine_qa_dependencies(record_path, target, evidence_dir))
        if key == "legal_review_record":
            copied_records.extend(_copy_legal_review_dependencies(record_path, target, evidence_dir))
    copied_evidence = export_root / "release-evidence.json"
    copied_evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return copied_evidence, copied_records


def _iter_export_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            yield path


def _relative_export_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_download_qa_preflight_stub(path: Path, *, version: str, dmg_name: str) -> None:
    data = {
        "schema_version": "netfix_release_preflight.v1",
        "status": "not_run",
        "download_qa_ready": False,
        "source_publication_ready": False,
        "paid_release_ready": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": "Download QA smoke has not been recorded for this export yet.",
        "next_steps": [
            f"python3 scripts/release_preflight.py --with-dmg-smoke --write-record <export-root>/download-qa-preflight.json",
            "After the record is written, verify SHA256SUMS.txt includes download-qa-preflight.json.",
        ],
        "package": {
            "name": "Netfix",
            "version": version,
            "dmg": dmg_name,
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_verify_download_script(path: Path) -> None:
    text = r'''#!/usr/bin/env python3
"""Verify the Netfix download export directory on this machine."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_checksums(path: Path) -> Dict[str, str]:
    checksums: Dict[str, str] = {}
    if not path.exists():
        return checksums
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        checksums[parts[1].strip()] = parts[0].strip()
    return checksums


def verify(*, require_recorded_preflight: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    checksums = parse_checksums(ROOT / "SHA256SUMS.txt")
    if not checksums:
        errors.append("checksums-missing")
    checked_checksums = 0
    for rel, expected in sorted(checksums.items()):
        target = ROOT / rel
        if not target.exists() or not target.is_file():
            errors.append(f"checksum-file-missing:{rel}")
            continue
        checked_checksums += 1
        actual = sha256(target)
        if actual != expected:
            errors.append(f"checksum-mismatch:{rel}")

    required_files = [
        "Netfix-0.2.0.dmg",
        "README-FIRST.md",
        "download-qa-preflight.json",
        "export-manifest.json",
        "release-manifest.json",
        "release-readiness.json",
    ]
    for rel in required_files:
        if not (ROOT / rel).exists():
            errors.append(f"required-file-missing:{rel}")
        if checksums and rel not in checksums:
            errors.append(f"required-checksum-missing:{rel}")

    manifest = load_json(ROOT / "export-manifest.json")
    if manifest.get("schema_version") != "netfix_release_export.v1":
        errors.append("export-manifest-schema")
    if manifest.get("source_workspace_included") is not False:
        errors.append("source-workspace-included")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
        errors.append("manifest-artifacts-missing")
    checked_artifacts = 0
    for rel, meta in sorted(artifacts.items()):
        target = ROOT / rel
        if not target.exists() or not target.is_file():
            errors.append(f"artifact-file-missing:{rel}")
            continue
        checked_artifacts += 1
        if isinstance(meta, dict):
            if meta.get("bytes") != target.stat().st_size:
                errors.append(f"artifact-bytes-mismatch:{rel}")
            expected_sha = meta.get("sha256")
            if expected_sha and sha256(target) != expected_sha:
                errors.append(f"artifact-sha-mismatch:{rel}")

    dmg_path = ROOT / "Netfix-0.2.0.dmg"
    dmg_sha = sha256(dmg_path) if dmg_path.exists() else ""
    preflight = load_json(ROOT / "download-qa-preflight.json")
    preflight_status = str(preflight.get("status") or "missing")
    download_qa_ready = bool(preflight.get("download_qa_ready"))
    if preflight.get("schema_version") != "netfix_release_preflight.v1":
        errors.append("preflight-schema")
    if require_recorded_preflight and not (preflight_status == "recorded" and download_qa_ready):
        errors.append("preflight-not-recorded")
    preflight_artifacts = preflight.get("artifacts")
    if isinstance(preflight_artifacts, dict) and preflight_artifacts.get("dmg_sha256"):
        if dmg_sha and preflight_artifacts.get("dmg_sha256") != dmg_sha:
            errors.append("preflight-dmg-sha-mismatch")
    elif require_recorded_preflight:
        errors.append("preflight-dmg-sha-missing")
    else:
        warnings.append("preflight-not-recorded")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "preflight_status": preflight_status,
        "download_qa_ready": download_qa_ready,
        "checksums_checked": checked_checksums,
        "artifacts_checked": checked_artifacts,
        "dmg_sha256": dmg_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify this Netfix download export directory.")
    parser.add_argument("--require-recorded-preflight", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify(require_recorded_preflight=args.require_recorded_preflight)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "OK" if result["ok"] else "FAILED"
        print(f"Netfix download verification: {status}")
        print(f"Preflight: {result['preflight_status']}  download_qa_ready={result['download_qa_ready']}")
        for error in result["errors"]:
            print(f"error: {error}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _sanitize_json_file(path: Path, replacements: list[tuple[str, str]]) -> None:
    data = _load_json(path)
    if not data:
        return
    path.write_text(json.dumps(sanitize_json(data, replacements), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _summarize_workspace_findings(findings: list[Any]) -> Dict[str, Any]:
    kinds: Dict[str, int] = {}
    roots: set[str] = set()
    next_steps_by_kind: Dict[str, list[str]] = {}
    for item in findings:
        kind = str(getattr(item, "kind", "") or "unknown")
        path = str(getattr(item, "path", "") or "")
        kinds[kind] = kinds.get(kind, 0) + 1
        if path:
            roots.add(path.split("/", 1)[0])
        steps = getattr(item, "next_steps", []) or []
        if steps:
            bucket = next_steps_by_kind.setdefault(kind, [])
            for step in steps:
                if step not in bucket:
                    bucket.append(str(step))
    return {
        "count": len(findings),
        "kinds": dict(sorted(kinds.items())),
        "roots": sorted(roots),
        "next_steps_by_kind": {
            key: value for key, value in sorted(next_steps_by_kind.items())
        },
    }


def _write_first_readme(
    path: Path,
    *,
    version: str,
    dmg_name: str,
    readiness: Dict[str, Any],
    source_workspace_findings_count: int,
    source_workspace_summary: Dict[str, Any],
) -> None:
    release_ready = bool(readiness.get("release_ready"))
    distribution_status = "paid external candidate" if release_ready else "internal QA candidate"
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    blockers = summary.get("blockers", 0)
    warnings = summary.get("warnings", 0)
    if release_ready:
        status_copy = (
            "这个包的机器状态是 paid external candidate。请保留随包附带的 evidence 文件，方便后续审计。"
        )
    else:
        status_copy = (
            "这个包现在是 internal QA candidate，还不是正式付费外发版本。"
            "`release-readiness.json` 仍然有 blocker，不要把它当成付费下载包发布。"
        )
    source_kinds = source_workspace_summary.get("kinds") if isinstance(source_workspace_summary.get("kinds"), dict) else {}
    source_roots = source_workspace_summary.get("roots") if isinstance(source_workspace_summary.get("roots"), list) else []
    next_steps_by_kind = source_workspace_summary.get("next_steps_by_kind") if isinstance(source_workspace_summary.get("next_steps_by_kind"), dict) else {}
    source_kinds_line = ", ".join(f"{kind} ({count})" for kind, count in source_kinds.items()) or "none"
    source_roots_line = ", ".join(str(item) for item in source_roots) or "none"
    source_next_lines: list[str] = []
    for kind, steps in next_steps_by_kind.items():
        if not isinstance(steps, list) or not steps:
            continue
        source_next_lines.append(f"- `{kind}`:")
        for step in steps:
            source_next_lines.append(f"  - {step}")
    source_next_block = "\n".join(source_next_lines) or "- none"

    text = f"""# Netfix {version} macOS 下载包

状态：{distribution_status}

{status_copy}

## 先看这里

这个包给 macOS 用户直接打开用：排查 ChatGPT、Codex、GitHub、代理和 IPv6 等网络问题；你有自己购买或合法获得的代理参数时，也可以复制整行粘贴，让 Netfix 帮你预检、保存、监控、部署和回滚。

普通使用不需要命令行，不需要自己启动 Python，也不需要打开 `127.0.0.1` 页面。

## 怎么打开

1. 打开 `{dmg_name}`。
2. 双击 `Netfix.app`，或拖到 Applications 后从启动台打开。Double-click `Netfix.app` 也可以。
3. 第一次打开看完本地隐私说明，然后点「一键诊断」。
4. 如果诊断失败，在恢复面板点「重试」或「复制支持包」。支持包会脱敏，方便发给技术人员；不要额外发送代理密码、API Key 或未脱敏截图。

## 粘贴代理怎么用

Netfix 不卖住宅 IP，也不承诺“干净 IP”或“绕过风控”。你需要先从自己的代理服务商后台复制连接参数，常见格式是：

- `host:port:username:password`
- `http://username:password@host:port`
- `socks5h://username:password@host:port`
- 表格里的 `host,port,username,password`

打开 App 后进入「设置 -> 代理」：

1. 把服务商给你的整行参数粘贴进去。
2. 点「检查并保存到这台 Mac」，Netfix 会先预检，再保存并监控；密码只进本机 Keychain。
3. 需要让这台 Mac 的常用 App 都走代理时，再点「开始使用这台 Mac 上网」（也就是部署到这台 Mac）并确认。
4. 出问题时点 `Restore original network settings` /「恢复原来的网络设置」。Netfix 会用上次部署前保存的本机备份回滚；如果这台 Mac 从没被 Netfix 部署过，它会直接说没有可回滚记录。

认证 HTTP/HTTPS 和 SOCKS 代理可能需要本机 127.0.0.1 桥接。只要这类部署还在用，就保持 Netfix 打开。

## AI 和 API Key

AI 只是帮你看报告、解释下一步；没有 API Key 也能一键诊断、代理部署、IPv6 处理和回滚。

需要 AI 时，在 App 的设置里选择 DeepSeek、Kimi/Moonshot、MiniMax 或 Qwen，粘贴 API Key 后保存测试。Key 只保存在本机 Keychain 或 provider-scoped 环境里；不要把 Key 粘到报告、截图、支持包或聊天里。

图片问诊只会走已配置为多模态的供应商；DeepSeek 在这个产品里只作为文本解释链路。发布前仍要完成 DeepSeek text setup、provider-scoped Keychain account selection、missing-key fallback、MiniMax/Kimi/Qwen 路由文案和 live provider smoke 证据。

## 给 Codex / Kimi 接入

打开 App 后进 `Settings -> AI Coding Assistant` /「设置 -> AI 编程助手」，点 `Copy for Codex` 注册 Codex。Kimi 当前 CLI 可能没有稳定的 `mcp add` 命令；点 `Copy Kimi / generic config` 后，把 stdio 配置填到支持 MCP 的 Kimi/Agent 宿主。

MCP 只让 Codex/Kimi 调用本机 Netfix 做诊断、查报告、查知识库和代理预检。MCP 不保存 API Key 或代理密码，也不会直接改系统代理；保存密钥和部署系统代理仍要回到 Netfix App 里确认。

## 这个包里有什么

- `{dmg_name}`：macOS App 安装镜像。
- `README-FIRST.md`：你现在看的这份说明。
- `verify-download.py`：给技术/QA 用的下载包自检脚本。
- `SHA256SUMS.txt`：每个文件的 SHA-256 校验值。
- `download-qa-preflight.json`：MCP dry-run 和 bundled DMG backend smoke 记录；`status: not_run` 表示这次导出还没跑下载 QA。
- `release-manifest.json`、`release-readiness.json`、`release-evidence.json`、`export-manifest.json`、`evidence/`：发布和审计证据。

QA 或支持交接时可以用 `shasum -a 256 {dmg_name}` 对照 `SHA256SUMS.txt`，但这不是普通用户第一次使用必须做的事。

## 未签名 QA 包说明

这个内部 QA 包还没有 Developer ID signed / notarized。干净 Mac 可能提示无法验证开发者。内部测试时，在 Finder 里 right-click `Netfix.app`，选 Open；如果还是拦截，到 System Settings -> Privacy & Security -> Open Anyway。

不要把这条未签名路径当作正式付费用户体验。公开收费发布前必须完成 Developer ID signing, notarization, stapling, and clean-machine QA。

## 发布状态

- Current status: {distribution_status}
- Blockers reported: {blockers}
- Warnings reported: {warnings}
- Source workspace included: no
- Source workspace findings excluded from this export: {source_workspace_findings_count}

## 源码开源阻塞项

这个二进制下载包故意不包含源码工作区，也不包含本地旧代理资料。源码仓库要公开发布，必须先让 workspace audit 变干净。

- Finding kinds: {source_kinds_line}
- Root paths/artifacts: {source_roots_line}

源码公开前必须处理：

{source_next_block}

以 `release-readiness.json` 判断这个包能不能对外售卖。只要它还显示 blocker，就不能把它宣传成正式付费外发版本。
"""
    path.write_text(text, encoding="utf-8")


def create_export(
    *,
    root: Path = ROOT,
    bundle: Path = DEFAULT_BUNDLE,
    dmg: Path = DEFAULT_DMG,
    out_dir: Path = DEFAULT_OUT,
    version: str = "0.2.0",
    evidence_file: Optional[Path] = None,
    skip_external: bool = False,
    make_zip: bool = False,
) -> Dict[str, Any]:
    root = root.resolve()
    bundle = bundle.resolve()
    dmg = dmg.resolve()
    out_dir = out_dir.resolve()

    manifest_path = bundle / "Contents/Resources/release-manifest.json"
    if not bundle.exists():
        raise FileNotFoundError(f"missing app bundle: {bundle}")
    if not dmg.exists():
        raise FileNotFoundError(f"missing DMG: {dmg}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing release manifest: {manifest_path}")

    export_name = f"Netfix-{version}-macos"
    export_root = out_dir / export_name
    if export_root.exists():
        shutil.rmtree(export_root)
    export_root.mkdir(parents=True)

    exported_dmg = export_root / dmg.name
    exported_bundle_manifest = export_root / "release-manifest.json"
    exported_readiness = export_root / "release-readiness.json"
    exported_manifest = export_root / "export-manifest.json"
    download_qa_preflight = export_root / "download-qa-preflight.json"
    verify_download_script = export_root / "verify-download.py"
    first_readme = export_root / "README-FIRST.md"
    checksums_path = export_root / "SHA256SUMS.txt"

    shutil.copy2(dmg, exported_dmg)
    shutil.copy2(manifest_path, exported_bundle_manifest)

    source_manifest = _load_json(manifest_path)
    source_evidence = evidence_file.resolve() if evidence_file is not None else root / "gui/macos/.build/release-evidence.json"
    copied_evidence, copied_evidence_records = _copy_release_evidence(source_evidence, root=root, export_root=export_root)
    receipt_path = source_manifest.get("distribution", {}).get("notarization_receipt") if isinstance(source_manifest.get("distribution"), dict) else None
    copied_receipt: Optional[Path] = None
    if receipt_path:
        candidate = Path(str(receipt_path))
        if candidate.exists():
            copied_receipt = export_root / candidate.name
            shutil.copy2(candidate, copied_receipt)

    sanitizers = build_replacements([
        (export_root / "release-evidence.json", "release-evidence.json"),
        (exported_dmg, exported_dmg.name),
        (export_root.parent / f"{export_name}.zip", f"{export_name}.zip"),
        (export_root, "."),
        (copied_evidence, "release-evidence.json" if copied_evidence else ""),
        (source_evidence, "<build-artifact>/release-evidence.json"),
        (bundle, "<build-artifact>/Netfix.app"),
        (dmg, "<build-artifact>/Netfix-0.2.0.dmg"),
        (root, "<source-workspace>"),
    ])
    for json_path in ([copied_evidence] if copied_evidence else []) + copied_evidence_records:
        if json_path is not None and json_path.suffix.lower() == ".json":
            _sanitize_json_file(json_path, sanitizers)

    readiness = sanitize_json(evaluate(
        root=export_root,
        bundle=bundle,
        dmg=exported_dmg,
        evidence_file=copied_evidence or source_evidence,
        require_runtime=True,
        skip_external=skip_external,
    ), sanitizers)
    exported_readiness.write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    source_workspace_findings = audit(root, "workspace")
    source_workspace_summary = sanitize_public_names(_summarize_workspace_findings(source_workspace_findings))
    if isinstance(source_workspace_summary.get("roots"), list):
        source_workspace_summary["roots"] = sorted({str(item) for item in source_workspace_summary["roots"]})
    _write_first_readme(
        first_readme,
        version=version,
        dmg_name=exported_dmg.name,
        readiness=readiness,
        source_workspace_findings_count=len(source_workspace_findings),
        source_workspace_summary=source_workspace_summary,
    )
    _write_download_qa_preflight_stub(download_qa_preflight, version=version, dmg_name=exported_dmg.name)
    _write_verify_download_script(verify_download_script)
    artifacts: Dict[str, Dict[str, Any]] = {}
    for path in (
        [exported_dmg, exported_bundle_manifest, exported_readiness, download_qa_preflight, verify_download_script, first_readme]
        + ([copied_evidence] if copied_evidence else [])
        + copied_evidence_records
        + ([copied_receipt] if copied_receipt else [])
    ):
        if path is None:
            continue
        artifacts[_relative_export_path(export_root, path)] = {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }

    distribution = source_manifest.get("distribution") if isinstance(source_manifest.get("distribution"), dict) else {}
    export_data = {
        "schema_version": "netfix_release_export.v1",
        "name": "Netfix",
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_workspace_included": False,
        "source_workspace_findings_excluded_count": len(source_workspace_findings),
        "source_workspace_findings_summary": source_workspace_summary,
        "artifact_scope": "downloadable-dmg-plus-metadata",
        "distribution_status": "paid_external_candidate" if readiness.get("release_ready") else "internal_qa_candidate",
        "paid_release_ready": bool(readiness.get("release_ready")),
        "developer_id_signed": bool(distribution.get("developer_id_signed")),
        "notarized": bool(distribution.get("notarized")),
        "artifacts": artifacts,
        "notes": [
            "This export intentionally excludes the source workspace and local proxy/config artifacts.",
            "README-FIRST.md explains first-run steps, release status, AI provider setup, and residential/custom proxy boundaries.",
            "download-qa-preflight.json is a not-run placeholder until scripts/release_preflight.py writes a real smoke record for this export.",
            "Do not market as paid external release until release-readiness.json reports release_ready=true, including manual clean-machine QA, legal review, and live provider smoke evidence.",
        ],
    }
    exported_manifest.write_text(json.dumps(export_data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    checksum_lines = []
    for path in _iter_export_files(export_root):
        checksum_lines.append(f"{_sha256(path)}  {_relative_export_path(export_root, path)}")
    checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    zip_path: Optional[Path] = None
    if make_zip:
        zip_path = out_dir / f"{export_name}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(export_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(out_dir))

    result = {
        "ok": True,
        "export_root": str(export_root),
        "zip": str(zip_path) if zip_path else None,
        "paid_release_ready": bool(readiness.get("release_ready")),
        "source_workspace_included": False,
        "source_workspace_findings_excluded_count": len(source_workspace_findings),
        "source_workspace_findings_summary": source_workspace_summary,
        "files": [_relative_export_path(export_root, path) for path in _iter_export_files(export_root)],
    }
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create a clean Netfix release export directory.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--dmg", type=Path, default=DEFAULT_DMG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--evidence-file", type=Path, default=None, help="Optional release-evidence.json to copy into the export and use for readiness.")
    parser.add_argument("--skip-external", action="store_true", help="Skip codesign/hdiutil checks inside readiness JSON.")
    parser.add_argument("--zip", action="store_true", help="Also create a zip containing the export directory.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = create_export(
            root=args.root,
            bundle=args.bundle,
            dmg=args.dmg,
            out_dir=args.out_dir,
            version=args.version,
            evidence_file=args.evidence_file,
            skip_external=args.skip_external,
            make_zip=args.zip,
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"release export failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Created release export: {result['export_root']}")
        print(f"Paid release ready: {result['paid_release_ready']}")
        if result.get("zip"):
            print(f"Zip: {result['zip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
