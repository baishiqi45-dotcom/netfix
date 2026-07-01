"""Residential/custom proxy profile parsing and safe apply planning."""
from __future__ import annotations

import json
import subprocess
import sys
import re
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlsplit

from netfix import codex, ip_intel, keychain, proxy_bridge
from netfix.constants import JOURNAL_DIR
from netfix.settings import delete_proxy_profile as delete_stored_proxy_profile
from netfix.settings import get_proxy_profiles, upsert_proxy_profile
from netfix.utils import secure_write_json


SUPPORTED_PROTOCOLS = {"http", "https", "socks5", "socks5h"}
BUNDLE_IMPORT_DEFAULT_LIMIT = 50
BUNDLE_IMPORT_MAX_LIMIT = 200
PROXY_APPLY_JOURNAL = JOURNAL_DIR / "proxy_apply_journal.json"
SYSTEM_APPLY_CONFIRMATION = "APPLY_PROXY_PROFILE"
PROXY_ROLLBACK_CONFIRMATION = "ROLLBACK_PROXY_PROFILE"
BRIDGE_RECOVERY_CONFIRMATION = "RESTORE_STALE_PROXY_BRIDGE"
BRIDGE_RESTART_CONFIRMATION = "RESTART_STALE_PROXY_BRIDGE"
ALLOWED_VALIDATION_TARGET_HOSTS = {
    "www.gstatic.com",
    "cp.cloudflare.com",
    "www.apple.com",
    "captive.apple.com",
    "api.github.com",
    "github.com",
    "api.openai.com",
    "api.deepseek.com",
    "api.moonshot.cn",
    "api.minimaxi.com",
}
EXIT_IDENTITY_URL = "https://api.ipify.org?format=json"
DEFAULT_TARGET_PROBES = [
    {
        "id": "google_204",
        "label": "Google connectivity probe",
        "url": "https://www.gstatic.com/generate_204",
        "ok_codes": {200, 204},
    },
    {
        "id": "cloudflare_204",
        "label": "Cloudflare captive portal probe",
        "url": "https://cp.cloudflare.com/generate_204",
        "ok_codes": {200, 204},
    },
    {
        "id": "apple_captive",
        "label": "Apple captive portal probe",
        "url": "https://captive.apple.com/hotspot-detect.html",
        "ok_codes": {200},
    },
]
AI_DEV_TARGET_PROBES = [
    {
        "id": "github_api",
        "label": "GitHub API",
        "url": "https://api.github.com/rate_limit",
        "ok_codes": {200, 403},
    },
    {
        "id": "github_web",
        "label": "GitHub web",
        "url": "https://github.com/",
        "ok_codes": {200, 301, 302},
    },
    {
        "id": "openai_api",
        "label": "OpenAI API",
        "url": "https://api.openai.com/v1/models",
        "ok_codes": {200, 401, 403},
    },
    {
        "id": "deepseek_api",
        "label": "DeepSeek API",
        "url": "https://api.deepseek.com/v1/models",
        "ok_codes": {200, 401, 403},
    },
    {
        "id": "kimi_api",
        "label": "Kimi/Moonshot API",
        "url": "https://api.moonshot.cn/v1/models",
        "ok_codes": {200, 401, 403},
    },
    {
        "id": "minimax_api",
        "label": "MiniMax API",
        "url": "https://api.minimaxi.com/v1/models",
        "ok_codes": {200, 401, 403, 404},
    },
]
VALIDATION_TARGET_PROFILES = {
    "baseline": {
        "id": "baseline",
        "label": "通用连通性",
        "description": "Google/Cloudflare/Apple captive portal probes for basic proxy health.",
        "probes": DEFAULT_TARGET_PROBES,
    },
    "ai_dev": {
        "id": "ai_dev",
        "label": "AI / 开发工具",
        "description": "Baseline probes plus GitHub, OpenAI, DeepSeek, Kimi/Moonshot, and MiniMax API reachability.",
        "probes": DEFAULT_TARGET_PROBES + AI_DEV_TARGET_PROBES,
    },
}


def _public_probe(probe: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "id": probe.get("id"),
        "label": probe.get("label"),
        "url": probe.get("url"),
        "host": (urlsplit(str(probe.get("url") or "")).hostname or ""),
    }
    ok_codes = probe.get("ok_codes") or set()
    item["ok_codes"] = sorted(int(code) for code in ok_codes)
    return item


def validation_target_profiles() -> Dict[str, Any]:
    """Return supported allowlisted validation target matrices."""
    profiles = []
    for profile in VALIDATION_TARGET_PROFILES.values():
        profiles.append({
            "id": profile["id"],
            "label": profile["label"],
            "description": profile["description"],
            "probes": [_public_probe(probe) for probe in profile["probes"]],
        })
    return {
        "ok": True,
        "schema_version": "netfix_proxy_validation_targets.v1",
        "default_profile": "baseline",
        "profiles": profiles,
        "allowed_hosts": sorted(ALLOWED_VALIDATION_TARGET_HOSTS),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(host: str, protocol: str) -> str:
    prefix = host.split(".")[0] if host else "proxy"
    prefix = re.sub(r"[^A-Za-z0-9_-]+", "-", prefix).strip("-") or "proxy"
    return f"{prefix}-{protocol}"


def _redacted_url(protocol: str, host: str, port: int, username: str = "") -> str:
    auth = f"{quote(username, safe='')}:***@" if username else ""
    return f"{protocol}://{auth}{host}:{port}"


def _proxy_url(profile: Dict[str, Any], password: str = "") -> str:
    protocol = str(profile.get("protocol") or "http")
    host = str(profile.get("host") or "")
    port = int(profile.get("port") or 0)
    username = str(profile.get("username") or "")
    if username:
        auth = quote(username, safe="")
        if password:
            auth += ":" + quote(password, safe="")
        return f"{protocol}://{auth}@{host}:{port}"
    return f"{protocol}://{host}:{port}"


def _redacted_proxy_env(profile: Dict[str, Any]) -> Dict[str, str]:
    protocol = str(profile.get("protocol") or "http")
    host = str(profile.get("host") or "")
    port = int(profile.get("port") or 0)
    username = str(profile.get("username") or "")
    proxy = _redacted_url(protocol, host, port, username)
    if protocol in {"socks5", "socks5h"}:
        return {"ALL_PROXY": proxy}
    return {"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy}


def _placeholder_proxy_env(profile: Dict[str, Any]) -> Dict[str, str]:
    protocol = str(profile.get("protocol") or "http")
    proxy = _placeholder_proxy_url(profile)
    if protocol in {"socks5", "socks5h"}:
        return {"ALL_PROXY": proxy}
    return {"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy}


def _placeholder_proxy_url(profile: Dict[str, Any]) -> str:
    """Return a copyable proxy URL with placeholders instead of secrets."""
    protocol = str(profile.get("protocol") or "http")
    host = str(profile.get("host") or "")
    port = int(profile.get("port") or 0)
    username = str(profile.get("username") or "")
    if username:
        return f"{protocol}://{quote(username, safe='')}:<password>@{host}:{port}"
    return f"{protocol}://{host}:{port}"


def _client_protocol(profile: Dict[str, Any]) -> str:
    protocol = str(profile.get("protocol") or "http").lower()
    return "socks5" if protocol == "socks5h" else protocol


def _clash_node(profile: Dict[str, Any]) -> Dict[str, Any]:
    protocol = str(profile.get("protocol") or "http").lower()
    node_type = "socks5" if protocol in {"socks5", "socks5h"} else "http"
    node: Dict[str, Any] = {
        "name": str(profile.get("name") or profile.get("id") or "netfix-proxy"),
        "type": node_type,
        "server": str(profile.get("host") or ""),
        "port": int(profile.get("port") or 0),
    }
    username = str(profile.get("username") or "")
    if username:
        node["username"] = username
        node["password"] = "<password>"
    if protocol == "socks5h":
        node["udp"] = True
        node["dialer-proxy"] = ""
    return node


def _client_export_slug(profile: Dict[str, Any]) -> str:
    raw = str(profile.get("name") or profile.get("id") or profile.get("host") or "netfix-proxy")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-._")
    return slug or "netfix-proxy"


def _simple_yaml(value: Any, indent: int = 0) -> str:
    """Serialize the small YAML subset needed for proxy client snippets."""
    space = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.append(_simple_yaml(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {json.dumps(item, ensure_ascii=False)}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{space}-")
                lines.append(_simple_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {json.dumps(item, ensure_ascii=False)}")
        return "\n".join(lines)
    return f"{space}{json.dumps(value, ensure_ascii=False)}"


def _client_package_readme(profile: Dict[str, Any], selected_formats: List[str], warnings: List[str]) -> str:
    protocol = str(profile.get("protocol") or "proxy")
    username = str(profile.get("username") or "")
    lines = [
        "# Netfix proxy client package",
        "",
        "This package is generated for a proxy credential you supplied to Netfix.",
        "Netfix does not sell proxies and this export does not include the saved Keychain password.",
        "",
        "## Files",
    ]
    for fmt in selected_formats:
        lines.append(f"- `{fmt}`: copy the matching file into the target client or use it as a snippet.")
    if username:
        lines.extend([
            "",
            "## Password placeholder",
            "Replace every `<password>` placeholder with the password from your proxy provider inside the target client.",
            "Do not paste the real password back into Netfix logs, support chats, or screenshots.",
        ])
    if protocol == "socks5h":
        lines.extend([
            "",
            "## DNS note",
            "`socks5h://` means remote DNS in tools that support it, but not every GUI client preserves that semantics.",
            "Enable remote DNS or rules DNS in the target client when available.",
        ])
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend([
        "",
        "## Safe boundary",
        "Authenticated SOCKS can be applied to macOS Web/Secure Web proxy traffic through the Netfix loopback bridge after explicit confirmation.",
        "Keep Netfix running while the bridge is active, or use rollback/recovery before quitting.",
    ])
    return "\n".join(lines) + "\n"


def export_client_profile(profile: Dict[str, Any], fmt: str = "all") -> Dict[str, Any]:
    """Return safe copy/paste snippets for proxy clients without secrets.

    The snippets use ``<password>`` placeholders when the profile has
    authentication. Netfix does not read or return the saved Keychain secret.
    """
    protocol = str(profile.get("protocol") or "").lower()
    host = str(profile.get("host") or "")
    try:
        port = int(profile.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    if protocol not in SUPPORTED_PROTOCOLS or not host or port <= 0:
        return {"ok": False, "error": "invalid profile"}

    fmt = str(fmt or "all").lower()
    supported = {"all", "url", "env", "clash", "mihomo", "sing-box"}
    if fmt not in supported:
        return {"ok": False, "error": f"unsupported export format: {fmt}", "supported_formats": sorted(supported)}

    redacted_url = _redacted_url(protocol, host, port, str(profile.get("username") or ""))
    placeholder_url = _placeholder_proxy_url(profile)
    node = _clash_node(profile)
    clash_yaml = _simple_yaml({"proxies": [node], "proxy-groups": [{"name": "Netfix", "type": "select", "proxies": [node["name"]]}]})
    client_proto = _client_protocol(profile)
    sing_box = {
        "outbounds": [
            {
                "type": "socks" if client_proto == "socks5" else "http",
                "tag": str(profile.get("name") or profile.get("id") or "netfix-proxy"),
                "server": host,
                "server_port": port,
            }
        ]
    }
    username = str(profile.get("username") or "")
    if username:
        sing_box["outbounds"][0]["username"] = username
        sing_box["outbounds"][0]["password"] = "<password>"

    snippets = {
        "url": {
            "label": "Generic proxy URL",
            "content": placeholder_url,
            "secret_placeholder": "<password>" in placeholder_url,
        },
        "env": {
            "label": "Shell environment",
            "content": "\n".join(f"export {key}='{value}'" for key, value in _placeholder_proxy_env(profile).items()),
            "secret_placeholder": username != "",
        },
        "clash": {
            "label": "Clash/Mihomo YAML snippet",
            "content": clash_yaml,
            "secret_placeholder": username != "",
        },
        "mihomo": {
            "label": "Mihomo YAML snippet",
            "content": clash_yaml,
            "secret_placeholder": username != "",
        },
        "sing-box": {
            "label": "sing-box outbound JSON snippet",
            "content": json.dumps(sing_box, ensure_ascii=False, indent=2),
            "secret_placeholder": username != "",
        },
    }

    selected = snippets if fmt == "all" else {fmt: snippets[fmt]}
    warnings = []
    if username:
        warnings.append("导出内容不会包含本机密码库里的代理密码；需要在客户端里把 <password> 替换为供应商密码。")
    if protocol == "socks5h":
        warnings.append("socks5h:// 的远程 DNS 语义不一定被每个客户端保留；请在目标客户端里启用远程 DNS/规则 DNS。")
    slug = _client_export_slug(profile)
    file_names = {
        "url": f"{slug}.proxy-url.txt",
        "env": f"{slug}.env.sh",
        "clash": f"{slug}.clash.yaml",
        "mihomo": f"{slug}.mihomo.yaml",
        "sing-box": f"{slug}.sing-box.json",
    }
    selected_formats = list(selected.keys())
    package_files = [{
        "path": "README.md",
        "format": "readme",
        "label": "First-run instructions",
        "content": _client_package_readme(profile, selected_formats, warnings),
        "secret_placeholder": False,
    }]
    for key, snippet in selected.items():
        package_files.append({
            "path": file_names[key],
            "format": key,
            "label": snippet["label"],
            "content": snippet["content"],
            "secret_placeholder": bool(snippet.get("secret_placeholder")),
        })
    recommended_format = "mihomo" if protocol in {"socks5", "socks5h"} else "url"
    return {
        "ok": True,
        "profile_id": profile.get("id"),
        "profile_name": profile.get("name"),
        "format": fmt,
        "redacted_url": redacted_url,
        "snippets": selected,
        "package": {
            "schema_version": "netfix_proxy_client_package.v1",
            "name": slug,
            "recommended_format": recommended_format if recommended_format in selected else selected_formats[0],
            "files": package_files,
            "file_count": len(package_files),
            "secret_placeholder": username != "",
            "warnings": warnings,
        },
        "warnings": warnings,
    }


def _bridge_system_profile(bridge: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": source.get("id"),
        "name": f"{source.get('name') or source.get('id')}-bridge",
        "protocol": "http",
        "host": bridge.get("listen_host") or "127.0.0.1",
        "port": int(bridge.get("listen_port") or 0),
        "username": "",
        "credential_ref": "",
    }


def _has_auth(profile: Dict[str, Any]) -> bool:
    return bool(profile.get("credential_ref") or profile.get("username"))


def deployment_decision(profile: Dict[str, Any], errors: Optional[List[str]] = None) -> Dict[str, Any]:
    """Return a user-facing support matrix for deploying a proxy profile."""
    errors = [str(item) for item in (errors or []) if str(item)]
    protocol = str(profile.get("protocol") or "").lower()
    host = str(profile.get("host") or "")
    try:
        port = int(profile.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    has_auth = _has_auth(profile) or bool(profile.get("password_set"))
    missing_fields: List[str] = []
    if not host:
        missing_fields.append("host")
    if port <= 0 or port > 65535 or any("port" in item.lower() for item in errors):
        missing_fields.append("port")
    if any("username" in item.lower() for item in errors):
        missing_fields.append("username")
    if protocol not in SUPPORTED_PROTOCOLS:
        missing_fields.append("protocol")
    missing_fields = sorted(set(missing_fields))

    base = {
        "schema_version": "netfix_proxy_deployment_decision.v1",
        "protocol": protocol or "unknown",
        "credential_present": bool(has_auth),
        "missing_fields": missing_fields,
        "client_export": {
            "status": "available",
            "formats": ["mihomo", "sing-box", "clash", "env", "url"],
            "secret_placeholder": bool(has_auth),
        },
        "app_env": {
            "status": "supported",
            "label": "可为子进程注入代理环境变量",
            "secret_source": "keychain" if has_auth else "none",
        },
        "monitor": {
            "status": "available_after_save",
            "label": "保存并验证后可启动持续健康监控",
        },
        "warnings": [],
        "next_steps": [],
    }
    if errors:
        base.update({
            "status": "blocked",
            "headline": "代理信息不完整，先修正供应商凭据格式",
            "primary_action": "fix_input",
            "system_apply": {
                "status": "blocked",
                "reason_code": "invalid_proxy_input",
                "label": "缺少必需字段，不能应用到系统",
                "requires_confirmation": False,
                "requires_netfix_running": False,
            },
            "next_steps": [
                "补齐主机、端口、用户名或密码后重新解析。",
                "优先粘贴供应商提供的完整 URL，或使用 host:port:user:pass 格式。",
            ],
        })
        return base

    if protocol in {"http", "https"} and has_auth:
        base.update({
            "status": "ready",
            "headline": "可以开始使用这台 Mac 上网：有账号密码的 HTTP/HTTPS 代理会由 Netfix 本机转发",
            "primary_action": "save_validate_apply_system",
            "system_apply": {
                "status": "bridge_required",
                "reason_code": "authenticated_http_bridge_required",
                "label": "保存到本机密码库后，可以让这台 Mac 使用；系统先连 127.0.0.1，再由 Netfix 带着账号密码转发到供应商代理",
                "requires_confirmation": True,
                "requires_netfix_running": True,
            },
            "next_steps": [
                "保存到本机密码库后验证出口身份和地区。",
                "验证通过后点“开始使用这台 Mac 上网”；使用期间需要保持 Netfix 运行。",
                "启动后台监控，失效时提示回滚或恢复桥接。",
            ],
        })
        return base

    if protocol in {"http", "https"}:
        base.update({
            "status": "ready",
            "headline": "可以开始使用这台 Mac 上网：无账号密码的 HTTP/HTTPS 代理可直接写入系统代理",
            "primary_action": "save_validate_apply_system",
            "system_apply": {
                "status": "supported",
                "reason_code": "system_http_supported_without_auth",
                "label": "验证通过后，可以让这台 Mac 使用 Web/Secure Web 代理",
                "requires_confirmation": True,
                "requires_netfix_running": False,
            },
            "next_steps": [
                "保存并验证出口身份。",
                "验证通过后点“开始使用这台 Mac 上网”，再启动健康监控。",
            ],
        })
        return base

    if protocol in {"socks5", "socks5h"} and has_auth:
        base.update({
            "status": "ready",
            "headline": "可以开始使用这台 Mac 上网：有账号密码的 SOCKS 代理会由 Netfix 本机转发",
            "primary_action": "save_validate_apply_system",
            "system_apply": {
                "status": "bridge_required",
                "reason_code": "authenticated_socks_bridge_required",
                "label": "保存到本机密码库后，可以让这台 Mac 使用；系统先连 127.0.0.1，再由 Netfix 转发到 SOCKS 代理",
                "requires_confirmation": True,
                "requires_netfix_running": True,
            },
            "warnings": [
                "有账号密码的 SOCKS 代理会走 Netfix 本机转发；使用期间需要保持 Netfix 运行。",
            ],
            "next_steps": [
                "保存到本机密码库后验证出口身份。",
                "验证通过后点“开始使用这台 Mac 上网”；Netfix 会启动 127.0.0.1 本机转发并使用已保存的账号密码。",
                "启动后台监控，失效时提示回滚或恢复桥接；也可以导出 Mihomo/sing-box/Clash 配置作为备用。",
            ],
        })
        return base

    base.update({
        "status": "ready",
        "headline": "可以开始使用这台 Mac 上网：无账号密码的 SOCKS 代理可写入系统 SOCKS 代理",
        "primary_action": "save_validate_apply_system",
        "system_apply": {
            "status": "supported",
            "reason_code": "system_socks_supported_without_auth",
            "label": "验证通过后可应用到系统 SOCKS 代理",
            "requires_confirmation": True,
            "requires_netfix_running": False,
        },
        "next_steps": [
            "保存并验证出口身份。",
            "验证通过后点“开始使用这台 Mac 上网”，再启动健康监控。",
        ],
    })
    if protocol == "socks5":
        base["warnings"].append("socks5:// 通常由本机解析 DNS；如需代理端解析 DNS，请使用 socks5h:// 或客户端配置。")
    return base


def _target_url_allowed(target_url: str) -> bool:
    try:
        split = urlsplit(target_url)
    except Exception:
        return False
    return split.scheme in {"https", "http"} and (split.hostname or "").lower() in ALLOWED_VALIDATION_TARGET_HOSTS


def _run_networksetup(args: List[str], timeout: int = 15) -> Dict[str, Any]:
    """Run networksetup and return a structured result."""
    proc = subprocess.run(
        ["networksetup", *args],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    result = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "args": ["networksetup", *args],
    }
    if not result["ok"]:
        raise RuntimeError(result["stderr"] or result["stdout"] or "networksetup failed")
    return result


def _parse_networksetup_fields(output: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"yes", "on", "1", "true", "enabled"}


def _parse_proxy_state(output: str) -> Dict[str, Any]:
    fields = _parse_networksetup_fields(output)
    return {
        "raw": output,
        "enabled": _truthy(fields.get("enabled", "")),
        "server": fields.get("server", ""),
        "port": int(fields.get("port") or 0) if str(fields.get("port") or "").isdigit() else 0,
        "authenticated": _truthy(fields.get("authenticated proxy enabled", "")),
    }


def _parse_auto_proxy_url_state(output: str) -> Dict[str, Any]:
    fields = _parse_networksetup_fields(output)
    return {
        "raw": output,
        "enabled": _truthy(fields.get("enabled", "")),
        "url": fields.get("url", ""),
    }


def _parse_autodiscovery_state(output: str) -> Dict[str, Any]:
    fields = _parse_networksetup_fields(output)
    if fields:
        value = next(iter(fields.values()), "")
    else:
        value = output.strip()
    return {"raw": output, "enabled": _truthy(value)}


def _parse_ipv6_state(output: str) -> Dict[str, Any]:
    fields = _parse_networksetup_fields(output)
    mode_raw = fields.get("ipv6", "")
    mode = mode_raw.strip().lower()
    address = fields.get("ipv6 ip address", "")
    router = fields.get("ipv6 router", "")
    prefix = fields.get("ipv6 prefix length", "") or fields.get("prefix length", "")
    if "off" in mode or "disabled" in mode:
        normalized = "off"
    elif "automatic" in mode or "auto" in mode:
        normalized = "automatic"
    elif "manual" in mode:
        normalized = "manual"
    else:
        normalized = "unknown"
    restorable = normalized in {"off", "automatic"} or (
        normalized == "manual" and bool(address and prefix and router)
    )
    return {
        "raw": output,
        "mode": normalized,
        "mode_raw": mode_raw,
        "enabled": normalized not in {"off", "unknown"},
        "address": address,
        "router": router,
        "prefix_length": prefix,
        "restorable": restorable,
    }


def list_network_services() -> List[str]:
    """Return configured macOS network services."""
    result = _run_networksetup(["-listallnetworkservices"])
    services = []
    for line in result["stdout"].splitlines():
        item = line.strip()
        if not item or item.startswith("An asterisk") or item.startswith("*"):
            continue
        services.append(item)
    return services


def _default_route_interface() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "interface":
            return value.strip()
    return ""


def _network_service_for_device(device: str, services: List[str]) -> str:
    if not device:
        return ""
    try:
        output = _run_networksetup(["-listallhardwareports"])["stdout"]
    except Exception:
        return ""
    current_port = ""
    for line in output.splitlines():
        item = line.strip()
        if item.startswith("Hardware Port:"):
            current_port = item.split(":", 1)[1].strip()
            continue
        if item.startswith("Device:"):
            current_device = item.split(":", 1)[1].strip()
            if current_device == device and current_port in services:
                return current_port
    return ""


def choose_network_service(requested: str = "") -> str:
    """Choose a likely active macOS network service without mutating state."""
    services = list_network_services()
    if requested:
        if requested not in services:
            raise RuntimeError(f"network service not found: {requested}")
        return requested
    active_service = _network_service_for_device(_default_route_interface(), services)
    if active_service:
        return active_service
    for preferred in ("Wi-Fi", "USB 10/100/1000 LAN", "Ethernet"):
        if preferred in services:
            return preferred
    if not services:
        raise RuntimeError("no network services found")
    return services[0]


def _capture_system_proxy_backup(service: str) -> Dict[str, Any]:
    web = _parse_proxy_state(_run_networksetup(["-getwebproxy", service])["stdout"])
    secure = _parse_proxy_state(_run_networksetup(["-getsecurewebproxy", service])["stdout"])
    socks = _parse_proxy_state(_run_networksetup(["-getsocksfirewallproxy", service])["stdout"])
    auto_url = _parse_auto_proxy_url_state(_run_networksetup(["-getautoproxyurl", service])["stdout"])
    autodiscovery = _parse_autodiscovery_state(_run_networksetup(["-getproxyautodiscovery", service])["stdout"])
    ipv6 = _parse_ipv6_state(_run_networksetup(["-getinfo", service])["stdout"])
    return {
        "service": service,
        "web": web,
        "secure": secure,
        "socks": socks,
        "auto_proxy_url": auto_url,
        "auto_discovery": autodiscovery,
        "ipv6": ipv6,
    }


def _backup_has_authenticated_proxy(backup: Dict[str, Any]) -> bool:
    return any(bool(backup.get(kind, {}).get("authenticated")) for kind in ("web", "secure", "socks"))


def _restore_proxy_kind(service: str, kind: str, state: Dict[str, Any]) -> List[List[str]]:
    commands: List[List[str]] = []
    if kind == "web":
        set_cmd = "-setwebproxy"
        state_cmd = "-setwebproxystate"
    elif kind == "secure":
        set_cmd = "-setsecurewebproxy"
        state_cmd = "-setsecurewebproxystate"
    elif kind == "socks":
        set_cmd = "-setsocksfirewallproxy"
        state_cmd = "-setsocksfirewallproxystate"
    else:
        raise ValueError(f"unsupported proxy kind: {kind}")

    if state.get("enabled") and state.get("server") and state.get("port"):
        commands.append([set_cmd, service, str(state["server"]), str(state["port"])])
        commands.append([state_cmd, service, "on"])
    else:
        commands.append([state_cmd, service, "off"])
    return commands


def _restore_ipv6_commands(service: str, state: Dict[str, Any]) -> List[List[str]]:
    mode = str(state.get("mode") or "")
    if mode == "off":
        return [["-setv6off", service]]
    if mode == "automatic":
        return [["-setv6automatic", service]]
    if mode == "manual" and state.get("address") and state.get("prefix_length") and state.get("router"):
        return [[
            "-setv6manual",
            service,
            str(state["address"]),
            str(state["prefix_length"]),
            str(state["router"]),
        ]]
    return []


def _disable_ipv6_commands(service: str, backup: Dict[str, Any]) -> List[List[str]]:
    state = backup.get("ipv6") if isinstance(backup.get("ipv6"), dict) else {}
    if not state or state.get("mode") == "off" or not state.get("restorable"):
        return []
    return [["-setv6off", service]]


def _restore_system_proxy_backup(backup: Dict[str, Any]) -> Dict[str, Any]:
    service = str(backup.get("service") or "")
    if not service:
        return {"ok": False, "error": "rollback journal is missing network service"}
    if _backup_has_authenticated_proxy(backup):
        return {
            "ok": False,
            "error": "current rollback backup included an authenticated system proxy that cannot be restored without exposing a password",
            "reason_code": "authenticated_proxy_backup_not_restorable",
        }
    commands: List[List[str]] = []
    for kind in ("web", "secure", "socks"):
        commands.extend(_restore_proxy_kind(service, kind, backup.get(kind, {})))

    auto_url = backup.get("auto_proxy_url", {})
    if auto_url.get("enabled") and auto_url.get("url"):
        commands.append(["-setautoproxyurl", service, str(auto_url["url"])])
        commands.append(["-setautoproxystate", service, "on"])
    else:
        commands.append(["-setautoproxystate", service, "off"])

    commands.append(["-setproxyautodiscovery", service, "on" if backup.get("auto_discovery", {}).get("enabled") else "off"])
    commands.extend(_restore_ipv6_commands(service, backup.get("ipv6", {})))

    executed = []
    for command in commands:
        _run_networksetup(command)
        executed.append({"args": ["networksetup", *command]})
    return {"ok": True, "network_service": service, "commands": executed}


def _write_apply_journal(entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"version": 1, "last_apply": entry}
    secure_write_json(PROXY_APPLY_JOURNAL, payload, sort_keys=True)
    return payload


def _read_apply_journal() -> Dict[str, Any]:
    if not PROXY_APPLY_JOURNAL.exists():
        return {}
    try:
        raw = json.loads(PROXY_APPLY_JOURNAL.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _current_bridge_record(bridge: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bridge_id = str(bridge.get("id") or "")
    host = str(bridge.get("listen_host") or "127.0.0.1")
    try:
        port = int(bridge.get("listen_port") or 0)
    except (TypeError, ValueError):
        port = 0
    for item in proxy_bridge.status().get("bridges", []):
        if bridge_id and item.get("id") == bridge_id:
            return item
        if item.get("listen_host") == host and int(item.get("listen_port") or 0) == port:
            return item
    return None


def _loopback_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    if host not in {"127.0.0.1", "localhost", "::1"} or port <= 0:
        return False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def _system_proxy_points_to_bridge(current: Dict[str, Any], bridge: Dict[str, Any]) -> bool:
    host = str(bridge.get("listen_host") or "127.0.0.1")
    try:
        port = int(bridge.get("listen_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if not host or not port:
        return False
    matches = []
    for kind in ("web", "secure"):
        state = current.get(kind, {})
        matches.append(
            bool(state.get("enabled"))
            and str(state.get("server") or "") == host
            and int(state.get("port") or 0) == port
        )
    return any(matches)


def _parse_colon_tuple(value: str) -> Optional[Dict[str, Any]]:
    parts = value.split(":", 3)
    if len(parts) == 4:
        host, port, username, password = parts
        if port.isdigit():
            return {
                "protocol": "http",
                "host": host,
                "port": int(port),
                "username": username,
                "password": password,
            }
    if len(parts) == 2 and parts[1].isdigit():
        return {
            "protocol": "http",
            "host": parts[0],
            "port": int(parts[1]),
            "username": "",
            "password": "",
        }
    return None


def _parse_userinfo_without_scheme(value: str) -> Optional[Dict[str, Any]]:
    if "@" not in value:
        return None
    auth, target = value.rsplit("@", 1)
    if ":" not in target:
        return None
    host, port_s = target.rsplit(":", 1)
    if not port_s.isdigit():
        return None
    username, _, password = auth.partition(":")
    return {
        "protocol": "http",
        "host": host,
        "port": int(port_s),
        "username": unquote(username),
        "password": unquote(password),
    }


def _is_proxy_table_header(value: str) -> bool:
    tokens = [part.strip().lower() for part in re.split(r"[\s,;\t]+", value.strip()) if part.strip()]
    if not tokens:
        return False
    has_host = any(token in {"host", "hostname", "server", "ip", "地址", "服务器"} for token in tokens)
    has_port = any(token in {"port", "端口"} for token in tokens)
    has_user = any(token in {"user", "username", "login", "account", "用户名", "账号"} for token in tokens)
    has_password = any(token in {"pass", "password", "pwd", "密码"} for token in tokens)
    return has_host and has_port and (has_user or has_password)


def _parse_table_row(value: str) -> Optional[Dict[str, Any]]:
    """Parse provider table rows such as host,port,user,pass or protocol host port user pass."""
    stripped = value.strip()
    if not stripped or _is_proxy_table_header(stripped):
        return None
    parts = [part.strip() for part in re.split(r"[\t,; ]+", stripped, maxsplit=4) if part.strip()]
    if len(parts) >= 4 and parts[1].isdigit():
        return {
            "protocol": "http",
            "host": parts[0],
            "port": int(parts[1]),
            "username": parts[2],
            "password": " ".join(parts[3:]),
        }
    if len(parts) >= 5 and parts[0].lower() in SUPPORTED_PROTOCOLS and parts[2].isdigit():
        return {
            "protocol": parts[0].lower(),
            "host": parts[1],
            "port": int(parts[2]),
            "username": parts[3],
            "password": parts[4],
        }
    return None


def _line_payload(raw_line: str, base: Dict[str, Any]) -> Dict[str, Any]:
    line = raw_line.strip()
    table = _parse_table_row(line)
    if table:
        payload = dict(base)
        payload.update(table)
        return payload
    payload = dict(base)
    payload["input"] = line
    return payload


def parse_proxy_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Parse common residential proxy credential formats.

    The returned object includes a redacted representation and never writes the
    password to disk.
    """
    raw = str(payload.get("input") or payload.get("url") or "").strip()
    protocol = str(payload.get("protocol") or "").strip().lower()
    host = str(payload.get("host") or "").strip()
    port = payload.get("port")
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    warnings: List[str] = []
    errors: List[str] = []

    parsed: Dict[str, Any] = {}
    protocol_defaulted_from_tuple = False
    if raw:
        if "://" in raw:
            split = urlsplit(raw)
            try:
                parsed_port = split.port
            except ValueError:
                parsed_port = None
                errors.append("port must be between 1 and 65535")
            parsed = {
                "protocol": split.scheme.lower(),
                "host": split.hostname or "",
                "port": parsed_port,
                "username": unquote(split.username or ""),
                "password": unquote(split.password or ""),
            }
        else:
            parsed = _parse_userinfo_without_scheme(raw) or _parse_colon_tuple(raw) or _parse_table_row(raw) or {}
            protocol_defaulted_from_tuple = bool(parsed) and not protocol
    if parsed:
        protocol = protocol or parsed.get("protocol", "")
        host = host or parsed.get("host", "")
        port = port if port not in (None, "") else parsed.get("port")
        username = username or parsed.get("username", "")
        password = password or parsed.get("password", "")

    protocol = protocol or "http"
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = 0

    if protocol not in SUPPORTED_PROTOCOLS:
        errors.append(f"unsupported protocol: {protocol}")
    if not host:
        errors.append("host is required")
    if (port_i <= 0 or port_i > 65535) and "port must be between 1 and 65535" not in errors:
        errors.append("port must be between 1 and 65535")
    if password and not username:
        errors.append("username is required when password is provided")
    if protocol == "https":
        warnings.append("https:// 表示连接到代理本身使用 TLS，不等同于普通 HTTP CONNECT 代理；请确认供应商文档。")
    if protocol == "socks5":
        warnings.append("socks5:// 通常由本机解析 DNS；如需代理端解析 DNS，请使用 socks5h://。")
    if protocol_defaulted_from_tuple:
        warnings.append("这行没有写代理类型，Netfix 先按 HTTP 代理处理；如果服务商标注 SOCKS5，请在参数类型里选择 SOCKS5。")
    if any(ch in username + password for ch in "@:/?#%"):
        warnings.append("用户名或密码含特殊字符，URL 形式粘贴时需要 percent-encode；netfix 内部会解码后安全处理。")

    profile_id = str(payload.get("id") or uuid.uuid4())
    credential_present = bool(username or password)
    profile = {
        "id": profile_id,
        "name": str(payload.get("name") or _safe_name(host, protocol)),
        "protocol": protocol,
        "host": host,
        "port": port_i,
        "username": username,
        "credential_ref": f"keychain://{keychain.PROXY_SERVICE}/{profile_id}" if credential_present else "",
        "provider": str(payload.get("provider") or ""),
        "expected_geo": payload.get("expected_geo") or {},
        "rotation": payload.get("rotation") or {"mode": "unknown", "ttl_seconds": None},
        "bypass_domains": payload.get("bypass_domains") or ["localhost", "*.local"],
    }
    public_profile = dict(profile)
    public_profile["username"] = username if username else ""
    public_profile["password_set"] = bool(password)
    decision = deployment_decision(public_profile, errors)

    return {
        "ok": not errors,
        "profile": public_profile,
        "redacted_url": _redacted_url(protocol, host, port_i, username) if not errors else "",
        "credential_present": credential_present,
        "deployment_decision": decision,
        "warnings": warnings,
        "errors": errors,
        "_secret": {"password": password} if password else {},
    }


def parse_proxy_bundle(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Preview a pasted provider list without saving secrets or mutating state."""
    raw_items = payload.get("items")
    if isinstance(raw_items, list):
        source_lines = [str(item) for item in raw_items]
    else:
        raw = str(payload.get("input") or payload.get("bundle") or payload.get("text") or "").strip()
        source_lines = raw.splitlines() if raw else []

    try:
        requested_limit = int(payload.get("limit") or BUNDLE_IMPORT_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        requested_limit = BUNDLE_IMPORT_DEFAULT_LIMIT
    limit = max(1, min(requested_limit, BUNDLE_IMPORT_MAX_LIMIT))
    base = {
        key: payload[key]
        for key in ("provider", "expected_geo", "rotation", "bypass_domains", "protocol")
        if key in payload
    }
    candidates: List[Dict[str, Any]] = []
    skipped = 0
    processed = 0
    truncated = False
    for line_number, raw_line in enumerate(source_lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or _is_proxy_table_header(line):
            skipped += 1
            continue
        if processed >= limit:
            truncated = True
            break
        processed += 1
        parsed = parse_proxy_input(_line_payload(line, base))
        candidate: Dict[str, Any] = {
            "line_number": line_number,
            "ok": bool(parsed.get("ok")),
            "redacted_url": parsed.get("redacted_url", ""),
            "credential_present": bool(parsed.get("credential_present")),
            "deployment_decision": parsed.get("deployment_decision"),
            "warnings": parsed.get("warnings", []),
            "errors": parsed.get("errors", []),
        }
        if parsed.get("ok"):
            profile = dict(parsed.get("profile") or {})
            profile.pop("credential_ref", None)
            candidate["profile"] = profile
        candidates.append(candidate)

    valid = [item for item in candidates if item.get("ok")]
    invalid = [item for item in candidates if not item.get("ok")]
    ready = [item for item in valid if (item.get("deployment_decision") or {}).get("status") == "ready"]
    limited = [item for item in valid if (item.get("deployment_decision") or {}).get("status") == "limited"]
    recommendation = ready[0] if ready else (valid[0] if valid else None)
    warnings = [
        "批量预检不会保存代理密码；选择某一行保存时才会写入本机密码库。",
        "预检结果只返回脱敏 URL 和部署决策，不会回显供应商密码。",
    ]
    if truncated:
        warnings.append(f"输入过多，只预检前 {limit} 条有效候选。")
    return {
        "ok": bool(valid),
        "schema_version": "netfix_proxy_import_preview.v1",
        "summary": {
            "input_line_count": len(source_lines),
            "processed_count": processed,
            "skipped_count": skipped,
            "valid_count": len(valid),
            "invalid_count": len(invalid),
            "ready_count": len(ready),
            "limited_count": len(limited),
        },
        "truncated": truncated,
        "recommendation": {
            "line_number": recommendation.get("line_number"),
            "redacted_url": recommendation.get("redacted_url"),
            "status": (recommendation.get("deployment_decision") or {}).get("status"),
            "headline": (recommendation.get("deployment_decision") or {}).get("headline"),
        } if recommendation else None,
        "candidates": candidates,
        "warnings": warnings,
    }


def save_proxy_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Save a non-secret proxy profile and store its password in Keychain."""
    parsed = parse_proxy_input(payload)
    if not parsed.get("ok"):
        parsed.pop("_secret", None)
        return parsed
    profile = dict(parsed["profile"])
    password = parsed.get("_secret", {}).get("password")
    if password:
        stored = keychain.set_secret(keychain.PROXY_SERVICE, profile["id"], password)
        if not stored.get("ok"):
            return {
                "ok": False,
                "error": stored.get("error", "failed to store proxy password"),
                "profile": profile,
                "warnings": parsed.get("warnings", []),
            }
    profile.pop("password_set", None)
    saved = upsert_proxy_profile(profile)
    saved["password_set"] = bool(password)
    return {
        "ok": True,
        "profile": saved,
        "deployment_decision": deployment_decision(saved),
        "warnings": parsed.get("warnings", []),
    }


def _profile_endpoint_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Return a non-secret endpoint summary for UI change receipts."""
    return {
        "protocol": str(profile.get("protocol") or ""),
        "host": str(profile.get("host") or ""),
        "port": int(profile.get("port") or 0),
        "username": str(profile.get("username") or ""),
        "credential_present": bool(profile.get("credential_ref") or profile.get("username")),
    }


def replace_proxy_profile(profile_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Replace one saved profile's endpoint/credentials while preserving its local identity."""
    profile_id = str(profile_id or "")
    existing = next((profile for profile in get_proxy_profiles() if str(profile.get("id") or "") == profile_id), None)
    if existing is None:
        return {"ok": False, "error": "profile not found", "profile_id": profile_id}

    replacement_payload = dict(payload)
    replacement_payload["id"] = profile_id
    for key in ("name", "provider", "expected_geo", "rotation", "bypass_domains"):
        if key not in replacement_payload and key in existing:
            replacement_payload[key] = existing[key]

    parsed = parse_proxy_input(replacement_payload)
    if not parsed.get("ok"):
        parsed.pop("_secret", None)
        parsed["profile_id"] = profile_id
        return parsed

    profile = dict(parsed["profile"])
    password = parsed.get("_secret", {}).get("password")
    warnings = list(parsed.get("warnings", []))
    keychain_result: Dict[str, Any] = {"ok": True, "service": keychain.PROXY_SERVICE, "account": profile_id, "skipped": True}
    if password:
        keychain_result = keychain.set_secret(keychain.PROXY_SERVICE, profile_id, password)
        if not keychain_result.get("ok"):
            return {
                "ok": False,
                "error": keychain_result.get("error", "failed to store proxy password"),
                "profile": profile,
                "warnings": warnings,
                "keychain": keychain_result,
            }
    elif profile.get("credential_ref") and existing.get("credential_ref"):
        warnings.append("existing_keychain_password_retained")
    elif not profile.get("credential_ref") and existing.get("credential_ref"):
        account = _keychain_account_from_ref(str(existing.get("credential_ref") or "")) or profile_id
        keychain_result = keychain.delete_secret(keychain.PROXY_SERVICE, account, missing_ok=True)
        if not keychain_result.get("ok"):
            warnings.append("profile_replaced_but_old_keychain_cleanup_failed")

    profile.pop("password_set", None)
    for field in ("last_check", "last_identity_report", "last_identity_summary"):
        profile.pop(field, None)
    saved = upsert_proxy_profile(profile)
    saved["password_set"] = bool(password)
    return {
        "ok": True,
        "profile_id": profile_id,
        "profile": saved,
        "previous_endpoint": _profile_endpoint_summary(existing),
        "new_endpoint": _profile_endpoint_summary(saved),
        "deployment_decision": deployment_decision(saved),
        "warnings": warnings,
        "keychain": keychain_result,
    }


def _keychain_account_from_ref(ref: str) -> str:
    prefix = "keychain://"
    if not ref.startswith(prefix):
        return ""
    path = ref[len(prefix):]
    parts = path.split("/", 1)
    if len(parts) != 2:
        return ""
    return parts[1] or ""


def delete_proxy_profile(profile_id: str) -> Dict[str, Any]:
    """Delete one saved proxy profile and attempt to remove its Keychain password."""
    deleted = delete_stored_proxy_profile(profile_id)
    if not deleted.get("ok"):
        return deleted
    profile = deleted.get("profile") if isinstance(deleted.get("profile"), dict) else {}
    account = _keychain_account_from_ref(str(profile.get("credential_ref") or "")) or str(profile.get("id") or profile_id)
    keychain_result = {"ok": True, "service": keychain.PROXY_SERVICE, "account": account, "skipped": True}
    warnings = []
    if account:
        keychain_result = keychain.delete_secret(keychain.PROXY_SERVICE, account, missing_ok=True)
        if not keychain_result.get("ok"):
            warnings.append("profile_deleted_but_keychain_cleanup_failed")
    return {
        "ok": True,
        "profile_id": str(profile.get("id") or profile_id),
        "profile": profile,
        "keychain": keychain_result,
        "warnings": warnings,
    }


def _classify_validate_error(exc: Exception) -> Tuple[str, str]:
    text = str(exc).lower()
    if isinstance(exc, HTTPError) and exc.code == 407:
        return "failed", "proxy_auth_required"
    if "407" in text or "authentication required" in text:
        return "failed", "proxy_auth_required"
    if "authentication failed" in text or "auth failed" in text:
        return "failed", "proxy_auth_failed"
    if "timed out" in text or "timeout" in text:
        return "failed", "timeout"
    if "nodename nor servname" in text or "name or service not known" in text or "temporary failure in name resolution" in text:
        return "failed", "dns_failed"
    if "connection refused" in text:
        return "failed", "connection_refused"
    return "failed", text[:160] or "unknown_error"


def _request_through_profile(
    profile: Dict[str, Any],
    url: str,
    *,
    timeout: int = 10,
    password: str = "",
) -> Tuple[int, bytes, float]:
    proxy_url = _proxy_url(profile, password=password)
    protocol = str(profile.get("protocol") or "")
    if protocol in {"socks5", "socks5h"}:
        return codex._request_socks5_proxy(url, proxy_url, timeout)
    return codex._request_http_proxy(url, proxy_url, timeout)


def _extract_json_ip(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text if len(text) <= 100 else ""
    if isinstance(parsed, dict):
        ip = parsed.get("ip")
        return str(ip).strip() if ip else ""
    return ""


def _geo_match(expected_geo: Any, identity: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(expected_geo, dict) or not expected_geo:
        return {"status": "not_configured"}
    expected_country = str(expected_geo.get("country_code") or expected_geo.get("country") or "").strip()
    expected_region = str(expected_geo.get("region") or expected_geo.get("state") or "").strip()
    expected_city = str(expected_geo.get("city") or "").strip()
    if not any((expected_country, expected_region, expected_city)):
        return {"status": "not_configured"}

    actual_country_code = str(identity.get("country_code") or "").strip()
    actual_country = str(identity.get("country") or "").strip()
    actual_region = str(identity.get("region") or "").strip()
    actual_city = str(identity.get("city") or "").strip()
    mismatches: List[str] = []
    if expected_country:
        expected = expected_country.lower()
        if expected not in {actual_country_code.lower(), actual_country.lower()}:
            mismatches.append("country")
    if expected_region and expected_region.lower() != actual_region.lower():
        mismatches.append("region")
    if expected_city and expected_city.lower() != actual_city.lower():
        mismatches.append("city")

    return {
        "status": "ok" if not mismatches else "warn",
        "expected": {
            "country": expected_country,
            "region": expected_region,
            "city": expected_city,
        },
        "actual": {
            "country": actual_country,
            "country_code": actual_country_code,
            "region": actual_region,
            "city": actual_city,
        },
        "mismatches": mismatches,
    }


def _dns_leak_assessment(profile: Dict[str, Any]) -> Dict[str, Any]:
    protocol = str(profile.get("protocol") or "")
    if protocol == "socks5":
        return {
            "status": "warn",
            "confidence": "heuristic",
            "risk": "some clients resolve DNS locally with socks5://; use socks5h:// for app-level remote DNS when supported",
        }
    if protocol == "socks5h":
        return {
            "status": "ok",
            "confidence": "heuristic",
            "risk": "profile requests use proxy-side hostname resolution in netfix validation",
        }
    if protocol in {"http", "https"}:
        return {
            "status": "unknown",
            "confidence": "heuristic",
            "risk": "HTTP CONNECT proxy validation does not prove every app will avoid local DNS",
        }
    return {"status": "unknown", "confidence": "none"}


def _ipv6_leak_assessment(profile: Dict[str, Any]) -> Dict[str, Any]:
    protocol = str(profile.get("protocol") or "")
    if protocol not in SUPPORTED_PROTOCOLS:
        return {
            "status": "unknown",
            "confidence": "none",
            "risk": "unsupported profile protocol",
        }
    if sys.platform != "darwin":
        return {
            "status": "unknown",
            "confidence": "not_applicable",
            "risk": "system-wide IPv6 fallback checks are implemented for macOS network services",
        }
    try:
        service = choose_network_service("")
        state = _parse_ipv6_state(_run_networksetup(["-getinfo", service])["stdout"])
    except Exception as exc:
        return {
            "status": "unknown",
            "confidence": "local_check_failed",
            "error": str(exc),
            "risk": "could not read the active macOS network service IPv6 state",
        }

    enabled = bool(state.get("enabled"))
    mode = str(state.get("mode") or "unknown")
    if enabled:
        return {
            "status": "warn",
            "confidence": "local_system_check",
            "network_service": service,
            "system_ipv6_enabled": True,
            "mode": mode,
            "risk": (
                "current macOS network service still has IPv6 enabled; system proxy apply will try to disable "
                "restorable IPv6 and record rollback data"
            ),
        }
    return {
        "status": "ok" if mode == "off" else "unknown",
        "confidence": "local_system_check",
        "network_service": service,
        "system_ipv6_enabled": False,
        "mode": mode,
        "risk": (
            "current macOS network service IPv6 is off"
            if mode == "off"
            else "macOS returned an IPv6 state that Netfix could not classify"
        ),
    }


def _target_probe_matrix(
    profile: Dict[str, Any],
    *,
    timeout: int = 10,
    password: str = "",
    target_profile: str = "baseline",
    target_urls: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    matrix = VALIDATION_TARGET_PROFILES.get(target_profile)
    probes = list((matrix or VALIDATION_TARGET_PROFILES["baseline"])["probes"])
    if target_urls:
        known = {
            item["url"]: item
            for item in DEFAULT_TARGET_PROBES + AI_DEV_TARGET_PROBES
        }
        seen = {str(item.get("url") or "") for item in probes}
        for target_url in target_urls:
            if not _target_url_allowed(target_url):
                probes.append({
                    "id": "custom",
                    "url": target_url,
                    "target": target_url,
                    "status": "blocked",
                    "http_code": 0,
                    "latency_ms": 0,
                    "error": "target_url_not_allowed",
                })
                continue
            if target_url in seen:
                continue
            seen.add(target_url)
            probes.append(known.get(target_url, {
                "id": "custom",
                "label": "Allowed custom validation target",
                "url": target_url,
                "ok_codes": {200, 204, 301, 302, 401, 403, 404},
            }))

    results: List[Dict[str, Any]] = []
    for probe in probes:
        target_url = str(probe.get("url") or "")
        if not _target_url_allowed(target_url):
            results.append({
                "id": probe.get("id") or "target",
                "target": target_url,
                "status": "blocked",
                "http_code": 0,
                "latency_ms": 0,
                "error": "target_url_not_allowed",
            })
            continue
        try:
            code, _body, duration_ms = _request_through_profile(profile, target_url, timeout=timeout, password=password)
            ok_codes = probe.get("ok_codes") or {200, 204}
            status = "ok" if code in ok_codes else "warn"
            results.append({
                "id": probe.get("id") or "target",
                "label": probe.get("label") or "",
                "target": target_url,
                "status": status,
                "http_code": code,
                "latency_ms": round(duration_ms),
                "error": None,
            })
        except Exception as exc:
            _status, error = _classify_validate_error(exc)
            code = exc.code if isinstance(exc, HTTPError) else 0
            results.append({
                "id": probe.get("id") or "target",
                "label": probe.get("label") or "",
                "target": target_url,
                "status": "fail",
                "http_code": code,
                "latency_ms": 0,
                "error": error,
            })
    return results


def audit_proxy_identity(
    profile: Dict[str, Any],
    *,
    timeout: int = 10,
    password: str = "",
    target_profile: str = "baseline",
    target_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return a conservative proxy exit identity and leak-risk report.

    This does not certify a residential IP. It records the observed exit IP and
    third-party IP intelligence, then labels DNS/IPv6 leakage as heuristic or
    untested unless netfix has real evidence.
    """
    report: Dict[str, Any] = {
        "status": "warn",
        "checked_at": _utc_now(),
        "target_profile": target_profile,
        "target_profile_label": VALIDATION_TARGET_PROFILES.get(target_profile, VALIDATION_TARGET_PROFILES["baseline"])["label"],
        "exit_ip": "",
        "identity": {},
        "expected_geo": _geo_match(profile.get("expected_geo"), {}),
        "dns_leak": _dns_leak_assessment(profile),
        "ipv6_leak": _ipv6_leak_assessment(profile),
        "target_matrix_status": "unknown",
        "targets": [],
        "warnings": [],
    }

    try:
        code, body, duration_ms = _request_through_profile(profile, EXIT_IDENTITY_URL, timeout=timeout, password=password)
        exit_ip = _extract_json_ip(body)
        report["identity_probe"] = {
            "target": EXIT_IDENTITY_URL,
            "http_code": code,
            "latency_ms": round(duration_ms),
            "status": "ok" if code == 200 and exit_ip else "warn",
        }
        if not exit_ip:
            report["identity_probe"]["error"] = "exit_ip_missing"
            report["warnings"].append("出口 IP 探测未返回可识别的 IP。")
        else:
            identity = ip_intel.get_ip_info(exit_ip, timeout=timeout)
            report["exit_ip"] = exit_ip
            report["identity"] = identity
            report["expected_geo"] = _geo_match(profile.get("expected_geo"), identity)
            if identity.get("ip_type") == "hosting/datacenter":
                report["warnings"].append("IP 情报倾向于机房/托管网络；不要对外宣称这是特定类型或高质量出口。")
            elif identity.get("ip_type") in {"unknown", None}:
                report["warnings"].append("IP 类型无法可靠判断；需要用户以供应商后台和目标网站实际结果为准。")
    except Exception as exc:
        _status, error = _classify_validate_error(exc)
        code = exc.code if isinstance(exc, HTTPError) else 0
        report["identity_probe"] = {
            "target": EXIT_IDENTITY_URL,
            "http_code": code,
            "latency_ms": 0,
            "status": "fail",
            "error": error,
        }
        report["warnings"].append(f"出口身份探测失败：{error}")

    report["targets"] = _target_probe_matrix(
        profile,
        timeout=timeout,
        password=password,
        target_profile=target_profile,
        target_urls=target_urls,
    )
    target_statuses = [item.get("status") for item in report["targets"]]
    if any(status in {"fail", "blocked"} for status in target_statuses):
        report["target_matrix_status"] = "fail"
    elif "warn" in target_statuses:
        report["target_matrix_status"] = "warn"
    elif target_statuses:
        report["target_matrix_status"] = "ok"
    if report.get("exit_ip") and report["target_matrix_status"] == "fail":
        report["status"] = "fail"
        report["warnings"].append("验证矩阵存在不可达目标；不要把该代理标记为当前场景已通过。")
    elif report.get("exit_ip") and report["target_matrix_status"] != "fail":
        report["status"] = "ok" if "warn" not in target_statuses and not report["warnings"] else "warn"
    elif report.get("exit_ip"):
        report["status"] = "warn"
    else:
        report["status"] = "fail"
    return report


def validate_proxy_profile(
    profile: Dict[str, Any],
    target_url: str = "https://www.gstatic.com/generate_204",
    timeout: int = 10,
    password: str = "",
    include_identity: bool = False,
    target_profile: str = "baseline",
    identity_target_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Validate a residential/custom proxy profile without applying it system-wide."""
    protocol = str(profile.get("protocol") or "")
    host = str(profile.get("host") or "")
    try:
        port = int(profile.get("port") or 0)
    except (TypeError, ValueError):
        port = 0

    started = time.perf_counter()
    check: Dict[str, Any] = {
        "profile_id": profile.get("id"),
        "status": "fail",
        "auth": "unknown",
        "tcp": "unknown",
        "target": target_url,
        "target_profile": target_profile,
        "http_code": 0,
        "latency_ms": 0,
        "error": None,
        "checked_via": _redacted_url(protocol, host, port, str(profile.get("username") or "")) if host and port else "",
    }
    if not _target_url_allowed(target_url):
        check["error"] = "target_url_not_allowed"
        return {"ok": False, "proxy_check": check}
    if target_profile not in VALIDATION_TARGET_PROFILES:
        check["error"] = "target_profile_not_allowed"
        check["supported_target_profiles"] = sorted(VALIDATION_TARGET_PROFILES)
        return {"ok": False, "proxy_check": check}
    if protocol not in SUPPORTED_PROTOCOLS or not host or port <= 0:
        check["error"] = "invalid profile"
        return {"ok": False, "proxy_check": check}

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        check["tcp"] = "ok"
    except Exception as exc:
        check["error"] = _classify_validate_error(exc)[1]
        check["latency_ms"] = round((time.perf_counter() - started) * 1000)
        return {"ok": False, "proxy_check": check}

    proxy_url = _proxy_url(profile, password=password)
    try:
        if protocol in {"socks5", "socks5h"}:
            code, _body, duration_ms = codex._request_socks5_proxy(target_url, proxy_url, timeout)
        else:
            code, _body, duration_ms = codex._request_http_proxy(target_url, proxy_url, timeout)
        check["http_code"] = code
        check["latency_ms"] = round(duration_ms)
        check["auth"] = "ok" if profile.get("credential_ref") or profile.get("username") else "not_required"
        check["status"] = "ok" if code in (200, 204, 301, 302, 401, 403, 404) else "warn"
        result = {"ok": check["status"] in {"ok", "warn"}, "proxy_check": check}
        if include_identity or target_profile != "baseline" or identity_target_urls:
            identity_report = audit_proxy_identity(
                profile,
                timeout=timeout,
                password=password,
                target_profile=target_profile,
                target_urls=identity_target_urls,
            )
            result["identity_report"] = identity_report
            if identity_report.get("status") == "fail":
                check["status"] = "fail"
                check["error"] = "identity_validation_failed"
                result["ok"] = False
            elif target_profile != "baseline" and identity_report.get("target_matrix_status") == "warn":
                check["status"] = "fail"
                check["error"] = "target_matrix_not_fully_validated"
                result["ok"] = False
        return result
    except Exception as exc:
        status, error = _classify_validate_error(exc)
        check["status"] = status
        check["error"] = error
        check["auth"] = "failed" if "auth" in error else "unknown"
        check["latency_ms"] = round((time.perf_counter() - started) * 1000)
        if isinstance(exc, HTTPError):
            check["http_code"] = exc.code
        return {"ok": False, "proxy_check": check}


def validate_saved_profile(
    profile: Dict[str, Any],
    target_url: str = "https://www.gstatic.com/generate_204",
    timeout: int = 10,
    include_identity: bool = False,
    target_profile: str = "baseline",
    identity_target_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Validate a saved profile, loading its password from Keychain if present."""
    password = ""
    if profile.get("credential_ref"):
        password = keychain.get_secret(keychain.PROXY_SERVICE, str(profile.get("id") or "")) or ""
    return validate_proxy_profile(
        profile,
        target_url=target_url,
        timeout=timeout,
        password=password,
        include_identity=include_identity,
        target_profile=target_profile,
        identity_target_urls=identity_target_urls,
    )


def apply_dry_run(profile: Dict[str, Any], mode: str = "system") -> Dict[str, Any]:
    """Return a safe plan for applying a proxy profile without changing state."""
    warnings = []
    if mode not in {"system", "app-env", "pac", "client-profile"}:
        return {"ok": False, "error": f"unsupported apply mode: {mode}"}
    protocol = profile.get("protocol")
    host = profile.get("host")
    port = profile.get("port")
    if protocol not in SUPPORTED_PROTOCOLS or not host or not port:
        return {"ok": False, "error": "invalid profile"}
    decision = deployment_decision(profile)

    steps: List[Dict[str, Any]] = []
    if mode == "system":
        steps.append({
            "tier": 2,
            "label": "设置 macOS 当前 Network Service 的 Web/SOCKS 代理",
            "safe_preview": f"{protocol}://{host}:{port}",
        })
        steps.append({
            "tier": 2,
            "label": "备份当前 IPv6 状态；可安全恢复时临时关闭 IPv6，避免绕过代理",
            "safe_preview": "networksetup -getinfo <service> -> optional -setv6off <service>",
        })
        if profile.get("credential_ref"):
            warnings.append("系统认证代理涉及密码，正式执行必须从本机密码库读取，不能拼进命令字符串。")
        if _has_auth(profile):
            if protocol in {"http", "https", "socks5", "socks5h"}:
                steps.append({
                    "tier": 2,
                    "label": "启动 127.0.0.1 本地桥接代理，由桥接进程向上游代理注入认证",
                    "safe_preview": "system proxy -> http://127.0.0.1:<netfix-bridge-port>",
                })
                warnings.append("认证代理不会直接写入系统代理；netfix 会使用本地桥接，App 退出后应回滚或保持后台运行。")
    elif mode == "app-env":
        steps.append({
            "tier": 1,
            "label": "仅为启动的子进程注入 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY",
            "safe_preview": f"{protocol}://{host}:{port}",
        })
    elif mode == "pac":
        steps.append({
            "tier": 2,
            "label": "生成本地 PAC 并指向无认证本地代理入口",
            "safe_preview": "PAC 不内嵌用户名或密码",
        })
    else:
        steps.append({
            "tier": 2,
            "label": "写入本地代理客户端 profile，执行前备份并展示 diff",
            "safe_preview": f"{protocol}://{host}:{port}",
        })

    return {
        "ok": True,
        "mode": mode,
        "profile_id": profile.get("id"),
        "status": "dry_run",
        "requires_confirmation": mode != "app-env",
        "deployment_decision": decision,
        "steps": steps,
        "warnings": warnings,
    }


def _apply_system_proxy_commands(profile: Dict[str, Any], service: str) -> List[List[str]]:
    protocol = str(profile.get("protocol") or "")
    host = str(profile.get("host") or "")
    port = str(int(profile.get("port") or 0))
    commands: List[List[str]] = [
        ["-setautoproxystate", service, "off"],
        ["-setproxyautodiscovery", service, "off"],
    ]
    if protocol in {"http", "https"}:
        commands.extend([
            ["-setwebproxy", service, host, port],
            ["-setwebproxystate", service, "on"],
            ["-setsecurewebproxy", service, host, port],
            ["-setsecurewebproxystate", service, "on"],
        ])
    elif protocol in {"socks5", "socks5h"}:
        commands.extend([
            ["-setsocksfirewallproxy", service, host, port],
            ["-setsocksfirewallproxystate", service, "on"],
        ])
    else:
        raise RuntimeError(f"unsupported protocol: {protocol}")
    return commands


def apply_proxy_profile(
    profile: Dict[str, Any],
    mode: str = "system",
    *,
    confirmed: bool = False,
    confirmation: str = "",
    network_service: str = "",
    target_url: str = "https://www.gstatic.com/generate_204",
    timeout: int = 10,
    verify: bool = True,
    rollback_on_verify_failure: bool = True,
    target_profile: str = "baseline",
) -> Dict[str, Any]:
    """Apply a saved proxy profile through a safe, confirmation-gated flow."""
    plan = apply_dry_run(profile, mode=mode)
    if not plan.get("ok"):
        return plan

    if mode == "app-env":
        return {
            "ok": True,
            "status": "applied",
            "mode": mode,
            "profile_id": profile.get("id"),
            "deployment_decision": plan.get("deployment_decision"),
            "applied": {
                "scope": "child_process_environment",
                "env_keys": list(_redacted_proxy_env(profile).keys()),
                "redacted_env": _redacted_proxy_env(profile),
                "secret_source": "keychain" if profile.get("credential_ref") else "none",
            },
            "warnings": plan.get("warnings", []),
        }

    if mode != "system":
        return {
            "ok": False,
            "status": "blocked",
            "mode": mode,
            "profile_id": profile.get("id"),
            "error": f"{mode} apply is not executable yet",
            "reason_code": "apply_mode_not_implemented",
            "deployment_decision": plan.get("deployment_decision"),
            "dry_run": plan,
        }

    if not confirmed or confirmation != SYSTEM_APPLY_CONFIRMATION:
        return {
            "ok": True,
            "status": "pending_confirmation",
            "mode": mode,
            "profile_id": profile.get("id"),
            "requires_confirmation": True,
            "confirmation": SYSTEM_APPLY_CONFIRMATION,
            "deployment_decision": plan.get("deployment_decision"),
            "dry_run": plan,
        }
    if sys.platform != "darwin":
        return {
            "ok": False,
            "status": "blocked",
            "mode": mode,
            "profile_id": profile.get("id"),
            "error": "system proxy apply is only supported on macOS",
            "reason_code": "system_apply_requires_macos",
            "deployment_decision": plan.get("deployment_decision"),
        }
    auth_bridge = _has_auth(profile)

    try:
        service = choose_network_service(network_service)
        backup = _capture_system_proxy_backup(service)
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "mode": mode,
            "profile_id": profile.get("id"),
            "error": str(exc),
            "reason_code": "system_proxy_backup_failed",
            "deployment_decision": plan.get("deployment_decision"),
        }

    if _backup_has_authenticated_proxy(backup):
        return {
            "ok": False,
            "status": "blocked",
            "mode": mode,
            "profile_id": profile.get("id"),
            "network_service": service,
            "error": "current system proxy uses authentication and cannot be safely restored without credentials",
            "reason_code": "current_authenticated_proxy_not_restorable",
            "deployment_decision": plan.get("deployment_decision"),
        }

    bridge_started: Optional[Dict[str, Any]] = None
    effective_profile = profile
    if auth_bridge:
        password = ""
        if profile.get("credential_ref"):
            password = keychain.get_secret(keychain.PROXY_SERVICE, str(profile.get("id") or "")) or ""
        bridge_result = proxy_bridge.start_http_bridge(profile, password=password)
        if not bridge_result.get("ok"):
            return {
                "ok": False,
                "status": "blocked",
                "mode": mode,
                "profile_id": profile.get("id"),
                "network_service": service,
                "error": bridge_result.get("error", "failed to start local proxy bridge"),
                "reason_code": bridge_result.get("reason_code", "bridge_start_failed"),
                "recommended_mode": "app-env",
                "deployment_decision": plan.get("deployment_decision"),
                "dry_run": plan,
            }
        bridge_started = bridge_result.get("bridge")
        effective_profile = _bridge_system_profile(bridge_started or {}, profile)

    entry = {
        "id": str(uuid.uuid4()),
        "created_at": _utc_now(),
        "profile_id": profile.get("id"),
        "profile_name": profile.get("name"),
        "mode": mode,
        "network_service": service,
        "redacted_url": _redacted_url(str(profile.get("protocol") or ""), str(profile.get("host") or ""), int(profile.get("port") or 0), str(profile.get("username") or "")),
        "backup": backup,
        "bridge": bridge_started,
    }
    try:
        executed = []
        for command in _apply_system_proxy_commands(effective_profile, service):
            _run_networksetup(command)
            executed.append({"args": ["networksetup", *command]})
        ipv6_commands = _disable_ipv6_commands(service, backup)
        for command in ipv6_commands:
            _run_networksetup(command)
            executed.append({"args": ["networksetup", *command]})
        entry["applied_at"] = _utc_now()
        entry["commands"] = executed
        entry["ipv6"] = {
            "disabled_during_apply": bool(ipv6_commands),
            "backup_mode": (backup.get("ipv6") or {}).get("mode") if isinstance(backup.get("ipv6"), dict) else None,
        }
        _write_apply_journal(entry)
    except Exception as exc:
        restore = _restore_system_proxy_backup(backup)
        bridge_stop = proxy_bridge.stop_bridge(str(bridge_started.get("id") or "")) if bridge_started else None
        entry["apply_error"] = str(exc)
        entry["restore_after_apply_error"] = restore
        entry["bridge_stop_after_apply_error"] = bridge_stop
        _write_apply_journal(entry)
        return {
            "ok": False,
            "status": "failed",
            "mode": mode,
            "profile_id": profile.get("id"),
            "network_service": service,
            "error": str(exc),
            "reason_code": "system_proxy_apply_failed",
            "deployment_decision": plan.get("deployment_decision"),
            "rollback": restore,
            "bridge_stop": bridge_stop,
        }

    verify_result = None
    if verify:
        verify_result = validate_proxy_profile(
            effective_profile,
            target_url=target_url,
            timeout=max(1, min(int(timeout), 60)),
            target_profile=target_profile,
        )
        entry["verify"] = verify_result
        if not verify_result.get("ok") and rollback_on_verify_failure:
            restore = _restore_system_proxy_backup(backup)
            bridge_stop = proxy_bridge.stop_bridge(str(bridge_started.get("id") or "")) if bridge_started and restore.get("ok") else None
            entry["rolled_back_at"] = _utc_now()
            entry["rollback_after_verify_failure"] = restore
            entry["bridge_stop_after_verify_failure"] = bridge_stop
            _write_apply_journal(entry)
            return {
                "ok": False,
                "status": "rolled_back_after_verify_failure",
                "mode": mode,
                "profile_id": profile.get("id"),
                "network_service": service,
                "verify": verify_result,
                "rollback": restore,
                "bridge_stop": bridge_stop,
                "reason_code": "verify_failed",
                "deployment_decision": plan.get("deployment_decision"),
            }
        _write_apply_journal(entry)

    return {
        "ok": True,
        "status": "applied",
        "mode": mode,
        "profile_id": profile.get("id"),
        "network_service": service,
        "journal_id": entry["id"],
        "redacted_url": entry["redacted_url"],
        "bridge": bridge_started,
        "applied": {"scope": "loopback_bridge", "requires_netfix_running": True} if bridge_started else {"scope": "system_proxy"},
        "ipv6": entry.get("ipv6"),
        "verify": verify_result,
        "deployment_decision": plan.get("deployment_decision"),
        "rollback_available": True,
    }


def rollback_last_proxy_apply(*, confirmed: bool = False, confirmation: str = "") -> Dict[str, Any]:
    """Rollback the last system proxy apply journal."""
    journal = _read_apply_journal()
    entry = journal.get("last_apply") if isinstance(journal.get("last_apply"), dict) else None
    if not entry:
        return {"ok": False, "status": "no_journal", "error": "no proxy apply journal found"}
    if not confirmed or confirmation != PROXY_ROLLBACK_CONFIRMATION:
        return {
            "ok": True,
            "status": "pending_confirmation",
            "requires_confirmation": True,
            "confirmation": PROXY_ROLLBACK_CONFIRMATION,
            "journal_id": entry.get("id"),
            "profile_id": entry.get("profile_id"),
            "network_service": entry.get("network_service"),
        }
    restore = _restore_system_proxy_backup(entry.get("backup", {}))
    bridge_stop = None
    bridge = entry.get("bridge") if isinstance(entry.get("bridge"), dict) else None
    if restore.get("ok") and bridge:
        bridge_stop = proxy_bridge.stop_bridge(str(bridge.get("id") or ""))
    entry["rolled_back_at"] = _utc_now()
    entry["rollback"] = restore
    entry["bridge_stop"] = bridge_stop
    _write_apply_journal(entry)
    return {
        "ok": bool(restore.get("ok")),
        "status": "rolled_back" if restore.get("ok") else "rollback_failed",
        "journal_id": entry.get("id"),
        "profile_id": entry.get("profile_id"),
        "network_service": entry.get("network_service"),
        "rollback": restore,
        "bridge_stop": bridge_stop,
    }


def detect_stale_bridge() -> Dict[str, Any]:
    """Detect whether system proxy still points at a Netfix bridge that is gone."""
    journal = _read_apply_journal()
    entry = journal.get("last_apply") if isinstance(journal.get("last_apply"), dict) else None
    if not entry:
        return {"ok": True, "status": "no_journal", "stale": False, "recovery_available": False}
    bridge = entry.get("bridge") if isinstance(entry.get("bridge"), dict) else None
    if not bridge:
        return {
            "ok": True,
            "status": "not_bridge_apply",
            "stale": False,
            "recovery_available": False,
            "journal_id": entry.get("id"),
            "profile_id": entry.get("profile_id"),
        }
    service = str(entry.get("network_service") or entry.get("backup", {}).get("service") or "")
    if not service:
        return {
            "ok": False,
            "status": "check_failed",
            "stale": False,
            "recovery_available": False,
            "error": "bridge journal is missing network service",
            "journal_id": entry.get("id"),
            "profile_id": entry.get("profile_id"),
            "bridge": bridge,
        }
    try:
        current = _capture_system_proxy_backup(service)
    except Exception as exc:
        return {
            "ok": False,
            "status": "check_failed",
            "stale": False,
            "recovery_available": False,
            "error": str(exc),
            "journal_id": entry.get("id"),
            "profile_id": entry.get("profile_id"),
            "network_service": service,
            "bridge": bridge,
        }

    points_to_bridge = _system_proxy_points_to_bridge(current, bridge)
    public = {
        "ok": True,
        "journal_id": entry.get("id"),
        "profile_id": entry.get("profile_id"),
        "profile_name": entry.get("profile_name"),
        "network_service": service,
        "bridge": bridge,
        "current": {
            "web": current.get("web", {}),
            "secure": current.get("secure", {}),
            "socks": current.get("socks", {}),
        },
        "system_points_to_bridge": points_to_bridge,
        "confirmation": BRIDGE_RECOVERY_CONFIRMATION,
    }
    if not points_to_bridge:
        return {**public, "status": "system_not_pointing_to_bridge", "stale": False, "recovery_available": False}

    record = _current_bridge_record(bridge)
    if record and record.get("running"):
        return {**public, "status": "healthy", "stale": False, "recovery_available": False, "active_bridge": record}

    host = str(bridge.get("listen_host") or "127.0.0.1")
    port = int(bridge.get("listen_port") or 0)
    port_open = _loopback_port_open(host, port)
    if port_open:
        return {
            **public,
            "status": "unknown_loopback_listener",
            "stale": True,
            "recovery_available": True,
            "port_open": True,
            "warning": "system proxy points at the last Netfix bridge port, but this backend does not own that listener",
        }
    return {
        **public,
        "status": "stale_bridge",
        "stale": True,
        "recovery_available": True,
        "port_open": False,
        "warning": "system proxy points at a Netfix bridge port that is no longer listening",
    }


def bridge_lifecycle(bridges: List[Dict[str, Any]], stale_check: Dict[str, Any]) -> Dict[str, Any]:
    """Return a stable user-facing lifecycle summary for the local bridge."""
    bridges = [item for item in bridges if isinstance(item, dict)]
    stale_check = stale_check if isinstance(stale_check, dict) else {}
    recovery_available = bool(stale_check.get("recovery_available"))
    status = str(stale_check.get("status") or "")
    active_bridge = stale_check.get("active_bridge") if isinstance(stale_check.get("active_bridge"), dict) else None
    first_bridge = active_bridge or (bridges[0] if bridges else None)
    base = {
        "schema_version": "netfix_proxy_bridge_lifecycle.v1",
        "status": "unknown",
        "severity": "info",
        "headline": "桥接状态未知",
        "primary_action": "refresh",
        "needs_attention": False,
        "recovery_available": recovery_available,
        "requires_netfix_running": False,
        "network_service": stale_check.get("network_service"),
        "profile_id": stale_check.get("profile_id"),
        "profile_name": stale_check.get("profile_name"),
        "confirmation": stale_check.get("confirmation") if recovery_available else None,
        "system_points_to_bridge": bool(stale_check.get("system_points_to_bridge")),
        "next_steps": ["刷新桥接状态；如果系统网络仍异常，再查看系统代理或回滚记录。"],
    }

    if recovery_available:
        detail = "上次 Netfix 本地桥接端口仍被系统代理引用。"
        if status == "unknown_loopback_listener":
            detail = "系统代理指向上次 Netfix 桥接端口，但当前后端不拥有该监听。"
        elif status == "stale_bridge":
            detail = "系统代理指向已停止的 Netfix 桥接端口。"
        return {
            **base,
            "status": "recovery_required",
            "severity": "warning",
            "headline": "需要恢复系统代理",
            "detail": detail,
            "primary_action": "recover_system_proxy",
            "needs_attention": True,
            "bridge": stale_check.get("bridge"),
            "port_open": stale_check.get("port_open"),
            "next_steps": [
                "点击恢复系统代理，写回 Netfix 应用前备份的系统代理状态。",
                "恢复属于确认式系统配置变更；执行前会要求确认短语。",
                "恢复后重新运行连接检查，确认 Codex/OpenAI/GitHub 等目标是否恢复。",
            ],
        }

    if status == "check_failed":
        return {
            **base,
            "status": "check_failed",
            "severity": "warning",
            "headline": "桥接恢复检查失败",
            "detail": str(stale_check.get("error") or "无法读取当前系统代理状态。"),
            "primary_action": "refresh",
            "needs_attention": True,
            "bridge": stale_check.get("bridge"),
            "next_steps": [
                "刷新桥接状态。",
                "如果持续失败，打开日志并检查 networksetup 权限或当前 Network Service。",
            ],
        }

    if first_bridge:
        audit = {
            "request_count": int(first_bridge.get("request_count") or 0),
            "active_connections": int(first_bridge.get("active_connections") or 0),
            "recent_client_count": len(first_bridge.get("recent_clients") or []),
            "idle_timeout_s": float(first_bridge.get("idle_timeout_s") or 0),
        }
        if status == "healthy":
            return {
                **base,
                "status": "running_system",
                "severity": "info",
                "headline": "系统代理桥接运行中",
                "primary_action": "keep_running_or_rollback",
                "requires_netfix_running": True,
                "bridge": first_bridge,
                "audit": audit,
                "next_steps": [
                    "保持 Netfix 运行，让系统代理继续通过本地桥接访问认证 HTTP/HTTPS 上游。",
                    "不用时点击恢复原来的网络设置，避免系统代理停留在本机转发端口。",
                ],
            }
        return {
            **base,
            "status": "running_local",
            "severity": "info",
            "headline": "本地桥接运行中",
            "primary_action": "inspect_or_rollback",
            "requires_netfix_running": True,
            "bridge": first_bridge,
            "audit": audit,
            "next_steps": [
                "本地桥接正在监听，可能服务于刚应用的系统代理或本机工具。",
                "查看请求计数和最近本机客户端；不用时回滚系统代理或停止相关流程。",
            ],
        }

    if status in {"system_not_pointing_to_bridge", "not_bridge_apply"}:
        return {
            **base,
            "status": "not_in_use",
            "headline": "系统当前未使用 Netfix 桥接",
            "primary_action": "none",
            "next_steps": ["需要让这台 Mac 使用有账号密码的代理时，先保存并验证代理参数，再确认开始使用。"],
        }

    return {
        **base,
        "status": "stopped",
        "headline": "本地桥接未启动",
        "primary_action": "none",
        "next_steps": ["有账号密码的 HTTP/HTTPS 代理确认开始使用后，本机转发状态会显示在这里。"],
    }


def recover_stale_bridge(*, confirmed: bool = False, confirmation: str = "") -> Dict[str, Any]:
    """Restore the pre-apply system proxy when a loopback bridge is stale."""
    state = detect_stale_bridge()
    if not state.get("ok"):
        return state
    if not state.get("recovery_available"):
        return {
            "ok": True,
            "status": "no_recovery_needed",
            "stale_check": state,
            "recovery_available": False,
        }
    if not confirmed or confirmation != BRIDGE_RECOVERY_CONFIRMATION:
        return {
            "ok": True,
            "status": "pending_confirmation",
            "requires_confirmation": True,
            "confirmation": BRIDGE_RECOVERY_CONFIRMATION,
            "stale_check": state,
            "recovery_available": True,
        }

    journal = _read_apply_journal()
    entry = journal.get("last_apply") if isinstance(journal.get("last_apply"), dict) else None
    if not entry:
        return {"ok": False, "status": "no_journal", "error": "no proxy apply journal found"}
    restore = _restore_system_proxy_backup(entry.get("backup", {}))
    bridge = entry.get("bridge") if isinstance(entry.get("bridge"), dict) else None
    bridge_stop = proxy_bridge.stop_bridge(str(bridge.get("id") or "")) if bridge else None
    entry["stale_bridge_recovered_at"] = _utc_now()
    entry["stale_bridge_check"] = state
    entry["stale_bridge_recovery"] = restore
    entry["stale_bridge_stop"] = bridge_stop
    _write_apply_journal(entry)
    return {
        "ok": bool(restore.get("ok")),
        "status": "recovered" if restore.get("ok") else "recovery_failed",
        "journal_id": entry.get("id"),
        "profile_id": entry.get("profile_id"),
        "network_service": entry.get("network_service"),
        "stale_check": state,
        "rollback": restore,
        "bridge_stop": bridge_stop,
    }


def restart_stale_bridge(*, confirmed: bool = False, confirmation: str = "", idle_timeout_s: float = 0) -> Dict[str, Any]:
    """Restart the last Netfix loopback bridge without changing system proxy settings."""
    state = detect_stale_bridge()
    if not state.get("ok"):
        return state
    if not state.get("recovery_available"):
        return {
            "ok": True,
            "status": "no_restart_needed",
            "restart_available": False,
            "stale_check": state,
        }
    if state.get("status") == "unknown_loopback_listener":
        return {
            "ok": False,
            "status": "blocked",
            "reason_code": "loopback_port_owned_by_unknown_process",
            "restart_available": False,
            "stale_check": state,
            "error": "system proxy points at the last Netfix bridge port, but another process is listening there",
        }
    if state.get("status") != "stale_bridge":
        return {
            "ok": False,
            "status": "blocked",
            "reason_code": "bridge_restart_requires_stale_bridge",
            "restart_available": False,
            "stale_check": state,
        }
    if not confirmed or confirmation != BRIDGE_RESTART_CONFIRMATION:
        return {
            "ok": True,
            "status": "pending_confirmation",
            "requires_confirmation": True,
            "confirmation": BRIDGE_RESTART_CONFIRMATION,
            "restart_available": True,
            "stale_check": state,
        }

    journal = _read_apply_journal()
    entry = journal.get("last_apply") if isinstance(journal.get("last_apply"), dict) else None
    if not entry:
        return {"ok": False, "status": "no_journal", "restart_available": False, "error": "no proxy apply journal found"}
    profile_id = str(entry.get("profile_id") or state.get("profile_id") or "")
    if not profile_id:
        return {"ok": False, "status": "blocked", "reason_code": "missing_profile_id", "restart_available": False}
    profile = next((item for item in get_proxy_profiles() if item.get("id") == profile_id), None)
    if not profile:
        return {
            "ok": False,
            "status": "blocked",
            "reason_code": "saved_profile_missing",
            "restart_available": False,
            "profile_id": profile_id,
        }
    if str(profile.get("protocol") or "") not in {"http", "https", "socks5", "socks5h"}:
        return {
            "ok": False,
            "status": "blocked",
            "reason_code": "bridge_unsupported_upstream_protocol",
            "restart_available": False,
            "profile_id": profile_id,
        }
    password = ""
    if profile.get("credential_ref"):
        password = keychain.get_secret(keychain.PROXY_SERVICE, profile_id) or ""
    if profile.get("username") and not password:
        return {
            "ok": False,
            "status": "blocked",
            "reason_code": "missing_keychain_password",
            "restart_available": False,
            "profile_id": profile_id,
            "error": "saved profile requires a Keychain password before the loopback bridge can be restarted",
        }

    old_bridge = state.get("bridge") if isinstance(state.get("bridge"), dict) else {}
    host = str(old_bridge.get("listen_host") or "127.0.0.1")
    port = int(old_bridge.get("listen_port") or 0)
    if port <= 0:
        return {
            "ok": False,
            "status": "blocked",
            "reason_code": "missing_bridge_port",
            "restart_available": False,
            "profile_id": profile_id,
            "stale_check": state,
        }

    started = proxy_bridge.start_http_bridge(
        profile,
        password=password,
        bind_host=host,
        bind_port=port,
        idle_timeout_s=max(0.0, float(idle_timeout_s or 0)),
    )
    if not started.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "reason_code": started.get("reason_code", "bridge_start_failed"),
            "restart_available": False,
            "profile_id": profile_id,
            "stale_check": state,
            "error": started.get("error", "failed to restart local proxy bridge"),
        }

    new_bridge = started.get("bridge") if isinstance(started.get("bridge"), dict) else {}
    entry["bridge_restart_previous_bridge"] = old_bridge
    entry["bridge_restarted_at"] = _utc_now()
    entry["bridge_restart_idle_timeout_s"] = max(0.0, float(idle_timeout_s or 0))
    entry["bridge"] = new_bridge
    _write_apply_journal(entry)
    refreshed = detect_stale_bridge()
    return {
        "ok": True,
        "status": "restarted",
        "restart_available": False,
        "profile_id": profile_id,
        "network_service": state.get("network_service"),
        "previous_bridge": old_bridge,
        "bridge": new_bridge,
        "stale_check": refreshed,
        "system_proxy_changed": False,
    }


def split_profile_path(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse /proxy/profiles/<id>/<operation> style API paths."""
    parts = [part for part in path.split("/") if part]
    if len(parts) == 3 and parts[:2] == ["proxy", "profiles"]:
        return parts[2], None
    if len(parts) == 4 and parts[:2] == ["proxy", "profiles"]:
        return parts[2], parts[3]
    return None, None
