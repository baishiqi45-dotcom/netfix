"""Bandwidth / process congestion diagnostic.

This is a *read-only* minimal sampler. It does not sniff packets, does not
inspect payloads, and only reports process names + direction + coarse rates.
The goal is to flag obvious hogs (BaiduNetdisk, OneDrive, iCloud Drive,
Docker, qBittorrent/Transmission, systemupdate) so users can pause them when
a real-time app like Codex is slow.

The sampler must NEVER block the main diagnosis when the underlying tools
are unavailable or fail: it returns ``status="unknown"`` and a friendly
``reason`` string instead.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from netfix.diagnose import register
from netfix.layers._helpers import diagnostic


# process name (case-insensitive) -> friendly label
_KNOWN_HOGS: List[Tuple[str, str]] = [
    # Cloud drive uploaders (常见耗上传的同步/网盘 App)
    ("baidunetdisk", "百度网盘"),
    ("baidunetdiskmac", "百度网盘"),
    ("netdisk_service", "百度网盘"),
    ("aliyundrive", "阿里云盘"),
    ("aliyundrivemac", "阿里云盘"),
    ("quarkclouddrive", "夸克网盘"),
    ("xunleicloud", "迅雷云盘"),
    ("onedrive", "OneDrive"),
    ("dropbox", "Dropbox"),
    ("iclouddrive", "iCloud Drive"),
    ("bird", "iCloud Drive"),
    ("clouddocs", "iCloud Drive"),
    # IM / meeting that may saturate upload
    ("wechat", "微信"),
    ("qqmusic", "QQ音乐"),
    ("qq", "QQ"),
    ("feishu", "飞书"),
    ("dingtalk", "钉钉"),
    ("lark", "Lark"),
    # Container / package / system tooling
    ("docker", "Docker"),
    ("containerd", "containerd"),
    ("brew", "Homebrew"),
    ("softwareupdated", "系统更新"),
    # Downloaders
    ("transmission", "Transmission"),
    ("qbittorrent", "qBittorrent"),
    ("xunlei", "迅雷"),
    ("motrix", "Motrix"),
    ("aria2c", "Aria2"),
    ("thunder", "迅雷"),
]

# Per-process min kilobits-per-second threshold before we treat it as a real
# hog. These thresholds intentionally ignore background noise.
_UPLOAD_HOG_THRESHOLD_KBPS = 1500  # 1.5 Mbps sustained upload
_DOWNLOAD_HOG_THRESHOLD_KBPS = 20000  # 20 Mbps sustained download

# We only ever return at most this many hogs in a diagnostic row.
_MAX_HOGS = 3

# Hard cap on tool runtime so bandwidth sampling never stalls the diagnose.
_SAMPLE_TIMEOUT_S = 4


def _friendly_label(process_name: str) -> Optional[str]:
    lowered = (process_name or "").lower()
    for needle, label in _KNOWN_HOGS:
        if needle in lowered:
            return label
    return None


def _classify_process(name: str) -> str:
    """Return "upload", "download", or "mixed" based on heuristics."""
    lowered = (name or "").lower()
    upload_bias = any(
        token in lowered
        for token in [
            "baidu", "onedrive", "icloud", "drive", "cloud",
            "sync", "backup", "dropbox", "upload",
        ]
    )
    download_bias = any(
        token in lowered
        for token in ["torrent", "qbittorrent", "transmission", "aria2c", "thunder", "motrix", "qqmusic"]
    )
    if upload_bias and not download_bias:
        return "upload"
    if download_bias and not upload_bias:
        return "download"
    if upload_bias:
        return "mixed"
    return "upload"


def _parse_nettop_table(stdout: str) -> List[Dict[str, Any]]:
    """Parse ``nettop -P -L 2 -d -x -J bytes_in,bytes_out`` CSV output.

    ``nettop`` reports a first cumulative-looking snapshot before the delta
    sample, even in ``-d`` mode. We split snapshots by the repeated CSV header
    and only use the last one to avoid false positives from long-running
    processes such as xray/sing-box.
    """
    samples: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cells = [c.strip() for c in stripped.split(",")]
        if "bytes_in" in cells and "bytes_out" in cells:
            if current:
                samples.append(current)
            current = []
            continue
        if len(cells) < 3:
            continue
        process_name = cells[0]
        rx_cell = cells[1]
        tx_cell = cells[2]
        # Full CSV fallback: time,process,interface,state,bytes_in,bytes_out,...
        if len(cells) >= 6 and ":" in cells[0]:
            process_name = cells[1]
            rx_cell = cells[4]
            tx_cell = cells[5]
        if not process_name:
            continue
        try:
            rx_bytes = int(float(rx_cell)) if rx_cell else 0
            tx_bytes = int(float(tx_cell)) if tx_cell else 0
        except ValueError:
            continue
        current.append({
            "process": process_name,
            "rx_bytes": max(0, rx_bytes),
            "tx_bytes": max(0, tx_bytes),
        })
    if current:
        samples.append(current)
    return samples[-1] if samples else []


def _parse_lsof(stdout: str) -> List[str]:
    """Parse ``lsof -i -P -n`` output, returning distinct process names."""
    names: List[str] = []
    seen = set()
    for line in stdout.splitlines():
        if line.startswith("COMMAND"):
            continue
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _sample_nettop() -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Try nettop for one ~1s window; return rows or (None, reason)."""
    if sys.platform != "darwin" or shutil.which("nettop") is None:
        return None, "nettop_unavailable"
    # Use CSV logging with delta mode and keep the last sample. One sample can
    # look cumulative on macOS; two samples costs ~1s and avoids false alerts.
    try:
        proc = subprocess.run(
            ["nettop", "-P", "-L", "2", "-d", "-x", "-J", "bytes_in,bytes_out"],
            text=True,
            capture_output=True,
            timeout=_SAMPLE_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"nettop_failed: {exc}".strip()

    stdout = proc.stdout or ""
    if proc.returncode != 0 and not stdout.strip():
        return None, f"nettop_failed: {(proc.stderr or '').strip()[:80]}"

    parsed = _parse_nettop_table(stdout)
    if not parsed:
        return None, "nettop_empty"
    return parsed, None


def _aggregate_by_process(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    agg: Dict[str, Dict[str, int]] = {}
    for row in rows:
        process = (row.get("process") or "").strip()
        if not process:
            continue
        rx = int(row.get("rx_bytes") or 0)
        tx = int(row.get("tx_bytes") or 0)
        existing = agg.setdefault(process, {"rx_bytes": 0, "tx_bytes": 0})
        existing["rx_bytes"] += rx
        existing["tx_bytes"] += tx
    return agg


def _candidate_hogs(agg: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    """Convert aggregated per-process totals into sorted, classified rows.

    Rates are reported as ``kbps = bytes * 8 / sample_seconds / 1000``.
    For a 1-second ``nettop -l 1`` window the math simplifies to bytes/125.
    """
    candidates: List[Dict[str, Any]] = []
    for process, totals in agg.items():
        label = _friendly_label(process)
        if not label:
            continue
        rx = int(totals.get("rx_bytes") or 0)
        tx = int(totals.get("tx_bytes") or 0)
        rx_kbps = rx * 8 / 1000.0
        tx_kbps = tx * 8 / 1000.0
        direction = _classify_process(process)
        # Pick the dominant direction for thresholds.
        dominant_kbps = tx_kbps if direction == "upload" else rx_kbps
        threshold = _UPLOAD_HOG_THRESHOLD_KBPS if direction == "upload" else _DOWNLOAD_HOG_THRESHOLD_KBPS
        candidates.append({
            "process": process,
            "label": label,
            "direction": direction,
            "rx_kbps": round(rx_kbps, 1),
            "tx_kbps": round(tx_kbps, 1),
            "rate_kbps": round(dominant_kbps, 1),
            "threshold_kbps": threshold,
            "is_hog": dominant_kbps >= threshold,
        })
    candidates.sort(key=lambda item: (not item["is_hog"], -item["rate_kbps"]))
    return candidates


def _summarize(hogs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the user-facing diagnostic details dict."""
    top = hogs[:_MAX_HOGS]
    any_upload = any(item["direction"] in {"upload", "mixed"} and item["is_hog"] for item in top)
    any_download = any(item["direction"] == "download" and item["is_hog"] for item in top)
    if any_upload:
        return {
            "reason": "upload_saturated",
            "headline": "检测到上行流量较高",
            "next_step": "如需优先保证实时应用，可先暂停百度网盘、OneDrive、iCloud、网盘或下载器的上传/同步。",
            "top_processes": top,
        }
    if any_download:
        return {
            "reason": "download_saturated",
            "headline": "检测到下行流量较高",
            "next_step": "如需优先保证实时应用，可先暂停下载器或系统更新。",
            "top_processes": top,
        }
    return {
        "reason": "no_significant_hog",
        "headline": "没有看到明显的后台占用",
        "next_step": "可以尝试重新诊断，或检查代理节点是否稳定。",
        "top_processes": top,
    }


@register("bandwidth_hog")
def bandwidth_hog(env: Dict[str, Any], core: Any, timeout: int = 8) -> Dict[str, Any]:
    """Return a coarse bandwidth-hog diagnostic.

    On macOS we sample nettop for one second. We deliberately do not run on
    Linux/Windows: the goal is a minimum-viable signal, not cross-platform
    coverage. Sampling failures are reported as ``status=unknown`` so the
    main diagnose path is never blocked.
    """
    rows, err = _sample_nettop()
    if rows is None:
        return diagnostic(
            "bandwidth_hog",
            "path",
            "unknown",
            {
                "reason": err or "sampler_unavailable",
                "headline": "暂时没法读取后台活动",
                "next_step": "这条诊断只在 macOS 上能用，需要先打开后台网络活动权限；Netfix 不会自己采集你的流量内容。",
                "top_processes": [],
                "sampler": "nettop",
            },
        )
    agg = _aggregate_by_process(rows)
    hogs = _candidate_hogs(agg)
    summary = _summarize(hogs)
    is_hog_active = any(item["is_hog"] for item in hogs[:_MAX_HOGS])
    status = "ok"
    if is_hog_active and summary["reason"] == "upload_saturated":
        status = "warn"
    elif is_hog_active and summary["reason"] == "download_saturated":
        status = "warn"
    elif summary["reason"] == "no_significant_hog" and hogs:
        status = "ok"
    return diagnostic(
        "bandwidth_hog",
        "path",
        status,
        {
            "reason": summary["reason"],
            "headline": summary["headline"],
            "next_step": summary["next_step"],
            "top_processes": summary["top_processes"],
            "sampler": "nettop",
            "sample_window_s": 1,
        },
    )
