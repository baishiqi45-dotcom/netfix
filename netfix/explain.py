"""Plain-language explanation engine for netfix reports.

Turns a diagnostic report into a user-facing card with:
- headline (one-sentence conclusion)
- explanation (2-3 sentences in plain Chinese)
- actions (safe, executable next steps)
- manual_steps (things the user must do by hand)
- technical (raw report snapshot for advanced users)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from netfix import user_facing_errors


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


# Mapping from root-cause id -> human-readable templates.
# Each entry can provide:
#   headline: one-line conclusion
#   explanation: 2-3 sentences
#   primary_action: id of the best fix to offer
#   actions: list of additional fix ids to suggest
#   manual_steps: list of manual step dicts/strings
_CAUSE_EXPLANATIONS: Dict[str, Dict[str, Any]] = {
    "proxy-down": {
        "headline": "代理客户端没有启动",
        "explanation": "你的代理软件没开，或者它的端口没开。流量没法通过代理出去，所以目标服务连不上。",
        "primary_action": "check-proxy-core",
        "actions": [],
        "manual_steps": ["打开你的代理软件（如 v2rayN、Clash、Surge）", "确认软件启动后，重新运行诊断"],
    },
    "system-proxy-off": {
        "headline": "系统代理没有开启",
        "explanation": "代理软件已经在运行，但 macOS 还没把它设为系统代理。浏览器和大多数 App 会忽略代理，直接连接网络。",
        "primary_action": "reset-system-proxy",
        "actions": [],
        "manual_steps": ["或者在代理软件里点击「设置系统代理」"],
    },
    "proxy-auth-required": {
        "headline": "代理服务器需要账号密码",
        "explanation": "你的网络代理返回了需要账号密码的提示（HTTP 407）。macOS 或代理软件里缺少正确的用户名/密码。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["在「系统设置 → 网络 → 代理」中补全用户名和密码", "或检查代理软件的认证配置"],
    },
    "proxy-http-failed": {
        "headline": "HTTP 代理测试请求失败",
        "explanation": "系统代理已配置，但通过它访问测试站点失败。可能是代理端口不对、协议不匹配或代理软件异常。",
        "primary_action": "check-proxy-core",
        "actions": ["reset-system-proxy"],
        "manual_steps": ["检查代理软件是否启动", "确认 HTTP/HTTPS 代理端口和软件里设置的一致"],
    },
    "proxy-socks-failed": {
        "headline": "SOCKS5 代理测试请求失败",
        "explanation": "SOCKS 代理端口没有正常响应。可能是代理软件没开，或者端口设置和系统代理不一致。",
        "primary_action": "check-proxy-core",
        "actions": [],
        "manual_steps": ["确认 SOCKS 端口已开启", "尝试使用 socks5h 让 SOCKS 代理解析域名，避免 DNS 泄漏"],
    },
    "dns-cache-stale": {
        "headline": "当前 DNS 服务器坏了",
        "explanation": "本地 DNS 无法解析域名，但公共 DNS 正常。这通常是路由器 DNS 缓存出了问题，或 Mac 的 DNS 设置不对。",
        "primary_action": "flush-dns-cache",
        "actions": ["set-public-dns"],
        "manual_steps": ["如果刷新缓存无效，尝试将 DNS 改为 1.1.1.1 或 8.8.8.8"],
    },
    "dns-local-failure": {
        "headline": "本地 DNS 解析失败",
        "explanation": "Mac 无法解析目标域名，可能是 DNS 缓存出了问题，或路由器 DNS 故障。",
        "primary_action": "flush-dns-cache",
        "actions": ["set-public-dns"],
        "manual_steps": [],
    },
    "dns-leak": {
        "headline": "DNS 在泄漏你的真实位置",
        "explanation": "代理已经开启，但 DNS 仍然走本地或运营商网络去解析。目标网站能通过 DNS 记录看到你的真实位置。",
        "primary_action": "set-public-dns",
        "actions": ["flush-dns-cache"],
        "manual_steps": ["在代理软件里开启 DNS 远程解析", "使用 socks5h 让 SOCKS 代理解析域名"],
    },
    "ipv6-exposed": {
        "headline": "IPv6 没有走代理，可能暴露真实网络",
        "explanation": "代理通常只接管 IPv4 流量，但你的网络有公网 IPv6。访问支持 IPv6 的目标时，流量可能绕过代理。",
        "primary_action": "disable-ipv6",
        "actions": [],
        "manual_steps": ["如果你不想关闭系统 IPv6，可以在代理软件里开启 IPv6 转发或关闭 IPv6。"],
    },
    "ipv6-fallback-risk": {
        "headline": "没有检测到 IPv6 泄漏",
        "explanation": "代理开启时系统仍有 IPv6 路由，但没有检测到公网 IPv6。一般可以继续使用；如果某些应用启动时反复重连，再考虑在代理软件里开启 IPv6 转发或关闭 IPv6。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["如果某个 App 仍然启动卡住，再处理 IPv6；没有公网 IPv6 时不要把它当成已经泄漏。"],
    },
    "dhcp-misconfig": {
        "headline": "没拿到正确的上网地址",
        "explanation": "Mac 没从路由器拿到正确的上网地址，可能是缺少网关/DNS，或者拿到了自分配地址。电脑无法正确连到路由器。",
        "primary_action": "renew-dhcp",
        "actions": [],
        "manual_steps": ["重启路由器", "在系统设置中「忘记网络」后重新连接"],
    },
    "gateway-unreachable": {
        "headline": "默认网关连不上",
        "explanation": "Mac 无法 ping 通路由器。可能是 Wi-Fi 信号太弱、网线松动，或者路由器死机。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["靠近路由器或切换到 5GHz 频段", "重启路由器", "检查网线连接"],
    },
    "local-wifi-issue": {
        "headline": "本地 Wi-Fi/网关有问题",
        "explanation": "网络路径的第一跳丢包严重或延迟很高。问题通常出在你的 Wi-Fi 信号、路由器负载或附近干扰。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["靠近路由器或切换到 5GHz 频段", "重启路由器", "检查是否有设备在大量下载"],
    },
    "ip-datacenter": {
        "headline": "当前出口属于数据中心网络",
        "explanation": "当前代理节点的 IP 属于数据中心/服务器网络。部分服务可能会要求额外验证，或对这类网络限制更严格。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["联系网络管理员或服务商更换合规可用的出口节点", "确认该出口是否符合目标服务的使用规则"],
    },
    "ip-reputation-risk": {
        "headline": "出口 IP 风险评分较高",
        "explanation": "这个 IP 之前可能被滥用，被一些安全数据库标记过。目标网站可能因此拒绝连接。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["切换到其他代理节点", "如果你想知道原因，可以让服务商或管理员去查这个 IP 的信誉记录。"],
    },
    "proxy-not-effective": {
        "headline": "代理似乎没有生效",
        "explanation": "公网看到的 IP 和你本机 IP 相同，说明流量没有走代理。可能是系统代理没开，或代理软件配置错误。",
        "primary_action": "reset-system-proxy",
        "actions": ["check-proxy-core"],
        "manual_steps": ["确认代理软件已启动", "检查系统代理是否指向正确端口"],
    },
    "node-failed": {
        "headline": "当前代理节点连不上目标服务",
        "explanation": "直连和走代理都无法访问目标服务，可能是当前节点挂了，或代理软件没运行。",
        "primary_action": "check-proxy-core",
        "actions": ["flush-dns-cache"],
        "manual_steps": ["在代理软件里切换到其他节点", "检查节点配置地址与端口"],
    },
    "active-node-unreachable": {
        "headline": "当前代理节点 TCP 层不可达",
        "explanation": "代理软件里配置的节点地址或端口连不上。可能是节点已下线，或你的网络到节点之间有阻断。",
        "primary_action": "check-proxy-core",
        "actions": [],
        "manual_steps": ["切换到其他节点", "检查服务商状态页"],
    },
    "network-quality-poor": {
        "headline": "网络响应性很差，可能会很卡",
        "explanation": "测得的基础延迟高或网络响应很慢。视频会议、ChatGPT 流式输出等实时应用会感觉明显卡顿。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["暂停大流量上传/下载", "切换到更稳定的网络或节点", "检查路由器 QoS"],
    },
    "network-quality-degraded": {
        "headline": "网络质量下降",
        "explanation": "延迟偏高或网速不够。可能是网络拥堵、代理节点负载高，或 Wi-Fi 信号不佳。",
        "primary_action": None,
        "actions": [],
        "manual_steps": ["切换到其他节点", "靠近路由器", "减少同时下载的设备"],
    },
    "direct-blocked": {
        "headline": "不走代理时连不上，代理可用",
        "explanation": "不经过代理时目标服务无法访问，但通过本地代理可以。这是正常情况，继续保持代理开启即可。",
        "primary_action": None,
        "actions": [],
        "manual_steps": [],
    },
    "mixed-proxy-pac": {
        "headline": "系统里同时开了手动代理和自动代理",
        "explanation": "macOS 同时启用了手动代理和自动代理。不同应用启动时可能先按自动规则走一遍，再回到本地代理，容易出现反复重连。",
        "primary_action": "disable-auto-proxy",
        "actions": [],
        "manual_steps": ["系统代理里只保留一种模式：手动代理，或者只用一个 PAC 文件，不要同时开启", "然后重启你刚才打不开的 App 再试"],
    },
    "ipv6-route-missing": {
        "headline": "Mac 没有可用的 IPv6 路由",
        "explanation": "Mac 没有可用的 IPv6 路由。如果目标优先使用 IPv6，连接会失败或变慢。",
        "primary_action": "disable-ipv6",
        "actions": [],
        "manual_steps": ["如果你需要保留 IPv6，就在路由器或代理软件里修复 IPv6 路由。"],
    },
    "ipv6-route-ambiguous": {
        "headline": "IPv6 路由状态不太干净",
        "explanation": "系统检测到了 IPv6 路由，但网关信息不明确。这通常不是硬断网，但会让支持 IPv6 的目标在启动连接时变慢。",
        "primary_action": "disable-ipv6",
        "actions": [],
        "manual_steps": ["如果你需要保留 IPv6，先处理自动代理或代理模式混用，再检查路由器 IPv6 设置。"],
    },
}


# Human-readable labels for fix ids.
_FIX_LABELS: Dict[str, str] = {
    "check-proxy-core": "检查代理软件是否运行",
    "flush-dns-cache": "刷新 DNS 缓存",
    "reset-system-proxy": "重新设置系统代理",
    "disable-auto-proxy": "关闭自动代理设置",
    "renew-dhcp": "续租 DHCP",
    "disable-ipv6": "暂时关闭 IPv6",
    "set-public-dns": "改用公共 DNS",
}


def _fix_action(fix_id: str, fix_def: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build an action dict from a fix definition."""
    tier = fix_def.get("tier", 3)
    return {
        "id": fix_id,
        "label": _FIX_LABELS.get(fix_id, fix_def.get("description", fix_id)),
        "tier": tier,
        "needs_confirm": tier >= 2,
        "verify_diagnostic": fix_def.get("verify_diagnostic"),
    }


def _severity(report: Dict[str, Any]) -> str:
    diagnostics = report.get("diagnostics", [])
    statuses = [d.get("status") for d in diagnostics]
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"


def _healthy_tip(report: Dict[str, Any]) -> str:
    """Return a short tip for healthy reports (e.g. residential IP)."""
    for d in report.get("diagnostics", []):
        if d.get("name") != "ip_reputation":
            continue
        details = d.get("details", {})
        ip_type = details.get("ip_type") or "unknown"
        ip = details.get("ip")
        isp = details.get("isp") or details.get("asn") or "未知"
        if ip_type in ("residential", "isp"):
            return f"当前出口看起来是宽带/运营商网络（{ip or isp}），这类网络通常更不容易触发额外验证。"
        if ip_type in ("hosting/datacenter", "proxy/vpn"):
            return f"当前出口是数据中心/代理 IP（{ip or isp}），部分 AI 服务可能会要求额外验证。"
        if ip:
            return f"当前出口 IP：{ip}（{isp}）。"
    return ""


def explain_report(report: Dict[str, Any], rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a plain-language explanation card for *report*."""
    if rules is None:
        from netfix.constants import RULES_DIR
        import json
        path = RULES_DIR / "symptoms.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                rules = json.load(f)
        else:
            rules = {"fixes": {}}

    fixes_map = rules.get("fixes", {})
    root_causes = report.get("root_causes", [])
    report_fixes = report.get("fixes", [])

    # Healthy report.
    if not root_causes:
        tip = _healthy_tip(report)
        explanation_text = "当前所有分层诊断都通过了，没有发现明显的网络或代理问题。"
        if tip:
            explanation_text += "\n" + tip
        return {
            "headline": "网络看起来正常",
            "severity": _severity(report),
            "explanation": explanation_text,
            "primary_action": None,
            "actions": [],
            "manual_steps": [],
            "technical": {k: v for k, v in report.items() if k != "explanation"},
        }

    # Pick the highest-confidence root cause.
    top = root_causes[0]
    cause_id = top.get("id", "unknown")
    template = _CAUSE_EXPLANATIONS.get(cause_id, {})

    headline = template.get("headline") or top.get("description") or "检测到网络问题"
    explanation = template.get("explanation") or top.get("description") or ""
    # Scrub any leaked internal jargon out of the headline / explanation so the
    # ordinary user never sees phrases like "ipv6_leak" or "proxy active".
    headline = user_facing_errors.scrub_internal_phrases(headline)
    explanation = user_facing_errors.scrub_internal_phrases(explanation)

    # If the report was produced by `fix --all` but no Tier 1 fix could be run,
    # tell the user honestly that the remaining issues need manual handling.
    no_auto_fixes = report.get("meta", {}).get("no_auto_fixes") is True
    if no_auto_fixes:
        headline = "这个问题需要手动处理"
        explanation = "这个问题需要手动处理，按下面步骤来；也可以点击「问 AI」获取更具体的建议。"

    # Collect action ids from template + report fixes, preserving order and deduping.
    action_ids: List[str] = []
    seen_ids: set = set()

    def add_action_id(fid: str) -> None:
        if fid and fid not in seen_ids and fid in fixes_map:
            action_ids.append(fid)
            seen_ids.add(fid)

    primary_id = template.get("primary_action")
    for fid in template.get("actions", []):
        add_action_id(fid)
    # Report-level fixes from reasoner.
    for fix in report_fixes:
        fid = fix.get("id") if isinstance(fix, dict) else fix
        add_action_id(fid)
    # Primary action goes first.
    if primary_id and primary_id in fixes_map:
        if primary_id in seen_ids:
            action_ids.remove(primary_id)
        action_ids.insert(0, primary_id)
        seen_ids.add(primary_id)

    actions = [_fix_action(fid, fixes_map[fid]) for fid in action_ids if fid in fixes_map]
    primary_action = actions[0] if actions else None

    # Manual steps: from template + root cause manual_steps + report manual_steps.
    manual_steps: List[Any] = []
    seen_manual: set = set()

    def add_manual(step: Any) -> None:
        key = step.get("description") if isinstance(step, dict) else str(step)
        if key and key not in seen_manual:
            manual_steps.append(step)
            seen_manual.add(key)

    for step in template.get("manual_steps", []):
        add_manual(step)
    for step in top.get("manual_steps", []):
        add_manual(step)
    for step in report.get("manual_steps", []):
        add_manual(step)

    # Normalize all manual steps to dicts so Swift/TypeScript consumers can
    # decode them consistently.
    manual_steps = [_normalize_manual_step(s) for s in manual_steps]

    # Avoid a circular reference when the explanation is embedded back into
    # the same report dict.
    technical = {k: v for k, v in report.items() if k != "explanation"}

    return {
        "headline": headline,
        "severity": _severity(report),
        "explanation": explanation,
        "primary_action": primary_action,
        "actions": actions,
        "manual_steps": manual_steps,
        "technical": technical,
    }
