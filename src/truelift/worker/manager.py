"""The app side of a run: admit, spawn, watch, cap, cancel and reconcile (C1, C10, SB19; D8).

``RunManager`` is shared by the API and the ``truelift run`` command.

* **Start.** The gate admits the run under the project's lock (C1). The ``runs`` row is inserted
  ``queued`` only if no run is queued or running on this machine, checked inside SQLite's write
  lock, so the app and ``truelift run`` cannot both start one (SB19). The app writes
  ``config.json`` and ``run.json``, then spawns ``python -m truelift.worker`` in a new session,
  so the worker leads its own process group with the pipeline's loky workers inside it.
* **Watch.** A thread waits for the worker with the profile's wall-clock cap. The outcome comes
  from the worker's exit code, its ``status.json`` and the manifest: ``succeeded`` needs exit 0
  and a manifest whose every hash matches (C10).
* **Cancel** kills the process group and sets ``cancelled``. Cancelling a run that has ended
  changes nothing.
* **Reconcile** at startup: a queued or running row whose worker is not alive, or whose watcher
  (a truelift process) is gone, becomes ``interrupted``. A live worker whose watcher is gone is
  killed first, because phase 1 does not re-adopt workers (design section 3, G25).
* **Shutdown** kills active workers and marks their runs ``interrupted``.

The worker's liveness is its pid **and** a fresh heartbeat in ``status.json`` naming that pid, so
a reused pid is never taken for a worker.
"""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from truelift.causal.compile import Profile
from truelift.causal.rules import RuleSet, load_rules
from truelift.store import ProjectStore
from truelift.store.db import ACTIVE_RUN_STATUSES, RunRow
from truelift.store.files import atomic_write
from truelift.worker import phases
from truelift.worker.gate import admit
from truelift.worker.job import EXIT_OK
from truelift.worker.layout import RunFolder, expected_outputs, read_json, utcnow, write_json

log = logging.getLogger("truelift.worker")

RUN_SCHEMA = "truelift.run/1"

# G03 measurements on the reference Mac (M1, M2) and caps (ruling R2: about 3x the median).
EXPECTED_S = {Profile.quick: 125.0, Profile.standard: 208.0}
CAPS_S = {Profile.quick: 390.0, Profile.standard: 630.0}

# Provider keys never reach the worker: it makes no model call (C7, defence in depth).
_SECRET_ENV = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")

CANCELLED = "You cancelled this run."
UNEXPECTED_STOP = "The analysis process stopped unexpectedly. Run it again."
NO_RESULTS = "The analysis finished without valid results. Run it again."
COULD_NOT_START = "The analysis could not start. Run it again."


def _minutes(seconds: float) -> int:
    return max(1, round(seconds / 60))


def interrupted_reason(profile: Profile | str) -> str:
    return f"This run was interrupted. Run it again (about {_minutes(EXPECTED_S[Profile(profile)])} min)."


def too_long_reason(cap_s: float) -> str:
    return f"This run took too long (more than {_minutes(cap_s)} min) and was stopped."


class RunActive(Exception):
    def __init__(self, run: RunRow):
        super().__init__("Another run is in progress. Wait for it or cancel it.")
        self.run = run


@dataclass(frozen=True)
class Limits:
    caps_s: dict[Profile, float] = field(default_factory=lambda: dict(CAPS_S))
    expected_s: dict[Profile, float] = field(default_factory=lambda: dict(EXPECTED_S))
    kill_grace_s: float = 5.0
    heartbeat_stale_s: float = 30.0


@dataclass(frozen=True)
class RunView:
    """What the status endpoint shows (C10/A7): enough to reattach after a page refresh."""

    row: RunRow
    phase: str | None
    phases: list[str]
    elapsed_s: float
    expected_s: float
    log_tail: list[str]


def worker_command(run_id: str, run_dir: Path) -> list[str]:
    return [sys.executable, "-m", "truelift.worker", run_id, "--run-dir", str(run_dir)]


def worker_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _SECRET_ENV}
    env["PYTHONUNBUFFERED"] = "1"
    if sys.platform == "darwin" and "DYLD_FALLBACK_LIBRARY_PATH" not in env:
        # lightgbm and xgboost need libomp; scikit-learn's wheel bundles one. The fallback path is
        # searched only when no system copy is found (G03/A5). It must be set before start-up.
        spec = importlib.util.find_spec("sklearn")
        if spec is not None and spec.origin is not None:
            env["DYLD_FALLBACK_LIBRARY_PATH"] = str(Path(spec.origin).parent / ".dylibs")
    return env


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass
class _Handle:
    proc: subprocess.Popen[bytes]
    thread: threading.Thread
    cap_s: float


class RunManager:
    def __init__(
        self,
        store: ProjectStore,
        *,
        limits: Limits | None = None,
        command: Callable[[str, Path], list[str]] = worker_command,
        rules: Callable[[], RuleSet] = load_rules,
        clock: Callable[[], datetime] = utcnow,
    ):
        self.store = store
        self.db = store.db
        self.limits = limits or Limits()
        self.command = command
        self._rules = rules
        self.clock = clock
        self._handles: dict[str, _Handle] = {}
        self._lock = threading.Lock()
        self._closing = False

    # --- folders and views ------------------------------------------------------------------

    def folder(self, row: RunRow) -> RunFolder:
        return RunFolder(self.store.projects_dir / row.project_id / "runs" / row.id)

    def get(self, run_id: str) -> RunRow | None:
        return self.db.run(run_id)

    def list(self, project_id: str) -> list[RunRow]:
        return self.db.runs_for(project_id)

    def view(self, row: RunRow) -> RunView:
        folder = self.folder(row)
        status = folder.read_status()
        profile = Profile(row.profile)
        run_phases = status.get("phases") if isinstance(status.get("phases"), list) else None
        if run_phases is None:
            config = read_json(folder.config) or {}
            sensitivity = (config.get("orchestrator") or {}).get("run_sensitivity")
            run_phases = phases.phases_for(profile, sensitivity if isinstance(sensitivity, bool) else None)
        phase = status.get("phase") if isinstance(status.get("phase"), str) else None
        if row.status == "queued":
            phase = None
        elif row.status == "running" and phase is None:
            phase = phases.PREPARE
        if row.started_at is None:
            elapsed = 0.0
        else:
            end = row.finished_at or self.clock()
            elapsed = max(0.0, (end - row.started_at).total_seconds())
        return RunView(
            row=row,
            phase=phase,
            phases=[str(p) for p in run_phases],
            elapsed_s=round(elapsed, 1),
            expected_s=self.limits.expected_s[profile],
            log_tail=folder.log_tail(),
        )

    def succeeded(self, row: RunRow) -> bool:
        """Results may be read only for a succeeded run whose manifest still verifies (C10)."""
        if row.status != "succeeded":
            return False
        folder = self.folder(row)
        config = read_json(folder.config) or {}
        sensitivity = bool((config.get("orchestrator") or {}).get("run_sensitivity"))
        return folder.verify_manifest(row.id, expected_outputs(sensitivity))

    # --- start --------------------------------------------------------------------------------

    def start(self, project_id: str, dag_version: int, profile: Profile | str) -> RunRow:
        row = self.prepare(project_id, dag_version, profile)
        return self.launch(row)

    def prepare(self, project_id: str, dag_version: int, profile: Profile | str) -> RunRow:
        """Admit the run, insert its row and write ``config.json`` and ``run.json``. Raises
        ``GateRefused``, ``RunActive`` or the store's ``NotFound``."""
        profile = Profile(profile)
        run_id = "run-" + secrets.token_hex(6)
        with self.store.open(project_id) as project:
            admitted = admit(project, dag_version, profile, self._rules())
            now = self.clock()
            row = RunRow(
                id=run_id,
                project_id=project_id,
                dag_version=dag_version,
                profile=profile.value,
                status="queued",
                reason=None,
                pid=None,
                owner_pid=os.getpid(),
                cancel_requested=False,
                config_sha256=admitted.inputs.config_sha256,
                created_at=now,
                started_at=None,
                finished_at=None,
            )
            active = self.db.insert_run_if_idle(row)
            if active is not None:
                raise RunActive(active)
            folder = RunFolder(project.root / "runs" / run_id)
            try:
                folder.root.mkdir(parents=True, exist_ok=False)
                atomic_write(folder.config, admitted.config.to_json())  # 1. config.json
                write_json(
                    folder.run,
                    {
                        "schema": RUN_SCHEMA,
                        "run_id": run_id,
                        "created_at": now.isoformat(),
                        "inputs": admitted.inputs.to_dict(),
                    },
                )
            except Exception:
                self._end(run_id, "failed", COULD_NOT_START)
                raise
        return row

    def launch(self, row: RunRow) -> RunRow:
        folder = self.folder(row)
        cap = self.limits.caps_s[Profile(row.profile)]
        with self._lock:
            if self._closing:
                self._end(row.id, "interrupted", interrupted_reason(row.profile))
                return self.db.run(row.id) or row
            try:
                proc = subprocess.Popen(  # noqa: S603 - our own interpreter and module
                    self.command(row.id, folder.root),
                    cwd=folder.root,
                    env=worker_env(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=os.name == "posix",
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
            except OSError:
                log.exception("could not start the worker for %s", row.id)
                self._end(row.id, "failed", COULD_NOT_START)
                return self.db.run(row.id) or row
            try:
                self.db.update_run(
                    row.id, only_if_active=True, status="running", pid=proc.pid, started_at=self.clock()
                )
            except SQLAlchemyError:
                # Without its row the run cannot be watched or shown: stop it at once.
                self._kill_group(proc.pid, proc)
                raise
            thread = threading.Thread(target=self._watch, args=(row.id, proc, cap), daemon=True)
            self._handles[row.id] = _Handle(proc, thread, cap)
            thread.start()
        return self.db.run(row.id) or row

    # --- watch --------------------------------------------------------------------------------

    def _watch(self, run_id: str, proc: subprocess.Popen[bytes], cap_s: float) -> None:
        timed_out = False
        try:
            returncode = proc.wait(timeout=cap_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc.pid, proc)
            returncode = proc.wait()
        else:
            # The leader is gone; make sure no loky worker of its group is left behind.
            self._kill_group(proc.pid, None, grace_s=0)
        try:
            self._finalize(run_id, returncode, timed_out, cap_s)
        except SQLAlchemyError:
            # The row stays queued or running; the next startup marks it interrupted (A8).
            log.exception("could not record the end of run %s", run_id)
        finally:
            with self._lock:
                self._handles.pop(run_id, None)

    def _finalize(self, run_id: str, returncode: int, timed_out: bool, cap_s: float) -> None:
        row = self.db.run(run_id)
        if row is None or row.status not in ACTIVE_RUN_STATUSES:
            return
        folder = self.folder(row)
        if row.cancel_requested:
            status, reason = "cancelled", CANCELLED
        elif timed_out:
            status, reason = "failed", too_long_reason(cap_s)
        elif returncode == EXIT_OK and self._manifest_ok(folder, row.id):
            status, reason = "succeeded", None
        else:
            worker = folder.read_status()
            if worker.get("state") == "failed" and isinstance(worker.get("reason"), str):
                status, reason = "failed", worker["reason"]
            elif returncode == EXIT_OK:
                status, reason = "failed", NO_RESULTS
            else:
                status, reason = "failed", UNEXPECTED_STOP
        self._end(run_id, status, reason)

    def _manifest_ok(self, folder: RunFolder, run_id: str) -> bool:
        config = read_json(folder.config) or {}
        sensitivity = bool((config.get("orchestrator") or {}).get("run_sensitivity"))
        return folder.verify_manifest(run_id, expected_outputs(sensitivity))

    def _end(self, run_id: str, status: str, reason: str | None) -> bool:
        return self.db.update_run(
            run_id, only_if_active=True, status=status, reason=reason, finished_at=self.clock()
        )

    def wait(self, run_id: str, timeout: float | None = None) -> RunRow | None:
        with self._lock:
            handle = self._handles.get(run_id)
        if handle is not None:
            handle.thread.join(timeout)
        return self.db.run(run_id)

    # --- cancel -------------------------------------------------------------------------------

    def cancel(self, run_id: str) -> RunRow | None:
        """Kill the run's process group and mark it ``cancelled``. Idempotent (A9)."""
        row = self.db.run(run_id)
        if row is None or row.status not in ACTIVE_RUN_STATUSES:
            return row
        self.db.update_run(run_id, only_if_active=True, cancel_requested=True)
        with self._lock:
            handle = self._handles.get(run_id)
        if handle is not None:
            self._kill_group(handle.proc.pid, handle.proc)
            handle.thread.join(self.limits.kill_grace_s + 10)
        elif self.worker_alive(row):
            self._kill_group(row.pid, None)
        # Watched here: the watcher has recorded it. Otherwise (queued, or another process's
        # run whose worker was just killed) record it now; a late watcher changes nothing.
        self._end(run_id, "cancelled", CANCELLED)
        return self.db.run(run_id)

    def _kill_group(
        self, pid: int | None, proc: subprocess.Popen[bytes] | None, grace_s: float | None = None
    ) -> None:
        """SIGTERM the process group, wait up to the grace period, then SIGKILL what is left."""
        if not pid:
            return
        grace = self.limits.kill_grace_s if grace_s is None else grace_s
        if os.name != "posix":  # pragma: no cover - phase 1 is macOS and Linux
            if proc is not None:
                with contextlib.suppress(OSError):
                    proc.kill()
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGTERM)
        if proc is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=grace)
        else:
            deadline = time.monotonic() + grace
            while pid_alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)

    # --- liveness, reconciliation and shutdown ------------------------------------------------

    def worker_alive(self, row: RunRow) -> bool:
        if not pid_alive(row.pid):
            return False
        status = self.folder(row).read_status()
        if status.get("pid") != row.pid or not isinstance(status.get("heartbeat_at"), str):
            return False
        try:
            beat = datetime.fromisoformat(status["heartbeat_at"])
        except ValueError:
            return False
        return (self.clock() - beat).total_seconds() <= self.limits.heartbeat_stale_s

    def reconcile(self) -> list[str]:
        """Mark queued or running rows with no live worker or no live watcher ``interrupted``
        (C10/A8). Returns the IDs it changed."""
        if not self.db.path.exists():
            return []  # no database yet, so no run
        changed = []
        for row in self.db.active_runs():
            with self._lock:
                if row.id in self._handles:
                    continue
            other_owner = row.owner_pid not in (None, os.getpid()) and pid_alive(row.owner_pid)
            alive = self.worker_alive(row)
            if other_owner and (alive or row.status == "queued"):
                continue  # another truelift process (the app or `truelift run`) is watching it
            # Record first, then stop the worker, so nothing that sees it die can record more.
            if self._end(row.id, "interrupted", interrupted_reason(row.profile)):
                changed.append(row.id)
            if alive:
                self._kill_group(row.pid, None)
        return changed

    def shutdown(self) -> None:
        """Phase 1 does not re-adopt workers: stop them and mark their runs interrupted (D8)."""
        with self._lock:
            self._closing = True
            handles = dict(self._handles)
        for run_id, handle in handles.items():
            row = self.db.run(run_id)
            with contextlib.suppress(SQLAlchemyError):
                self._end(run_id, "interrupted", interrupted_reason(row.profile if row else "quick"))
            self._kill_group(handle.proc.pid, handle.proc)
        for handle in handles.values():
            handle.thread.join(self.limits.kill_grace_s + 10)
