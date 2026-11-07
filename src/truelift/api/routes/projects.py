"""Projects and proposals. Stub (G02); G08 replaces it with the project store (C11)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from truelift.api.errors import ApiError, error_responses
from truelift.api.routes import DemoProject, Fakes
from truelift.api.schemas import (
    Decision,
    Project,
    ProjectCreate,
    ProjectSummary,
    Proposal,
    ProposalDecisionIn,
    ProposalStatus,
    Stage,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(fakes: Fakes) -> list[ProjectSummary]:
    demo = fakes.project()
    return [
        ProjectSummary(**demo.model_dump()),
        *(ProjectSummary(**p.model_dump()) for p in fakes.created.values()),
    ]


@router.post("", status_code=status.HTTP_201_CREATED, responses=error_responses(409))
def create_project(body: ProjectCreate, fakes: Fakes) -> Project:
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:63] or "project"
    if slug == fakes.project().id or slug in fakes.created:
        raise ApiError(409, "project_exists", "A project with this name already exists.")
    project = Project(
        id=slug,
        name=body.name,
        stage=Stage.setup,
        updated_at=datetime.now(UTC),
        data_version=None,
        mapping_version=None,
        dag_version=None,
        knowledge_version=0,
    )
    fakes.created[slug] = project
    return project


@router.get("/{project_id}", responses=error_responses(404))
def get_project(project_id: DemoProject, fakes: Fakes) -> Project:
    return fakes.project()


@router.get("/{project_id}/proposals", responses=error_responses(404))
def list_proposals(
    project_id: DemoProject,
    fakes: Fakes,
    status: Annotated[ProposalStatus | None, Query()] = None,
) -> list[Proposal]:
    return [p for p in fakes.proposals.values() if status is None or p.status == status]


@router.post("/{project_id}/proposals/{proposal_id}/decision", responses=error_responses(404, 409))
def decide_proposal(
    project_id: DemoProject,
    proposal_id: Annotated[str, Path(pattern=r"^P[0-9]{1,6}$")],
    body: ProposalDecisionIn,
    fakes: Fakes,
) -> Proposal:
    proposal = fakes.proposals.get(proposal_id)
    if proposal is None:
        raise ApiError(404, "proposal_not_found", "No proposal with this ID.")
    if body.knowledge_version != fakes.knowledge_version:
        raise ApiError(409, "stale_version", "Your knowledge files changed. Reload and decide again.")
    if proposal.status is not ProposalStatus.pending:
        raise ApiError(409, "already_decided", "This proposal was already decided.")
    new_status = ProposalStatus.accepted if body.decision is Decision.accept else ProposalStatus.rejected
    proposal = proposal.model_copy(update={"status": new_status})
    fakes.proposals[proposal_id] = proposal
    if new_status is ProposalStatus.accepted:
        fakes.knowledge_version += 1
    return proposal
