"""Results of a succeeded run: the run's digest (G31, G09; C5, C6, C10).

Results are served only when all of these hold (C10):

* the run's row in ``state.db`` says ``succeeded`` (G09), which the app records only after the
  worker exited cleanly with a manifest whose every hash matched;
* ``runs/<run_id>/manifest.json`` still verifies: it lists every expected output, and each listed
  file is on disk with its recorded sha256;
* the manifest lists ``digest.json`` (in the ``Results`` shape) and its hash matches.

A run that failed, was interrupted or cancelled, or whose outputs have no manifest, has no
results, never a partial answer. G10 builds ``digest.json`` and adds it to the manifest; G14
adds its narrative.

The demo project's runs (``run-demo…``) still come from the G02 fakes.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter
from pydantic import ValidationError

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import results
from truelift.api.routes import Fakes
from truelift.api.routes.runs import RunIdPath, Runs
from truelift.api.schemas import Results, RunStatus

router = APIRouter(tags=["results"])

_NO_RESULTS = "This run has no results. Only finished runs show numbers."
DIGEST = "digest.json"


def _no_results() -> ApiError:
    return ApiError(409, "run_not_succeeded", _NO_RESULTS)


@router.get("/runs/{run_id}/results", responses=error_responses(404, 409))
def get_results(run_id: RunIdPath, runs: Runs, fakes: Fakes) -> Results:
    run = fakes.current(run_id)
    if run is not None:
        if run.status is not RunStatus.succeeded:
            # C10: no partial results, ever.
            raise _no_results()
        return results(run_id)

    row = runs.get(run_id)
    if row is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    if not runs.succeeded(row):  # status and the whole manifest (C10)
        raise _no_results()
    folder = runs.folder(row)
    try:
        expected = json.loads(folder.manifest.read_bytes())["files"][DIGEST]
        raw = (folder.root / DIGEST).read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        raise _no_results() from None
    if not isinstance(expected, str) or hashlib.sha256(raw).hexdigest() != expected:
        raise _no_results()
    try:
        digest = Results.model_validate_json(raw)
    except ValidationError:
        raise _no_results() from None
    if digest.run_id != run_id:
        raise _no_results()
    return digest
