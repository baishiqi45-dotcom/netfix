"""IP intelligence lookups with local caching.

Queries public IP APIs to determine the user's egress IP, ISP, ASN, and
whether the address is classified as hosting / proxy / VPN / high-risk.
Results are cached locally for one hour to reduce external requests.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import request
from urllib.error import URLError

from netfix.constants import JOURNAL_DIR
from netfix.utils import secure_write_json

CACHE_TTL_SECONDS = 3600
CACHE_FILE = Path(JOURNAL_DIR) / "ip_cache.json"


def _cache_load() -> Dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _cache_save(data: Dict[str, Any]) -> None:
    try:
        secure_write_json(CACHE_FILE, data)
    except OSError:
        pass


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    cache = _cache_load()
    entry = cache.get(key)
    if not entry or not isinstance(entry, dict):
        return None
    ts = entry.get("ts", 0)
    if time.time() - ts > CACHE_TTL_SECONDS:
        return None
    return entry.get("data")


def _cache_set(key: str, data: Dict[str, Any]) -> None:
    cache = _cache_load()
    cache[key] = {"ts": time.time(), "data": data}
    _cache_save(cache)


def _fetch_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    try:
        req = request.Request(url, headers={"User-Agent": "netfix/0.2"})
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except (URLError, json.JSONDecodeError, OSError, TimeoutError):
        return None


def current_ipv4(timeout: int = 10) -> Optional[str]:
    """Return the current public IPv4 address as seen by ip.sb."""
    data = _fetch_json("https://api.ip.sb/ip", timeout=timeout)
    if data and isinstance(data, str):
        return data.strip()
    # Fallback to ipify
    data = _fetch_json("https://api.ipify.org?format=json", timeout=timeout)
    if isinstance(data, dict):
        return data.get("ip")
    return None


def current_ipv6(timeout: int = 10) -> Optional[str]:
    """Return the current public IPv6 address, if available."""
    data = _fetch_json("https://api6.ip.sb/ip", timeout=timeout)
    if data and isinstance(data, str):
        return data.strip()
    data = _fetch_json("https://api6.ipify.org?format=json", timeout=timeout)
    if isinstance(data, dict):
        return data.get("ip")
    return None


def _query_ip_api(ip: Optional[str], timeout: int = 10) -> Optional[Dict[str, Any]]:
    target = ip or ""
    url = (
        f"http://ip-api.com/json/{target}?fields="
        "status,message,country,countryCode,region,regionName,city,"
        "isp,org,as,query,proxy,hosting"
    )
    data = _fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return None
    if data.get("status") != "success":
        return None
    return {
        "ip": data.get("query"),
        "country": data.get("country"),
        "country_code": data.get("countryCode"),
        "region": data.get("regionName"),
        "city": data.get("city"),
        "isp": data.get("isp"),
        "org": data.get("org"),
        "asn": data.get("as"),
        "proxy": bool(data.get("proxy")),
        "hosting": bool(data.get("hosting")),
        "source": "ip-api.com",
    }


def _query_ip_sb(ip: Optional[str], timeout: int = 10) -> Optional[Dict[str, Any]]:
    target = ip or ""
    url = f"https://api.ip.sb/geoip/{target}"
    data = _fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return None
    return {
        "ip": data.get("ip") or data.get("query"),
        "country": data.get("country"),
        "country_code": data.get("country_code"),
        "region": data.get("region"),
        "city": data.get("city"),
        "isp": data.get("isp"),
        "asn": data.get("asn"),
        "type": data.get("type"),
        "source": "ip.sb",
    }


def _query_proxycheck(ip: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Optional risk lookup via proxycheck.io free tier."""
    url = f"https://proxycheck.io/v2/{ip}?risk=1&vpn=1&asn=1"
    data = _fetch_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return None
    inner = data.get(ip)
    if not isinstance(inner, dict):
        return None
    return {
        "risk": inner.get("risk"),
        "vpn": bool(inner.get("vpn")),
        "proxy": bool(inner.get("proxy")),
        "type": inner.get("type"),
        "isp": inner.get("isp"),
        "asn": inner.get("asn"),
        "source": "proxycheck.io",
    }


def get_ip_info(ip: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
    """Return IP intelligence for *ip*, or the current public IP if None.

    The result merges ip-api.com (primary) and ip.sb (fallback). If
    proxycheck.io returns data it is merged as ``risk_info``.
    """
    if not ip:
        ip = current_ipv4(timeout=timeout)
    if not ip:
        return {"error": "unable to determine public IP", "status": "warn"}

    cached = _cache_get(ip)
    if cached:
        return dict(cached, cached=True)

    info = _query_ip_api(ip, timeout=timeout)
    if not info:
        info = _query_ip_sb(ip, timeout=timeout)
    if not info:
        return {"ip": ip, "error": "all IP lookup services failed", "status": "warn"}

    info.setdefault("ip", ip)
    info.setdefault("source", "unknown")

    # Best-effort risk score from proxycheck.io.
    risk = _query_proxycheck(ip, timeout=timeout)
    if risk:
        info["risk_info"] = risk
        if risk.get("risk") is not None:
            info["risk_score"] = risk["risk"]

    # Heuristic residential / datacenter classification.
    if info.get("hosting"):
        info["ip_type"] = "hosting/datacenter"
    elif info.get("type") in ("hosting", "datacenter"):
        info["ip_type"] = "hosting/datacenter"
    elif info.get("type") in ("residential", "isp"):
        info["ip_type"] = "residential"
    elif info.get("proxy") or info.get("vpn"):
        info["ip_type"] = "proxy/vpn"
    else:
        info["ip_type"] = "unknown"

    info["status"] = "ok"
    _cache_set(ip, info)
    return info


def get_dual_stack_ips(timeout: int = 10) -> Dict[str, Optional[str]]:
    """Return public IPv4 and IPv6 addresses."""
    return {
        "ipv4": current_ipv4(timeout),
        "ipv6": current_ipv6(timeout),
    }


def clear_cache() -> None:
    """Delete the local IP intelligence cache."""
    try:
        os.remove(CACHE_FILE)
    except FileNotFoundError:
        pass
