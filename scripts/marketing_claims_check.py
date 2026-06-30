#!/usr/bin/env python3
"""Static guard for customer-facing marketing and capability claims."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


TEXT_SUFFIXES = {".md", ".markdown", ".html", ".swift", ".txt"}
ROOT_SURFACE_FILES = {
    "README.md",
    "README.en.md",
    "DESIGN.md",
    "PRODUCT_DESIGN.md",
    "PRODUCT_STRATEGY.md",
    "PRODUCT_STRATEGY_V2.md",
    "CONTRIBUTING.md",
    "OPEN_SOURCE.md",
}
SURFACE_DIRS = ("docs", "gui/web", "gui/macos/Sources")
EXCLUDED_PARTS = {
    ".git",
    ".build",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "cases",
    "tests",
    "fixtures",
    "iphone-v2rayn-package-2026-06-14",
}

RESIDENTIAL_PROXY_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\bclean\s+residential(?:\s+ip)?\b", re.I),
    re.compile(r"干净\s*住宅\s*IP|干净\s*住宅", re.I),
    re.compile(r"\banti[-\s]?ban\b|\bavoid\s+ban(?:s|ning)?\b", re.I),
    re.compile(r"\bbypass(?:ing)?\s+(?:third[-\s]?party\s+)?(?:platform\s+)?(?:risk|fraud|ban|access)?\s*controls?\b", re.I),
    re.compile(r"\bevade\s+fraud\s+controls?\b", re.I),
    re.compile(r"绕过.{0,8}风控|规避.{0,8}风控|逃避.{0,8}风控|过风控|防封|养号|解封|突破.{0,8}封锁", re.I),
    re.compile(r"\b(?:guarantee|guarantees|guaranteed|certified|verified)\b.{0,80}\b(?:residential\s+ip|proxy|residential\s+proxy)\b", re.I),
    re.compile(r"\b(?:residential\s+ip|residential\s+proxy)\b.{0,80}\b(?:accepted|low[-\s]?risk|clean|safe)\b", re.I),
    re.compile(r"(?:住宅\s*IP|住宅代理).{0,80}(?:平台接受|低风险|干净|保证|稳定过)", re.I),
)

RESIDENTIAL_SAFE_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\b(?:do(?:es)?\s+not|don't|must\s+not|should\s+not|cannot|can't|never|avoid|not\s+claim|not\s+imply|without\s+implying|not\s+guarantee|does\s+not\s+guarantee|no\s+guarantee|no\s+.{0,30}claims?|not\s+be\s+used\s+to)\b", re.I),
    re.compile(r"\b(?:does\s+not\s+provide|does\s+not\s+sell|does\s+not\s+resell|do\s+not\s+market|must\s+avoid)\b", re.I),
    re.compile(r"不承诺|不保证|不销售|不提供|不内置|不推荐|不得|不能|不要|避免|禁止|不会|不应|不把|不可营销|确认式恢复", re.I),
)

DEEPSEEK_VISION_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(
        r"deepseek.{0,80}\b(?:support|supports|supported|handle|handles|process|processes|accept|accepts|can\s+(?:answer|process|read|diagnose)|answer|answers)\b.{0,80}\b(?:image|images|screenshot|vision|multimodal|image[-\s]?question)\b",
        re.I,
    ),
    re.compile(r"deepseek.{0,80}(?:支持|可以|可用于|可处理|能|能够|用于).{0,80}(?:图片|截图|视觉|多模态|图片问诊|截图问诊)", re.I),
    re.compile(r"deepseek.{0,40}\b(?:vision|multimodal)\b(?:\s+(?:model|provider|adapter|capability))?", re.I),
    re.compile(r"deepseek.{0,40}(?:视觉|多模态)(?:模型|供应商|能力|适配)?", re.I),
    re.compile(r"\b(?:image[-\s]?question|screenshot\s+diagnosis)\b.{0,40}\b(?:via|by|with|using)\s+deepseek\b", re.I),
    re.compile(r"(?:图片问诊|截图问诊).{0,40}(?:走|用|使用|调用)\s*DeepSeek", re.I),
)

DEEPSEEK_SAFE_PATTERNS: Sequence[re.Pattern[str]] = (
    re.compile(r"\b(?:text[-\s]?only|text[-\s]?first|text\s+explanation|text\s+default|remains\s+text[-\s]?only|not\s+a\s+vision|not\s+multimodal|must\s+not\s+assume|instead\s+of\s+implying)\b", re.I),
    re.compile(r"(?:只|仅|仍只|仍然只|当前只).{0,12}文本|文本.{0,12}(?:默认|优先|主力|解释)|不支持|没有.{0,8}多模态|不具备.{0,8}多模态|没办法.{0,8}发图片|不能把|不把|不要把|误标|误宣|图片问诊链路|图片链路", re.I),
    re.compile(r"(?:route|routes|routed|走|路由).{0,40}(?:Kimi|MiniMax|Qwen|Moonshot)", re.I),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    text: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "text": self.text,
        }


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS or part.endswith(".zip") for part in path.parts)


def _is_text_surface(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def _iter_surface_files(root: Path) -> List[Path]:
    if root.is_file():
        return [root] if _is_text_surface(root) else []

    files: List[Path] = []
    for name in ROOT_SURFACE_FILES:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            files.append(candidate)
    for rel_dir in SURFACE_DIRS:
        directory = root / rel_dir
        if not directory.exists():
            continue
        for candidate in directory.rglob("*"):
            if candidate.is_file() and _is_text_surface(candidate) and not _is_excluded(candidate.relative_to(root)):
                files.append(candidate)

    if not files:
        for candidate in root.rglob("*"):
            if candidate.is_file() and _is_text_surface(candidate) and not _is_excluded(candidate.relative_to(root)):
                files.append(candidate)

    return sorted(set(files))


def _matches_any(patterns: Iterable[re.Pattern[str]], line: str) -> bool:
    return any(pattern.search(line) for pattern in patterns)


def _safe_residential_context(line: str) -> bool:
    return _matches_any(RESIDENTIAL_SAFE_PATTERNS, line)


def _safe_deepseek_context(line: str) -> bool:
    return _matches_any(DEEPSEEK_SAFE_PATTERNS, line)


def _find_line_claims(path: Path, root: Path, line_no: int, line: str) -> List[Finding]:
    findings: List[Finding] = []
    stripped = " ".join(line.strip().split())
    if not stripped:
        return findings
    rel_path = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)

    if _matches_any(RESIDENTIAL_PROXY_PATTERNS, stripped) and not _safe_residential_context(stripped):
        findings.append(Finding(rel_path, line_no, "residential_proxy_claim", stripped))

    if _matches_any(DEEPSEEK_VISION_PATTERNS, stripped) and not _safe_deepseek_context(stripped):
        findings.append(Finding(rel_path, line_no, "deepseek_vision_claim", stripped))

    return findings


def scan_file(path: Path, root: Path) -> List[Finding]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    findings: List[Finding] = []
    for line_no, line in enumerate(lines, start=1):
        findings.extend(_find_line_claims(path, root, line_no, line))
    return findings


def run(root: Path, paths: Optional[Iterable[Path]] = None) -> Dict[str, Any]:
    root = root.resolve()
    files = [path.resolve() for path in paths] if paths is not None else _iter_surface_files(root)
    findings: List[Finding] = []
    for path in files:
        if path.exists() and path.is_file() and _is_text_surface(path):
            findings.extend(scan_file(path, root))
    return {
        "ok": not findings,
        "root": str(root),
        "checked": len(files),
        "findings": [finding.as_dict() for finding in findings],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check customer-facing claims for unsafe proxy or LLM capability wording.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--path", action="append", type=Path, dest="paths", help="specific file to scan; repeatable")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args(argv)

    result = run(args.root, args.paths)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"marketing claims check passed: {result['checked']} file(s)")
    else:
        print(f"marketing claims check failed: {len(result['findings'])} finding(s)", file=sys.stderr)
        for finding in result["findings"]:
            print(f"- {finding['path']}:{finding['line']} {finding['kind']}: {finding['text']}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
