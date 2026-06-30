"""Reusable CLI runner and background job queue for netfix."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from netfix.constants import REPO_ROOT


def _stringify_argv(argv: List[Any]) -> List[str]:
    return [str(x) for x in argv]


def _cli_command(argv: List[str]) -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable] + argv
    return [sys.executable, "-m", "netfix.cli"] + argv


def run_cli(argv: List[str], timeout: int = 60) -> Dict[str, Any]:
    """Run a netfix CLI command and return a structured result."""
    argv = _stringify_argv(argv)
    cmd = _cli_command(argv)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0:
            error = stderr.strip() or stdout.strip() or f"command failed (rc={proc.returncode})"
            return {"ok": False, "error": error, "returncode": proc.returncode}
        try:
            return {"ok": True, "result": json.loads(stdout), "stderr": stderr}
        except json.JSONDecodeError:
            return {"ok": True, "raw": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": exc.stderr.strip() if exc.stderr else "command timed out",
            "returncode": -1,
            "timeout": True,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Minimal in-process background job runner
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_jobs_counter = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in job.items() if not key.startswith("_")}


def _run_cli_for_job(argv: List[str], timeout: int, job_id: str) -> Dict[str, Any]:
    argv = _stringify_argv(argv)
    cmd = _cli_command(argv)
    proc: Optional[subprocess.Popen[str]] = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job["_process"] = proc

        stdout, stderr = proc.communicate(timeout=timeout)
        stdout = stdout or ""
        stderr = stderr or ""
        if proc.returncode != 0:
            error = stderr.strip() or stdout.strip() or f"command failed (rc={proc.returncode})"
            return {"ok": False, "error": error, "returncode": proc.returncode}
        try:
            return {"ok": True, "result": json.loads(stdout), "stderr": stderr}
        except json.JSONDecodeError:
            return {"ok": True, "raw": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            proc.kill()
            proc.communicate()
        return {
            "ok": False,
            "error": exc.stderr.strip() if exc.stderr else "command timed out",
            "returncode": -1,
            "timeout": True,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}
    finally:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.pop("_process", None)


def start_job(argv: List[str], timeout: int = 60) -> str:
    """Start a CLI run in a background thread and return a job id."""
    global _jobs_counter
    argv = _stringify_argv(argv)
    with _jobs_lock:
        job_id = str(_jobs_counter)
        _jobs_counter += 1
        _jobs[job_id] = {
            "status": "running",
            "command": argv,
            "started_at": _utc_now(),
            "_cancel_requested": False,
        }

    def _target() -> None:
        result = _run_cli_for_job(argv, timeout=timeout, job_id=job_id)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            if job.get("_cancel_requested"):
                job.update({
                    "status": "cancelled",
                    "ok": False,
                    "error": "job cancelled",
                    "finished_at": job.get("finished_at") or _utc_now(),
                })
                job.pop("_process", None)
                return
            _jobs[job_id] = {
                "status": "done",
                "command": argv,
                "started_at": job.get("started_at"),
                "finished_at": _utc_now(),
                "result": result,
            }

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return the status/result of a background job, or None if unknown."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return None
    return _public_job(dict(job))


def cancel_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Request cancellation for a background job and terminate its child process."""
    proc: Optional[subprocess.Popen[str]] = None
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job.get("status") in {"done", "cancelled"}:
            return _public_job(dict(job))
        job["_cancel_requested"] = True
        job["status"] = "cancelled"
        job["ok"] = False
        job["error"] = "job cancelled"
        job["finished_at"] = _utc_now()
        proc = job.get("_process")

    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass

    return get_job(job_id)
