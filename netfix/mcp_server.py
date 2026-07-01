"""Model Context Protocol (MCP) stdio server for netfix."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from netfix import agent_tools, keychain, llm_explain, llm_provider, residential_proxy, settings
from netfix.constants import VERSION
from netfix.redaction import redact_text
from netfix.report import Report
from netfix.service_runner import run_cli


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _tool(
    name: str,
    description: str,
    schema: Optional[Dict[str, Any]] = None,
    read_only: bool = True,
) -> Dict[str, Any]:
    annotations = {"readOnlyHint": read_only}
    if not read_only:
        annotations["destructiveHint"] = True
    return {
        "name": name,
        "description": description,
        "inputSchema": schema or {"type": "object", "properties": {}},
        "annotations": annotations,
    }


_TOOLS: List[Dict[str, Any]] = [
    _tool(
        "netfix_codex",
        "Run the Codex / OpenAI / GitHub health check.",
        {
            "type": "object",
            "properties": {"timeout": {"type": "integer", "default": 60}},
        },
    ),
    _tool(
        "netfix_services",
        "Probe overseas service groups.",
        {
            "type": "object",
            "properties": {
                "group": {"type": "string"},
                "timeout": {"type": "integer", "default": 60},
            },
        },
    ),
    _tool("netfix_triage", "Run the OSI five-layer triage.", read_only=True),
    _tool("netfix_doctor", "Run the full diagnostic suite.", read_only=True),
    _tool("netfix_report", "Return the latest saved report.", read_only=True),
    _tool(
        "netfix_kb_query",
        "Query the netfix knowledge base.",
        {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    _tool(
        "netfix_fix_issue",
        "Execute a netfix repair by issue id. Tier 2 fixes require dry_run first, then confirmed=true and confirmation=APPLY_SYSTEM_FIX.",
        {
            "type": "object",
            "properties": {
                "issue": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "confirmed": {"type": "boolean", "default": False},
                "confirmation": {"type": "string", "description": "Required for Tier 2 execution: APPLY_SYSTEM_FIX"},
                "yes": {"type": "boolean", "default": False, "description": "Deprecated; does not bypass Tier 2 confirmation."},
            },
            "required": ["issue"],
        },
        read_only=False,
    ),
    _tool("netfix_rollback", "Rollback the last Tier 2 change.", read_only=False),
    _tool(
        "netfix_explain",
        "Return a plain-language explanation and recommended actions for the latest report.",
        read_only=True,
    ),
    _tool(
        "netfix_llm_providers",
        "List LLM provider presets. Domestic models are prioritized: DeepSeek, Kimi/Moonshot, MiniMax, Qwen.",
        read_only=True,
    ),
    _tool(
        "netfix_explain_llm",
        "Explain the latest report with the optional configured LLM after local redaction; falls back to local rules.",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "mode": {"type": "string", "enum": ["explain", "image_question"], "default": "explain"},
                "redaction_level": {"type": "string", "enum": ["balanced", "strict"], "default": "balanced"},
                "upload_confirmed": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required for cloud upload and always required for image_question mode.",
                },
                "allow_fallback": {
                    "type": "boolean",
                    "description": "When false, do not try fallback providers after the configured provider.",
                },
                "images": {
                    "type": "array",
                    "maxItems": 3,
                    "description": "Inline PNG/JPEG/WebP/GIF data URLs only; remote URLs are ignored by the safety layer.",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "data_url": {"type": "string"},
                                    "url": {"type": "string"},
                                },
                            },
                        ]
                    },
                },
                "timeout": {"type": "integer", "default": 60},
            },
        },
        read_only=True,
    ),
    _tool(
        "netfix_proxy_switch",
        "Switch to a healthy proxy profile.",
        {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "auto": {"type": "boolean", "default": False},
                "timeout": {"type": "integer", "default": 60},
            },
        },
        read_only=False,
    ),
    _tool(
        "netfix_proxy_parse",
        "Parse and redact a residential/custom proxy credential string without saving credentials.",
        {
            "type": "object",
            "properties": {
                "input": {"type": "string"},
                "protocol": {"type": "string"},
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
        },
        read_only=True,
    ),
    _tool(
        "netfix_proxy_import_preview",
        "Batch-preflight a pasted residential/custom proxy supplier list without saving credentials.",
        {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Multi-line supplier paste. Supports URLs, host:port:user:pass, and host,port,user,password rows.",
                },
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of raw proxy rows. Used when input is not provided.",
                },
                "provider": {"type": "string"},
                "expected_geo": {"type": "object"},
                "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
            },
        },
        read_only=True,
    ),
    _tool("netfix_get_global_state", "Return the primary network path summary.", read_only=True),
    _tool("netfix_get_interfaces", "List network interfaces and their IP addresses.", read_only=True),
    _tool("netfix_get_dns_state", "Return active DNS resolvers and search domains.", read_only=True),
    _tool("netfix_get_proxy_state", "Return system HTTP/HTTPS/SOCKS/PAC proxy settings (credentials redacted).", read_only=True),
    _tool("netfix_get_routes", "Return the IPv4 routing table summary.", read_only=True),
    _tool("netfix_get_listeners", "Return local TCP listening ports and processes.", read_only=True),
    _tool(
        "netfix_dns_resolve",
        "Resolve a domain via the system resolver or an explicit DNS server.",
        {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "resolver": {"type": "string"},
            },
            "required": ["target"],
        },
        read_only=True,
    ),
    _tool(
        "netfix_test_proxy_for_url",
        "Fetch a URL through the system-configured proxy.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        read_only=True,
    ),
    _tool(
        "netfix_test_direct_for_url",
        "Fetch a URL directly, bypassing proxies.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        read_only=True,
    ),
    _tool("netfix_check_proxy_auth", "Detect whether the system proxy requires authentication.", read_only=True),
    _tool("netfix_get_ip_reputation", "Return the public IPv4 identity, ISP/ASN and reputation.", read_only=True),
    _tool(
        "netfix_trace_path",
        "Trace the network path to a target.",
        {
            "type": "object",
            "properties": {"target": {"type": "string", "default": "8.8.8.8"}},
        },
        read_only=True,
    ),
    _tool(
        "netfix_flush_dns",
        "Plan or execute the DNS cache flush fix through FixEngine.",
        {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": True},
                "timeout": {"type": "integer", "default": 60},
            },
        },
        read_only=False,
    ),
    _tool(
        "netfix_renew_dhcp",
        "Plan or execute the DHCP renew fix through FixEngine.",
        {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": True},
                "timeout": {"type": "integer", "default": 60},
            },
        },
        read_only=False,
    ),
    _tool(
        "netfix_disable_ipv6",
        "Plan or execute the disable IPv6 fix through FixEngine.",
        {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": True},
                "timeout": {"type": "integer", "default": 60},
            },
        },
        read_only=False,
    ),
]


# Direct dispatch for agent tools that do not need a CLI round-trip.
_AGENT_TOOL_DISPATCH = {
    "netfix_get_global_state": lambda _a: agent_tools.get_global_state(),
    "netfix_get_interfaces": lambda _a: agent_tools.get_interfaces(),
    "netfix_get_dns_state": lambda _a: agent_tools.get_dns_state(),
    "netfix_get_proxy_state": lambda _a: agent_tools.get_proxy_state(),
    "netfix_get_routes": lambda _a: agent_tools.get_routes(),
    "netfix_get_listeners": lambda _a: agent_tools.get_listeners(),
    "netfix_dns_resolve": lambda a: agent_tools.dns_resolve(a.get("target", ""), a.get("resolver")),
    "netfix_test_proxy_for_url": lambda a: agent_tools.test_proxy_for_url(a.get("url", "")),
    "netfix_test_direct_for_url": lambda a: agent_tools.test_direct_for_url(a.get("url", "")),
    "netfix_check_proxy_auth": lambda _a: agent_tools.check_proxy_auth(),
    "netfix_get_ip_reputation": lambda _a: agent_tools.get_ip_reputation(),
    "netfix_trace_path": lambda a: agent_tools.trace_path(a.get("target", "8.8.8.8")),
    "netfix_llm_providers": lambda _a: {"ok": True, "providers": _llm_providers_for_mcp()},
    "netfix_proxy_parse": lambda a: _parse_proxy_for_mcp(a),
    "netfix_proxy_import_preview": lambda a: _import_proxy_preview_for_mcp(a),
    "netfix_explain_llm": lambda a: _explain_llm_for_mcp(a),
}


_FIX_TOOL_IDS = {
    "netfix_flush_dns": "flush-dns-cache",
    "netfix_renew_dhcp": "renew-dhcp",
    "netfix_disable_ipv6": "disable-ipv6",
}


_VISION_ADAPTER_READY_STATUSES = {
    "openai_compatible_image_url_ready",
    "provider_supports_vision_adapter_ready",
}


def _log(fmt: str, *args: Any) -> None:
    print(fmt % args, file=sys.stderr, flush=True)


def _parse_proxy_for_mcp(args: Dict[str, Any]) -> Dict[str, Any]:
    result = residential_proxy.parse_proxy_input(args)
    return _strip_internal_secrets(result)


def _strip_internal_secrets(value: Any) -> Any:
    """Drop internal secret carriers before returning MCP payloads."""
    if isinstance(value, dict):
        return {
            key: _strip_internal_secrets(item)
            for key, item in value.items()
            if key != "_secret"
        }
    if isinstance(value, list):
        return [_strip_internal_secrets(item) for item in value]
    return value


def _sanitize_mcp_output(value: Any, path: tuple[str, ...] = ()) -> Any:
    """Redact command-output text while preserving structured MCP payloads."""
    if isinstance(value, dict):
        return {key: _sanitize_mcp_output(item, path + (str(key).lower(),)) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_mcp_output(item, path) for item in value]
    if isinstance(value, str) and path and path[-1] in {"error", "stderr", "stdout", "stdout_tail", "raw"}:
        return redact_text(value)
    return value


def _fix_issue_for_mcp(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute fixes through the same confirmation gate as the local HTTP API."""
    from netfix import api  # Lazy import keeps MCP startup small and avoids cycles.

    body = {
        "fix_id": str(args.get("issue") or "").strip(),
        "dry_run": bool(args.get("dry_run")),
        "confirmed": bool(args.get("confirmed") or args.get("confirm")),
        "confirmation": str(args.get("confirmation") or ""),
        "timeout": int(args.get("timeout") or 90),
    }
    status, payload = api._execute_confirmed_fix(body)
    result = _sanitize_mcp_output(_strip_internal_secrets(payload))
    if isinstance(result, dict):
        result.setdefault("http_status", status)
    return result


def _import_proxy_preview_for_mcp(args: Dict[str, Any]) -> Dict[str, Any]:
    return residential_proxy.parse_proxy_bundle(args)


def _llm_providers_for_mcp() -> List[Dict[str, Any]]:
    """Return provider presets with the same local readiness cues as the Web UI."""
    llm_settings = settings.load_settings().get("llm", {})
    features = llm_settings.get("features") if isinstance(llm_settings.get("features"), dict) else {}
    image_feature_enabled = bool(features.get("image_question"))
    active_provider = str(llm_settings.get("provider") or "deepseek")
    active_account = str(llm_settings.get("api_key_account") or active_provider)
    providers: List[Dict[str, Any]] = []
    for provider in llm_provider.list_providers():
        item = dict(provider)
        provider_id = str(item.get("id") or "")
        account = active_account if provider_id == active_provider else provider_id
        item["api_key_account"] = account
        item["api_key_set"] = keychain.has_secret(
            keychain.LLM_SERVICE,
            account,
            allow_generic_llm_override=provider_id == active_provider,
        )
        image_status = str(item.get("image_question_status") or "")
        image_adapter_ready = bool(item.get("supports_vision") and image_status in _VISION_ADAPTER_READY_STATUSES)
        item["fallback_ready"] = bool(item["api_key_set"])
        item["text_explain_ready"] = bool(item["api_key_set"])
        item["image_question_provider_supported"] = bool(item.get("supports_vision"))
        item["image_question_adapter_ready"] = image_adapter_ready
        item["image_question_ready"] = bool(item["api_key_set"] and image_adapter_ready and image_feature_enabled)
        item["netfix_mode"] = "text_and_image_question" if item["image_question_ready"] else "text_report_only"
        providers.append(item)
    return providers


def _explain_llm_for_mcp(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        report = Report.load().as_dict()
    except Exception as exc:
        return {"ok": False, "error": f"failed to load latest report: {exc}"}
    mode = str(args.get("mode") or "explain")
    if mode not in {"explain", "image_question"}:
        mode = "explain"
    allow_fallback = args.get("allow_fallback")
    return {
        "ok": True,
        "result": llm_explain.explain_with_llm(
            report,
            question=str(args.get("question") or ""),
            mode=mode,
            redaction_level=str(args.get("redaction_level") or "balanced"),
            upload_confirmed=bool(args.get("upload_confirmed") or args.get("upload_consent_confirmed")),
            allow_fallback=allow_fallback if isinstance(allow_fallback, bool) else None,
            image_inputs=args.get("images") if isinstance(args.get("images"), list) else None,
        ),
    }


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _result(req_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# CLI command builders
# ---------------------------------------------------------------------------

def _ensure_json_and_timeout(argv: List[str], timeout: int) -> List[str]:
    cmd = list(argv)
    if "--json" not in cmd:
        cmd.append("--json")
    if "--timeout" not in cmd:
        cmd.extend(["--timeout", str(timeout)])
    return cmd


def _build_argv(name: str, args: Dict[str, Any]) -> List[str]:
    timeout = int(args.get("timeout", 60))

    if name == "netfix_codex":
        return _ensure_json_and_timeout(["codex"], timeout)

    if name == "netfix_services":
        argv: List[str] = ["services"]
        group = args.get("group")
        if group:
            argv.extend(["--group", str(group)])
        return _ensure_json_and_timeout(argv, timeout)

    if name == "netfix_triage":
        return _ensure_json_and_timeout(["triage"], timeout)

    if name == "netfix_doctor":
        return _ensure_json_and_timeout(["doctor"], timeout)

    if name == "netfix_report":
        return _ensure_json_and_timeout(["report"], timeout)

    if name == "netfix_explain":
        return _ensure_json_and_timeout(["explain"], timeout)

    if name == "netfix_kb_query":
        query = args.get("query", "")
        return _ensure_json_and_timeout(["kb", "--query", str(query)], timeout)

    if name == "netfix_fix_issue":
        argv = ["fix", "--issue", str(args.get("issue", ""))]
        if args.get("dry_run"):
            argv.append("--dry-run")
        return _ensure_json_and_timeout(argv, timeout)

    if name in _FIX_TOOL_IDS:
        argv = ["fix", "--issue", _FIX_TOOL_IDS[name]]
        if args.get("dry_run", True):
            argv.append("--dry-run")
        return _ensure_json_and_timeout(argv, timeout)

    if name == "netfix_rollback":
        return _ensure_json_and_timeout(["rollback"], timeout)

    if name == "netfix_proxy_switch":
        argv = ["proxy-switch"]
        profile = args.get("profile")
        if profile:
            argv.extend(["--profile", str(profile)])
        if args.get("auto"):
            argv.append("--auto")
        return _ensure_json_and_timeout(argv, timeout)

    raise ValueError(f"unknown tool: {name}")


def _call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "netfix_fix_issue":
        result = _fix_issue_for_mcp(args)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        is_error = isinstance(result, dict) and (not result.get("ok", True) or int(result.get("http_status", 200)) >= 400)
        return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}

    if name in _AGENT_TOOL_DISPATCH:
        try:
            result = _sanitize_mcp_output(_strip_internal_secrets(_AGENT_TOOL_DISPATCH[name](args)))
        except Exception as exc:  # pragma: no cover - defensive
            text = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2)
            return {"content": [{"type": "text", "text": text}], "isError": True}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        is_error = isinstance(result, dict) and result.get("status") in ("fail",) and result.get("error")
        return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}

    try:
        argv = _build_argv(name, args)
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}

    result = _sanitize_mcp_output(_strip_internal_secrets(run_cli(argv, timeout=int(args.get("timeout", 60)))))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": not result.get("ok", True)}


# ---------------------------------------------------------------------------
# Request dispatch
# ---------------------------------------------------------------------------

def _handle(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return _result(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "netfix", "version": VERSION},
                "capabilities": {"tools": {}},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _result(req_id, {"tools": _TOOLS})

    if method == "tools/call":
        params = req.get("params") or {}
        tool_args = params.get("arguments") or {}
        tool_name = params.get("name")
        if not tool_name:
            return _error(req_id, -32602, "missing params.name")
        return _result(req_id, _call_tool(tool_name, tool_args))

    return _error(req_id, -32601, f"method not found: {method}")


# ---------------------------------------------------------------------------
# Server loop
# ---------------------------------------------------------------------------

def serve() -> None:
    """Read JSON-RPC from stdin and write JSON-RPC to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _log("invalid JSON-RPC request: %s", exc)
            continue

        if not isinstance(req, dict):
            _log("invalid JSON-RPC request type: %s", type(req).__name__)
            continue

        try:
            resp = _handle(req)
        except Exception as exc:  # pragma: no cover - defensive
            _log("handler exception: %s", exc)
            resp = _error(req.get("id"), -32603, str(exc))

        if resp is not None:
            print(json.dumps(resp, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    serve()
