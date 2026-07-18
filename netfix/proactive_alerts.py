"""Netfix 主动救火事件检测：4 类网络异常的本地检测 + 冷却。

事件类型
--------
1. exit_ip_type_change      出口 IP 从住宅/运营商变成数据中心
2. dns_failure_rate_spike    DNS 解析失败率突然上升
3. node_consecutive_timeout 同一代理节点连续 3 次超时
4. rtt_spike                 网络 RTT 陡增

约束
----
- 不引入新依赖
- 所有 fingerprint 与 agent_session.py 用同样 hash 函数（compute_fingerprint）
- 不写网络，只读（监听层已经提供数据）
- 写 ~/.netfix/proactive_alerts.json 用于冷却追踪
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from netfix.constants import JOURNAL_DIR
from netfix.agent_session import compute_fingerprint


ALERT_FILE = JOURNAL_DIR / "proactive_alerts.json"


def _now() -> float:
    return time.time()


def _cooldown_default(alert_type: str) -> int:
    return {
        "exit_ip_type_change": 6 * 3600,
        "dns_failure_rate_spike": 30 * 60,
        "node_consecutive_timeout": 30 * 60,
        "rtt_spike": 15 * 60,
    }.get(alert_type, 60 * 60)


def _load() -> Dict[str, Any]:
    if not ALERT_FILE.exists():
        return {"schema_version": "proactive_alerts.v1", "alerts": []}
    try:
        return json.loads(ALERT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "proactive_alerts.v1", "alerts": []}


def _save(state: Dict[str, Any]) -> None:
    ALERT_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = ALERT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ALERT_FILE)


def list_alerts(active_only: bool = True) -> List[Dict[str, Any]]:
    """Return alerts. If active_only=True, drop those whose cooldown has elapsed."""
    state = _load()
    now = _now()
    out = []
    for raw in state.get("alerts", []):
        if active_only and raw.get("expires_at", 0) < now:
            continue
        if raw.get("dismissed"):
            continue
        out.append(dict(raw))
    return out


def dismiss_alert(alert_id: str) -> bool:
    """Mark an alert as dismissed by id; returns True if any was changed."""
    state = _load()
    changed = False
    for raw in state.get("alerts", []):
        if raw.get("alert_id") == alert_id:
            raw["dismissed"] = True
            raw["dismissed_at"] = _now()
            changed = True
    if changed:
        _save(state)
    return changed


def clear_alerts() -> int:
    """Wipe all alerts. Returns number removed."""
    state = _load()
    n = len(state.get("alerts", []))
    _save({"schema_version": "proactive_alerts.v1", "alerts": []})
    return n


def _make_alert_id(alert_type: str, fingerprint: str) -> str:
    seed = f"{alert_type}::{fingerprint}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _emit_alert(alert_type: str, payload: Dict[str, Any], fingerprint: str) -> Optional[Dict[str, Any]]:
    """Append alert to journal; return the new alert dict if it wasn't already on cooldown."""
    now = _now()
    aid = _make_alert_id(alert_type, fingerprint)
    state = _load()

    for raw in state.get("alerts", []):
        if raw.get("alert_id") == aid:
            if raw.get("dismissed"):
                return None
            cooldown_until = raw.get("cooldown_until", 0)
            if cooldown_until > now:
                return None

    alert = {
        "alert_id": aid,
        "alert_type": alert_type,
        "fingerprint": fingerprint,
        "triggered_at": now,
        "expires_at": now + _cooldown_default(alert_type),
        "cooldown_until": now + _cooldown_default(alert_type),
        "dismissed": False,
        "payload": dict(payload),
    }
    state.setdefault("alerts", []).append(alert)
    state["alerts"] = state["alerts"][-200:]
    _save(state)
    return alert


# ---------------------------------------------------------------------------
# 检测器
# ---------------------------------------------------------------------------

@dataclass
class BaselineSample:
    exit_ip_type: Optional[str] = None
    dns_resolve_total: int = 0
    dns_resolve_failed: int = 0
    node_consecutive_timeouts: int = 0
    last_rtt_ms: Optional[float] = None


def detect_exit_ip_type_change(
    previous_type: Optional[str],
    current_type: Optional[str],
    previous_risk: Optional[float],
    current_risk: Optional[float],
    fingerprint: str = "",
    *,
    threshold_risk: float = 70.0,
) -> Optional[Dict[str, Any]]:
    """Detect exit IP moving from residential to datacenter."""
    if not previous_type or not current_type or previous_type == current_type:
        return None
    residential = {"residential", "isp", "mobile", "unknown"}
    datacenter = {"datacenter", "hosting", "proxy", "vpn"}
    if previous_type in residential and current_type in datacenter:
        payload = {
            "from_type": previous_type,
            "to_type": current_type,
            "previous_risk": previous_risk,
            "current_risk": current_risk,
            "severity": "fail" if (current_risk or 0) >= threshold_risk else "warn",
        }
        return _emit_alert("exit_ip_type_change", payload, fingerprint or compute_fingerprint({"ip": str(previous_type) + "->" + str(current_type)}))
    return None


def detect_dns_failure_rate_spike(
    recent_total: int,
    recent_failed: int,
    baseline_failure_rate: Optional[float] = None,
    fingerprint: str = "",
    *,
    min_total: int = 5,
    min_failed: int = 3,
    rate_threshold: float = 0.4,
    delta_vs_baseline: float = 0.3,
) -> Optional[Dict[str, Any]]:
    """Detect DNS failure rate jumping above baseline+threshold."""
    if recent_total < min_total or recent_failed < min_failed:
        return None
    rate = recent_failed / max(1, recent_total)
    if rate < rate_threshold:
        return None
    if baseline_failure_rate is not None and (rate - baseline_failure_rate) < delta_vs_baseline:
        return None
    payload = {
        "window_total": recent_total,
        "window_failed": recent_failed,
        "failure_rate": round(rate, 3),
        "baseline_rate": baseline_failure_rate,
        "severity": "fail" if rate >= 0.7 else "warn",
    }
    fp = fingerprint or compute_fingerprint({"dns": f"{recent_total}/{recent_failed}"})
    return _emit_alert("dns_failure_rate_spike", payload, fp)


def detect_node_consecutive_timeout(
    profile_id: Optional[str],
    consecutive_timeouts: int,
    fingerprint: str = "",
    *,
    threshold: int = 3,
) -> Optional[Dict[str, Any]]:
    """Detect a proxy node has been timing out 3+ times in a row."""
    if not profile_id or consecutive_timeouts < threshold:
        return None
    payload = {
        "profile_id": profile_id,
        "consecutive_timeouts": consecutive_timeouts,
        "severity": "fail" if consecutive_timeouts >= 5 else "warn",
    }
    fp = fingerprint or compute_fingerprint({"node": str(profile_id)})
    return _emit_alert("node_consecutive_timeout", payload, fp)


def detect_rtt_spike(
    current_rtt_ms: Optional[float],
    baseline_rtt_ms: Optional[float],
    gateway_rtt_ms: Optional[float] = None,
    proxy_rtt_ms: Optional[float] = None,
    fingerprint: str = "",
    *,
    hard_threshold_ms: float = 500.0,
    ratio_threshold: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """Detect latency jumps hard (>=500ms) or 3x the baseline."""
    if current_rtt_ms is None:
        return None
    triggered = False
    if current_rtt_ms >= hard_threshold_ms:
        triggered = True
    if baseline_rtt_ms is not None and baseline_rtt_ms > 0:
        if current_rtt_ms >= baseline_rtt_ms * ratio_threshold:
            triggered = True
    if not triggered:
        return None
    layer = "unknown"
    if gateway_rtt_ms is not None and proxy_rtt_ms is not None:
        if gateway_rtt_ms > proxy_rtt_ms:
            layer = "local_wifi"
        elif proxy_rtt_ms > gateway_rtt_ms:
            layer = "proxy_node"
    payload = {
        "current_rtt_ms": round(current_rtt_ms, 1),
        "baseline_rtt_ms": round(baseline_rtt_ms, 1) if baseline_rtt_ms else None,
        "gateway_rtt_ms": round(gateway_rtt_ms, 1) if gateway_rtt_ms else None,
        "proxy_rtt_ms": round(proxy_rtt_ms, 1) if proxy_rtt_ms else None,
        "layer": layer,
        "severity": "fail" if current_rtt_ms >= 1500 else "warn",
    }
    fp = fingerprint or compute_fingerprint({"rtt": str(current_rtt_ms)})
    return _emit_alert("rtt_spike", payload, fp)


# ---------------------------------------------------------------------------
# Confirmation 字面值（与 AGENTS.md 表格同步）
# ---------------------------------------------------------------------------

CONFIRMATION_PHRASE_REQUIRED_FOR_PROACTIVE = False  # 主动救火只生成卡片，不自动修复


def to_card(alert: Dict[str, Any], *, scenario_id: str = "") -> Dict[str, Any]:
    """Convert stored alert into AIChatView card-shape payload."""
    alert_type = alert.get("alert_type", "")
    payload = alert.get("payload", {})
    cards: Dict[str, Dict[str, Any]] = {
        "exit_ip_type_change": {
            "scenario_id": "ai-service-risk-control",
            "headline": "你现在用的是另一类出口网络",
            "body": (
                f"出口刚从 {payload.get('from_type')} 变成 {payload.get('to_type')}。"
                f"ChatGPT、Claude 等服务可能因此要求额外验证；目前还没有替你切换设置。"
            ),
            "buttons": [
                {"id": "check_ai_service", "label": "检查 AI 服务"},
                {"id": "switch_node", "label": "切回上个健康节点"},
                {"id": "dismiss", "label": "这次忽略"},
            ],
        },
        "dns_failure_rate_spike": {
            "scenario_id": "dns-abnormal",
            "headline": "最近几分钟，网站地址开始频繁查不到",
            "body": (
                f"最近 {payload.get('window_total')} 次解析有 {payload.get('window_failed')} 次失败"
                f"（失败率 {int(payload.get('failure_rate', 0) * 100)}%）。先对比公共 DNS，不会修改设置。"
            ),
            "buttons": [
                {"id": "start_read_only_check", "label": "开始只读检查"},
                {"id": "remind_later", "label": "稍后提醒"},
                {"id": "dismiss", "label": "忽略本次"},
            ],
        },
        "node_consecutive_timeout": {
            "scenario_id": "proxy-node-failure",
            "headline": "当前代理节点可能已经下线",
            "body": (
                f"同一节点连续 {payload.get('consecutive_timeouts')} 次连接超时，本地代理软件仍在运行。"
                "更像是节点上游故障。"
            ),
            "buttons": [
                {"id": "test_other_nodes", "label": "测试其他节点"},
                {"id": "open_proxy_app", "label": "打开代理软件"},
                {"id": "dismiss", "label": "暂停此节点监控"},
            ],
        },
        "rtt_spike": {
            "scenario_id": "wifi-gateway-down",
            "headline": f"网络延迟突然升到 {int(payload.get('current_rtt_ms', 0))}ms",
            "body": (
                f"Mac 到路由器 {int(payload.get('gateway_rtt_ms') or 0)}ms，"
                f"代理路径 {int(payload.get('proxy_rtt_ms') or 0)}ms。"
                f"卡顿主要出现在 {_layer_label(payload.get('layer'))}。"
            ),
            "buttons": [
                {"id": "view_bandwidth_hogs", "label": "查看谁在占网"},
                {"id": "test_other_nodes", "label": "测试其他节点"},
                {"id": "dismiss", "label": "已知，先不处理"},
            ],
        },
    }
    spec = cards.get(alert_type, {})
    return {
        "schema_version": "netfix_proactive_card.v1",
        "card_id": alert.get("alert_id", ""),
        "alert_type": alert_type,
        "scenario_id": scenario_id or spec.get("scenario_id", ""),
        "phase": "proactive_alert",
        "headline": spec.get("headline", ""),
        "body": spec.get("body", ""),
        "buttons": spec.get("buttons", []),
        "evidence": [alert.get("payload", {})],
        "interruptible": True,
        "source": "monitor",
        "triggered_at": alert.get("triggered_at"),
    }


def _layer_label(layer: Optional[str]) -> str:
    return {
        "local_wifi": "本地 Wi-Fi / 路由器",
        "proxy_node": "代理节点",
        "unknown": "不能确定",
    }.get(layer or "unknown", "不能确定")
