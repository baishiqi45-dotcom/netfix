"""自由文本症状 intake：对 rules/symptoms.json 做关键词计分匹配。

输入用户的一句话症状描述（支持中文口语），输出命中的症状、建议检查和
建议调用的 MCP 工具，作为对话式排查的第一步路由：intake → 建议工具 → netfix_chat。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from netfix.constants import RULES_DIR

SCHEMA_VERSION = "netfix_symptom_intake.v1"

# rules/symptoms.json 的关键词偏技术术语，这里补常见中文/口语说法。
_EXTRA_KEYWORDS: Dict[str, List[str]] = {
    "codex-unreachable": ["codex 打不开", "codex打不开", "openai 连不上", "chatgpt 打不开"],
    "dns-failure": ["dns", "解析不了", "域名解析", "打不开网页"],
    "proxy-auth-failure": ["代理认证", "要密码"],
    "vpn-node-failure": ["节点超时", "节点挂了", "连不上节点", "超时"],
    "wifi-gateway-down": ["wifi", "无线", "路由器", "断网", "上不了网", "没有网"],
    "ssl-cert-error": ["证书", "ssl"],
    "mtu-mismatch": ["mtu", "大包"],
    "ipv6-leak": ["ipv6", "泄漏"],
    "system-proxy-not-effective": ["系统代理", "代理没生效", "代理不生效", "微信", "发不出去"],
    "macos-firewall-block": ["防火墙", "拦截"],
    "ai-service-ip-blocked": ["风控", "封号", "被墙", "chatgpt", "claude"],
    "dhcp-misconfig": ["dhcp", "自分配", "169.254"],
    "dns-leak": ["dns 泄漏", "dns泄漏"],
    "ip-reputation-risk": ["ip 风险", "数据中心", "高风险"],
    "proxy-auth-required": ["代理认证", "要密码"],
    "local-wifi-issue": ["网速慢", "很慢", "网络慢", "丢包", "延迟高", "卡顿", "转圈"],
    "cli-no-proxy": [
        "codex cli 连不上",
        "命令行连不上",
        "终端连不上",
        "浏览器可以",
        "浏览器能开",
        "cli 不行",
        "curl 不行",
        "终端代理",
        "git 代理",
        "export proxy",
    ],
    "network-switch": [
        "换网络",
        "换 wifi",
        "换 wi-fi",
        "切换 wifi",
        "切换网络",
        "换了网络",
        "换了 wifi",
        "回家",
        "回公司",
        "到了公司",
        "换路由器",
        "换网了",
        "代理全乱",
    ],
}

# 症状规则里的诊断 id → 现有 MCP 工具。
_DIAGNOSTIC_TOOLS: Dict[str, Dict[str, Any]] = {
    "codex_api_direct": {"tool": "netfix_codex", "arguments": {}, "why": "检查 Codex/OpenAI 直连与代理链路"},
    "codex_api_via_proxy": {"tool": "netfix_codex", "arguments": {}, "why": "检查 Codex/OpenAI 直连与代理链路"},
    "node_reachability": {"tool": "netfix_services", "arguments": {}, "why": "探测海外服务组可达性"},
    "proxy_core_status": {"tool": "netfix_get_listeners", "arguments": {}, "why": "确认本地代理端口是否在监听"},
    "proxy_auth_check": {"tool": "netfix_check_proxy_auth", "arguments": {}, "why": "检测系统代理是否要求认证"},
    "dns_local": {"tool": "netfix_get_dns_state", "arguments": {}, "why": "查看当前 DNS 解析器状态"},
    "dns_public": {"tool": "netfix_dns_resolve", "arguments": {"target": "example.com"}, "why": "用系统解析器实测域名解析"},
    "dns_cache": {"tool": "netfix_get_dns_state", "arguments": {}, "why": "查看当前 DNS 解析器状态"},
    "dns_leak": {"tool": "netfix_get_dns_state", "arguments": {}, "why": "查看当前 DNS 解析器状态"},
    "dns_resolvers": {"tool": "netfix_get_dns_state", "arguments": {}, "why": "查看当前 DNS 解析器状态"},
    "gateway": {"tool": "netfix_get_global_state", "arguments": {}, "why": "查看主网络路径与网关状态"},
    "wifi_signal": {"tool": "netfix_get_global_state", "arguments": {}, "why": "查看主网络路径与网关状态"},
    "path_trace": {"tool": "netfix_trace_path", "arguments": {"target": "8.8.8.8"}, "why": "跟踪到公网的网络路径"},
    "ip_reputation": {"tool": "netfix_get_ip_reputation", "arguments": {}, "why": "查看出口 IP 信誉与 ISP/ASN"},
    "ipv6_leak": {"tool": "netfix_triage", "arguments": {}, "why": "跑五层排查确认 IPv6 泄漏面"},
    "system_proxy_state": {"tool": "netfix_get_proxy_state", "arguments": {}, "why": "查看系统代理设置是否生效"},
    "interface_state": {"tool": "netfix_get_interfaces", "arguments": {}, "why": "查看网卡与地址分配"},
    "ipv4_route": {"tool": "netfix_get_routes", "arguments": {}, "why": "查看 IPv4 路由表"},
    "dhcp_state": {"tool": "netfix_get_interfaces", "arguments": {}, "why": "查看网卡与地址分配"},
    "mtu_probe": {"tool": "netfix_triage", "arguments": {}, "why": "跑五层排查定位 MTU/链路问题"},
}

_FALLBACK_NOTE = "未匹配到已知症状，建议先运行 netfix_triage 做一次五层排查，再把结果交给 netfix_chat 分析。"
_MATCHED_NOTE = "按关键词命中计分，confidence 仅供排序参考；建议先运行 suggested_tools 收集证据，再用 netfix_chat 结合 history 多轮分析。"


def _load_symptoms() -> List[Dict[str, Any]]:
    try:
        data = json.loads((RULES_DIR / "symptoms.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in data.get("symptoms", []) or [] if isinstance(item, dict)]


def _score_symptom(text: str, symptom: Dict[str, Any]) -> Tuple[float, int]:
    """大小写不敏感的子串命中计分；第 2 个及以后的关键词命中各加 0.5 权重。"""
    keywords = [str(kw) for kw in symptom.get("keywords", []) or []]
    keywords += _EXTRA_KEYWORDS.get(str(symptom.get("id") or ""), [])
    hits = sum(1 for kw in dict.fromkeys(keywords) if kw and kw.lower() in text)
    if not hits:
        return 0.0, 0
    return hits + 0.5 * (hits - 1), hits


def intake_symptoms(text: str, limit: int = 3) -> Dict[str, Any]:
    """对自由文本症状描述做计分匹配，返回命中症状与建议的后续动作。"""
    normalized = str(text or "").strip().lower()
    if not normalized:
        return {
            "schema_version": SCHEMA_VERSION,
            "matched_symptoms": [],
            "suggested_checks": [],
            "suggested_tools": [],
            "note": _FALLBACK_NOTE,
        }

    scored = []
    for symptom in _load_symptoms():
        score, _hits = _score_symptom(normalized, symptom)
        if score <= 0:
            continue
        scored.append((score, symptom))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    top = scored[: max(1, int(limit))]

    matched_symptoms = []
    suggested_checks: List[str] = []
    suggested_tools: List[Dict[str, Any]] = []
    seen_tools = set()
    for score, symptom in top:
        symptom_id = str(symptom.get("id") or "")
        matched_symptoms.append({
            "id": symptom_id,
            "name": str(symptom.get("name") or symptom_id),
            "score": score,
            "confidence": min(0.95, round(0.35 + 0.15 * score, 2)),
        })
        for diagnostic in symptom.get("diagnostics", []) or []:
            diagnostic_id = str(diagnostic)
            if diagnostic_id not in suggested_checks:
                suggested_checks.append(diagnostic_id)
            tool = _DIAGNOSTIC_TOOLS.get(diagnostic_id)
            if tool and tool["tool"] not in seen_tools:
                seen_tools.add(tool["tool"])
                suggested_tools.append({
                    "tool": tool["tool"],
                    "arguments": dict(tool["arguments"]),
                    "why": tool["why"],
                })

    return {
        "schema_version": SCHEMA_VERSION,
        "matched_symptoms": matched_symptoms,
        "suggested_checks": suggested_checks,
        "suggested_tools": suggested_tools,
        "note": _MATCHED_NOTE if matched_symptoms else _FALLBACK_NOTE,
    }
