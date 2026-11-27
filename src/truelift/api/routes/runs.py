"""Start, poll, list and cancel runs (G09; C1, C10, SB19; D8).

Real projects go through ``truelift.worker``:

* ``POST /projects/{id}/runs`` runs the gate (C1). A refusal is a 409 with the plain reason, for
  example "Your DAG changed after you confirmed it…". A second run while one is queued or running
  on this machine is a 409 ``run_active`` (SB19). Otherwise the worker is spawned and the run is
  returned ``running``.
* ``GET /runs/{id}`` returns the status, phase, elapsed time and log tail, so a page refresh
  reattaches (A7).
* ``POST /runs/{id}/cancel`` kills the worker's process group and returns ``cancelled``; a run
  that has ended is returned as it is (A9).

The demo project (``petfood-de``) and its runs (``run-demo…``) still come from the G02 fakes:
fake runs advance by wall clock through the phases and then succeed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import DEMO_PROJECT
from truelift.api.routes import Fakes
from truelift.api.schemas import ProjectId, Run, RunCreate, RunId, RunProfile, RunStatus
from truelift.store import ProjectStore
from truelift.worker.gate import GateRefused
from truelift.worker.manager import RunActive, RunManager

router = APIRouter(tags=["runs"])

RunIdPath = Annotated[RunId, Path()]
ProjectPath = Annotated[ProjectId, Path()]
_RUN_ACTIVE = "Another run is in progress. Wait for it or cancel it."


def get_runs(request: Request) -> RunManager:
    return request.app.state.runs


def get_store(request: Request) -> ProjectStore:
    return request.app.state.store


Runs = Annotated[RunManager, Depends(get_runs)]
Store = Annotated[ProjectStore, Depends(get_store)]


def to_run(manager: RunManager, run_id: str) -> Run | None:
    row = manager.get(run_id)
    if row is None:
        return None
    view = manager.view(row)
    return Run(
        id=row.id,
        project_id=row.project_id,
        status=RunStatus(row.status),
        profile=RunProfile(row.profile),
        phase=view.phase,
        phases=view.phases,
        elapsed_s=view.elapsed_s,
        expected_s=view.expected_s,
        log_tail=view.log_tail,
        reason=row.reason,
        created_at=row.created_at,
    )


@router.post(
    "/projects/{project_id}/runs",
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(404, 409),
)
def start_run(project_id: ProjectPath, body: RunCreate, fakes: Fakes, runs: Runs, store: Store) -> Run:
    if project_id == DEMO_PROJECT:
        if body.dag_version != fakes.dag.version:
            raise ApiError(
                409, "stale_version", "The DAG changed since you opened it. Reload and review again."
            )
        if fakes.active_run() is not None:
            raise ApiError(409, "run_active", _RUN_ACTIVE)
        return fakes.new_run(body.profile)
    store.get(project_id)  # 404 for an unknown project
    try:
        row = runs.start(project_id, body.dag_version, body.profile.value)
    except GateRefused as exc:
        raise ApiError(409, exc.code, exc.message) from exc
    except RunActive as exc:
        raise ApiError(409, "run_active", _RUN_ACTIVE) from exc
    run = to_run(runs, row.id)
    assert run is not None
    return run


@router.get("/projects/{project_id}/runs", responses=error_responses(404))
def list_runs(project_id: ProjectPath, fakes: Fakes, runs: Runs, store: Store) -> list[Run]:
    if project_id == DEMO_PROJECT:
        fake = [fakes.current(run_id) for run_id in list(fakes.runs)]
        return sorted((r for r in fake if r), key=lambda r: r.created_at, reverse=True)
    store.get(project_id)
    return [run for row in runs.list(project_id) if (run := to_run(runs, row.id)) is not None]


@router.get("/runs/{run_id}", responses=error_responses(404))
def get_run(run_id: RunIdPath, fakes: Fakes, runs: Runs) -> Run:
    run = fakes.current(run_id) or to_run(runs, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    return run


@router.post("/runs/{run_id}/cancel", responses=error_responses(404))
def cancel_run(run_id: RunIdPath, fakes: Fakes, runs: Runs) -> Run:
    run = fakes.current(run_id)
    if run is not None:
        if run.status in {RunStatus.queued, RunStatus.running}:
            run = run.model_copy(update={"status": RunStatus.cancelled, "reason": "You cancelled this run."})
            fakes.runs[run_id].run = run
        return run  # cancelling a finished or cancelled run changes nothing (idempotent)
    if runs.cancel(run_id) is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    real = to_run(runs, run_id)
    assert real is not None
    return real
