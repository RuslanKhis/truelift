"""Request and response models of the public /api contract (C16; client generated from these).

G02 serves them from fakes. G07–G14 and G31 replace the handlers but keep these shapes; a shape
change is a contract change that regenerates ``frontend/src/client`` and shows up in review.
Input models forbid unknown fields and bound every string and list (SB09).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

ProjectId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]
RunId = Annotated[str, StringConstraints(pattern=r"^run-[a-z0-9]{4,32}$")]
ItemId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ColumnName = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class In(BaseModel):
    """Base for request bodies: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


# --- Projects and stages (D2: the stage machine lives in code) ------------------------------


class Stage(StrEnum):
    setup = "setup"
    data = "data"
    mapping = "mapping"
    interview = "interview"
    dag_review = "dag_review"
    identification = "identification"
    run = "run"
    results = "results"


class ProjectSummary(BaseModel):
    id: ProjectId
    name: str
    stage: Stage
    updated_at: datetime


class Project(ProjectSummary):
    data_version: int | None
    mapping_version: int | None
    dag_version: int | None
    knowledge_version: int = Field(description="Bumps on every accepted proposal; sent back on decisions.")


class ProjectCreate(In):
    name: Annotated[str, StringConstraints(min_length=1, max_length=80, strip_whitespace=True)]


# --- Setup: provider, key, disclosure, consent, budget, ledger (C7, C8, C15; G11 replaces) --


class Provider(StrEnum):
    gemini = "gemini"
    claude = "claude"


class ProviderInfo(BaseModel):
    provider: Provider
    label: str
    model_id: str
    key_configured: bool


class SetupStatus(BaseModel):
    providers: list[ProviderInfo]
    active_provider: Provider | None


class ApiKeyIn(In):
    """The key is sent once, kept only in the OS keychain (G11) and never returned or echoed."""

    provider: Provider
    api_key: SecretStr = Field(min_length=10, max_length=400)


class DisclosureCategory(BaseModel):
    id: str
    title: str
    description: str


class Disclosure(BaseModel):
    provider: Provider
    version: str
    categories: list[DisclosureCategory]
    example_payload: dict[str, Any] = Field(description="Built from the user's own uploaded file.")
    retention_note: str


class ConsentIn(In):
    provider: Provider
    disclosure_version: Annotated[str, StringConstraints(min_length=1, max_length=32)]


class ConsentRecord(BaseModel):
    provider: Provider
    disclosure_version: str
    accepted_at: datetime


class AiState(StrEnum):
    available = "available"
    no_key = "no_key"
    consent_needed = "consent_needed"
    unavailable = "unavailable"
    budget_paused = "budget_paused"


class Usage(BaseModel):
    tokens_used: int
    token_budget: int
    ai_state: AiState


class BudgetIn(In):
    token_budget: int = Field(ge=10_000, le=100_000_000)


class LedgerEntry(BaseModel):
    """One model call. Categories and sizes only, never content (C8)."""

    at: datetime
    provider: Provider
    model_id: str
    categories: list[str]
    bytes_sent: int
    input_tokens: int
    output_tokens: int


# --- Data intake and mapping (C12; G07 replaces) --------------------------------------------


class IntakeErrorCode(StrEnum):
    """Upload rejection reasons. The fake upload returns one when the file stem equals its code."""

    not_csv = "not_csv"
    empty_file = "empty_file"
    missing_date = "missing_date"
    not_weekly = "not_weekly"
    duplicate_keys = "duplicate_keys"
    malformed_rows = "malformed_rows"


class DataVersion(BaseModel):
    version: int
    filename: str
    fingerprint: str
    rows: int
    columns: int
    uploaded_at: datetime


class SemanticType(StrEnum):
    date = "date"
    key = "key"
    money = "money"
    volume = "volume"
    rate = "rate"
    index = "index"
    flag = "flag"
    count = "count"
    text = "text"


class ColumnProfile(BaseModel):
    name: str
    semantic_type: SemanticType
    min: float | None
    max: float | None
    missing_share: float
    ground_truth_excluded: bool = Field(description='Shown as "ground truth: excluded" (C4).')


class DataProfile(BaseModel):
    data_version: int
    rows: int
    weeks: int
    regions: int
    columns: list[ColumnProfile]
    observations: list[str]


class Role(StrEnum):
    date = "date"
    region = "region"
    category = "category"
    outcome = "outcome"
    treatment_rate = "treatment_rate"
    treatment_spend = "treatment_spend"
    population = "population"
    control = "control"
    ignore = "ignore"


class RoleAssignment(In):
    column: ColumnName
    role: Role


class RoleCheck(BaseModel):
    column: str
    role: Role
    ok: bool
    reason: str | None = Field(default=None, description="Plain-language reason when not ok.")


class MappingStatus(StrEnum):
    proposed = "proposed"
    confirmed = "confirmed"
    needs_review = "needs_review"


class Mapping(BaseModel):
    version: int
    status: MappingStatus
    data_fingerprint: str
    roles: list[RoleCheck]


class MappingIn(In):
    expected_version: int = Field(ge=0, description="The version being edited; a stale one returns 409.")
    roles: list[RoleAssignment] = Field(min_length=1, max_length=500)


class VersionIn(In):
    version: int = Field(ge=1)


# --- Proposals (C11; G08 replaces) ----------------------------------------------------------


class ProposalKind(StrEnum):
    fact = "fact"
    mapping = "mapping"
    dag_edit = "dag_edit"


class ProposalStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class TurnQuote(BaseModel):
    turn: int
    text: str


class Proposal(BaseModel):
    id: str
    kind: ProposalKind
    status: ProposalStatus
    file: str = Field(description="business.md, market.md or data.md")
    fact_id: str | None
    summary: str
    new_text: str
    source: TurnQuote | None
    contradiction: bool
    contradicts: TurnQuote | None = Field(description="The confirmed answer this one conflicts with.")


class Decision(StrEnum):
    accept = "accept"
    reject = "reject"


ProposalId = Annotated[str, StringConstraints(pattern=r"^P[0-9]{1,6}$")]


class ProposalDecisionIn(In):
    decision: Decision
    knowledge_version: int = Field(ge=0, description="A stale knowledge version returns 409.")
    resolves_contradiction: bool = Field(
        default=False,
        description=(
            "Accepting a proposal marked `contradiction` replaces a confirmed fact, so it needs this "
            "set to true: the user chose the new answer for this fact. Otherwise 409 "
            "`contradiction_choice_needed`. Rejecting keeps the confirmed fact and needs nothing."
        ),
    )


class ProposalBatchIn(In):
    """Accept several proposals at once: all are applied or none (409 on a contradiction)."""

    proposal_ids: list[ProposalId] = Field(min_length=1, max_length=100)
    knowledge_version: int = Field(ge=0, description="A stale knowledge version returns 409.")


# --- DAG and identification (C1, C3; G31 replaces) ------------------------------------------


class NodeRole(StrEnum):
    treatment = "treatment"
    outcome = "outcome"
    confounder = "confounder"
    mediator = "mediator"
    modifier = "modifier"
    predictor = "predictor"


class DagNode(BaseModel):
    id: str
    label: str
    role: NodeRole
    column: str | None = Field(description="None means unobserved.")


class EdgeBasis(StrEnum):
    fact = "fact"
    assumed = "assumed"


class Opinion(StrEnum):
    agree = "agree"
    disagree = "disagree"
    not_sure = "not_sure"


class DagEdge(BaseModel):
    id: str
    source: str
    target: str
    sentence: str = Field(description="The edge card text, in business language.")
    basis: EdgeBasis
    fact_ids: list[str]
    opinion: Opinion | None


class DagStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    stale = "stale"


class DagVersion(BaseModel):
    version: int
    status: DagStatus
    nodes: list[DagNode]
    edges: list[DagEdge]


class OpinionIn(In):
    opinion: Opinion
    dag_version: int = Field(ge=1)


class Remedy(StrEnum):
    add_data = "add_data"
    use_proxy = "use_proxy"
    accept_risk = "accept_risk"


class IdentificationBlock(BaseModel):
    code: str
    message: str = Field(description="What is missing, in business words.")
    node_ids: list[str]
    remedies: list[Remedy]


class Identification(BaseModel):
    dag_version: int
    identified: bool
    adjustment_set: list[str]
    blocks: list[IdentificationBlock]


# --- Runs and results (C1, C5, C6, C10; G09, G10, G14 replace) ------------------------------


class RunProfile(StrEnum):
    quick = "quick"
    standard = "standard"


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    interrupted = "interrupted"
    cancelled = "cancelled"


class RunCreate(In):
    dag_version: int = Field(ge=1)
    profile: RunProfile


class Run(BaseModel):
    id: RunId
    project_id: ProjectId
    status: RunStatus
    profile: RunProfile
    phase: str | None
    phases: list[str]
    elapsed_s: float
    expected_s: float
    log_tail: list[str]
    reason: str | None = Field(description="Plain reason for failed, interrupted or cancelled.")
    created_at: datetime


class Verdict(StrEnum):
    worth_it = "worth_it"
    not_worth_it = "not_worth_it"
    undetermined = "undetermined"


class ResultWarning(BaseModel):
    code: str
    message: str


class Finding(BaseModel):
    id: str
    scope: str = Field(description="total, region:<name> or season:<name>")
    label: str
    roi: float
    ci_low: float
    ci_high: float
    threshold: float
    verdict: Verdict
    incremental_revenue: float
    warnings: list[ResultWarning]


class StatementLabel(StrEnum):
    fact = "fact"
    inference = "inference"
    hypothesis = "hypothesis"


class Statement(BaseModel):
    label: StatementLabel
    text: str
    finding_ids: list[str]
    verification: str | None


class NarrativeSource(StrEnum):
    ai = "ai"
    template = "template"


class Narrative(BaseModel):
    source: NarrativeSource
    note: str | None
    statements: list[Statement]


class Results(BaseModel):
    run_id: RunId
    currency: str
    headline: Finding
    breakdown: list[Finding]
    narrative: Narrative


# --- Agent ----------------------------------------------------------------------------------


class AgentMessageIn(In):
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000)]


class Health(BaseModel):
    status: str
