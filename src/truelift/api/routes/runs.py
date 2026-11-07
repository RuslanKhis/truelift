"""Start, poll, list and cancel runs. Stub (G02); G09 replaces it with the run gate and worker (C1, C10).

Fake runs advance by wall clock through the phases and then succeed. ``run-demo01`` has succeeded
and ``run-demo02`` was interrupted, so the run and results screens can show both.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, status

from truelift.api.errors import ApiError, error_responses
from truelift.api.routes import DemoProject, Fakes
from truelift.api.schemas import Run, RunCreate, RunId, RunStatus

router = APIRouter(tags=["runs"])

RunIdPath = Annotated[RunId, Path()]


@router.post(
    "/projects/{project_id}/runs",
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(404, 409),
)
def start_run(project_id: DemoProject, body: RunCreate, fakes: Fakes) -> Run:
    if body.dag_version != fakes.dag.version:
        raise ApiError(409, "stale_version", "The DAG changed since you opened it. Reload and review again.")
    if fakes.active_run() is not None:
        raise ApiError(409, "run_active", "Another run is in progress. Wait for it or cancel it.")
    return fakes.new_run(body.profile)


@router.get("/projects/{project_id}/runs", responses=error_responses(404))
def list_runs(project_id: DemoProject, fakes: Fakes) -> list[Run]:
    runs = [fakes.current(run_id) for run_id in list(fakes.runs)]
    return sorted((r for r in runs if r), key=lambda r: r.created_at, reverse=True)


@router.get("/runs/{run_id}", responses=error_responses(404))
def get_run(run_id: RunIdPath, fakes: Fakes) -> Run:
    run = fakes.current(run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    return run


@router.post("/runs/{run_id}/cancel", responses=error_responses(404))
def cancel_run(run_id: RunIdPath, fakes: Fakes) -> Run:
    run = fakes.current(run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    if run.status in {RunStatus.queued, RunStatus.running}:
        run = run.model_copy(update={"status": RunStatus.cancelled, "reason": "You cancelled this run."})
        fakes.runs[run_id].run = run
    return run  # cancelling a finished or cancelled run changes nothing (idempotent)
