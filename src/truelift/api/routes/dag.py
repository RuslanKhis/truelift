"""DAG versions, edge opinions, confirmation and identification. Stub (G02); G31 replaces it (C1, C3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import identification
from truelift.api.routes import DemoProject, Fakes
from truelift.api.schemas import DagEdge, DagStatus, DagVersion, Identification, OpinionIn, VersionIn

router = APIRouter(prefix="/projects/{project_id}/dag", tags=["dag"])

_STALE = "The DAG changed since you opened it. Reload and review again."


@router.get("", responses=error_responses(404))
def get_dag(project_id: DemoProject, fakes: Fakes) -> DagVersion:
    return fakes.dag


@router.put("/edges/{edge_id}/opinion", responses=error_responses(404, 409))
def put_edge_opinion(
    project_id: DemoProject,
    edge_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
    body: OpinionIn,
    fakes: Fakes,
) -> DagEdge:
    if body.dag_version != fakes.dag.version:
        raise ApiError(409, "stale_version", _STALE)
    edges = {e.id: e for e in fakes.dag.edges}
    if edge_id not in edges:
        raise ApiError(404, "edge_not_found", "No edge with this ID.")
    edge = edges[edge_id].model_copy(update={"opinion": body.opinion})
    edges[edge_id] = edge
    fakes.dag = fakes.dag.model_copy(update={"edges": list(edges.values()), "status": DagStatus.draft})
    return edge


@router.post("/confirm", responses=error_responses(404, 409))
def confirm_dag(project_id: DemoProject, body: VersionIn, fakes: Fakes) -> DagVersion:
    if body.version != fakes.dag.version:
        raise ApiError(409, "stale_version", _STALE)
    if any(e.opinion is None for e in fakes.dag.edges):
        raise ApiError(422, "edges_unreviewed", "Answer every edge card before confirming.")
    fakes.dag = fakes.dag.model_copy(update={"status": DagStatus.confirmed})
    return fakes.dag


@router.get("/identification", responses=error_responses(404))
def get_identification(project_id: DemoProject, fakes: Fakes) -> Identification:
    return identification(fakes.dag)
