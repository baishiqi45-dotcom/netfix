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
        add("interface-down", "Mac 没有拿到有效的网络地址，或者网络接口没启用", 0.9,
            manual_steps=["检查网线或 Wi-Fi 连接", "在系统设置中重新连接网络"])
    elif diag_map.get("interface_state", {}).get("status") == "warn":
        add("interface-warning", "Mac 的网络接口状态有点异常", 0.6)

    if diag_map.get("dhcp_state", {}).get("status") == "fail":
        add("dhcp-misconfig", "Mac 没从路由器拿到正确的上网地址", 0.9,
            manual_steps=["重启路由器", "在系统设置中「忘记网络」后重新连接"])
    elif diag_map.get("dhcp_state", {}).get("status") == "warn":
        add("dhcp-missing-options", "Mac 从路由器拿到的地址信息不完整，缺少网关或 DNS", 0.7)

    if diag_map.get("ipv4_route", {}).get("status") == "fail":
        add("no-ipv4-route", "Mac 找不到通往互联网的路由", 0.9,
            manual_steps=["检查网线/Wi-Fi 是否已连接", "重启路由器", "运行 `sudo route flush` 后重新连网"])

    ipv6_route = diag_map.get("ipv6_route", {})
    if ipv6_route.get("status") == "warn":
        ipv6_route_details = ipv6_route.get("details", {})
        if ipv6_route_details.get("has_default_route"):
            add("ipv6-route-ambiguous", "IPv6 路由状态不太干净，网关信息不明确，访问 IPv6 目标时可能变慢", 0.45)
        else:
            add("ipv6-route-missing", "Mac 没有可用的 IPv6 路由，访问 IPv6 目标可能失败", 0.6)

    # Proxy core health.
    if diag_map.get("proxy_core_status", {}).get("status") == "fail":
        add("proxy-down", "代理软件没有运行，或者它的端口没开", 0.9,
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
        add("node-failed", "直连和走代理都无法访问 OpenAI，可能是代理线路暂时不可用，或代理软件没运行", 0.8,
            fixes=["check-proxy-core", "flush-dns-cache"],
            manual_steps=["在代理软件里切换到其他节点", "检查节点配置地址与端口"])

    # DNS patterns.
    dns_local = diag_map.get("dns_local", {}).get("status")
    dns_public = diag_map.get("dns_public", {}).get("status")
    if dns_public == "fail" and dns_local == "fail":
        add("dns-cache-stale", "本地和公共 DNS 都没法解析域名，可能是 DNS 缓存出问题，或网络层有故障", 0.85,
            fixes=["flush-dns-cache"])
    elif dns_local == "fail" and dns_public == "ok":
        add("dns-cache-stale", "Mac 的 DNS 解析坏了，但公共 DNS 正常；可能是 DNS 缓存出问题", 0.8,
            fixes=["flush-dns-cache"])

    # Gateway / Wi-Fi.
    if diag_map.get("gateway", {}).get("status") == "fail":
        add("gateway-unreachable", "连不上路由器，可能是 Wi-Fi 或网线有问题", 0.85,
            manual_steps=["靠近路由器或切换 Wi-Fi 频段", "重启路由器", "在系统设置中忘记网络后重连"])

    # System proxy.
    system_proxy = diag_map.get("system_proxy_state", {})
    system_proxy_status = system_proxy.get("status")
    if system_proxy_status == "fail":
        add("system-proxy-off", "系统代理没开，或者指向了错误的端口", 0.8,
            fixes=["reset-system-proxy"])
    elif system_proxy_status == "warn":
        system_proxy_details = system_proxy.get("details", {})
        if system_proxy_details.get("mixed_auto_and_manual"):
            add(
                "mixed-proxy-pac",
                "系统里同时开了手动代理和自动代理，容易冲突",
                0.7,
                fixes=["disable-auto-proxy"],
                manual_steps=[
                    "系统代理里只保留一种模式：手动代理，或者只用一个 PAC 文件，不要同时开启",
                    "然后重启你刚才打不开的 App 再试",
                ],
            )
        else:
            add("system-proxy-off", "系统代理没开，或者指向了错误的端口", 0.8,
                fixes=["reset-system-proxy"])

    # Proxy protocol / auth.
    if diag_map.get("proxy_auth_check", {}).get("details", {}).get("requires_auth"):
        add("proxy-auth-required", "代理服务器需要账号密码（HTTP 407）", 0.95,
            manual_steps=["在系统设置 > 网络 > 代理中补全用户名和密码", "或检查代理软件认证配置"])

    if diag_map.get("proxy_http_test", {}).get("status") == "fail":
        add("proxy-http-failed", "HTTP 代理测试没通过", 0.85,
            fixes=["check-proxy-core"],
            manual_steps=["检查代理软件是否启动", "确认系统 HTTP/HTTPS 代理端口正确"])

    if diag_map.get("proxy_socks_test", {}).get("status") == "fail":
        add("proxy-socks-failed", "SOCKS5 代理测试没通过", 0.85,
            fixes=["check-proxy-core"],
            manual_steps=["确认 SOCKS 端口已开启", "尝试使用 socks5h 以避免 DNS 泄漏"])

    if diag_map.get("pac_state", {}).get("status") == "warn":
        add("pac-unreachable", "自动代理文件（PAC）配置好了，但访问不到", 0.75,
            manual_steps=["检查 PAC 文件地址是否可达", "临时切换到手动代理以排除 PAC 问题"])

    # Node reachability (TCP layer).
    node_reach = diag_map.get("node_reachability", {}).get("status")
    node_details = diag_map.get("node_reachability", {}).get("details", {})
    if node_reach == "fail":
        active = (node_details.get("profiles") or [])
        dead = [p for p in active if p.get("reachable") is False]
        add("active-node-unreachable", "当前代理节点连不上（TCP 层）", 0.9,
            fixes=["check-proxy-core"],
            manual_steps=["在代理软件里切换到其他节点", "若全部节点都不可达，检查服务商或本地网络"])
    elif node_reach == "warn":
        add("some-nodes-unreachable", "部分代理节点连不上", 0.6,
            manual_steps=["在代理软件里切换到延迟更低/更稳定的节点"])

    # MTU mismatch.
    if diag_map.get("mtu_probe", {}).get("status") == "warn":
        add("mtu-too-high", "网络包大小（MTU）不匹配：小包通、大卡不通", 0.75,
            manual_steps=["运行 Netfix 自带的 mtu-tune 工具，探测并设置合适的 MTU"])

    # IPv6 leak / risk.
    ipv6_leak = diag_map.get("ipv6_leak", {})
    if ipv6_leak.get("status") in ("warn", "fail"):
        ipv6_leak_details = ipv6_leak.get("details", {})
        if ipv6_leak_details.get("leak_confirmed"):
            add("ipv6-exposed", "IPv6 可能没走代理", 0.85,
                fixes=["disable-ipv6"],
                manual_steps=["如果你不想关闭 IPv6，也可以在代理软件里开启 IPv6 转发或关闭 IPv6。"])
        elif ipv6_leak_details.get("fallback_risk"):
            add(
                "ipv6-fallback-risk",
                "代理开启时系统仍有 IPv6 路由，部分目标可能先尝试 IPv6 后变慢",
                0.45,
                manual_steps=[
                    "没有检测到公网 IPv6 泄漏，一般可以继续使用；如果某些 App 启动卡住，再在代理软件里开启 IPv6 转发或关闭 IPv6。",
                ],
            )

    # DNS leak.
    if diag_map.get("dns_leak", {}).get("status") == "warn":
        add("dns-leak", "DNS 可能没走代理（代理开着，但 DNS 仍走本地）", 0.8,
            fixes=["flush-dns-cache"],
            manual_steps=["将 DNS 改为公共 DNS，或在代理软件中启用 DNS 远程解析", "使用 socks5h 让 SOCKS 代理解析"])

    # IP reputation.
    ip_rep = diag_map.get("ip_reputation", {})
    if ip_rep.get("status") in ("warn", "fail"):
        details = ip_rep.get("details", {})
        if details.get("same_as_local"):
            add("proxy-not-effective", "代理好像没生效，公网看到的 IP 和本机一样", 0.85,
                fixes=["check-proxy-core", "reset-system-proxy"],
                manual_steps=["确认代理软件已启动", "检查系统代理是否指向正确端口"])
        elif details.get("ip_type") == "hosting/datacenter":
            add("ip-datacenter", "当前出口属于数据中心/服务器网络，部分服务可能要求额外验证", 0.75,
                manual_steps=["联系网络管理员或服务商更换合规可用的出口节点", "确认该出口是否符合目标服务的使用规则"])
        elif details.get("risk_score") is not None and details.get("risk_score") >= 33:
            add("ip-reputation-risk", "出口 IP 风险较高，目标服务可能限制访问", 0.75,
                manual_steps=["切换到其他节点", "如果你想知道原因，可以让服务商或管理员去查这个 IP 的信誉记录。"])

    # Path / transit.
    path = diag_map.get("path_trace", {})
    path_hops = path.get("details", {}).get("hops", [])
    if path.get("status") == "fail" and path_hops:
        first = path_hops[0]
        if first.get("loss_percent") is not None and first.get("loss_percent") > 5:
            add("local-wifi-issue", "到路由器的第一跳丢包严重，本地 Wi-Fi/网关有问题", 0.85,
                manual_steps=["靠近路由器", "切换到 5GHz 频段", "重启路由器"])
        else:
            add("upstream-congestion", "上游网络丢包，可能是运营商或中转节点问题", 0.6)
    elif path.get("status") == "warn":
        add("path-warning", "路径中间有丢包或延迟偏高", 0.5)

    # Network quality.
    nq = diag_map.get("network_quality", {})
    bandwidth_hog = diag_map.get("bandwidth_hog", {})
    bandwidth_reason = str(bandwidth_hog.get("details", {}).get("reason") or "")
    bandwidth_status = bandwidth_hog.get("status")
    if nq.get("status") in ("warn", "fail"):
        rpm = nq.get("details", {}).get("responsiveness_rpm")
        base_rtt = nq.get("details", {}).get("base_rtt_ms")
        if bandwidth_status in {"warn", "fail"} and bandwidth_reason in {"upload_saturated", "download_saturated"}:
            headline = "检测到上行流量较高" if bandwidth_reason == "upload_saturated" else "检测到下行流量较高"
            steps = [
                item.get("label", item.get("process", ""))
                for item in bandwidth_hog.get("details", {}).get("top_processes", [])
                if isinstance(item, dict) and item.get("is_hog")
            ]
            if not steps:
                steps = ["暂时看不出是哪个 App；可以打开活动监视器看上传/下载带宽"]
            add(
                "upload-congestion" if bandwidth_reason == "upload_saturated" else "download-congestion",
                headline,
                0.95,
                manual_steps=steps + [
                    "如需优先保证实时应用，可先暂停上面看到的 App 或下载器",
                    "暂停后仍有明显等待时，再检查代理节点或切换网络",
                ],
            )
        elif rpm is not None and rpm < 50:
            add("network-quality-poor", "网络响应较慢", 0.8,
                manual_steps=["暂停大流量上传/下载", "切换网络或节点", "检查路由器有没有限速或 QoS 设置"])
        elif base_rtt is not None and base_rtt > 200:
            add("network-latency-high", "基础延迟偏高，实时应用会变慢", 0.6,
                manual_steps=["切换网络或节点", "检查路由器是否拥塞"])
        else:
            add("network-quality-degraded", "网络质量下降，延迟偏高或网速低", 0.6)

    # Standalone bandwidth hog without a quality drop (always report to give the user a hint).
    if bandwidth_status in {"warn", "fail"} and nq.get("status") not in {"warn", "fail"}:
        add(
            "bandwidth-hog-detected",
            "网络本身正常，但后台有大流量上传或下载" if bandwidth_reason == "upload_saturated" else "网络本身正常，但后台在大量下载",
            0.45,
            manual_steps=[
                "暂停上一步列出的 App 或下载器，实时应用会更顺畅",
            ],
        )

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
