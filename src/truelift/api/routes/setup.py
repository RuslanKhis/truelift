"""Provider, key, disclosure, consent, budget and ledger (G11; C7, C8, C15, D17).

* ``GET /setup`` lists the providers pinned in ``models.yaml``, whether each has a key, and the
  active one. A key the provider rejected shows as not configured, so setup asks for a new one.
* ``PUT /setup/key`` stores the key in the OS keychain only and reads it back (C7). The key is
  never returned, echoed, logged or written anywhere else. A locked or missing keychain is a 503
  ``keychain_unavailable`` that names the environment variable to use instead (A7).
* ``GET /projects/{id}/disclosure`` is the versioned list of what may leave the machine, with an
  example built from the project's own mapping; ``POST /consent`` records acceptance of that
  version (409 ``disclosure_changed`` for an old one, A2).
* ``GET /usage``, ``PUT /budget`` and ``GET /ledger`` read the gateway's state in ``state.db``:
  tokens used (estimates included until the provider reports usage), the budget, the AI state,
  and one ledger row per provider attempt with categories and sizes only (D17).

The demo project (``petfood-de``) still answers from the G02 fakes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request, status

from truelift.agents.gateway import DISCLOSURE_VERSION, RETENTION_NOTE, Gateway
from truelift.agents.keys import KeychainUnavailable
from truelift.agents.payload import build_payload
from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import DEMO_PROJECT
from truelift.api.fakes import DISCLOSURE_VERSION as DEMO_DISCLOSURE_VERSION
from truelift.api.routes import Fakes
from truelift.api.schemas import (
    ApiKeyIn,
    BudgetIn,
    ConsentIn,
    ConsentRecord,
    Disclosure,
    DisclosureCategory,
    LedgerEntry,
    ProjectId,
    Provider,
    ProviderInfo,
    SetupStatus,
    Usage,
)
from truelift.store import ProjectStore, VersionKind

router = APIRouter(tags=["setup"])

ProjectPath = Annotated[ProjectId, Path()]
_DISCLOSURE_CHANGED = "What will be shared has changed. Review it again."


def get_gateway(request: Request) -> Gateway:
    return request.app.state.gateway


def get_store(request: Request) -> ProjectStore:
    return request.app.state.store


GatewayDep = Annotated[Gateway, Depends(get_gateway)]
Store = Annotated[ProjectStore, Depends(get_store)]


def _real(store: ProjectStore, project_id: str) -> str:
    store.get(project_id)  # 404 project_not_found
    return project_id


@router.get("/setup")
def get_setup(gateway: GatewayDep) -> SetupStatus:
    providers = [
        ProviderInfo(
            provider=Provider(p.provider), label=p.label, model_id=p.model_id, key_configured=p.key_configured
        )
        for p in gateway.providers()
    ]
    active = gateway.active_provider()
    return SetupStatus(providers=providers, active_provider=Provider(active) if active else None)


@router.put("/setup/key", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(503))
def put_api_key(body: ApiKeyIn, gateway: GatewayDep) -> None:
    try:
        gateway.save_key(body.provider.value, body.api_key.get_secret_value())
    except KeychainUnavailable as exc:
        raise ApiError(503, "keychain_unavailable", str(exc)) from None


def _example_payload(store: ProjectStore, project_id: str) -> dict[str, Any]:
    record = store.read_version(project_id, VersionKind.mapping)
    columns = (record.content.get("columns") or []) if record else []
    example = build_payload(
        columns=[{"name": c.get("name", ""), "type": c.get("type", "")} for c in columns if c.get("name")],
        summary={},
        sample_rows=[],
    )
    return example.data


@router.get("/projects/{project_id}/disclosure", responses=error_responses(404))
def get_disclosure(
    project_id: ProjectPath,
    fakes: Fakes,
    store: Store,
    gateway: GatewayDep,
    provider: Annotated[Provider, Query()],
) -> Disclosure:
    if project_id == DEMO_PROJECT:
        return fakes.disclosure(provider)
    _real(store, project_id)
    return Disclosure(
        provider=provider,
        version=DISCLOSURE_VERSION,
        categories=[
            DisclosureCategory(id=cid, title=title, description=desc)
            for cid, title, desc in gateway.disclosure_categories()
        ],
        example_payload=_example_payload(store, project_id),
        retention_note=RETENTION_NOTE,
    )


@router.post("/projects/{project_id}/consent", responses=error_responses(404, 409))
def post_consent(
    project_id: ProjectPath, body: ConsentIn, fakes: Fakes, store: Store, gateway: GatewayDep
) -> ConsentRecord:
    if project_id == DEMO_PROJECT:
        if body.disclosure_version != DEMO_DISCLOSURE_VERSION:
            raise ApiError(409, "disclosure_changed", _DISCLOSURE_CHANGED)
        fakes.consent = ConsentRecord(
            provider=body.provider, disclosure_version=body.disclosure_version, accepted_at=datetime.now(UTC)
        )
        return fakes.consent
    _real(store, project_id)
    try:
        row = gateway.accept(project_id, body.provider.value, body.disclosure_version)
    except ValueError:
        raise ApiError(409, "disclosure_changed", _DISCLOSURE_CHANGED) from None
    return ConsentRecord(
        provider=body.provider, disclosure_version=row.disclosure_version, accepted_at=row.accepted_at
    )


def _usage(gateway: Gateway, project_id: str) -> Usage:
    view = gateway.usage(project_id)
    return Usage(tokens_used=view.tokens_used, token_budget=view.token_budget, ai_state=view.ai_state)


@router.get("/projects/{project_id}/usage", responses=error_responses(404))
def get_usage(project_id: ProjectPath, fakes: Fakes, store: Store, gateway: GatewayDep) -> Usage:
    if project_id == DEMO_PROJECT:
        return fakes.usage()
    return _usage(gateway, _real(store, project_id))


@router.put("/projects/{project_id}/budget", responses=error_responses(404))
def put_budget(
    project_id: ProjectPath, body: BudgetIn, fakes: Fakes, store: Store, gateway: GatewayDep
) -> Usage:
    if project_id == DEMO_PROJECT:
        fakes.token_budget = body.token_budget
        return fakes.usage()
    gateway.set_budget(_real(store, project_id), body.token_budget)
    return _usage(gateway, project_id)


@router.get("/projects/{project_id}/ledger", responses=error_responses(404))
def get_ledger(project_id: ProjectPath, fakes: Fakes, store: Store, gateway: GatewayDep) -> list[LedgerEntry]:
    if project_id == DEMO_PROJECT:
        return fakes.ledger()
    return [
        LedgerEntry(
            at=row.at,
            provider=Provider(row.provider),
            model_id=row.model_id,
            categories=json.loads(row.categories),
            bytes_sent=row.bytes_sent,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
        )
        for row in gateway.ledger(_real(store, project_id))
    ]
