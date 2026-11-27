"""G09/A1, A3–A9: the run lifecycle with real worker processes (C9, C10, SB19; D8).

The worker is the production ``truelift.worker.job`` in its own process group; only the pipeline
fit is scripted (tests/worker/fake_worker.py), so each run takes seconds. Local.
"""

from __future__ import annotations

import json
import os
import signal

import pytest
from sqlalchemy.exc import OperationalError

from tests.worker.support import finished_run, manager, wait_for, wait_for_phase
from truelift.causal.compile import Profile
from truelift.store.db import StateDb
from truelift.worker import phases
from truelift.worker.layout import RunFolder
from truelift.worker.manager import CANCELLED, UNEXPECTED_STOP, Limits, RunActive, pid_alive


def _folder(store, project, run_id) -> RunFolder:
    return RunFolder(store.projects_dir / project / "runs" / run_id)


# --- A1: the run folder, in order, with env.json (C9, C10) -------------------------------------


def test_a_run_writes_its_files_in_order_with_the_manifest_last(store, project) -> None:
    m = manager(store, "ok")
    row = m.start(project, 1, "quick")
    final = m.wait(row.id, timeout=60)
    assert final is not None and final.status == "succeeded", final
    folder = _folder(store, project, row.id)

    seen = json.loads((folder.work / "seen.json").read_text())
    # When the fit started: config, run record, env, log, status and work/ exist; no manifest.
    assert seen["seen"] == {
        "config.json": True,
        "run.json": True,
        "env.json": True,
        "log.txt": True,
        "status.json": True,
        "work": True,
        "manifest.json": False,
    }
    assert seen["data"] == "v1.csv"
    manifest = json.loads(folder.manifest.read_bytes())
    assert manifest["run_id"] == row.id
    assert {"config.json", "run.json", "env.json"} <= set(manifest["files"])
    assert "log.txt" not in manifest["files"] and "status.json" not in manifest["files"]
    newest_output = max((folder.root / rel).stat().st_mtime_ns for rel in manifest["files"])
    assert folder.manifest.stat().st_mtime_ns >= newest_output
    assert m.succeeded(final)

    env = json.loads(folder.env.read_bytes())
    assert env["versions"]["doubleml-pipeline"] == "0.2.3"
    assert env["cpu_count"] == os.cpu_count() and env["n_jobs"] == -1
    assert env["platform"] and env["python"].startswith("3.12")
    assert env["seeds"]["hparam_search"] == 1
    assert env["config_sha256"] == row.config_sha256
    assert env["data_fingerprint"].startswith("sha256:")


# --- A3: a killed worker never leaves results (C10) --------------------------------------------


@pytest.mark.parametrize("how", ["outside_kill", "self_kill"])
def test_a_killed_worker_fails_and_leaves_no_manifest(store, project, how) -> None:
    m = manager(store, "sleep" if how == "outside_kill" else "crash")
    row = m.start(project, 1, "quick")
    if how == "outside_kill":
        wait_for_phase(m, row.id, phases.NUISANCE)
        os.killpg(row.pid or m.get(row.id).pid, signal.SIGKILL)
    final = m.wait(row.id, timeout=60)
    assert final is not None and final.status == "failed" and final.reason == UNEXPECTED_STOP
    folder = _folder(store, project, row.id)
    assert not folder.manifest.exists() and not m.succeeded(final)
    assert folder.config.is_file()  # kept for support


def test_outputs_without_a_manifest_are_never_read(store, project) -> None:
    folder = finished_run(store, project, "run-nomanifest1")
    folder.manifest.unlink()
    row = store.db.run("run-nomanifest1")
    assert row is not None and row.status == "succeeded"
    assert not manager(store).succeeded(row)


def test_a_changed_output_breaks_the_manifest(store, project) -> None:
    folder = finished_run(store, project, "run-tampered1")
    target = folder.root / "work" / "metadata.json"
    target.write_text("changed\n")
    assert not manager(store).succeeded(store.db.run("run-tampered1"))


# --- A4: a pipeline ValueError fails with a plain reason --------------------------------------


def test_a_pipeline_value_error_fails_with_a_plain_reason(store, project) -> None:
    m = manager(store, "valueerror")
    row = m.start(project, 1, "quick")
    final = m.wait(row.id, timeout=60)
    assert final is not None and final.status == "failed"
    assert final.reason == (
        "The analysis could not run on this data: Column 'media_grps' is not in the data. "
        "More detail on a second line."
    )
    folder = _folder(store, project, row.id)
    assert folder.config.is_file() and not folder.manifest.exists()
    assert "Traceback" in folder.log.read_text()  # details for support stay in the log


def test_a_run_without_its_outputs_fails(store, project) -> None:
    m = manager(store, "missing")
    row = m.start(project, 1, "quick")
    final = m.wait(row.id, timeout=60)
    assert final is not None and final.status == "failed"
    assert "without all its results" in (final.reason or "")
    assert not _folder(store, project, row.id).manifest.exists()


# --- A5: the wall-clock cap ---------------------------------------------------------------------


def test_a_run_over_its_cap_fails_as_too_long(store, project) -> None:
    limits = Limits(caps_s={Profile.quick: 3.0, Profile.standard: 3.0}, kill_grace_s=1.0)
    m = manager(store, "sleep", limits)
    row = m.start(project, 1, "quick")
    final = m.wait(row.id, timeout=60)
    assert final is not None and final.status == "failed"
    assert final.reason is not None and "took too long" in final.reason
    assert not pid_alive(final.pid)


def test_default_caps_are_three_times_the_g03_median() -> None:
    limits = Limits()
    assert limits.expected_s == {Profile.quick: 125.0, Profile.standard: 208.0}
    for profile in Profile:
        assert 3 * limits.expected_s[profile] <= limits.caps_s[profile] <= 3.2 * limits.expected_s[profile]


# --- A6: one run at a time per machine (C10, SB19) --------------------------------------------


def test_a_second_run_is_refused_while_one_is_active(store, project) -> None:
    m = manager(store, "sleep")
    first = m.start(project, 1, "quick")
    with pytest.raises(RunActive) as info:
        m.start(project, 1, "quick")
    assert info.value.run.id == first.id
    # Another process on the same state.db (for example `truelift run`) is refused too.
    other = StateDb(store.db.path)
    try:
        assert other.active_runs()[0].id == first.id
        from dataclasses import replace

        assert other.insert_run_if_idle(replace(first, id="run-other0001")) is not None
    finally:
        other.dispose()
    m.cancel(first.id)
    assert len(store.db.runs_for(project)) == 1


# --- A7: status, elapsed time and log tail, reattached after a refresh ------------------------


def test_status_shows_phase_elapsed_time_and_log_tail(store, project) -> None:
    m = manager(store, "sleep")
    row = m.start(project, 1, "quick")
    try:
        wait_for_phase(m, row.id, phases.NUISANCE)
        # A new manager over the same store (a refreshed page reads the row and the folder).
        fresh = manager(store, "sleep")
        current = fresh.get(row.id)
        assert current is not None and current.status == "running"
        view = fresh.view(current)
        assert view.phase == phases.NUISANCE
        assert view.phases == phases.phases_for(Profile.quick)
        assert view.elapsed_s >= 0 and view.expected_s == 125.0
        assert any("Phase 1" in line for line in view.log_tail)
        wait_for(lambda: m.view(m.get(row.id)).elapsed_s >= 1.0, timeout=10)
    finally:
        m.cancel(row.id)


# --- A8: startup reconciliation ------------------------------------------------------------------


def test_restart_interrupts_a_run_whose_watcher_is_gone(store, project) -> None:
    """The backend that watched the run is gone; its worker is still alive. The next startup
    stops the worker and marks the run interrupted (phase 1 does not re-adopt)."""
    old = manager(store, "sleep")
    row = old.start(project, 1, "quick")
    wait_for_phase(old, row.id, phases.NUISANCE)
    old._handles.clear()  # the old backend's memory is lost

    restarted = manager(store, "sleep")
    assert restarted.reconcile() == [row.id]
    final = store.db.run(row.id)
    assert final is not None and final.status == "interrupted"
    assert final.reason == "This run was interrupted. Run it again (about 2 min)."
    wait_for(lambda: not pid_alive(row.pid or final.pid), timeout=10)


def test_restart_interrupts_queued_and_dead_runs(store, project) -> None:
    m = manager(store, "ok")
    queued = m.prepare(project, 1, "quick")  # never launched: the backend died before spawning
    assert manager(store).reconcile() == [queued.id]
    assert store.db.run(queued.id).status == "interrupted"


def test_restart_leaves_a_run_another_live_process_watches(store, project) -> None:
    import subprocess
    import sys

    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        m = manager(store, "ok")
        row = m.prepare(project, 1, "quick")
        store.db.update_run(row.id, owner_pid=owner.pid)
        assert manager(store).reconcile() == []
        assert store.db.run(row.id).status == "queued"
    finally:
        owner.kill()
        owner.wait()


def test_a_database_write_failure_is_reconciled_at_startup(store, project, monkeypatch) -> None:
    m = manager(store, "ok")
    real_update = store.db.update_run

    def failing(run_id, **values):
        if values.get("status") in {"succeeded", "failed", "cancelled"}:
            raise OperationalError("UPDATE runs", {}, Exception("database is locked"))
        return real_update(run_id, **values)

    monkeypatch.setattr(store.db, "update_run", failing)
    row = m.start(project, 1, "quick")
    m.wait(row.id, timeout=60)
    assert store.db.run(row.id).status == "running"  # the end could not be recorded
    monkeypatch.setattr(store.db, "update_run", real_update)

    assert manager(store).reconcile() == [row.id]
    assert store.db.run(row.id).status == "interrupted"


def test_shutdown_stops_workers_and_marks_runs_interrupted(store, project) -> None:
    m = manager(store, "sleep")
    row = m.start(project, 1, "quick")
    wait_for_phase(m, row.id, phases.NUISANCE)
    m.shutdown()
    final = store.db.run(row.id)
    assert final is not None and final.status == "interrupted"
    assert not pid_alive(final.pid)


# --- A9: cancel ---------------------------------------------------------------------------------


def test_cancel_kills_the_process_group_and_is_idempotent(store, project) -> None:
    m = manager(store, "sleep")
    row = m.start(project, 1, "quick")
    folder = _folder(store, project, row.id)
    child_pid = int(
        wait_for(lambda: (folder.work / "child.pid").is_file() and (folder.work / "child.pid").read_text())
    )
    assert pid_alive(child_pid)

    cancelled = m.cancel(row.id)
    assert cancelled is not None and cancelled.status == "cancelled" and cancelled.reason == CANCELLED
    assert not pid_alive(cancelled.pid)
    wait_for(lambda: not pid_alive(child_pid), timeout=10)  # the whole group, not only the leader
    assert not folder.manifest.exists() and not m.succeeded(cancelled)

    again = m.cancel(row.id)
    assert again == store.db.run(row.id) and again.status == "cancelled"
    assert again.finished_at == cancelled.finished_at


def test_cancelling_a_finished_run_changes_nothing(store, project) -> None:
    m = manager(store, "ok")
    row = m.start(project, 1, "quick")
    done = m.wait(row.id, timeout=60)
    assert done is not None and done.status == "succeeded"
    assert m.cancel(row.id) == done
