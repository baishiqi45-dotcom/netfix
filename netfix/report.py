"""Report generation and persistence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import JOURNAL_DIR, VERSION
from .i18n import fmt, t
from .utils import human_time, secure_write_json, to_json


class Report:
    """A netfix diagnostic/fix report."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data

    def as_dict(self) -> Dict[str, Any]:
        return self.data

    def to_json(self, pretty: bool = False) -> str:
        return to_json(self.data, pretty=pretty)

    def _status_symbol(self, status: str) -> str:
        if status == "ok":
            return "✓"
        if status == "fail":
            return "✗"
        return "?"

    @staticmethod
    def _confidence_label(confidence: Any) -> str:
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            return ""
        if value >= 0.8:
            return "很确定"
        if value >= 0.6:
            return "比较确定"
        return "可能"

    @staticmethod
    def _fix_tier_label(tier: Any) -> str:
        try:
            value = int(tier)
        except (TypeError, ValueError):
            value = 3
        return {
            1: "可自动处理",
            2: "需要你确认",
            3: "请手动操作",
        }.get(value, "请手动操作")

    def summary(self) -> Dict[str, Any]:
        """Return a one-sentence conclusion and recommended action."""
        env = self.data.get("environment", {})
        diagnostics = self.data.get("diagnostics", [])
        root_causes = self.data.get("root_causes", [])
        fixes = self.data.get("fixes", [])

        # Decide overall health from diagnostics.
        statuses = [d.get("status") for d in diagnostics]
        has_fail = "fail" in statuses
        has_warn = "warn" in statuses
        all_ok = not has_fail and not has_warn

        if all_ok:
            headline = t("summary.healthy")
        elif env.get("gui_client") and has_fail:
            headline = t("summary.proxy_broken")
        elif has_fail:
            headline = t("summary.no_network")
        elif has_warn:
            headline = t("summary.proxy_needed")
        else:
            headline = t("summary.partial")

        # Pick the first actionable fix tier.
        action = t("action.tier3.manual")
        if fixes:
            tiers = [f.get("tier", 3) for f in fixes]
            if 1 in tiers:
                action = t("action.tier1.auto")
            elif 2 in tiers:
                action = t("action.tier2.confirm")

        return {
            "headline": headline,
            "action": action,
            "root_cause": root_causes[0].get("description") if root_causes else None,
        }

    def to_human(self) -> str:
        meta = self.data.get("meta", {})
        env = self.data.get("environment", {})
        diagnostics = self.data.get("diagnostics", [])
        root_causes = self.data.get("root_causes", [])
        fixes = self.data.get("fixes", [])
        manual_steps = self.data.get("manual_steps", [])

        summary = self.summary()
        lines = [
            f"netfix {meta.get('version', VERSION)}",
            f"{meta.get('timestamp', 'unknown')}",
            "",
            f"【结论】{summary['headline']}",
        ]
        if summary["root_cause"]:
            lines.append(f"【最可能的原因】{summary['root_cause']}")
        lines.append(f"【建议】{summary['action']}")
        lines.append("")

        # Environment card
        lines.append(f"{t('section.environment')}")
        lines.append(
            f"  {t('label.gui_client')}: {env.get('gui_client') or t('label.unknown')}"
        )
        lines.append(
            f"  {t('label.active_core')}: {env.get('active_core') or t('label.none')}"
        )
        lines.append(
            f"  {t('label.mixed_port')}: {env.get('mixed_port') or t('label.none')}"
        )
        sys_proxy = env.get("system_proxy", {})
        proxies = [
            f"HTTP={sys_proxy.get('http') or '-'}",
            f"HTTPS={sys_proxy.get('https') or '-'}",
            f"SOCKS={sys_proxy.get('socks') or '-'}",
        ]
        lines.append(f"  {t('label.system_proxy')}: {' / '.join(proxies)}")
        active = env.get("active_profile")
        if active:
            lines.append(
                f"  {t('label.active_profile')}: {active.get('remarks') or active.get('id')}"
            )

        # Diagnostics by group/layer
        lines.extend(["", f"{t('section.diagnostics')}"])
        for diag in diagnostics:
            status = diag.get("status", "unknown")
            symbol = self._status_symbol(status)
            label = diag.get("name", "unknown")
            proxy = diag.get("proxy_used")
            if proxy and proxy != "direct":
                label = f"{label} ({proxy})"
            status_text = t(f"status.{status}", status)
            lines.append(f"  {symbol} {label}: {status_text}")

        # Root causes
        lines.extend(["", f"{t('section.root_causes')}"])
        if root_causes:
            for rc in root_causes:
                conf = rc.get("confidence")
                label = self._confidence_label(conf)
                conf_str = f"（{label}）" if label else ""
                lines.append(f"  - {rc.get('description')}{conf_str}")
        else:
            lines.append(f"  {t('label.none')}")

        # Fixes
        lines.extend(["", f"{t('section.fixes')}"])
        if fixes:
            for fix in fixes:
                tier = fix.get("tier", 3)
                lines.append(
                    f"  [{self._fix_tier_label(tier)}] {fix.get('id')}: {fix.get('description')}"
                )
                cmd = fix.get("command") or "N/A"
                lines.append(f"      {t('fix.command')}: {cmd}")
        else:
            lines.append(f"  {t('label.none')}")

        # Manual steps
        lines.extend(["", f"{t('section.manual_steps')}"])
        if manual_steps:
            for ms in manual_steps:
                desc = ms.get("description") or ms.get("id")
                lines.append(f"  - {desc}")
                for step in ms.get("steps", []):
                    lines.append(f"      • {step}")
        else:
            lines.append(f"  {t('label.none')}")

        # Advanced: raw JSON collapsed at the end
        lines.extend(["", f"{t('section.advanced')}"])
        lines.append(self.to_json(pretty=False))

        return "\n".join(lines)

    def _persistent_data(self) -> Dict[str, Any]:
        try:
            from netfix.redaction import redact_report
            redacted = redact_report(self.data, level="balanced").get("redacted_report")
            if isinstance(redacted, dict):
                return redacted
        except Exception:
            pass
        return self.data

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path else JOURNAL_DIR / "last_report.json"
        if path is None:
            try:
                from netfix.settings import get_privacy_settings
                if not get_privacy_settings().get("save_latest_report", True):
                    if target.exists():
                        target.unlink()
                    self._append_event(target)
                    return target
            except Exception:
                pass
        secure_write_json(target, self._persistent_data())
        self._append_event(target)
        return target

    def _append_event(self, report_path: Path) -> None:
        """Append a lightweight snapshot to the event log for timeline views."""
        diagnostics = self.data.get("diagnostics", [])
        statuses = [d.get("status") for d in diagnostics]
        status = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "ok")
        root_causes = self.data.get("root_causes", [])
        event = {
            "timestamp": self.data.get("meta", {}).get("timestamp", human_time()),
            "type": "report",
            "status": status,
            "headline": self.summary()["headline"],
            "root_cause": root_causes[0].get("description") if root_causes else None,
            "report_path": str(report_path),
        }
        try:
            from netfix.logs import append_event
            append_event(event)
        except Exception:
            # Retention is best-effort; report persistence must never fail because
            # an old event cannot be pruned.
            pass

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Report":
        target = Path(path) if path else JOURNAL_DIR / "last_report.json"
        data = json.loads(target.read_text(encoding="utf-8"))
        return cls(data)
