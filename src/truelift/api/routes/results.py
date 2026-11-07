"""Results of a succeeded run. Stub (G02); G31 serves the digest, G10 and G14 fill it (C5, C6, C10)."""

from __future__ import annotations

from fastapi import APIRouter

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import results
from truelift.api.routes import Fakes
from truelift.api.routes.runs import RunIdPath
from truelift.api.schemas import Results, RunStatus

router = APIRouter(tags=["results"])


@router.get("/runs/{run_id}/results", responses=error_responses(404, 409))
def get_results(run_id: RunIdPath, fakes: Fakes) -> Results:
    run = fakes.current(run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    if run.status is not RunStatus.succeeded:
        # C10: no partial results, ever.
        raise ApiError(409, "run_not_succeeded", "This run has no results. Only finished runs show numbers.")
    return results(run_id)
