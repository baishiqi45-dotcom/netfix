"""Fix execution engine: planning, backups, journaling and rollback.

The engine reads ``rules/symptoms.json`` to map root causes to fixes,
executes them according to their safety tier, backs up files before
mutating changes, and records everything in ``~/.netfix/journal.jsonl``.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from netfix import diagnose
from netfix.constants import JOURNAL_DIR, REPO_ROOT, RULES_DIR
from netfix.safety import FixTier, audit_sudo, classify_command, is_dangerous
from netfix.utils import admin_command_script, confirm, ensure_private_dir, human_time, run_command, secure_append_text


class FixEngine:
    """Run fixes safely and keep an audit journal."""

    def __init__(self, journal_dir: Path = JOURNAL_DIR):
        self.journal_dir = Path(journal_dir)
        self.backup_dir = self.journal_dir / "backups"
        ensure_private_dir(self.journal_dir)
        ensure_private_dir(self.backup_dir)
        self.journal_file = self.journal_dir / "journal.jsonl"
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        path = RULES_DIR / "symptoms.json"
        if not path.exists():
            return {"symptoms": [], "fixes": {}}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def plan(self, report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return a list of fixes matching the symptoms/root causes in *report*."""
        fixes: List[Dict[str, Any]] = []
        seen: set[str] = set()
        fixes_map = self.rules.get("fixes", {})

        # If the report already contains fixes from the reasoner, prefer them.
        report_fixes = report.get("fixes", [])
        for fix in report_fixes:
            fid = fix.get("id") if isinstance(fix, dict) else fix
            if not fid or fid in seen or fid not in fixes_map:
                continue
            definition = fixes_map[fid].copy()
            definition["id"] = fid
            definition["tier"] = FixTier(definition.get("tier", 1))
            definition["_confidence"] = fix.get("confidence", 0.5) if isinstance(fix, dict) else 0.5
            fixes.append(definition)
            seen.add(fid)

        # Fallback: match by explicit symptom ids and root cause ids.
        symptoms = self.rules.get("symptoms", [])
        report_symptoms = report.get("symptoms", [])
        root_causes = report.get("root_causes", [])

        for sid in report_symptoms:
            for symptom in symptoms:
                if symptom["id"] == sid:
                    self._collect_fixes(symptom, fixes_map, fixes, seen)
                    break

        rc_ids = {rc.get("id") for rc in root_causes}
        for symptom in symptoms:
            for cause in symptom.get("root_causes", []):
                if cause.get("id") in rc_ids:
                    self._collect_fixes(symptom, fixes_map, fixes, seen)
                    break

        # Stable sort: lower tier first, then by original confidence.
        fixes.sort(key=lambda f: (f["tier"].value, f.get("_confidence", 0)), reverse=False)
        for fix in fixes:
            fix.pop("_confidence", None)
        return fixes

    @staticmethod
    def _collect_fixes(
        symptom: Dict[str, Any],
        fixes_map: Dict[str, Any],
        out: List[Dict[str, Any]],
        seen: set[str],
    ) -> None:
        confidence = max(
            (c.get("confidence", 0.5) for c in symptom.get("root_causes", [])),
            default=0.5,
        )
        for fid in symptom.get("fixes", []):
            if fid in fixes_map and fid not in seen:
                fix = fixes_map[fid].copy()
                fix["id"] = fid
                fix["tier"] = FixTier(fix.get("tier", 1))
                fix["_confidence"] = confidence
                out.append(fix)
                seen.add(fid)

    @staticmethod
    def _looks_like_permission_error(res: Dict[str, Any]) -> bool:
        text = f"{res.get('stdout', '')}\n{res.get('stderr', '')}".lower()
        markers = (
            "permission",
            "not permitted",
            "operation not permitted",
            "authorization",
            "administrator",
            "privilege",
            "must be root",
            "requires root",
            "not allowed",
        )
        return any(marker in text for marker in markers)

    def _run_guarded_command(self, cmd: str, running_as_root: bool) -> Dict[str, Any]:
        cmd = self._resolve_repo_relative_paths(cmd)
        if is_dangerous(cmd):
            return {
                "command": cmd,
                "ok": False,
                "status": "skipped",
                "reason": "dangerous pattern",
            }

        override = classify_command(cmd)
        if override == FixTier.MANUAL:
            return {
                "command": cmd,
                "ok": False,
                "status": "skipped",
                "reason": "classified manual",
            }

        cmd_list = shlex.split(cmd)
        if override == FixTier.CONFIRM and not running_as_root:
            if not cmd.strip().lower().startswith("sudo "):
                res = run_command(cmd_list, timeout=30)
                if not res["ok"] and self._looks_like_permission_error(res):
                    script = admin_command_script(cmd)
                    res = run_command(["osascript", "-e", script], timeout=120)
            else:
                script = admin_command_script(cmd)
                res = run_command(["osascript", "-e", script], timeout=120)

            if not res["ok"] and ("User canceled" in res["stderr"] or "[-128]" in res["stderr"]):
                res["stderr"] = "用户取消了授权"
        else:
            res = run_command(cmd_list, timeout=30)

        return {
            "command": cmd,
            "ok": res["ok"],
            "returncode": res["returncode"],
            "stderr": res["stderr"],
        }

    @staticmethod
    def _resolve_repo_relative_paths(cmd: str) -> str:
        """Make rule commands work from the App bundle, not just repo cwd."""
        try:
            parts = shlex.split(cmd)
        except ValueError:
            return cmd
        changed = False
        resolved: List[str] = []
        for part in parts:
            if part.startswith("bin/") or part.startswith("rules/"):
                resolved.append(str(REPO_ROOT / part))
                changed = True
            else:
                resolved.append(part)
        return shlex.join(resolved) if changed else cmd

    def execute(
        self,
        fix_id: str,
        dry_run: bool = False,
        auto_confirm: bool = False,
        confirmed: bool = False,
        env: Optional[Dict[str, Any]] = None,
        core: Any = None,
    ) -> Dict[str, Any]:
        """Execute (or preview) a single fix by id.

        Tier 1 fixes run automatically (unless ``dry_run`` is set).
        Tier 2 fixes back up files, then require an explicit confirmation.
        CLI calls ask for ``y/N``; local App/API calls may pass ``confirmed``
        only after their own user-facing confirmation.
        Tier 3 fixes only return manual steps.
        ``auto_confirm`` only bypasses Tier 0/Tier 1 confirmation.
        """
        fixes_map = self.rules.get("fixes", {})
        if fix_id not in fixes_map:
            return {"ok": False, "error": f"fix '{fix_id}' not found"}

        fix = fixes_map[fix_id].copy()
        fix["id"] = fix_id
        tier = FixTier(fix.get("tier", 1))
        commands = fix.get("commands", [])
        verify = fix.get("verify")
        verify_diagnostic = fix.get("verify_diagnostic")
        backup_paths = fix.get("backup_paths", [])
        description = fix.get("description", fix_id)
        manual_steps = fix.get("manual_steps", [])
        reverse = fix.get("reverse", [])

        result: Dict[str, Any] = {
            "fix_id": fix_id,
            "tier": tier.name,
            "description": description,
            "dry_run": dry_run,
            "auto_confirm": auto_confirm,
            "commands": commands,
            "executed": [],
            "verified": False,
        }

        # Tier 3: manual-only.
        if tier == FixTier.MANUAL:
            result["status"] = "manual"
            result["manual_steps"] = manual_steps
            return result

        # Tier 2: confirm + backup.
        if tier == FixTier.CONFIRM:
            if dry_run:
                result["status"] = "dry-run"
                result["preview"] = commands
                return result

            backups = self._backup_paths(backup_paths)
            result["backups"] = backups
            preview = "\n".join(f"  {c}" for c in commands)
            prompt = f"确认执行修复 [{fix_id}] {description}?\n{preview}"
            if confirmed:
                approved = True
                result["confirmed"] = True
            else:
                if auto_confirm:
                    result["auto_confirm_ignored"] = True
                approved = confirm(prompt, default=False)
            if auto_confirm and not confirmed:
                result["auto_confirm_ignored"] = True
            if approved:
                self._audit_commands(commands, approved=True)
            else:
                self._audit_commands(commands, approved=False)
                result["status"] = "cancelled"
                result["backups"] = backups
                return result

        # Tier 1: auto-safe.
        if tier == FixTier.AUTO_SAFE:
            if dry_run:
                result["status"] = "dry-run"
                result["preview"] = commands
                return result
            self._audit_commands(commands, approved=True)

        # Tier 0: read-only, nothing to do.
        if tier == FixTier.READONLY:
            result["status"] = "no-op"
            return result

        # Run commands.
        running_as_root = os.geteuid() == 0
        for cmd in commands:
            result["executed"].append(self._run_guarded_command(cmd, running_as_root))

        # Verify.
        verification_ran = False
        if verify:
            verification_ran = True
            vres = run_command(shlex.split(verify), timeout=30)
            result["verified"] = vres["ok"]
            result["verify_output"] = vres["stdout"]

        if verify_diagnostic:
            verification_ran = True
            diag_res = diagnose.run_diagnostic(
                verify_diagnostic, env or {}, core, timeout=20
            )
            result["verify_diagnostic"] = diag_res
            result["verified"] = diag_res.get("status") == "ok"

        # Journal entry.
        journal_entry = {
            "timestamp": human_time(),
            "fix_id": fix_id,
            "tier": tier.value,
            "commands": commands,
            "backups": result.get("backups", {}),
            "reverse": reverse,
        }
        self._write_journal(journal_entry)

        all_ok = all(e.get("ok", True) for e in result["executed"])
        verification_ok = (not verification_ran) or bool(result.get("verified"))
        result["verification_failed"] = verification_ran and not verification_ok
        result["ok"] = all_ok and verification_ok
        if not all_ok:
            result["status"] = "partial"
        elif not verification_ok:
            result["status"] = "failed"
        else:
            result["status"] = "ok"
        return result

    def rollback(self) -> Dict[str, Any]:
        """Undo the last journaled fix: restore backups and run reverse commands."""
        if not self.journal_file.exists():
            return {"ok": False, "error": "no journal found"}
        lines = self.journal_file.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return {"ok": False, "error": "journal empty"}

        last = json.loads(lines[-1])
        if last.get("action") == "rollback":
            return {"ok": False, "error": "last entry is already a rollback"}

        result: Dict[str, Any] = {
            "fix_id": last.get("fix_id"),
            "commands_reversed": [],
            "backups_restored": {},
        }

        # Restore backups first.
        for src, dst in last.get("backups", {}).items():
            try:
                shutil.copy2(dst, src)
                result["backups_restored"][src] = dst
            except Exception as exc:  # pragma: no cover - defensive
                result["backups_restored"][src] = {"error": str(exc)}

        # Run reverse commands.
        running_as_root = os.geteuid() == 0
        for cmd in last.get("reverse", []):
            result["commands_reversed"].append(self._run_guarded_command(cmd, running_as_root))

        self._write_journal({
            "timestamp": human_time(),
            "fix_id": last.get("fix_id"),
            "tier": last.get("tier"),
            "action": "rollback",
            "commands": last.get("commands", []),
        })

        backups = last.get("backups", {})
        backups_ok = all(
            not isinstance(v, dict) for v in result["backups_restored"].values()
        ) if backups else True
        reversed_ok = all(r["ok"] for r in result["commands_reversed"]) if last.get("reverse") else True
        result["ok"] = backups_ok and reversed_ok
        return result

    def _backup_paths(self, paths: List[str]) -> Dict[str, str]:
        backups: Dict[str, str] = {}
        for p in paths:
            src = Path(p).expanduser()
            if src.exists():
                ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                dst = self.backup_dir / f"{src.name}.{ts}"
                shutil.copy2(src, dst)
                backups[str(src)] = str(dst)
        return backups

    def _write_journal(self, entry: Dict[str, Any]) -> None:
        secure_append_text(self.journal_file, json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def _audit_commands(commands: List[str], approved: bool) -> None:
        for cmd in commands:
            if "sudo" in cmd.lower() or classify_command(cmd) in (FixTier.CONFIRM, FixTier.MANUAL):
                audit_sudo(cmd, approved=approved)
