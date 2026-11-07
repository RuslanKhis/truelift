"""Provider, key, disclosure, consent, budget and ledger. Stub (G02); G11 replaces it (C7, C8, C15).

The stub never stores a key: it validates the shape and discards it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import DISCLOSURE_VERSION
from truelift.api.routes import DemoProject, Fakes
from truelift.api.schemas import (
    ApiKeyIn,
    BudgetIn,
    ConsentIn,
    ConsentRecord,
    Disclosure,
    LedgerEntry,
    Provider,
    SetupStatus,
    Usage,
)

router = APIRouter(tags=["setup"])


@router.get("/setup")
def get_setup(fakes: Fakes) -> SetupStatus:
    return SetupStatus(providers=fakes.providers(), active_provider=Provider.gemini)


@router.put("/setup/key", status_code=status.HTTP_204_NO_CONTENT)
def put_api_key(body: ApiKeyIn) -> None:
    # Stub: the key is validated and dropped. G11 writes it to the OS keychain only.
    del body


@router.get("/projects/{project_id}/disclosure", responses=error_responses(404))
def get_disclosure(
    project_id: DemoProject, fakes: Fakes, provider: Annotated[Provider, Query()]
) -> Disclosure:
    return fakes.disclosure(provider)


@router.post("/projects/{project_id}/consent", responses=error_responses(404, 409))
def post_consent(project_id: DemoProject, body: ConsentIn, fakes: Fakes) -> ConsentRecord:
    if body.disclosure_version != DISCLOSURE_VERSION:
        raise ApiError(409, "disclosure_changed", "What will be shared has changed. Review it again.")
    fakes.consent = ConsentRecord(
        provider=body.provider, disclosure_version=body.disclosure_version, accepted_at=datetime.now(UTC)
    )
    return fakes.consent


@router.get("/projects/{project_id}/usage", responses=error_responses(404))
def get_usage(project_id: DemoProject, fakes: Fakes) -> Usage:
    return fakes.usage()


@router.put("/projects/{project_id}/budget", responses=error_responses(404))
def put_budget(project_id: DemoProject, body: BudgetIn, fakes: Fakes) -> Usage:
    fakes.token_budget = body.token_budget
    return fakes.usage()


@router.get("/projects/{project_id}/ledger", responses=error_responses(404))
def get_ledger(project_id: DemoProject, fakes: Fakes) -> list[LedgerEntry]:
    return fakes.ledger()
