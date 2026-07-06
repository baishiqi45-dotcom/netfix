"""Shared user-facing error mapping for netfix.

Both Python callers (api.py, fix_engine.py, llm_explain.py) and Swift UI code
need to translate the same internal reason codes and HTTP status codes into
the same plain-language messages. The table here is the single source of
truth. Swift ships a mirror that references the same ``code`` values; the
two surfaces stay in sync by sharing the canonical code list.

Each entry returns:

* ``headline`` — one short sentence the user reads first
* ``next_step`` — what the user should do next (no jargon)
* ``technical`` — optional detail only used in "查看日志"

The same payload is returned for both the Python HTTP API
(``/user-facing/errors``) and the Swift mirror, so the App and the doc site
never disagree about what an error means.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# Canonical reason codes used across netfix API and UI.
USER_FACING_CODES: Dict[str, Dict[str, str]] = {
    # ---- proxy authentication / credentials ----
    "proxy_auth_failed": {
        "headline": "代理账号或密码不对",
        "next_step": "回服务商后台重新复制完整的地址、端口、用户名和密码，再粘贴进来。",
        "technical": "代理服务器返回 407/身份验证失败；请确认 username/password 或重新生成密钥。",
    },
    "proxy_auth_required": {
        "headline": "代理需要账号密码，但你没填",
        "next_step": "回服务商后台找到用户名和密码，粘贴完整一行后重试。",
        "technical": "代理客户端或系统代理里没有用户名/密码，HTTP 407。",
    },
    # ---- network / reachability ----
    "proxy_unreachable": {
        "headline": "连不上代理服务器",
        "next_step": "确认地址、端口没抄错；也试试把服务商给的备用节点换一行粘进来。",
        "technical": "TCP 或 HTTP 连接失败：connection refused / timeout / no route to host。",
    },
    "dns_failed": {
        "headline": "解析不到代理服务器的名字",
        "next_step": "可能是 DNS 暂时出问题；点重试，或把代理地址改成 IP 直连。",
        "technical": "name resolution failure; check DNS settings or replace hostname with IP.",
    },
    "timeout": {
        "headline": "网络太慢或代理没响应",
        "next_step": "等几秒再点重试；如果是 SOCKS5/HTTP 一直超时，看下是不是代理线路暂时不可用。",
        "technical": "向上游或代理建立的请求在时间内没收到响应。",
    },
    # ---- system proxy / routing ----
    "system_proxy_not_set": {
        "headline": "系统代理没有切过去",
        "next_step": "到「部署代理」里点「开始使用这台 Mac 上网」，Netfix 会备份后帮你切。",
        "technical": "macOS Network Service 的 Web/Secure Web/SOCKS 代理未启用。",
    },
    "system_proxy_recovery_required": {
        "headline": "网络设置可恢复",
        "next_step": "到「设置 → 代理 → 恢复原来的网络设置」，点「恢复」。",
        "technical": "Detect stale proxy bridge; last apply journal exists but bridge is not alive.",
    },
    "auto_proxy_pac_conflict": {
        "headline": "手动代理和自动代理同时开启",
        "next_step": "打开 Netfix 设置，在代理区域关闭自动代理（PAC / WPAD），只留 Netfix 帮你设的代理。",
        "technical": "Mixed PAC + manual proxy detected; recommend disable-auto-proxy.",
    },
    # ---- IPv6 ----
    "ipv6_leak_confirmed": {
        "headline": "IPv6 可能没有走代理",
        "next_step": "打开 Netfix 设置，在代理区域关闭 IPv6；之后能完整走代理。",
        "technical": "Confirmed IPv6 leakage: public IPv6 reachable while proxy active.",
    },
    "ipv6_fallback_risk": {
        "headline": "没有检测到公网 IPv6",
        "next_step": "一般可以继续用；如果某个 App 启动一直卡，再去处理 IPv6，不用反复点修复按钮。",
        "technical": "ipv6_leak warn with no public IPv6 and fallback_risk=true; not actionable.",
    },
    # ---- DNS leak / quality ----
    "dns_leak_detected": {
        "headline": "DNS 可能没有走代理",
        "next_step": "在代理客户端里开启 DNS 劫持/远程解析，或用 socks5h:// 让 SOCKS 代理解析域名。",
        "technical": "DNS queries bypass the proxy; recommend set-public-dns or socks5h.",
    },
    # ---- proxy profile parsing ----
    "unsupported_input_format": {
        "headline": "目前不支持这种代理链接",
        "next_step": "请到服务商后台复制 HTTP 或 SOCKS5 的地址、端口、用户名和密码。",
        "technical": "ss://、vmess:// 或 Clash 订阅链接暂不支持；只解析 HTTP/SOCKS5。",
    },
    "missing_required_field": {
        "headline": "代理参数没写全",
        "next_step": "补齐地址、端口、用户名、密码后再粘贴。",
        "technical": "host/port/username/password 不完整，无法组成可部署的代理。",
    },
    # ---- general engine ----
    "fix_cancelled": {
        "headline": "你刚才取消了",
        "next_step": "系统设置没改动；要继续时重新点对应按钮即可。",
        "technical": "用户在 Tier 2 确认弹窗点了取消；fix.status = cancelled。",
    },
    "fix_verification_failed": {
        "headline": "处理了一下，但还没完全好",
        "next_step": "再点一次诊断；如果仍然提示同一项，按下面手动步骤继续处理。",
        "technical": "fix.executed == ok 但 verify_diagnostic.status != ok。",
    },
    "fix_command_failed": {
        "headline": "修复没有跑完",
        "next_step": "重试一次；如果仍然失败，再点「查看日志」把最近一次失败记录拿来排查。",
        "technical": "fix.executed[*].ok == false；具体见 executed 数组里的 stderr。",
    },
    # ---- backend / app ----
    "backend_unreachable": {
        "headline": "Netfix 本地服务还没准备好",
        "next_step": "等几秒重试；如果一直是这个，退出 Netfix 再打开一次。",
        "technical": "本地 HTTP API 没有响应或 token 校验失败；常见于本地服务未启动。",
    },
    "decode_failed": {
        "headline": "App 和本地服务没对上话",
        "next_step": "点「查看日志」记录错误；退出 Netfix 重开一次；仍然出错就到 GitHub 提 issue。",
        "technical": "JSON 数据结构与客户端解码模型不一致；常见于版本不匹配。",
    },
    "keychain_failed": {
        "headline": "本机密码库写入失败",
        "next_step": "打开「系统设置 → 隐私与安全性 → 密码」授权 Netfix 访问；然后重新粘贴。",
        "technical": "Keychain SecItemAdd 返回 errSecAuthFailed / missing entitlement。",
    },
    "permission_denied": {
        "headline": "macOS 没给 Netfix 权限",
        "next_step": "在「设置 → 权限」里点授权按钮，系统会弹窗让你同意。",
        "technical": "TCC / Accessibility / Full Disk Access / Local Network 权限被拒。",
    },
    # ---- AI / cloud ----
    "llm_disabled": {
        "headline": "AI 还没启用，不影响诊断",
        "next_step": "需要更易懂的解释时，到「设置 → AI」启用并粘贴 Key。",
        "technical": "settings.llm.enabled == false；本地规则解释照常可用。",
    },
    "missing_api_key": {
        "headline": "还没填 AI 密钥",
        "next_step": "到「设置 → AI」选供应商并粘贴 API Key。不填也能照常用诊断和代理部署。",
        "technical": "keychain has no API key for the active provider chain。",
    },
    # ---- bandwidth / upload congestion ----
    "bandwidth_hog_detected": {
        "headline": "后台 App 占用较高",
        "next_step": "先在「活动监视器」里暂停看到的上传/下载 App，再重新打开实时应用。",
        "technical": "diagnostic bandwidth_hog detected active upload/download at the process level.",
    },
    "upload_congestion": {
        "headline": "检测到上行流量较高",
        "next_step": "如需优先保证实时应用，可先暂停百度网盘、OneDrive、iCloud、网盘或下载器的上传/同步。",
        "technical": "diagnostic bandwidth_hog reason=upload_saturated; top_processes carries process names and direction.",
    },
    "download_congestion": {
        "headline": "检测到下行流量较高",
        "next_step": "如需优先保证实时应用，可先暂停下载器或系统更新后再试。",
        "technical": "diagnostic bandwidth_hog reason=download_saturated.",
    },
}


_HTTP_STATUS_FALLBACK: Dict[int, Tuple[str, str, str]] = {
    400: ("请求被本地服务拒绝", "点重试或检查输入；如果仍然失败就查看日志。", "HTTP 400 通常表示请求参数不被本地服务接受。"),
    401: ("本地服务要求登录或 token", "重启 Netfix；问题持续就看日志。", "HTTP 401，多为本地 API token 失效。"),
    403: ("操作被拒绝（权限或来源）", "按上面给的授权说明再试一次。", "HTTP 403 cross-origin / 权限不足。"),
    404: ("本地服务没找到这条", "可能接口改版；查看日志或更新 Netfix。", "HTTP 404。"),
    409: ("需要先确认", "按提示在 App 里点确认。", "HTTP 409 confirmation required。"),
    502: ("本地服务链路失败", "稍后重试；持续出错就查看日志。", "HTTP 502 upstream failure。"),
}


# Vendor / 3rd-party English fragments the user shouldn't see in plain UI.
# Kept here so the same fragments are scrubbed on both Python and Swift sides.
_INTERNAL_PHRASES: List[str] = [
    "system proxy",
    "system_proxy",
    "proxy active",
    "proxy_apply",
    "ipv6_leak",
    "ipv6 default route",
    "default route",
    "tier 1",
    "tier 2",
    "tier 3",
    "tier1",
    "tier2",
    "tier3",
    "manual steps",
    "automatic proxy discovery",
    "WPAD",
    "PAC URL",
    "mixed_auto_and_manual",
    "verification_failed",
    "fix_command_failed",
    "fix_cancelled",
    "fix_verification_failed",
    "proxy_core_status",
    "codex_api_direct",
    "codex_api_via_proxy",
    "node_reachability",
    "exit IP",
    "exit_ip",
    "default route present",
]


def lookup_code(code: Optional[str]) -> Optional[Dict[str, str]]:
    """Return a copy of the message for *code* if known, else ``None``."""
    if not code:
        return None
    entry = USER_FACING_CODES.get(str(code))
    if not entry:
        return None
    return {"code": str(code), **entry}


def lookup_http_status(status: int) -> Dict[str, str]:
    """Fallback message for raw HTTP status codes that don't have a reason code."""
    entry = _HTTP_STATUS_FALLBACK.get(int(status))
    if not entry:
        return {
            "code": f"http_{status}",
            "headline": f"请求返回 {status}",
            "next_step": "重试一次；若仍失败查看日志或重新打开 Netfix。",
            "technical": f"本地服务返回 HTTP {status}。",
        }
    return {"code": f"http_{status}", "headline": entry[0], "next_step": entry[1], "technical": entry[2]}


def all_codes() -> List[Dict[str, str]]:
    """Return every entry — used by tests and Swift bootstrap."""
    return [{"code": code, **entry} for code, entry in USER_FACING_CODES.items()]


# ---- Mapping from raw Python exception / diagnose strings ----

_AUTH_RE = re.compile(
    r"407|proxy\s*auth(?:entication)?|auth_failed|authentication\s*required|user/pass",
    re.IGNORECASE,
)
_UNREACHABLE_RE = re.compile(
    r"connection\s+refused|no\s+route|host\s+is\s+down|connect\s+timeout",
    re.IGNORECASE,
)
_DNS_RE = re.compile(
    r"name\s+or\s+service\s+not\s+known|temporary\s+failure\s+in\s+name\s+resolution|"
    r"name_not_resolved|nodename\s+nor\s+servname|getaddrinfo\s+failed",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(r"timed?\s*out|timeout", re.IGNORECASE)
_V6_CONFIRMED_RE = re.compile(r"\bpublic\s+ipv6\b|leak_confirmed", re.IGNORECASE)
_V6_FALLBACK_RE = re.compile(r"no\s+public\s+ipv6|fallback_risk", re.IGNORECASE)
_UNSUPPORTED_FORMAT_RE = re.compile(r"ss://|vmess://|subscription|clash\s*yaml", re.IGNORECASE)


def classify_text(text: str) -> Dict[str, str]:
    """Best-effort mapping from a free-form technical string to a friendly card."""
    if not text:
        return {
            "code": "unknown",
            "headline": "出现了一个未识别的问题",
            "next_step": "可以重试；如果问题持续，点「查看日志」把记录给开发者。",
            "technical": "",
        }
    if _AUTH_RE.search(text):
        return lookup_code("proxy_auth_failed") or _unknown()
    if _UNSUPPORTED_FORMAT_RE.search(text):
        return lookup_code("unsupported_input_format") or _unknown()
    if _DNS_RE.search(text):
        return lookup_code("dns_failed") or _unknown()
    # Fallback / not-yet-confirmed leak must be checked BEFORE confirmed,
    # because "no public ipv6" contains the substring "public ipv6".
    if _V6_FALLBACK_RE.search(text):
        return lookup_code("ipv6_fallback_risk") or _unknown()
    if _V6_CONFIRMED_RE.search(text):
        return lookup_code("ipv6_leak_confirmed") or _unknown()
    if _UNREACHABLE_RE.search(text):
        return lookup_code("proxy_unreachable") or _unknown()
    if _TIMEOUT_RE.search(text):
        return lookup_code("timeout") or _unknown()
    return _unknown(text)


def _unknown(text: str = "") -> Dict[str, str]:
    return {
        "code": "unknown",
        "headline": "出现了一个尚未分类的问题",
        "next_step": "可以重试或点「查看日志」给开发者。",
        "technical": text[:200] if text else "",
    }


def scrub_internal_phrases(text: str) -> str:
    """Replace internal jargon with friendlier tokens in a free-form string."""
    if not text:
        return text
    out = text
    replacements = {
        "ipv6_leak": "IPv6 旁路",
        "system proxy": "系统代理",
        "proxy active": "代理正在生效",
        "system_proxy": "系统代理",
        "default route": "默认路由",
        "tier 1": "低风险",
        "tier 2": "需要确认",
        "tier 3": "只能手动",
        "verification_failed": "复查还没过",
        "exit IP": "出口 IP",
        "backend": "本地服务",
    }
    lower = out.lower()
    for src, dst in replacements.items():
        if src.lower() in lower:
            idx = lower.find(src.lower())
            while idx != -1:
                out = out[:idx] + dst + out[idx + len(src):]
                lower = out.lower()
                idx = lower.find(src.lower())
    return out


def render_error(*, code: Optional[str] = None, message: Optional[str] = None, http_status: Optional[int] = None) -> Dict[str, Any]:
    """Build a card for an error: prefer reason code, fall back to message, then HTTP."""
    if code:
        entry = lookup_code(code)
        if entry:
            return {**entry, "source": "code"}
    if message:
        entry = classify_text(str(message))
        return {**entry, "source": "message"}
    if http_status is not None:
        entry = lookup_http_status(int(http_status))
        return {**entry, "source": "http_status"}
    return _unknown()
