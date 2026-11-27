"""DAG versions, edge opinions, confirmation and identification (G31; C1, C3, C11; D5, D6).

Real projects are served by the project store and the causal core:

* ``POST /build`` turns the confirmed facts and a business-type template into a new DAG version
  (``truelift.causal.build``). Building again from unchanged facts writes no new version.
* ``GET`` returns the current version, each edge with its supporting facts or ``assumed``.
* ``PUT /edges/{edge_id}/opinion`` records Agree, Disagree or Not sure beside the version; it
  never changes the version itself (D6: changes go through proposals).
* ``POST /confirm`` confirms the current version once every edge has an opinion and none is
  Disagree. The store records the content hash and the cited facts (C1).
* ``GET /identification`` runs ``truelift.causal.identify`` on the current version and the
  confirmed column mapping. Block reasons are business sentences from ``rules/``.

The current mapping version's content is ``{columns: [...], panel: {...}}``: the column roles
(``ColumnMapping``) and the panel summary (``PanelSummary``) that G07 writes. The demo project
(``petfood-de``) still answers from the G02 fakes.
"""

from __future__ import annotations

import functools
import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from pydantic import ValidationError

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import DEMO_PROJECT, FakeStore, identification
from truelift.api.routes import Fakes
from truelift.api.schemas import (
    DagBuildIn,
    DagEdge,
    DagNode,
    DagStatus,
    DagVersion,
    EdgeBasis,
    Identification,
    IdentificationBlock,
    NodeRole,
    Opinion,
    OpinionIn,
    ProjectId,
    Remedy,
    VersionIn,
)
from truelift.causal.build import BuildError, DagDraft, build_dag
from truelift.causal.identify import IdentifyInputError, identify
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.causal.rules import RuleSet, load_rules
from truelift.store import ProjectStore, VersionKind
from truelift.store.versions import VersionRecord

router = APIRouter(prefix="/projects/{project_id}/dag", tags=["dag"])

ProjectPath = Annotated[ProjectId, Path()]
EdgeIdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
_STALE = "The DAG changed since you opened it. Reload and review again."


def get_store(request: Request) -> ProjectStore:
    return request.app.state.store


Store = Annotated[ProjectStore, Depends(get_store)]


@functools.cache
def _rules() -> RuleSet:
    return load_rules()


def edge_id(source: str, target: str) -> str:
    """A stable ID for the arrow ``source -> target``, the same in every version."""
    return "e-" + hashlib.sha256(f"{source}->{target}".encode()).hexdigest()[:12]


# --- routes -------------------------------------------------------------------------------


@router.get("", responses=error_responses(404, 422))
def get_dag(project_id: ProjectPath, store: Store, fakes: Fakes) -> DagVersion:
    if project_id == DEMO_PROJECT:
        return fakes.dag
    return _view(store, project_id, _current(store, project_id))


@router.post("/build", responses=error_responses(404, 409, 422))
def build(project_id: ProjectPath, body: DagBuildIn, store: Store, fakes: Fakes) -> DagVersion:
    """Build the diagram from the confirmed facts and the business-type template. Unconfirmed
    facts and rejected proposals never reach it. Unchanged facts give the same version back."""
    if project_id == DEMO_PROJECT:
        return fakes.dag
    current = store.read_version(project_id, VersionKind.dag)
    if (current.version if current else None) != body.dag_version:
        raise ApiError(409, "stale_version", _STALE)
    rules = _rules()
    template_id = body.template or (_draft(current).template if current else None)
    if template_id is None:
        raise ApiError(422, "template_needed", "Choose your type of business first.")
    template = rules.templates.get(template_id)
    if template is None:
        raise ApiError(422, "unknown_template", "We have no diagram for this type of business.")
    knowledge = store.knowledge(project_id)
    knowledge.require_valid()
    mapping, _, mapping_record = _mapping(store, project_id)
    vocabulary = {n.id: n.label for t in rules.templates.values() for n in t.nodes}
    try:
        built = build_dag(template, knowledge.facts.values(), mapping, vocabulary=vocabulary)
    except BuildError as exc:
        raise ApiError(409, "dag_build_failed", str(exc)) from exc
    content = built.draft.to_content()
    if current is not None and current.content == content and list(current.cites) == sorted(built.cites):
        return _view(store, project_id, current)
    version = store.write_version(
        project_id,
        VersionKind.dag,
        content,
        expected_current=body.dag_version,
        cites=built.cites,
        data_fingerprint=mapping_record.data_fingerprint,
    )
    record = store.read_version(project_id, VersionKind.dag, version)
    assert record is not None
    return _view(store, project_id, record)


@router.put("/edges/{edge_id}/opinion", responses=error_responses(404, 409, 422))
def put_edge_opinion(
    project_id: ProjectPath, edge_id: EdgeIdPath, body: OpinionIn, store: Store, fakes: Fakes
) -> DagEdge:
    if project_id == DEMO_PROJECT:
        return _fake_opinion(fakes, edge_id, body)
    record = _current(store, project_id)
    if body.dag_version != record.version:
        raise ApiError(409, "stale_version", _STALE)
    edges = {e.id: e for e in _view(store, project_id, record).edges}
    if edge_id not in edges:
        raise ApiError(404, "edge_not_found", "No edge with this ID.")
    store.set_opinion(project_id, VersionKind.dag, record.version, edge_id, body.opinion.value)
    return edges[edge_id].model_copy(update={"opinion": body.opinion})


@router.post("/confirm", responses=error_responses(404, 409, 422))
def confirm_dag(project_id: ProjectPath, body: VersionIn, store: Store, fakes: Fakes) -> DagVersion:
    if project_id == DEMO_PROJECT:
        return _fake_confirm(fakes, body)
    record = _current(store, project_id)
    if body.version != record.version:
        raise ApiError(409, "stale_version", _STALE)
    view = _view(store, project_id, record)
    if any(e.opinion is None for e in view.edges):
        raise ApiError(422, "edges_unreviewed", "Answer every edge card before confirming.")
    disputed = [e for e in view.edges if e.opinion is Opinion.disagree]
    if disputed:
        raise ApiError(
            409,
            "edges_disputed",
            f"You disagreed with {len(disputed)} arrow{'s' if len(disputed) > 1 else ''}. Tell the assistant "
            "what is different; it proposes a change, and you review the new version.",
        )
    store.confirm_version(project_id, VersionKind.dag, record.version)
    return _view(store, project_id, record)


@router.get("/identification", responses=error_responses(404, 409, 422))
def get_identification(project_id: ProjectPath, store: Store, fakes: Fakes) -> Identification:
    if project_id == DEMO_PROJECT:
        return identification(fakes.dag)
    record = _current(store, project_id)
    dag = _draft(record).dag
    mapping, panel, _ = _mapping(store, project_id)
    if panel is None:
        raise ApiError(
            409, "profile_needed", "Upload your data again so we can check it before the analysis."
        )
    try:
        result = identify(dag, mapping, panel, _rules())
    except IdentifyInputError as exc:
        raise ApiError(
            409, "mapping_mismatch", "The diagram and your column roles do not fit together."
        ) from exc
    return Identification(
        dag_version=record.version,
        identified=result.identified,
        adjustment_set=result.adjustment_set,
        blocks=[
            IdentificationBlock(
                code=b.code, message=b.message, node_ids=b.node_ids, remedies=[Remedy(r) for r in b.remedies]
            )
            for b in result.blocks
        ],
    )


# --- helpers ------------------------------------------------------------------------------


def _current(store: ProjectStore, project_id: str) -> VersionRecord:
    record = store.read_version(project_id, VersionKind.dag)
    if record is None:
        raise ApiError(404, "dag_not_found", "There is no diagram yet. Finish the interview, then build it.")
    return record


def _draft(record: VersionRecord) -> DagDraft:
    try:
        return DagDraft.from_content(record.content)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            422, "dag_invalid", f"Diagram version {record.version} is not valid. Build it again."
        ) from exc


def _mapping(
    store: ProjectStore, project_id: str
) -> tuple[ColumnMapping, PanelSummary | None, VersionRecord]:
    record = store.read_version(project_id, VersionKind.mapping)
    if record is None:
        raise ApiError(409, "mapping_needed", "Confirm your column roles first.")
    content: dict[str, Any] = record.content
    try:
        mapping = ColumnMapping.model_validate({"columns": content.get("columns")})
        panel = PanelSummary.model_validate(content["panel"]) if content.get("panel") else None
    except ValidationError as exc:
        raise ApiError(422, "mapping_invalid", "Your column roles are not valid. Review them again.") from exc
    return mapping, panel, record


def _view(store: ProjectStore, project_id: str, record: VersionRecord) -> DagVersion:
    draft = _draft(record)
    status = store.version_status(project_id, VersionKind.dag, record.version)
    opinions = store.opinions(project_id, VersionKind.dag, record.version)
    nodes = [
        DagNode(id=n.id, label=n.label or n.id, role=NodeRole(n.role or "predictor"), column=n.column)
        for n in draft.dag.nodes
    ]
    edges = []
    for e in draft.edges:
        eid = edge_id(e.from_, e.to)
        opinion = opinions.get(eid)
        edges.append(
            DagEdge(
                id=eid,
                source=e.from_,
                target=e.to,
                sentence=e.sentence,
                basis=EdgeBasis(e.basis),
                fact_ids=e.facts,
                opinion=Opinion(opinion) if opinion in Opinion.__members__ else None,
            )
        )
    return DagVersion(
        version=record.version,
        status=DagStatus(status.value),
        template=draft.template,
        nodes=nodes,
        edges=edges,
    )


# --- the demo project's fakes (G02) --------------------------------------------------------


def _fake_opinion(fakes: FakeStore, eid: str, body: OpinionIn) -> DagEdge:
    if body.dag_version != fakes.dag.version:
        raise ApiError(409, "stale_version", _STALE)
    edges = {e.id: e for e in fakes.dag.edges}
    if eid not in edges:
        raise ApiError(404, "edge_not_found", "No edge with this ID.")
    edge = edges[eid].model_copy(update={"opinion": body.opinion})
    edges[eid] = edge
    fakes.dag = fakes.dag.model_copy(update={"edges": list(edges.values()), "status": DagStatus.draft})
    return edge


def _fake_confirm(fakes: FakeStore, body: VersionIn) -> DagVersion:
    if body.version != fakes.dag.version:
        raise ApiError(409, "stale_version", _STALE)
    if any(e.opinion is None for e in fakes.dag.edges):
        raise ApiError(422, "edges_unreviewed", "Answer every edge card before confirming.")
    fakes.dag = fakes.dag.model_copy(update={"status": DagStatus.confirmed})
    return fakes.dag
