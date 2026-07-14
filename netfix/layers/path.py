"""Path / transit layer diagnostics: traceroute, mtr, networkQuality."""
from __future__ import annotations

import json
import re
import shutil
from typing import Any, Dict, List, Optional

from netfix.diagnose import register
from netfix.layers._helpers import diagnostic
from netfix.utils import run_command


def _parse_traceroute(stdout: str) -> List[Dict[str, Any]]:
    """Parse `traceroute` output into a list of hops."""
    hops: List[Dict[str, Any]] = []
    for line in stdout.splitlines():
        # Examples:
        #  1  192.168.1.1 (192.168.1.1)  2.123 ms  1.987 ms  2.045 ms
        #  2  * * *
        match = re.match(r"\s*(\d+)\s+(.+)", line)
        if not match:
            continue
        idx, rest = match.groups()
        if rest.strip() == "* * *" or rest.strip().startswith("*"):
            hops.append({"hop": int(idx), "host": None, "ip": None, "rtt_ms": None})
            continue
        # Extract host/ip and first rtt.
        host_ip_match = re.search(r"(\S+)\s+\(([\d.]+)\)", rest)
        rtt_match = re.search(r"(\d+(?:\.\d+)?)\s*ms", rest)
        if host_ip_match:
            host, ip = host_ip_match.groups()
            rtt = float(rtt_match.group(1)) if rtt_match else None
            hops.append({"hop": int(idx), "host": host, "ip": ip, "rtt_ms": rtt})
    return hops


def _parse_mtr(stdout: str) -> List[Dict[str, Any]]:
    """Parse `mtr -r` report output."""
    hops: List[Dict[str, Any]] = []
    for line in stdout.splitlines():
        # Skip headers.
        if not line.strip() or line.startswith("HOST:") or line.startswith("Start:"):
            continue
        if "Loss%" in line or "Snt" in line:
            continue
        # Typical field order: HOST, Loss%, Snt, Last, Avg, Best, Wrst, StDev
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            hop_no = int(parts[0])
        except ValueError:
            continue
        host = parts[1]
        if host == "???":
            host = None
        try:
            loss = float(parts[2].rstrip("%"))
        except ValueError:
            loss = None
        try:
            avg = float(parts[4])
        except (ValueError, IndexError):
            avg = None
        hops.append({"hop": hop_no, "host": host, "ip": None, "loss_percent": loss, "rtt_ms": avg})
    return hops


def _path_status(hops: List[Dict[str, Any]]) -> str:
    """Derive a status from traceroute/MTR hop data."""
    if not hops:
        return "warn"
    # First hop high loss = local problem.
    first = hops[0]
    if first.get("loss_percent") is not None and first["loss_percent"] > 5:
        return "fail"
    if first.get("rtt_ms") is not None and first["rtt_ms"] > 50:
        return "warn"
    # Last hop loss = real problem.
    last = hops[-1]
    if last.get("loss_percent") is not None and last["loss_percent"] > 5:
        return "fail"
    # Intermediate loss only is often ICMP deprioritization.
    mid_loss = any(
        h.get("loss_percent") is not None and h["loss_percent"] > 5
        for h in hops[1:-1]
    )
    if mid_loss:
        return "warn"
    return "ok"


@register("path_trace")
def path_trace(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Trace the route to a well-known target."""
    target = env.get("path_target", "8.8.8.8")
    mtr_bin = shutil.which("mtr")
    hops: List[Dict[str, Any]] = []
    tool = "traceroute"

    if mtr_bin:
        # Report mode, 10 probes, no DNS resolution.
        res = run_command(
            ["sudo", mtr_bin, "-r", "-n", "-c", "10", target],
            timeout=timeout,
        )
        if res["ok"]:
            hops = _parse_mtr(res["stdout"])
            tool = "mtr"

    if not hops:
        res = run_command(["traceroute", "-n", "-m", "15", "-w", "2", target], timeout=timeout)
        if res["ok"]:
            hops = _parse_traceroute(res["stdout"])

    if not hops:
        return diagnostic(
            "path_trace",
            "path",
            "warn",
            {"target": target, "error": "unable to run traceroute/mtr"},
        )

    status = _path_status(hops)
    return diagnostic(
        "path_trace",
        "path",
        status,
        {"target": target, "tool": tool, "hops": hops, "hop_count": len(hops)},
    )


@register("network_quality")
def network_quality(env: Dict[str, Any], core: Any, timeout: int = 30) -> Dict[str, Any]:
    """Run Apple's `networkQuality` responsiveness test."""
    if shutil.which("networkQuality") is None:
        return diagnostic(
            "network_quality",
            "path",
            "warn",
            {"error": "networkQuality not available"},
        )

    res = run_command(["networkQuality", "-c"], timeout=timeout)
    if not res["ok"]:
        return diagnostic(
            "network_quality",
            "path",
            "warn",
            {"error": res["stderr"], "stdout": res["stdout"]},
        )

    text = res["stdout"]
    # Try JSON first, fall back to regex.
    data: Optional[Dict[str, Any]] = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        pass

    if data:
        base_rtt = data.get("base_rtt", data.get("baseRTT"))
        dl = data.get("dl_throughput")
        ul = data.get("ul_throughput")
        rpm = data.get("responsiveness")
    else:
        base_rtt = _re_float(r"baseRTT\s*[:=]\s*([\d.]+)", text)
        dl = _re_float(r"dl_throughput\s*[:=]\s*([\d.]+)", text)
        ul = _re_float(r"ul_throughput\s*[:=]\s*([\d.]+)", text)
        rpm = _re_float(r"responsiveness\s*[:=]\s*([\d.]+)", text)

    # Apple's compact output reports throughput in bits per second. The
    # dashboard contract stores kbit/s so it can format Mbps without inflating
    # the value by 1000x.
    dl_kbps = float(dl) / 1000.0 if dl is not None else None
    ul_kbps = float(ul) / 1000.0 if ul is not None else None

    status = "ok"
    if rpm is not None and rpm < 50:
        status = "fail"
    elif rpm is not None and rpm < 200:
        status = "warn"
    elif base_rtt is not None and base_rtt > 200:
        status = "warn"

    return diagnostic(
        "network_quality",
        "path",
        status,
        {
            "base_rtt_ms": base_rtt,
            "dl_throughput_kbps": dl_kbps,
            "ul_throughput_kbps": ul_kbps,
            "responsiveness_rpm": rpm,
        },
    )


def _re_float(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None
