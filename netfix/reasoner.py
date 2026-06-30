"""Local rule-based root cause reasoner.

Takes the runtime ``env`` and a list of diagnostic results, then returns
root causes sorted by confidence.  Each root cause includes suggested
fixes and manual steps.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from netfix.constants import RULES_DIR


def reason(env: Dict[str, Any], diagnostics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Infer root causes from *diagnostics* and the rule base.

    Returns a list of dicts: ``{id, description, confidence, fixes,
    manual_steps}`` sorted by confidence descending.
    """
    rules_path = RULES_DIR / "symptoms.json"
    rules: Dict[str, Any] = {"symptoms": [], "fixes": {}}
    if rules_path.exists():
        with open(rules_path, encoding="utf-8") as f:
            rules = json.load(f)

    diag_map = {d["name"]: d for d in diagnostics if "name" in d}
    results: List[Dict[str, Any]] = []

    def add(
        cause_id: str,
        description: str,
        confidence: float,
        fixes: List[str] | None = None,
        manual_steps: List[str] | None = None,
    ) -> None:
        for r in results:
            if r["id"] == cause_id:
                r["confidence"] = max(r["confidence"], confidence)
                if fixes:
                    existing = set(r.get("fixes", []))
                    r.setdefault("fixes", []).extend([x for x in fixes if x not in existing])
                if manual_steps:
                    existing = set(r.get("manual_steps", []))
                    r.setdefault("manual_steps", []).extend([x for x in manual_steps if x not in existing])
                return
        results.append({
            "id": cause_id,
            "description": description,
            "confidence": confidence,
            "fixes": list(fixes or []),
            "manual_steps": list(manual_steps or []),
        })

    # Local network / interface / DHCP.
    if diag_map.get("interface_state", {}).get("status") == "fail":
        add("interface-down", "默认网络接口无有效 IP 或处于非活动状态", 0.9,
            manual_steps=["检查网线或 Wi-Fi 连接", "在系统设置中重新连接网络"])
    elif diag_map.get("interface_state", {}).get("status") == "warn":
        add("interface-warning", "默认网络接口状态异常", 0.6)

    if diag_map.get("dhcp_state", {}).get("status") == "fail":
        add("dhcp-misconfig", "DHCP 未分配有效地址，可能是 169.254 自分配", 0.9,
            manual_steps=["尝试在系统设置中「续租 DHCP」", "重启路由器"])
    elif diag_map.get("dhcp_state", {}).get("status") == "warn":
        add("dhcp-missing-options", "DHCP 租约缺少网关或 DNS 选项", 0.7)

    if diag_map.get("ipv4_route", {}).get("status") == "fail":
        add("no-ipv4-route", "没有可用的 IPv4 默认路由", 0.9,
            manual_steps=["检查网线/Wi-Fi 是否已连接", "重启路由器", "运行 `sudo route flush` 后重连"])

    ipv6_route = diag_map.get("ipv6_route", {})
    if ipv6_route.get("status") == "warn":
        ipv6_route_details = ipv6_route.get("details", {})
        if ipv6_route_details.get("has_default_route"):
            add("ipv6-route-ambiguous", "IPv6 默认路由存在但网关解析异常，可能导致 IPv6 优先连接回退变慢", 0.45)
        else:
            add("ipv6-route-missing", "IPv6 默认路由缺失，使用 IPv6 的目标可能失败", 0.6)

    # Proxy core health.
    if diag_map.get("proxy_core_status", {}).get("status") == "fail":
        add("proxy-down", "代理核心未运行或 mixed 端口未监听", 0.9,
            fixes=["check-proxy-core"])

    # Codex reachability patterns.
    direct = diag_map.get("codex_api_direct", {}).get("status")
    via_proxy = diag_map.get("codex_api_via_proxy", {}).get("status")
    codex_401 = any(
        d.get("status") == "warn" and d.get("http_code") == 401
        for d in diagnostics
        if d.get("name", "").startswith("openai")
    )

    if codex_401 and diag_map.get("proxy_core_status", {}).get("status") == "ok":
        add("codex-reachable-needs-key", "网络能连到 OpenAI，但 API Key 没配好；如果只是修 ChatGPT 网页，可以先忽略这个", 0.99)
    elif direct == "fail" and via_proxy == "ok":
        add("direct-blocked", "直连无法访问 OpenAI，但经本地代理可通；代理当前正常", 0.95)
    elif direct == "fail" and via_proxy == "fail":
        add("node-failed", "直连与代理均无法访问 OpenAI，可能是当前节点或代理核心失效", 0.8,
            fixes=["check-proxy-core", "flush-dns-cache"],
            manual_steps=["在 GUI 客户端切换到其他节点", "检查节点配置地址与端口"])

    # DNS patterns.
    dns_local = diag_map.get("dns_local", {}).get("status")
    dns_public = diag_map.get("dns_public", {}).get("status")
    if dns_public == "fail" and dns_local == "fail":
        add("dns-cache-stale", "本地与公共 DNS 均无法解析，可能存在缓存污染或网络层故障", 0.85,
            fixes=["flush-dns-cache"])
    elif dns_local == "fail" and dns_public == "ok":
        add("dns-cache-stale", "本地 resolver 失效，公共 DNS 正常；可能缓存污染", 0.8,
            fixes=["flush-dns-cache"])

    # Gateway / Wi-Fi.
    if diag_map.get("gateway", {}).get("status") == "fail":
        add("gateway-unreachable", "默认网关不可达，Wi-Fi/物理层故障", 0.85,
            manual_steps=["靠近路由器或切换 Wi-Fi 频段", "重启路由器", "在系统设置中忘记网络后重连"])

    # System proxy.
    system_proxy = diag_map.get("system_proxy_state", {})
    system_proxy_status = system_proxy.get("status")
    if system_proxy_status == "fail":
        add("system-proxy-off", "系统代理未开启或指向错误端口", 0.8,
            fixes=["reset-system-proxy"])
    elif system_proxy_status == "warn":
        system_proxy_details = system_proxy.get("details", {})
        if system_proxy_details.get("mixed_auto_and_manual"):
            add(
                "mixed-proxy-pac",
                "手动代理和 PAC/WPAD 自动代理同时开启，部分应用启动时可能先走自动代理或直连再回退",
                0.7,
                fixes=["disable-auto-proxy"],
                manual_steps=[
                    "在代理客户端里只保留一种系统代理模式：手动 HTTP/HTTPS/SOCKS 或 PAC，不要同时开启",
                    "优先关闭 macOS 代理自动发现/WPAD 后重新启动 Codex 验证",
                ],
            )
        else:
            add("system-proxy-off", "系统代理未开启或指向错误端口", 0.8,
                fixes=["reset-system-proxy"])

    # Proxy protocol / auth.
    if diag_map.get("proxy_auth_check", {}).get("details", {}).get("requires_auth"):
        add("proxy-auth-required", "代理服务器要求认证（HTTP 407）", 0.95,
            manual_steps=["在系统设置 > 网络 > 代理中补全用户名和密码", "或检查代理客户端认证配置"])

    if diag_map.get("proxy_http_test", {}).get("status") == "fail":
        add("proxy-http-failed", "HTTP 代理测试请求失败", 0.85,
            fixes=["check-proxy-core"],
            manual_steps=["检查代理客户端是否启动", "确认系统 HTTP/HTTPS 代理端口正确"])

    if diag_map.get("proxy_socks_test", {}).get("status") == "fail":
        add("proxy-socks-failed", "SOCKS5 代理测试请求失败", 0.85,
            fixes=["check-proxy-core"],
            manual_steps=["确认 SOCKS 端口已开启", "尝试使用 socks5h:// 以避免 DNS 泄漏"])

    if diag_map.get("pac_state", {}).get("status") == "warn":
        add("pac-unreachable", "PAC 自动代理文件配置但无法访问", 0.75,
            manual_steps=["检查 PAC 文件 URL 是否可达", "临时切换到手动代理以排除 PAC 问题"])

    # Node reachability (TCP layer).
    node_reach = diag_map.get("node_reachability", {}).get("status")
    node_details = diag_map.get("node_reachability", {}).get("details", {})
    if node_reach == "fail":
        active = (node_details.get("profiles") or [])
        dead = [p for p in active if p.get("reachable") is False]
        add("active-node-unreachable", "当前代理节点 TCP 层不可达", 0.9,
            fixes=["check-proxy-core"],
            manual_steps=["在 GUI 客户端切换到其他节点", "若全部节点都不可达，检查服务商或本地网络"])
    elif node_reach == "warn":
        add("some-nodes-unreachable", "部分代理节点 TCP 层不可达", 0.6,
            manual_steps=["在 GUI 客户端切换到延迟/可达性更好的节点"])

    # MTU mismatch.
    if diag_map.get("mtu_probe", {}).get("status") == "warn":
        add("mtu-too-high", "MTU 不匹配：小包通大卡", 0.75,
            manual_steps=["运行 bin/mtu-tune.sh 探测并设置最佳 MTU"])

    # IPv6 leak / risk.
    ipv6_leak = diag_map.get("ipv6_leak", {})
    if ipv6_leak.get("status") in ("warn", "fail"):
        ipv6_leak_details = ipv6_leak.get("details", {})
        if ipv6_leak_details.get("leak_confirmed"):
            add("ipv6-exposed", "检测到公网 IPv6 可能绕过代理", 0.85,
                fixes=["disable-ipv6"],
                manual_steps=["如果你不想关闭 IPv6，也可以在代理客户端里开启 IPv6 转发或关闭 IPv6。"])
        elif ipv6_leak_details.get("fallback_risk"):
            add(
                "ipv6-fallback-risk",
                "代理开启时仍存在 IPv6 默认路由，部分目标可能先尝试 IPv6 后回退，导致启动变慢或重连",
                0.65,
                manual_steps=[
                    "如果你不想改系统 IPv6，可以先在代理客户端里开启 IPv6 转发或关闭 IPv6。",
                ],
                fixes=["disable-ipv6"],
            )

    # DNS leak.
    if diag_map.get("dns_leak", {}).get("status") == "warn":
        add("dns-leak", "检测到 DNS 泄漏风险（代理开启但 DNS 仍走本地）", 0.8,
            fixes=["flush-dns-cache"],
            manual_steps=["将 DNS 改为公共 DNS 或在代理客户端中启用 DNS 劫持", "使用 socks5h:// 让 SOCKS 代理解析"])

    # IP reputation.
    ip_rep = diag_map.get("ip_reputation", {})
    if ip_rep.get("status") in ("warn", "fail"):
        details = ip_rep.get("details", {})
        if details.get("same_as_local"):
            add("proxy-not-effective", "代理似乎未生效，公网 IP 与本地 IP 相同", 0.85,
                fixes=["check-proxy-core", "reset-system-proxy"],
                manual_steps=["确认代理客户端已启动", "检查系统代理是否指向正确端口"])
        elif details.get("ip_type") == "hosting/datacenter":
            add("ip-datacenter", "出口 IP 属于数据中心/服务器，容易被目标站风控", 0.75,
                manual_steps=["切换到住宅 IP 或移动 IP 节点", "联系代理服务商更换出口"])
        elif details.get("risk_score") is not None and details.get("risk_score") >= 33:
            add("ip-reputation-risk", "出口 IP 风险评分较高，可能被拉黑", 0.75,
                manual_steps=["切换到其他节点", "在 AbuseIPDB/proxycheck.io 上复核该 IP"])

    # Path / transit.
    path = diag_map.get("path_trace", {})
    path_hops = path.get("details", {}).get("hops", [])
    if path.get("status") == "fail" and path_hops:
        first = path_hops[0]
        if first.get("loss_percent") is not None and first.get("loss_percent") > 5:
            add("local-wifi-issue", "第一跳丢包严重，本地 Wi-Fi/网关存在问题", 0.85,
                manual_steps=["靠近路由器", "切换到 5GHz 频段", "重启路由器"])
        else:
            add("upstream-congestion", "上游网络丢包，可能是 ISP 或中转节点问题", 0.6)
    elif path.get("status") == "warn":
        add("path-warning", "路径存在中间跳丢包或延迟偏高", 0.5)

    # Network quality.
    nq = diag_map.get("network_quality", {})
    if nq.get("status") in ("warn", "fail"):
        rpm = nq.get("details", {}).get("responsiveness_rpm")
        if rpm is not None and rpm < 50:
            add("network-quality-poor", "网络响应性很差，可能出现卡顿和高延迟", 0.8,
                manual_steps=["暂停大流量上传/下载", "切换网络或节点", "检查路由器 QoS"])
        else:
            add("network-quality-degraded", "网络质量下降，基础延迟偏高或吞吐量低", 0.6)

    # Match symptom rules by diagnostic failures.
    # Warnings only trigger a symptom when it explicitly opts in via
    # ``trigger_on_warn: true``; most warn-only signals are handled above by
    # explicit rules to keep the root-cause list tight.
    for symptom in rules.get("symptoms", []):
        diag_names = symptom.get("diagnostics", [])
        matched_fail = any(
            diag_map.get(n, {}).get("status") == "fail" for n in diag_names
        )
        matched_warn = symptom.get("trigger_on_warn", False) and any(
            diag_map.get(n, {}).get("status") == "warn" for n in diag_names
        )
        if not (matched_fail or matched_warn):
            continue

        for cause in symptom.get("root_causes", []):
            confidence = cause.get("confidence", 0.5)
            if matched_fail:
                confidence = min(confidence * 1.0, 1.0)
            else:
                confidence = confidence * 0.7
            add(
                cause["id"],
                cause["description"],
                confidence,
                fixes=symptom.get("fixes", []),
                manual_steps=symptom.get("manual_steps", []),
            )

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results
