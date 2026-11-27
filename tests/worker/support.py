"""Helpers for the worker tests (G09). Everything runs in ``tmp_path``; nothing touches the user's
home folder."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

from truelift.causal.compile import Profile
from truelift.store import ProjectStore
from truelift.store.db import RunRow
from truelift.worker.layout import RunFolder, expected_outputs, write_json
from truelift.worker.manager import Limits, RunManager

FAKE_WORKER = Path(__file__).resolve().parent / "fake_worker.py"

FAST = Limits(kill_grace_s=2.0)


def fake_command(mode: str) -> Callable[[str, Path], list[str]]:
    def command(run_id: str, run_dir: Path) -> list[str]:
        return [sys.executable, str(FAKE_WORKER), mode, run_id, "--run-dir", str(run_dir)]

    return command


def manager(store: ProjectStore, mode: str = "ok", limits: Limits = FAST) -> RunManager:
    return RunManager(store, limits=limits, command=fake_command(mode))


def wait_for(predicate: Callable[[], object], timeout: float = 30.0, every: float = 0.1) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(every)
    raise AssertionError("condition not met in time")


def wait_for_phase(m: RunManager, run_id: str, phase: str, timeout: float = 30.0) -> None:
    def reached() -> bool:
        row = m.get(run_id)
        return row is not None and m.view(row).phase == phase

    wait_for(reached, timeout)


def finished_run(
    store: ProjectStore, project_id: str, run_id: str, *, digest: bytes | None = None
) -> RunFolder:
    """A run folder as a succeeded run leaves it (expected outputs, manifest last) and its row.

    ``digest`` is written as ``digest.json`` before the manifest, so the manifest lists it, as
    G10 will once it builds the digest."""
    from datetime import UTC, datetime

    folder = RunFolder(store.projects_dir / project_id / "runs" / run_id)
    folder.work.mkdir(parents=True)
    write_json(folder.config, {"orchestrator": {"run_sensitivity": False}})
    write_json(folder.run, {"run_id": run_id})
    write_json(folder.env, {"schema": "truelift.env/1"})
    for rel in expected_outputs(False):
        (folder.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder.root / rel).write_text("x\n")
    if digest is not None:
        (folder.root / "digest.json").write_bytes(digest)
    folder.write_manifest(run_id, expected_outputs(False))
    now = datetime.now(UTC)
    row = RunRow(
        id=run_id,
        project_id=project_id,
        dag_version=1,
        profile=Profile.quick.value,
        status="succeeded",
        reason=None,
        pid=None,
        owner_pid=None,
        cancel_requested=False,
        config_sha256="0" * 64,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    assert store.db.insert_run_if_idle(row) is None
    return folder
