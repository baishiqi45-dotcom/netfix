"""netfix CLI entry point and subcommands."""
from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from netfix import api, dashboard_state, diagnose, explain, kb, llm_explain, logs, reasoner, residential_proxy, services, settings
from netfix.codex import check_codex
from netfix.constants import CASES_DIR, RULES_DIR, VERSION
from netfix.detect import detect_environment, get_core
from netfix.fix_engine import FixEngine
from netfix.safety import FixTier
from netfix.report import Report
from netfix.utils import confirm, ensure_dir, human_time, print_json


def _load_rules() -> Dict[str, Any]:
    path = RULES_DIR / "symptoms.json"
    if not path.exists():
        return {"symptoms": [], "fixes": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _enrich_env(env: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in GUI/core fields that detect_environment leaves empty."""
    core = get_core(env)
    env["gui_client"] = core.name if core else None
    env["active_core"] = core.name if core else None
    if core:
        inbound = core.get_inbound() or {}
        env["mixed_port"] = inbound.get("port")
        env["active_profile"] = core.get_active_profile()
        env["profiles"] = core.list_profiles()
    else:
        # Infer mixed port from listening ports when no core adapter matched.
        for info in env.get("listening_ports", []):
            if info.get("port") in (10808, 7890, 9090):
                env["mixed_port"] = info.get("port")
                break

    mixed_port = env.get("mixed_port") or 10808
    env["mixed_proxy"] = f"http://127.0.0.1:{mixed_port}"
    env["dns_target"] = env.get("dns_target", "example.com")
    return env


def _resolve_fix(fix_id: str) -> Dict[str, Any]:
    rules = _load_rules()
    definition = rules.get("fixes", {}).get(fix_id, {})
    commands = definition.get("commands", [])
    command = commands[0] if len(commands) == 1 else "; ".join(commands)
    tier = definition.get("tier", 3)
    return {
        "id": fix_id,
        "tier": tier,
        "description": definition.get("description", ""),
        "command": command,
        "commands": commands,
        "verify": definition.get("verify", ""),
        "auto": tier == 1,
    }


def _normalize_manual_step(item: Any) -> Dict[str, Any]:
    """Convert a string, list or dict manual step into a structured dict."""
    if isinstance(item, dict):
        return {
            "id": item.get("id", ""),
            "description": item.get("description", ""),
            "steps": list(item.get("steps", [])),
        }
    if isinstance(item, list):
        return {"id": "", "description": "", "steps": [str(s) for s in item]}
    return {"id": str(item), "description": str(item), "steps": []}


_DIAGNOSTIC_DISPLAY_NAMES = {
    "proxy_core_status": "代理软件状态",
    "system_proxy_state": "系统代理设置",
    "proxy_http_test": "代理连通性",
    "proxy_auth_check": "代理账号密码",
    "proxy_pac_state": "自动代理脚本",
    "codex_api_direct": "OpenAI 直连",
    "codex_api_via_proxy": "OpenAI 走代理",
    "github_direct": "GitHub 直连",
    "github_via_proxy": "GitHub 走代理",
    "dns": "DNS 解析",
    "dns_resolution": "DNS 解析",
    "wifi_signal": "Wi-Fi 信号",
    "gateway": "网关连接",
    "connectivity": "网络连通性",
    "ssl_cert": "网站证书",
    "mtu_probe": "网络包大小",
    "ip_reputation": "出口 IP 类型",
    "egress_identity": "出口身份",
    "ipv6_leak": "IPv6 泄漏检查",
    "local_ipv4": "本机 IPv4",
    "local_ipv6": "本机 IPv6",
    "default_route": "默认上网路线",
    "packet_loss": "丢包情况",
    "traceroute": "访问路径",
    "bandwidth_hog": "后台网络占用",
}


def _diagnostic_display_name(item: Dict[str, Any]) -> str:
    """Return a user-facing name for a diagnostic item."""
    existing = str(item.get("display_name") or "").strip()
    if existing:
        return existing
    name = str(item.get("name") or "").strip()
    if not name:
        return "网络检查"
    if name in _DIAGNOSTIC_DISPLAY_NAMES:
        return _DIAGNOSTIC_DISPLAY_NAMES[name]
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    label = str(details.get("label") or details.get("service") or "").strip()
    if label:
        return label
    if name.endswith("_direct"):
        return f"{name[:-7].replace('_', ' ').title()} 直连"
    if name.endswith("_via_proxy"):
        return f"{name[:-10].replace('_', ' ').title()} 走代理"
    return name.replace("_", " ")


def _normalize_diagnostic(item: Dict[str, Any]) -> Dict[str, Any]:
    """Attach display_name while preserving diagnostic IDs for rules/tests."""
    normalized = dict(item)
    normalized["display_name"] = _diagnostic_display_name(normalized)
    return normalized


def _build_report(
    env: Dict[str, Any],
    diagnostics: List[Dict[str, Any]],
    root_causes_raw: List[Dict[str, Any]],
    *,
    origin: str = "unknown",
    coverage: str = "partial",
) -> Dict[str, Any]:
    fix_ids: set = set()
    manual_entries: List[Any] = []
    for rc in root_causes_raw:
        fix_ids.update(rc.get("fixes", []))
        for ms in rc.get("manual_steps", []):
            if ms not in manual_entries:
                manual_entries.append(ms)

    root_causes = [
        {
            "id": rc["id"],
            "description": rc["description"],
            "confidence": rc.get("confidence"),
        }
        for rc in root_causes_raw
    ]

    report = {
        "schema_version": "netfix_report.v1",
        "meta": {
            "version": VERSION,
            "timestamp": human_time(),
            "platform": env.get("platform", {}).get("platform"),
            "hostname": platform.node(),
            "origin": origin,
            "coverage": coverage,
            "route_signature": dashboard_state.build_route_signature(env),
        },
        "environment": env,
        "diagnostics": [_normalize_diagnostic(item) for item in diagnostics],
        "root_causes": root_causes,
        "fixes": [_resolve_fix(fid) for fid in sorted(fix_ids)],
        "manual_steps": [_normalize_manual_step(ms) for ms in manual_entries],
    }
    report["explanation"] = explain.explain_report(report)
    return report


def _output(obj: Any, json_mode: bool, human_renderer=None) -> None:
    if json_mode:
        print_json(obj)
    elif human_renderer is not None:
        print(human_renderer())
    else:
        print(obj)


def _run_diagnostics(
    names: List[str], env: Dict[str, Any], core: Optional[Any], timeout: int
) -> List[Dict[str, Any]]:
    # Cap per-diagnostic timeout so a full doctor run finishes within the UI
    # HTTP window even on flaky networks. Apple's networkQuality normally
    # needs longer than the small reachability probes, so give that explicit
    # user-requested measurement up to 30 seconds instead of returning an
    # empty sample every time.
    regular_timeout = max(5, min(timeout, 10))
    quality_timeout = max(regular_timeout, min(timeout, 60))
    return [
        diagnose.run_diagnostic(
            name,
            env,
            core,
            timeout=quality_timeout if name == "network_quality" else regular_timeout,
        )
        for name in names
    ]


def _maybe_save_case(report_data: Dict[str, Any], args: argparse.Namespace) -> Optional[Path]:
    """Optionally persist the report as a case file in cases/."""
    if not getattr(args, "save_case", False):
        return None
    ensure_dir(Path(CASES_DIR))
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    rc = report_data.get("root_causes", [{}])[0]
    rc_id = rc.get("id", "unknown") if rc else "healthy"
    filename = f"{ts}-{rc_id}.md"
    path = Path(CASES_DIR) / filename

    env = report_data.get("environment", {})
    active = env.get("active_profile") or {}
    lines = [
        "# Case",
        "",
        "## 元信息",
        "",
        f"- **日期**：{report_data.get('meta', {}).get('timestamp', '')}",
        f"- **客户端**：{env.get('gui_client', 'unknown')} ({env.get('active_core', 'unknown')})",
        f"- **活动节点**：{active.get('remarks', active.get('id', 'unknown'))}",
        f"- **症状**：{rc.get('description', '网络自检')}",
        "",
        "## 关键诊断",
        "",
        "```json",
        json.dumps(
            {
                "diagnostics": report_data.get("diagnostics", []),
                "root_causes": report_data.get("root_causes", []),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        "```",
        "",
        "## 修复过程",
        "",
        "（待填写）",
        "",
        "## 沉淀建议",
        "",
        "（待填写：是否需要更新 rules/symptoms.json、bin 脚本或 final.md）",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def cmd_codex(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    service_results = services.check_services(
        group_ids=["ai", "dev"],
        proxy_url=args.proxy,
        mixed_port=env.get("mixed_port"),
        timeout=args.timeout,
    )
    diagnostics = list(service_results)
    diagnostics.extend(services.codex_compat_diagnostics(service_results))
    diagnostics.append(
        diagnose.run_diagnostic("proxy_core_status", env, core, timeout=args.timeout)
    )
    diagnostics.append(
        diagnose.run_diagnostic("system_proxy_state", env, core, timeout=args.timeout)
    )
    diagnostics.append(
        diagnose.run_diagnostic("node_reachability", env, core, timeout=args.timeout)
    )
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="codex", coverage="target_subset")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_services(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    group_ids = args.group.split(",") if args.group else None
    # Service probes run through multiple proxy modes per endpoint; keep each
    # probe short so a group check finishes well within the HTTP timeout.
    probe_timeout = max(5, min(args.timeout, 10))
    service_results = services.check_services(
        group_ids=group_ids,
        proxy_url=args.proxy,
        mixed_port=env.get("mixed_port"),
        timeout=probe_timeout,
    )
    diagnostics = list(service_results)
    diagnostics.append(
        diagnose.run_diagnostic("proxy_core_status", env, core, timeout=args.timeout)
    )
    root_causes = reasoner.reason(env, diagnostics)
    summary = services.summarize_group(service_results)
    report_data = _build_report(env, diagnostics, root_causes, origin="services", coverage="target_subset")
    report_data["service_summary"] = summary
    report = Report(report_data)
    report.save()
    _output(report.as_dict(), args.json, report.to_human)
    return 0


_LAYER_DIAGNOSTICS = [
    "wifi_signal",
    "interface_state",
    "dhcp_state",
    "gateway",
    "ipv4_route",
    "ipv6_route",
    "dns_resolvers",
    "dns_local",
    "dns_public",
    "system_proxy_state",
    "proxy_http_test",
    "proxy_socks_test",
    "proxy_auth_check",
    "pac_state",
    "ip_reputation",
    "dns_leak",
    "ipv6_leak",
    "path_trace",
    "network_quality",
    "bandwidth_hog",
]


def cmd_layers(args: argparse.Namespace) -> int:
    """Run the full layered network-stack diagnostic suite."""
    env = _enrich_env(detect_environment())
    core = get_core(env)
    diagnostics = _run_diagnostics(_LAYER_DIAGNOSTICS, env, core, args.timeout)
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="layers", coverage="network_stack")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def _triage_report(args: argparse.Namespace) -> Report:
    """Run the lightweight triage diagnostics and persist the report."""
    env = _enrich_env(detect_environment())
    core = get_core(env)
    names = [
        "gateway",
        "dns_local",
        "dns_public",
        "dns_resolvers",
        "proxy_core_status",
        "system_proxy_state",
        "ip_reputation",
    ]
    diagnostics = _run_diagnostics(names, env, core, args.timeout)
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="triage", coverage="partial")
    report = Report(report_data)
    report.save()
    return report


def cmd_triage(args: argparse.Namespace) -> int:
    report = _triage_report(args)
    case_path = _maybe_save_case(report.as_dict(), args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_proxy(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    names = [
        "proxy_core_status",
        "system_proxy_state",
        "proxy_http_test",
        "proxy_socks_test",
        "proxy_auth_check",
        "pac_state",
        "node_reachability",
        "codex_api_via_proxy",
    ]
    diagnostics = _run_diagnostics(names, env, core, args.timeout)
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="proxy", coverage="proxy_subset")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run the full diagnostic suite."""
    env = _enrich_env(detect_environment())
    core = get_core(env)
    # Combine layered diagnostics with legacy service probes.
    names = list(_LAYER_DIAGNOSTICS)
    names += [
        "proxy_core_status",
        "node_reachability",
        "codex_api_direct",
        "codex_api_via_proxy",
        "mtu_probe",
    ]
    diagnostics = _run_diagnostics(names, env, core, args.timeout)
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="doctor", coverage="current_mac_full")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_dns(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    env["dns_target"] = args.domain
    names = ["dns_local", "dns_public", "dns_cache"]
    diagnostics = _run_diagnostics(names, env, core, args.timeout)
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="dns", coverage="target_subset")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_wifi(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    diagnostics = [diagnose.run_diagnostic("wifi_signal", env, core, timeout=args.timeout)]
    report_data = _build_report(env, diagnostics, [], origin="wifi", coverage="target_subset")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_ssl(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    env["ssl_target"] = args.domain
    diagnostics = [diagnose.run_diagnostic("ssl_cert", env, core, timeout=args.timeout)]
    report_data = _build_report(env, diagnostics, [], origin="ssl", coverage="target_subset")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_connectivity(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    env["connectivity_target"] = args.target
    diagnostics = [diagnose.run_diagnostic("connectivity", env, core, timeout=args.timeout)]
    report_data = _build_report(env, diagnostics, [], origin="connectivity", coverage="target_subset")
    report = Report(report_data)
    report.save()
    case_path = _maybe_save_case(report_data, args)
    if case_path and not args.json:
        print(f"[case saved] {case_path}")
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    engine = FixEngine()

    def _rerun_and_report(no_auto_fixes: bool = False) -> int:
        """Run a fresh doctor report and output it."""
        names = list(_LAYER_DIAGNOSTICS)
        names += [
            "proxy_core_status",
            "node_reachability",
            "codex_api_direct",
            "codex_api_via_proxy",
            "mtu_probe",
        ]
        diagnostics = _run_diagnostics(names, env, core, args.timeout)
        root_causes = reasoner.reason(env, diagnostics)
        report_data = _build_report(
            env,
            diagnostics,
            root_causes,
            origin="post_fix_doctor",
            coverage="current_mac_full",
        )
        if no_auto_fixes:
            report_data.setdefault("meta", {})["no_auto_fixes"] = True
        report = Report(report_data)
        report.save()
        _output(report.as_dict(), args.json, report.to_human)
        return 0

    if args.all:
        report_path = Path.home() / ".netfix" / "last_report.json"
        report: Dict[str, Any] = {}
        if report_path.exists():
            report = Report.load(report_path).as_dict()
        fixes = engine.plan(report)
        results = []
        ran_any_auto_fix = False
        for fix in fixes:
            tier = fix.get("tier", FixTier.MANUAL)
            # 一键修复只自动执行 Tier 1（AUTO_SAFE）；Tier 2 需要用户在具体修复卡片上确认。
            if tier == FixTier.AUTO_SAFE:
                ran_any_auto_fix = True
                results.append(
                    engine.execute(
                        fix["id"],
                        dry_run=args.dry_run,
                        auto_confirm=args.yes,
                        env=env,
                        core=core,
                    )
                )
        if args.report:
            return _rerun_and_report(no_auto_fixes=not ran_any_auto_fix)
        _output(results, args.json)
        return 0

    if not args.issue:
        print("error: --issue <id> or --all required", file=sys.stderr)
        return 2

    result = engine.execute(
        args.issue,
        dry_run=args.dry_run,
        auto_confirm=args.yes,
        env=env,
        core=core,
    )
    if args.report:
        # 如果修复本身失败，先把错误返回给 GUI，而不是再跑一遍诊断把失败掩盖掉。
        if not result.get("ok", True):
            _output(result, args.json)
            return 1
        return _rerun_and_report()
    _output(result, args.json)
    if result.get("status") in ("cancelled", "manual"):
        return 1
    return 0 if result.get("ok", True) else 1


def _explanation_card_to_human(card: Dict[str, Any]) -> str:
    """Render an explanation/LLM card as plain-language sections."""
    lines = [f"【结论】{card.get('headline') or '暂无明确结论'}", ""]
    detail = str(card.get("explanation") or "").strip()
    if detail:
        lines.append(f"【为什么】{detail}")
        lines.append("")

    lines.append("【建议操作】")
    wrote_action = False
    for action in card.get("actions") or []:
        if not isinstance(action, dict) or not action.get("id"):
            continue
        wrote_action = True
        lines.append(f"  - {action.get('label') or action['id']}")
        lines.append(f"    python3 netfix.py fix --issue {action['id']}")
    for step in card.get("manual_steps") or []:
        if isinstance(step, dict):
            desc = step.get("description") or step.get("id")
            substeps = step.get("steps") or []
        else:
            desc, substeps = str(step), []
        if not desc and not substeps:
            continue
        wrote_action = True
        if desc:
            lines.append(f"  - {desc}")
        for sub in substeps:
            lines.append(f"      • {sub}")
    if not wrote_action:
        lines.append("  暂无可执行操作；可以先跑 python3 netfix.py doctor 做一次完整检查。")
    return "\n".join(lines)


def cmd_explain(args: argparse.Namespace) -> int:
    """Print the plain-language explanation for the latest report."""
    report = Report.load().as_dict()
    explanation = explain.explain_report(report)
    _output(explanation, args.json, lambda: _explanation_card_to_human(explanation))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Answer a natural-language network question in plain words."""
    try:
        report: Optional[Dict[str, Any]] = Report.load().as_dict()
    except Exception:
        report = None
    if report is None:
        # 还没有诊断报告，先跑一次轻量 triage 拿到上下文再回答。
        report = _triage_report(args).as_dict()
    # LLM 未配置时 explain_with_llm 会自动降级为本地规则卡片，无需特判。
    card = llm_explain.explain_with_llm(report, question=args.question)
    _output(card, args.json, lambda: _explanation_card_to_human(card))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    report = Report.load()
    _output(report.as_dict(), args.json, report.to_human)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """Inspect, prune, or clear local report/event logs."""
    actions: List[Dict[str, Any]] = []
    if args.retention_days is not None:
        privacy = settings.update_privacy_settings({"log_retention_days": args.retention_days})
        actions.append({"action": "set_retention", "settings": privacy})
    if args.prune:
        days = args.retention_days or settings.get_privacy_settings().get("log_retention_days", 7)
        actions.append({"action": "prune", "result": logs.prune_events(days)})
    if args.clear:
        actions.append({"action": "clear", "result": logs.clear_logs(clear_latest_report=True, clear_events=True)})
    payload = logs.load_logs()
    if actions:
        payload["actions"] = actions
    _output(payload, args.json)
    return 0 if payload.get("ok") else 1


def cmd_rollback(args: argparse.Namespace) -> int:
    engine = FixEngine()
    result = engine.rollback()
    _output(result, args.json)
    return 0 if result.get("ok") else 1


def cmd_kb(args: argparse.Namespace) -> int:
    results = kb.query(args.query)
    _output(results, args.json)
    return 0


def _notify(title: str, message: str) -> None:
    if platform.system() != "Darwin":
        return
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def _codex_summary(args: argparse.Namespace) -> Dict[str, Any]:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    diagnostics = check_codex(proxy_url=args.proxy, timeout=args.timeout)
    diagnostics.append(
        diagnose.run_diagnostic("proxy_core_status", env, core, timeout=args.timeout)
    )
    diagnostics.append(
        diagnose.run_diagnostic("node_reachability", env, core, timeout=args.timeout)
    )
    root_causes = reasoner.reason(env, diagnostics)
    report_data = _build_report(env, diagnostics, root_causes, origin="codex", coverage="target_subset")
    report = Report(report_data)
    report.save()
    return report_data


def _codex_status(summary: Dict[str, Any]) -> str:
    causes = summary.get("root_causes", [])
    if not causes:
        return "healthy"
    ids = [c.get("id", "unknown") for c in causes]
    return ",".join(ids)


def cmd_watch(args: argparse.Namespace) -> int:
    last_status: Optional[str] = None
    run = 0
    while args.max_runs == 0 or run < args.max_runs:
        run += 1
        summary = _codex_summary(args)
        status = _codex_status(summary)
        timestamp = summary.get("meta", {}).get("timestamp", "")
        if not args.json:
            print(f"[{timestamp}] run={run} status={status}")

        if last_status is not None and status != last_status:
            if args.save_case:
                path = _maybe_save_case(summary, args)
                if path and not args.json:
                    print(f"[case saved] {path}")
            if args.notify:
                if status == "healthy":
                    _notify("netfix", "网络已恢复")
                else:
                    _notify("netfix", f"网络异常：{status}")
            if args.json:
                print_json({"event": "state_change", "from": last_status, "to": status, "summary": summary})
        elif args.json:
            print_json({"event": "tick", "run": run, "status": status})

        last_status = status
        if args.max_runs == 0 or run < args.max_runs:
            time.sleep(args.interval)
    return 0


def _find_saved_proxy_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    for profile in settings.get_proxy_profiles():
        if profile_id in (str(profile.get("id") or ""), str(profile.get("name") or "")):
            return profile
    return None


def cmd_proxy_monitor(args: argparse.Namespace) -> int:
    """Continuously validate a saved residential/custom proxy profile."""
    profile = _find_saved_proxy_profile(args.profile)
    if profile is None:
        _output({"ok": False, "error": f"profile not found: {args.profile}"}, args.json)
        return 1

    run = 0
    last_status: Optional[str] = None
    final_ok = True
    while args.max_runs == 0 or run < args.max_runs:
        run += 1
        result = residential_proxy.validate_saved_profile(
            profile,
            target_url=args.target_url,
            timeout=args.timeout,
        )
        check = result.get("proxy_check", {})
        status = str(check.get("status") or "fail")
        final_ok = final_ok and bool(result.get("ok"))
        updated = dict(profile)
        updated["last_check"] = check
        settings.upsert_proxy_profile(updated)
        profile = updated

        event = {
            "event": "proxy_check",
            "run": run,
            "profile_id": profile.get("id"),
            "profile_name": profile.get("name"),
            "status": status,
            "changed": last_status is not None and status != last_status,
            "proxy_check": check,
        }
        if args.json:
            print_json(event)
        else:
            message = check.get("error") or f"http={check.get('http_code')}"
            print(f"run={run} profile={profile.get('name') or profile.get('id')} status={status} {message}")

        last_status = status
        if args.max_runs == 0 or run < args.max_runs:
            time.sleep(args.interval)
    return 0 if final_ok else 1


def _probe_tcp(host: str, port: int, timeout: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _mihomo_delay(core: Any, name: str, timeout: int) -> Optional[int]:
    import urllib.request
    info = core.get_api_info() or {}
    port = info.get("port")
    secret = info.get("secret")
    if not port:
        return None
    url = f"http://127.0.0.1:{port}/proxies/{urllib.request.quote(name)}/delay"
    data = json.dumps({"timeout": timeout * 1000, "url": "http://www.gstatic.com/generate_204"}).encode("utf-8")
    req = urllib.request.Request(url, method="GET", data=data)
    req.add_header("Content-Type", "application/json")
    if secret:
        req.add_header("Authorization", f"Bearer {secret}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("delay")
    except Exception:
        return None


def _pick_healthy_profile(core: Any, active: Dict[str, Any], timeout: int) -> Optional[Dict[str, Any]]:
    profiles = core.list_profiles()
    if not profiles:
        return None

    # mihomo: use API delay when reachable.
    if core.can_api_switch():
        best: Optional[Dict[str, Any]] = None
        best_delay: Optional[int] = None
        for p in profiles:
            name = p.get("remarks") or p.get("id")
            if name == active.get("remarks") or name == active.get("id"):
                continue
            delay = _mihomo_delay(core, name, timeout)
            if delay and (best_delay is None or delay < best_delay):
                best = p
                best_delay = delay
        return best

    # v2rayN / others: TCP probe to node address:port.
    for p in profiles:
        if p.get("id") == active.get("id"):
            continue
        addr = p.get("address")
        port = p.get("port")
        if not addr or not port:
            continue
        if _probe_tcp(addr, port, timeout):
            return p
    return None


def cmd_proxy_switch(args: argparse.Namespace) -> int:
    env = _enrich_env(detect_environment())
    core = get_core(env)
    if not core:
        _output({"ok": False, "error": "no running proxy core detected"}, args.json)
        return 1

    active = core.get_active_profile() or {}
    target: Optional[Dict[str, Any]] = None

    if args.profile:
        for p in core.list_profiles():
            if args.profile in (p.get("id"), p.get("remarks")):
                target = p
                break
        if not target:
            _output({"ok": False, "error": f"profile not found: {args.profile}"}, args.json)
            return 1
    elif args.auto:
        target = _pick_healthy_profile(core, active, args.timeout)
        if not target:
            _output({"ok": False, "error": "no healthy alternative profile found"}, args.json)
            return 1
    else:
        _output(
            {
                "ok": False,
                "error": "use --profile <id/name> or --auto",
                "active_profile": active,
                "profiles": core.list_profiles(),
            },
            args.json,
        )
        return 2

    if target.get("id") == active.get("id"):
        _output({"ok": True, "message": "target profile is already active", "profile": target}, args.json)
        return 0

    tier = 1 if core.can_api_switch() else 2
    if args.dry_run:
        _output({"ok": True, "dry_run": True, "tier": tier, "profile": target}, args.json)
        return 0

    if tier >= 2:
        if args.json:
            _output(
                {
                    "ok": False,
                    "error": "Tier 2 operation requires interactive confirmation; use --dry-run in JSON/API mode",
                    "tier": tier,
                    "profile": target,
                },
                args.json,
            )
            return 1

        prompt = (
            f"确认切换代理节点到 {target.get('remarks') or target.get('id')}? "
            "这会修改代理客户端配置，v2rayN 可能需要手动重启。"
        )
        if not confirm(prompt, default=False):
            _output({"ok": False, "status": "cancelled", "tier": tier, "profile": target}, args.json)
            return 1

    ok = core.switch_profile(target["id"])
    result = {
        "ok": ok,
        "core": core.name,
        "tier": tier,
        "from": active,
        "to": target,
    }
    if not ok:
        result["error"] = "switch_profile failed"
        _output(result, args.json)
        return 1

    if tier >= 2:
        result["notice"] = "v2rayN GUI must be restarted for the change to take effect"
    _output(result, args.json)
    return 0


def cmd_server(args: argparse.Namespace) -> int:
    """Start the local HTTP API server."""
    api.run_server(host=args.host, port=args.port, timeout=args.timeout)
    return 0


_CLI_START_HERE_EPILOG = """\
start here:

  人话提问：python3 netfix.py ask "我网速很慢"
  快速排查：python3 netfix.py triage
  完整检查：python3 netfix.py doctor
  人话解释上次报告：python3 netfix.py explain
  预览修复：python3 netfix.py fix --issue <id> --dry-run
  查解决手册：python3 netfix.py kb --query 关键词

  普通用户：打开 Netfix.app，主窗口已经自动接入 /dashboard/state。
  Agent / Codex：用 python3 netfix.py codex --json 一键检查 Codex 链路。
  开发者：python3 netfix.py server --host 127.0.0.1 --port 0 起本地 HTTP API；
           浏览器会打开 Web 控制台，token 写入 ~/.netfix/api-token-<pid>.txt。

单个子命令的详细参数：python3 netfix.py <cmd> --help。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netfix",
        description="Offline-first network self-rescue agent for macOS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_START_HERE_EPILOG,
    )
    parser.add_argument("--version", action="version", version=f"netfix {VERSION}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出 JSON")
    common.add_argument("--dry-run", action="store_true", help="只打印不执行")
    common.add_argument("--yes", action="store_true", help="自动确认“安全、不会改系统网络设置”的修复")
    common.add_argument(
        "--timeout", type=int, default=30, help="网络探针超时（秒），默认 30"
    )
    common.add_argument(
        "--save-case", action="store_true", help="把本次报告保存为 cases/ 下的 case 文件"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", parents=[common], help='人话提问，如 ask "我网速很慢"')
    p_ask.add_argument("question", type=str, help="你的网络问题")

    p_codex = sub.add_parser("codex", parents=[common], help="Codex / OpenAI / GitHub 健康检查")
    p_codex.add_argument("--proxy", type=str, default=None, help="手动指定代理 URL")

    p_services = sub.add_parser("services", parents=[common], help="境外服务分组健康检查")
    p_services.add_argument("--group", type=str, default=None, help="分组 id，逗号分隔，如 ai,dev,common")
    p_services.add_argument("--proxy", type=str, default=None, help="手动指定代理 URL")

    p_triage = sub.add_parser("triage", aliases=["check"], parents=[common], help="快速排查最常见网络问题")
    p_triage.set_defaults(command="triage")
    sub.add_parser("proxy", parents=[common], help="代理核心专项诊断")
    p_doctor = sub.add_parser("doctor", aliases=["full-check"], parents=[common], help="完整检查网络、DNS、代理和目标网站")
    p_doctor.set_defaults(command="doctor")
    sub.add_parser("layers", parents=[common], help="全栈分层诊断")

    p_dns = sub.add_parser("dns", parents=[common], help="DNS 诊断")
    p_dns.add_argument("domain", nargs="?", default="example.com", help="目标域名")

    sub.add_parser("wifi", parents=[common], help="Wi-Fi 信号诊断")

    p_ssl = sub.add_parser("ssl", parents=[common], help="SSL/TLS 证书诊断")
    p_ssl.add_argument("domain", nargs="?", default="cloudflare.com", help="目标域名")

    p_conn = sub.add_parser("connectivity", parents=[common], help="端到端连通性")
    p_conn.add_argument("target", nargs="?", default="8.8.8.8:443", help="host:port")

    p_fix = sub.add_parser("fix", parents=[common], help="执行修复")
    p_fix.add_argument("--issue", type=str, help="修复项 ID")
    p_fix.add_argument("--all", action="store_true", help="执行当前报告里所有 Tier 1 修复")
    p_fix.add_argument("--report", action="store_true", help="修复后重新诊断并返回报告（供 UI 使用）")

    sub.add_parser("report", parents=[common], help="显示上一次报告")
    p_logs = sub.add_parser("logs", parents=[common], help="查看/清理本地报告和事件日志")
    p_logs.add_argument("--clear", action="store_true", help="清理 last_report.json 和 events.jsonl")
    p_logs.add_argument("--prune", action="store_true", help="按保留天数裁剪 events.jsonl")
    p_logs.add_argument("--retention-days", type=int, help="设置事件日志保留天数（1-365）")
    sub.add_parser("explain", parents=[common], help="用人话解释上一次报告")
    sub.add_parser("rollback", parents=[common], help="恢复上一次修改前的网络设置")

    p_kb = sub.add_parser("kb", aliases=["guide"], parents=[common], help="按关键词查解决手册")
    p_kb.set_defaults(command="kb")
    p_kb.add_argument("--query", type=str, required=True, help="关键词")

    p_watch = sub.add_parser("watch", parents=[common], help="持续监控 Codex 连通性")
    p_watch.add_argument("--interval", type=int, default=60, help="检查间隔（秒），默认 60")
    p_watch.add_argument("--max-runs", type=int, default=0, help="最大检查次数，0 为无限")
    p_watch.add_argument("--notify", action="store_true", help="状态变化时弹出 macOS 通知")
    p_watch.add_argument("--proxy", type=str, default=None, help="手动指定代理 URL")

    p_proxy_monitor = sub.add_parser("proxy-monitor", parents=[common], help="持续验证保存的自定义代理配置")
    p_proxy_monitor.add_argument("--profile", type=str, required=True, help="Profile id 或名称")
    p_proxy_monitor.add_argument("--interval", type=int, default=60, help="检查间隔（秒），默认 60")
    p_proxy_monitor.add_argument("--max-runs", type=int, default=0, help="最大检查次数，0 为无限")
    p_proxy_monitor.add_argument(
        "--target-url",
        type=str,
        default="https://www.gstatic.com/generate_204",
        help="验证目标 URL，默认 Google 204 探针",
    )

    p_switch = sub.add_parser("proxy-switch", parents=[common], help="切换到健康代理节点")
    p_switch.add_argument("--profile", type=str, help="目标节点 id 或名称")
    p_switch.add_argument("--auto", action="store_true", help="自动选择第一个健康节点")

    p_server = sub.add_parser("server", help="启动本地 HTTP API 服务")
    p_server.add_argument("--host", type=str, default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    p_server.add_argument("--port", type=int, default=0, help="监听端口，0 表示自动分配")
    p_server.add_argument("--timeout", type=int, default=60, help="默认 CLI 超时（秒）")

    return parser


_COMMAND_HANDLERS = {
    "ask": cmd_ask,
    "codex": cmd_codex,
    "services": cmd_services,
    "triage": cmd_triage,
    "proxy": cmd_proxy,
    "doctor": cmd_doctor,
    "layers": cmd_layers,
    "dns": cmd_dns,
    "wifi": cmd_wifi,
    "ssl": cmd_ssl,
    "connectivity": cmd_connectivity,
    "fix": cmd_fix,
    "report": cmd_report,
    "logs": cmd_logs,
    "explain": cmd_explain,
    "rollback": cmd_rollback,
    "kb": cmd_kb,
    "watch": cmd_watch,
    "proxy-monitor": cmd_proxy_monitor,
    "proxy-switch": cmd_proxy_switch,
    "server": cmd_server,
}

# Subcommand aliases registered in build_parser().
_KNOWN_COMMAND_WORDS = set(_COMMAND_HANDLERS) | {"check", "full-check", "guide"}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        first = argv[0]
        if (
            not first.startswith("-")
            and first not in _KNOWN_COMMAND_WORDS
            and not any(word.startswith(first) for word in _KNOWN_COMMAND_WORDS)
        ):
            # 用户把自然语言直接当成了子命令；给一条能看懂的路，而不是英文报错。
            print(f'看不懂这个命令："{first}"。', file=sys.stderr)
            print('直接描述你的问题：python3 netfix.py ask "你的网络问题"', file=sys.stderr)
            print("完整检查：python3 netfix.py doctor", file=sys.stderr)
            return 2
    args = parser.parse_args(argv)

    try:
        return _COMMAND_HANDLERS[args.command](args)
    except Exception as exc:
        if args.json:
            print_json({"ok": False, "error": str(exc)})
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
