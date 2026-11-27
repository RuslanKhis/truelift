"""Results of a succeeded run: the run's digest (G31; C5, C6, C10).

A real run's results are ``runs/<run_id>/digest.json`` in its project folder, in the ``Results``
shape. They are served only when the run's ``manifest.json`` lists ``digest.json`` with the
sha256 of the file on disk (C10: the worker writes the manifest last, by atomic rename, and only
after a run succeeds). With no manifest, or a hash that does not match, there are no results,
never a partial answer. G09 writes the run folder and adds its status from the runs table; G10
builds the digest and G14 its narrative.

Manifest format: ``{"files": {"digest.json": "<sha256 hex>", ...}}``.

The demo project's runs (``run-demo…``) still come from the G02 fakes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import results
from truelift.api.routes import Fakes
from truelift.api.routes.runs import RunIdPath
from truelift.api.schemas import Results, RunStatus
from truelift.store import ProjectStore

router = APIRouter(tags=["results"])

_NO_RESULTS = "This run has no results. Only finished runs show numbers."


def get_store(request: Request) -> ProjectStore:
    return request.app.state.store


Store = Annotated[ProjectStore, Depends(get_store)]


@router.get("/runs/{run_id}/results", responses=error_responses(404, 409))
def get_results(run_id: RunIdPath, store: Store, fakes: Fakes) -> Results:
    run = fakes.current(run_id)
    if run is not None:
        if run.status is not RunStatus.succeeded:
            # C10: no partial results, ever.
            raise ApiError(409, "run_not_succeeded", _NO_RESULTS)
        return results(run_id)

    found = store.run_dir(run_id)
    if found is None:
        raise ApiError(404, "run_not_found", "No run with this ID.")
    _, folder = found
    try:
        manifest = json.loads((folder / "manifest.json").read_bytes())
        expected = manifest["files"]["digest.json"]
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        raise ApiError(409, "run_not_succeeded", _NO_RESULTS) from None
    try:
        raw = (folder / "digest.json").read_bytes()
    except FileNotFoundError:
        raise ApiError(409, "run_not_succeeded", _NO_RESULTS) from None
    if not isinstance(expected, str) or hashlib.sha256(raw).hexdigest() != expected:
        raise ApiError(409, "run_not_succeeded", _NO_RESULTS)
    try:
        digest = Results.model_validate_json(raw)
    except ValidationError:
        raise ApiError(409, "run_not_succeeded", _NO_RESULTS) from None
    if digest.run_id != run_id:
        raise ApiError(409, "run_not_succeeded", _NO_RESULTS)
    return digest
