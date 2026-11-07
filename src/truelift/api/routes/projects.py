"""Projects and proposals, served by the project store (G08, C11, D1).

Agents only propose; these routes are where the user decides. Accepting applies a proposal to
the knowledge files, rejecting changes no knowledge file, a stale ``knowledge_version`` is a 409
and a contradiction needs its own explicit decision. A batch accept is all-or-nothing.

The demo project (``petfood-de``) still comes from the G02 fakes, because the routes for its
data, DAG and runs are stubs until G07, G09–G11, G14 and G31 land. Its ID is reserved, so no
real project can take it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import DEMO_PROJECT, FakeStore
from truelift.api.routes import Fakes
from truelift.api.schemas import (
    Decision,
    Project,
    ProjectCreate,
    ProjectId,
    ProjectSummary,
    Proposal,
    ProposalBatchIn,
    ProposalDecisionIn,
    ProposalKind,
    ProposalStatus,
    Stage,
    TurnQuote,
)
from truelift.store import ProjectInfo, ProjectStore, ProposalView, Source, SourceKind
from truelift.store import ProposalStatus as StoreProposalStatus

router = APIRouter(prefix="/projects", tags=["projects"])


def get_store(request: Request) -> ProjectStore:
    return request.app.state.store


Store = Annotated[ProjectStore, Depends(get_store)]
ProjectPath = Annotated[ProjectId, Path()]
ProposalPath = Annotated[str, Path(pattern=r"^P[0-9]{1,6}$")]


def _project(info: ProjectInfo) -> Project:
    return Project(
        id=info.id,
        name=info.name,
        stage=Stage(info.stage),
        updated_at=info.updated_at,
        data_version=None,  # G07 adds data versions
        mapping_version=info.mapping_version,
        dag_version=info.dag_version,
        knowledge_version=info.knowledge_version,
    )


def _quote(source: Source | None) -> TurnQuote | None:
    if source is None or source.kind is not SourceKind.interview:
        return None
    return TurnQuote(turn=source.turn or 0, text=source.quote or "")


def _proposal(view: ProposalView) -> Proposal:
    p = view.proposal
    return Proposal(
        id=p.id,
        kind=ProposalKind.fact,
        status=ProposalStatus(p.status.value),
        file=p.file,
        fact_id=p.fact_id,
        summary=p.summary,
        new_text=p.text,
        source=_quote(p.source.to_source()),
        contradiction=view.contradiction,
        contradicts=_quote(view.contradicts),
    )


@router.get("")
def list_projects(store: Store, fakes: Fakes) -> list[ProjectSummary]:
    demo = fakes.project()
    return [
        ProjectSummary(**demo.model_dump()),
        *(ProjectSummary(**_project(info).model_dump()) for info in store.list()),
    ]


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(409))
def create_project(body: ProjectCreate, store: Store) -> Project:
    """Lay out the project folder (knowledge files, ``dag/``, ``mapping/``, ``proposals/``,
    ``runs/``) and add it to the index."""
    return _project(store.create(body.name))


@router.get("/{project_id}", responses=error_responses(404))
def get_project(project_id: ProjectPath, store: Store, fakes: Fakes) -> Project:
    if project_id == DEMO_PROJECT:
        return fakes.project()
    return _project(store.get(project_id))


@router.get("/{project_id}/proposals", responses=error_responses(404))
def list_proposals(
    project_id: ProjectPath,
    store: Store,
    fakes: Fakes,
    status: Annotated[ProposalStatus | None, Query()] = None,
) -> list[Proposal]:
    if project_id == DEMO_PROJECT:
        return [p for p in fakes.proposals.values() if status is None or p.status == status]
    wanted = StoreProposalStatus(status.value) if status else None
    return [_proposal(v) for v in store.proposals(project_id, wanted)]


@router.post("/{project_id}/proposals/accept", responses=error_responses(404, 409))
def accept_proposals(
    project_id: ProjectPath, body: ProposalBatchIn, store: Store, fakes: Fakes
) -> list[Proposal]:
    """Accept several proposals: all are applied or none. A contradiction refuses the batch
    (409 ``contradiction_in_batch``); decide it on its own."""
    if project_id == DEMO_PROJECT:
        return _fake_batch(fakes, body)
    decided = store.accept_batch(project_id, body.proposal_ids, knowledge_version=body.knowledge_version)
    ids = {p.id for p in decided}
    views = {v.proposal.id: v for v in store.proposals(project_id) if v.proposal.id in ids}
    return [_proposal(views[p.id]) for p in decided]


@router.post("/{project_id}/proposals/{proposal_id}/decision", responses=error_responses(404, 409))
def decide_proposal(
    project_id: ProjectPath,
    proposal_id: ProposalPath,
    body: ProposalDecisionIn,
    store: Store,
    fakes: Fakes,
) -> Proposal:
    if project_id == DEMO_PROJECT:
        return _fake_decide(fakes, proposal_id, body)
    store.decide(
        project_id,
        proposal_id,
        accept=body.decision is Decision.accept,
        knowledge_version=body.knowledge_version,
        resolves_contradiction=body.resolves_contradiction,
    )
    return _proposal(store.proposal(project_id, proposal_id))


# --- the demo project's fakes (G02), until its other routes move to the store ----------------

_STALE = "Your knowledge files changed. Reload and decide again."


def _fake_decide(fakes: FakeStore, proposal_id: str, body: ProposalDecisionIn) -> Proposal:
    proposal = fakes.proposals.get(proposal_id)
    if proposal is None:
        raise ApiError(404, "proposal_not_found", "No proposal with this ID.")
    if body.knowledge_version != fakes.knowledge_version:
        raise ApiError(409, "stale_version", _STALE)
    if proposal.status is not ProposalStatus.pending:
        raise ApiError(409, "already_decided", "This proposal was already decided.")
    accept = body.decision is Decision.accept
    if accept and proposal.contradiction and not body.resolves_contradiction:
        raise ApiError(
            409, "contradiction_choice_needed", "This conflicts with a confirmed fact. Choose which to keep."
        )
    proposal = proposal.model_copy(
        update={"status": ProposalStatus.accepted if accept else ProposalStatus.rejected}
    )
    fakes.proposals[proposal_id] = proposal
    if accept:
        fakes.knowledge_version += 1
    return proposal


def _fake_batch(fakes: FakeStore, body: ProposalBatchIn) -> list[Proposal]:
    if body.knowledge_version != fakes.knowledge_version:
        raise ApiError(409, "stale_version", _STALE)
    found = [fakes.proposals.get(i) for i in body.proposal_ids]
    if any(p is None for p in found):
        raise ApiError(404, "proposal_not_found", "No proposal with this ID.")
    chosen = [p for p in found if p is not None]
    if any(p.status is not ProposalStatus.pending for p in chosen):
        raise ApiError(409, "already_decided", "This proposal was already decided.")
    if any(p.contradiction for p in chosen):
        raise ApiError(409, "contradiction_in_batch", "Decide each conflicting proposal on its own.")
    accepted = [p.model_copy(update={"status": ProposalStatus.accepted}) for p in chosen]
    fakes.proposals.update({p.id: p for p in accepted})
    fakes.knowledge_version += 1
    return accepted
