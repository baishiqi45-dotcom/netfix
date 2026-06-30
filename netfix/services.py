"""Configurable overseas service list and grouped reachability probes."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from netfix.codex import _detect_system_proxy, check_endpoint
from netfix.constants import RULES_DIR

logger = logging.getLogger(__name__)

USER_SERVICES_DIR = Path.home() / "Library/Application Support/netfix"
USER_SERVICES_FILE = USER_SERVICES_DIR / "services.json"


def builtin_services_path() -> Path:
    return RULES_DIR / "services.json"


def user_services_path() -> Path:
    return USER_SERVICES_FILE


def _deep_merge(base: Any, override: Any) -> Any:
    """Recursively merge override into base.

    Dicts are merged. Lists of dicts that contain an ``id`` key are merged by
    ``id`` (new ids are appended); other lists are replaced.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = _deep_merge(result.get(key), value)
        return result
    if isinstance(base, list) and isinstance(override, list):
        if base and all(isinstance(x, dict) and "id" in x for x in base + override):
            by_id = {x["id"]: dict(x) for x in base}
            for item in override:
                iid = item["id"]
                if iid in by_id:
                    by_id[iid] = _deep_merge(by_id[iid], item)
                else:
                    by_id[iid] = dict(item)
            # Preserve original order, append new ids at the end.
            result = []
            seen = set()
            for x in base:
                if x["id"] in by_id and x["id"] not in seen:
                    result.append(by_id[x["id"]])
                    seen.add(x["id"])
            for iid, item in by_id.items():
                if iid not in seen:
                    result.append(item)
                    seen.add(iid)
            return result
        return list(override)
    return override


def load_services() -> Dict[str, Any]:
    """Load built-in service directory, optionally merged with user overrides."""
    data: Dict[str, Any] = {"version": "0.0.0", "groups": []}
    builtin = builtin_services_path()
    if builtin.exists():
        try:
            with builtin.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            logger.warning("Failed to load built-in services: %s", exc)

    user = user_services_path()
    if user.exists():
        try:
            with user.open("r", encoding="utf-8") as fh:
                user_data = json.load(fh)
            data = _deep_merge(data, user_data)
        except Exception as exc:
            logger.warning("Failed to load user services override: %s", exc)
    return data


def list_groups(services: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = services if services is not None else load_services()
    return data.get("groups", [])


def list_services(
    group_id: Optional[str] = None,
    services: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return services, optionally filtered by group id."""
    data = services if services is not None else load_services()
    result: List[Dict[str, Any]] = []
    for group in data.get("groups", []):
        if group_id is not None and group.get("id") != group_id:
            continue
        for svc in group.get("services", []):
            entry = dict(svc)
            entry["group"] = group.get("id")
            entry["group_name"] = group.get("name")
            result.append(entry)
    return result


def get_service(service_id: str, services: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    for svc in list_services(services=services):
        if svc.get("id") == service_id:
            return svc
    return None


def _build_proxy_modes(
    proxy_url: Optional[str] = None,
    mixed_port: Optional[int] = None,
    use_system_proxy: bool = True,
) -> List[Tuple[str, Optional[str]]]:
    """Return ordered proxy modes as (label, proxy_url)."""
    modes: List[Tuple[str, Optional[str]]] = [("direct", None)]
    if use_system_proxy:
        system_proxy, _ = _detect_system_proxy()
        if system_proxy:
            modes.append(("system", system_proxy))
    port = mixed_port or 10808
    modes.append((f"127.0.0.1:{port}", f"http://127.0.0.1:{port}"))
    if proxy_url:
        modes.append((proxy_url, proxy_url))
    return modes


def check_service(
    service: Dict[str, Any],
    proxy_modes: List[Tuple[str, Optional[str]]],
    timeout: int = 10,
) -> List[Dict[str, Any]]:
    """Probe a single service through all configured proxy modes."""
    results: List[Dict[str, Any]] = []
    for label, purl in proxy_modes:
        result = check_endpoint(
            name=service["id"],
            url=service["url"],
            path=service["path"],
            proxy_url=purl,
            proxy_used=label,
            timeout=timeout,
            expect=service.get("expect", 200),
        )
        # For reachability checks, any HTTP response from the server (2xx-4xx)
        # means the network path works.  Only 407 (proxy auth) and 5xx/server
        # errors are kept as warnings.
        http_code = result.get("http_code") or 0
        if result.get("status") == "warn" and 200 <= http_code < 500 and http_code != 407:
            result["status"] = "ok"
            details = result.setdefault("details", {})
            details["reachable"] = True
            if http_code in (401, 403):
                details["auth_required"] = True
                details["note"] = "服务可达，但返回 401/403，需要登录或 API key"
            elif http_code in (301, 302, 303, 307, 308):
                details["redirect"] = True
                details["note"] = "服务可达，返回重定向（3xx），网络路径正常"
            elif http_code == 404:
                details["note"] = "服务可达，但路径返回 404，可能该接口不存在"
            else:
                details["note"] = f"服务可达，返回 HTTP {http_code}"
        results.append(result)
    return results


def check_services(
    group_ids: Optional[List[str]] = None,
    proxy_url: Optional[str] = None,
    mixed_port: Optional[int] = None,
    use_system_proxy: bool = True,
    timeout: int = 5,
    parallel: bool = True,
) -> List[Dict[str, Any]]:
    """Probe all services in the given groups through all proxy modes."""
    data = load_services()
    if group_ids is None:
        group_ids = [g.get("id") for g in list_groups(data) if g.get("id")]
    proxy_modes = _build_proxy_modes(proxy_url, mixed_port, use_system_proxy)

    services_to_check: List[Dict[str, Any]] = []
    for group in data.get("groups", []):
        gid = group.get("id")
        if gid not in group_ids:
            continue
        for svc in group.get("services", []):
            services_to_check.append(svc)

    if not parallel or len(services_to_check) <= 1:
        results: List[Dict[str, Any]] = []
        for svc in services_to_check:
            results.extend(check_service(svc, proxy_modes, timeout))
        return results

    # Parallel across services; modes within one service stay sequential.
    lock = threading.Lock()
    all_results: List[Dict[str, Any]] = []
    errors: List[Exception] = []

    def worker(svc: Dict[str, Any]) -> None:
        try:
            res = check_service(svc, proxy_modes, timeout)
            with lock:
                all_results.extend(res)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(svc,)) for svc in services_to_check]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if errors:
        logger.warning("Some service probes failed: %s", errors)
    return all_results


def summarize_group(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-service reachability summary keyed by service id."""
    def reachable(r: Dict[str, Any]) -> bool:
        return r.get("status") != "fail" and (r.get("http_code") or 0) > 0

    by_service: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        by_service.setdefault(r["name"], []).append(r)

    summary: Dict[str, Any] = {}
    for name, items in by_service.items():
        direct = any(reachable(r) and r.get("proxy_used") == "direct" for r in items)
        proxy = any(reachable(r) and r.get("proxy_used") != "direct" for r in items)
        summary[name] = {
            "direct_ok": direct,
            "proxy_ok": proxy,
            "reachable": direct or proxy,
        }
    return summary


def codex_compat_diagnostics(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Derive legacy 'codex_api_direct' / 'codex_api_via_proxy' diagnostics.

    The legacy reasoner expects these names. This adapter lets us migrate to the
    service catalog without rewriting the reasoner in Phase 1.
    """
    compat: List[Dict[str, Any]] = []
    openai_direct = next(
        (r for r in results if r.get("name") == "openai_api" and r.get("proxy_used") == "direct"),
        None,
    )
    openai_proxy = next(
        (
            r
            for r in results
            if r.get("name") == "openai_api" and r.get("proxy_used") not in (None, "direct")
        ),
        None,
    )
    if openai_direct:
        compat.append({**openai_direct, "name": "codex_api_direct", "proxy_used": "direct"})
    if openai_proxy:
        compat.append({**openai_proxy, "name": "codex_api_via_proxy", "proxy_used": "proxy"})
    return compat
