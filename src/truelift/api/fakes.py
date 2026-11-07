"""In-memory fake data behind the G02 stub routes. One instance per app; nothing touches disk.

The example is the neutral one from the design: a pet-food brand in Germany, eight regions,
weekly data. Every number here is made up for the interface. Real handlers replace this module
route by route (G07 intake, G08 projects and proposals, G09 runs, G10/G14 results, G11 setup,
G31 DAG and identification).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from truelift.api.schemas import (
    AiState,
    ColumnProfile,
    ConsentRecord,
    DagEdge,
    DagNode,
    DagStatus,
    DagVersion,
    DataProfile,
    DataVersion,
    Disclosure,
    DisclosureCategory,
    EdgeBasis,
    Finding,
    Identification,
    IdentificationBlock,
    LedgerEntry,
    Mapping,
    MappingStatus,
    Narrative,
    NarrativeSource,
    NodeRole,
    Project,
    Proposal,
    ProposalKind,
    ProposalStatus,
    Provider,
    ProviderInfo,
    Remedy,
    Results,
    ResultWarning,
    Role,
    RoleAssignment,
    RoleCheck,
    Run,
    RunProfile,
    RunStatus,
    SemanticType,
    Stage,
    Statement,
    StatementLabel,
    TurnQuote,
    Usage,
    Verdict,
)

DEMO_PROJECT = "petfood-de"
DISCLOSURE_VERSION = "2026-11-1"
RUN_PHASES = ["prepare", "nuisance models", "effect estimation", "sensitivity", "write outputs"]
_EXPECTED_S = {RunProfile.quick: 30.0, RunProfile.standard: 120.0}


def _now() -> datetime:
    return datetime.now(UTC)


def verdict(ci_low: float, ci_high: float, threshold: float) -> Verdict:
    """The C6 rule, so fake tiles are consistent. G10 owns the real one."""
    if ci_low > threshold:
        return Verdict.worth_it
    if ci_high < threshold:
        return Verdict.not_worth_it
    return Verdict.undetermined


_COLUMNS = [
    ColumnProfile(
        name="week",
        semantic_type=SemanticType.date,
        min=None,
        max=None,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="region",
        semantic_type=SemanticType.key,
        min=None,
        max=None,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="revenue",
        semantic_type=SemanticType.money,
        min=18_400,
        max=96_100,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="discount_rate",
        semantic_type=SemanticType.rate,
        min=0,
        max=0.3,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="discount_spend",
        semantic_type=SemanticType.money,
        min=0,
        max=14_200,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="population",
        semantic_type=SemanticType.count,
        min=1_100_000,
        max=13_400_000,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="holiday_week",
        semantic_type=SemanticType.flag,
        min=0,
        max=1,
        missing_share=0,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="store_traffic",
        semantic_type=SemanticType.index,
        min=62,
        max=141,
        missing_share=0.02,
        ground_truth_excluded=False,
    ),
    ColumnProfile(
        name="truth_roi",
        semantic_type=SemanticType.rate,
        min=None,
        max=None,
        missing_share=0,
        ground_truth_excluded=True,
    ),
]
_COLUMN_BY_NAME = {c.name: c for c in _COLUMNS}
_DEFAULT_ROLES = [
    RoleAssignment(column="week", role=Role.date),
    RoleAssignment(column="region", role=Role.region),
    RoleAssignment(column="revenue", role=Role.outcome),
    RoleAssignment(column="discount_rate", role=Role.treatment_rate),
    RoleAssignment(column="discount_spend", role=Role.treatment_spend),
    RoleAssignment(column="population", role=Role.population),
    RoleAssignment(column="holiday_week", role=Role.control),
    RoleAssignment(column="store_traffic", role=Role.control),
    RoleAssignment(column="truth_roi", role=Role.ignore),
]


def check_role(assignment: RoleAssignment) -> RoleCheck:
    """A tiny stand-in for the C12 validator on the fake profile. G07 owns the real one."""
    col = _COLUMN_BY_NAME.get(assignment.column)
    role = assignment.role

    def bad(reason: str) -> RoleCheck:
        return RoleCheck(column=assignment.column, role=role, ok=False, reason=reason)

    if col is None:
        return bad("This column is not in the uploaded file.")
    if col.ground_truth_excluded and role is not Role.ignore:
        return bad("This is a ground-truth column and is always excluded.")
    numeric = col.semantic_type in {
        SemanticType.money,
        SemanticType.volume,
        SemanticType.rate,
        SemanticType.index,
        SemanticType.count,
        SemanticType.flag,
    }
    if role is Role.date and col.semantic_type is not SemanticType.date:
        return bad("This column does not hold dates.")
    if role is Role.treatment_rate and not (
        col.min is not None and col.max is not None and 0 <= col.min <= col.max <= 1
    ):
        return bad("A discount rate must be between 0 and 1 in every row.")
    if role is Role.treatment_spend and not (numeric and col.min is not None and col.min >= 0):
        return bad("Discount spend must be zero or more in every row.")
    if role is Role.outcome and not numeric:
        return bad("Sales must be numbers.")
    if role is Role.population and not (col.min is not None and col.min > 0):
        return bad("Population must be above zero in every row.")
    return RoleCheck(column=assignment.column, role=role, ok=True)


@dataclass
class FakeRun:
    run: Run
    started: float


@dataclass
class FakeStore:
    """Per-app fake state. The agent admission set lives in app.state, not here."""

    knowledge_version: int = 3
    mapping: Mapping = field(init=False)
    dag: DagVersion = field(init=False)
    proposals: dict[str, Proposal] = field(init=False)
    runs: dict[str, FakeRun] = field(init=False)
    consent: ConsentRecord | None = None
    token_budget: int = 2_000_000
    tokens_used: int = 184_320
    data: DataVersion | None = field(init=False)
    created: dict[str, Project] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.data = DataVersion(
            version=1,
            filename="sales_panel.csv",
            fingerprint="sha256:3f1c0a9e5b7d",
            rows=1248,
            columns=len(_COLUMNS),
            uploaded_at=datetime(2026, 11, 5, 9, 30, tzinfo=UTC),
        )
        self.mapping = Mapping(
            version=1,
            status=MappingStatus.proposed,
            data_fingerprint=self.data.fingerprint,
            roles=[check_role(a) for a in _DEFAULT_ROLES],
        )
        self.dag = _demo_dag()
        self.proposals = {p.id: p for p in _demo_proposals()}
        self.runs = {}
        for run in _demo_runs():
            self.runs[run.id] = FakeRun(run=run, started=time.monotonic() - run.elapsed_s)

    # --- projects

    def project(self) -> Project:
        return Project(
            id=DEMO_PROJECT,
            name="Pet food, Germany",
            stage=Stage.dag_review,
            updated_at=datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
            data_version=self.data.version if self.data else None,
            mapping_version=self.mapping.version,
            dag_version=self.dag.version,
            knowledge_version=self.knowledge_version,
        )

    # --- setup

    def providers(self) -> list[ProviderInfo]:
        return [
            ProviderInfo(
                provider=Provider.gemini,
                label="Google Gemini",
                model_id="gemini-3.8-flash",
                key_configured=True,
            ),
            ProviderInfo(
                provider=Provider.claude,
                label="Anthropic Claude",
                model_id="claude-sonnet-5-5",
                key_configured=False,
            ),
        ]

    def disclosure(self, provider: Provider) -> Disclosure:
        return Disclosure(
            provider=provider,
            version=DISCLOSURE_VERSION,
            categories=[
                DisclosureCategory(
                    id="columns",
                    title="Column names and types",
                    description="The names and kinds of your columns.",
                ),
                DisclosureCategory(
                    id="summary",
                    title="Summary statistics",
                    description="Per column: minimum, maximum, share missing.",
                ),
                DisclosureCategory(
                    id="sample_rows",
                    title="Up to 20 sample rows",
                    description="Ground-truth columns removed. Never the whole file.",
                ),
                DisclosureCategory(
                    id="answers", title="Your answers", description="What you type in the interview."
                ),
                DisclosureCategory(
                    id="results",
                    title="Result aggregates",
                    description="Headline and breakdown numbers of a run.",
                ),
            ],
            example_payload={
                "columns": [
                    {"name": c.name, "type": c.semantic_type} for c in _COLUMNS if not c.ground_truth_excluded
                ],
                "summary": {"revenue": {"min": 18400, "max": 96100, "missing_share": 0}},
                "sample_rows": [
                    {"week": "2025-01-06", "region": "Bayern", "revenue": 61250, "discount_rate": 0.1},
                    {"week": "2025-01-06", "region": "Berlin", "revenue": 40480, "discount_rate": 0.0},
                ],
            },
            retention_note="The provider keeps requests according to its own terms for API use.",
        )

    def usage(self) -> Usage:
        state = AiState.budget_paused if self.tokens_used >= self.token_budget else AiState.available
        return Usage(tokens_used=self.tokens_used, token_budget=self.token_budget, ai_state=state)

    def ledger(self) -> list[LedgerEntry]:
        base = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
        return [
            LedgerEntry(
                at=base.replace(minute=m),
                provider=Provider.gemini,
                model_id="gemini-3.8-flash",
                categories=cats,
                bytes_sent=b,
                input_tokens=i,
                output_tokens=o,
            )
            for m, cats, b, i, o in [
                (2, ["columns", "summary", "sample_rows"], 9_412, 6_210, 340),
                (5, ["answers"], 2_118, 7_034, 412),
                (9, ["answers"], 2_604, 7_480, 388),
            ]
        ]

    # --- intake

    def profile(self) -> DataProfile:
        return DataProfile(
            data_version=self.data.version if self.data else 0,
            rows=1248,
            weeks=156,
            regions=8,
            columns=_COLUMNS,
            observations=[
                "Discounts were zero in 17% of weeks, mostly in January and February.",
                "store_traffic is missing in 2% of rows.",
            ],
        )

    def upload(self, filename: str, size: int) -> DataVersion:
        version = (self.data.version if self.data else 0) + 1
        self.data = DataVersion(
            version=version,
            filename=filename,
            fingerprint="sha256:" + uuid.uuid4().hex[:12],
            rows=1248,
            columns=len(_COLUMNS),
            uploaded_at=_now(),
        )
        return self.data

    # --- runs

    def new_run(self, profile: RunProfile) -> Run:
        run_id = "run-" + uuid.uuid4().hex[:8]
        run = Run(
            id=run_id,
            project_id=DEMO_PROJECT,
            status=RunStatus.queued,
            profile=profile,
            phase=None,
            phases=RUN_PHASES,
            elapsed_s=0,
            expected_s=_EXPECTED_S[profile],
            log_tail=[],
            reason=None,
            created_at=_now(),
        )
        self.runs[run_id] = FakeRun(run=run, started=time.monotonic())
        return run

    def current(self, run_id: str) -> Run | None:
        """Advance a fake run by wall clock: queued, then each phase, then succeeded."""
        fake = self.runs.get(run_id)
        if fake is None:
            return None
        run = fake.run
        if run.status in {RunStatus.queued, RunStatus.running}:
            elapsed = time.monotonic() - fake.started
            share = elapsed / run.expected_s
            if share >= 1:
                run = run.model_copy(
                    update={"status": RunStatus.succeeded, "phase": None, "elapsed_s": run.expected_s}
                )
                run.log_tail = ["outputs written", "manifest written"]
            else:
                idx = min(int(share * len(RUN_PHASES)), len(RUN_PHASES) - 1)
                run = run.model_copy(
                    update={
                        "status": RunStatus.running,
                        "phase": RUN_PHASES[idx],
                        "elapsed_s": round(elapsed, 1),
                        "log_tail": [f"phase: {p}" for p in RUN_PHASES[: idx + 1]][-3:],
                    }
                )
            fake.run = run
        return run

    def active_run(self) -> Run | None:
        for run_id in list(self.runs):
            run = self.current(run_id)
            if run and run.status in {RunStatus.queued, RunStatus.running}:
                return run
        return None


def _demo_dag() -> DagVersion:
    nodes = [
        DagNode(id="discount", label="Discount depth", role=NodeRole.treatment, column="discount_rate"),
        DagNode(id="sales", label="Weekly sales", role=NodeRole.outcome, column="revenue"),
        DagNode(id="holiday", label="Holiday weeks", role=NodeRole.confounder, column="holiday_week"),
        DagNode(id="stock_age", label="Ageing stock", role=NodeRole.confounder, column=None),
        DagNode(id="traffic", label="Store traffic", role=NodeRole.mediator, column="store_traffic"),
        DagNode(id="region_size", label="Region size", role=NodeRole.modifier, column="population"),
    ]
    edges = [
        DagEdge(
            id="e1",
            source="holiday",
            target="discount",
            sentence="Holiday weeks make you discount more.",
            basis=EdgeBasis.fact,
            fact_ids=["F012"],
            opinion=None,
        ),
        DagEdge(
            id="e2",
            source="holiday",
            target="sales",
            sentence="Holiday weeks lift sales on their own.",
            basis=EdgeBasis.fact,
            fact_ids=["F012"],
            opinion=None,
        ),
        DagEdge(
            id="e3",
            source="stock_age",
            target="discount",
            sentence="Ageing stock makes you discount.",
            basis=EdgeBasis.fact,
            fact_ids=["F012"],
            opinion=None,
        ),
        DagEdge(
            id="e4",
            source="discount",
            target="traffic",
            sentence="Discounts bring more people into stores.",
            basis=EdgeBasis.assumed,
            fact_ids=[],
            opinion=None,
        ),
        DagEdge(
            id="e5",
            source="traffic",
            target="sales",
            sentence="More store traffic means more sales.",
            basis=EdgeBasis.assumed,
            fact_ids=[],
            opinion=None,
        ),
        DagEdge(
            id="e6",
            source="discount",
            target="sales",
            sentence="Discounts change weekly sales.",
            basis=EdgeBasis.assumed,
            fact_ids=[],
            opinion=None,
        ),
    ]
    return DagVersion(version=4, status=DagStatus.draft, nodes=nodes, edges=edges)


def identification(dag: DagVersion) -> Identification:
    return Identification(
        dag_version=dag.version,
        identified=False,
        adjustment_set=["holiday"],
        blocks=[
            IdentificationBlock(
                code="unobserved_confounder",
                message=(
                    "Ageing stock drives both discounts and sales, and your file has no column for it. "
                    "We need weekly stock-age data, an accepted stand-in, "
                    "or your explicit acceptance of the risk."
                ),
                node_ids=["stock_age"],
                remedies=[Remedy.add_data, Remedy.use_proxy, Remedy.accept_risk],
            )
        ],
    )


def _demo_proposals() -> list[Proposal]:
    return [
        Proposal(
            id="P005",
            kind=ProposalKind.fact,
            status=ProposalStatus.pending,
            file="market.md",
            fact_id="F021",
            summary="Christmas and Black Friday are the busiest weeks.",
            new_text="Our busiest weeks are Black Friday and the two weeks before Christmas.",
            source=TurnQuote(turn=9, text="Black Friday and the run-up to Christmas, by far"),
            contradiction=False,
            contradicts=None,
        ),
        Proposal(
            id="P006",
            kind=ProposalKind.fact,
            status=ProposalStatus.pending,
            file="business.md",
            fact_id="F009",
            summary="Competitor promotions now said to influence the discount calendar.",
            new_text="We react to competitor promotions in the same week.",
            source=TurnQuote(turn=15, text="if the competitor runs a promo we usually answer that week"),
            contradiction=True,
            contradicts=TurnQuote(turn=6, text="competitors don't really affect when we discount"),
        ),
    ]


def _demo_runs() -> list[Run]:
    created = datetime(2026, 11, 5, 11, 0, tzinfo=UTC)
    common = {
        "project_id": DEMO_PROJECT,
        "profile": RunProfile.standard,
        "phases": RUN_PHASES,
        "created_at": created,
    }
    return [
        Run(
            id="run-demo01",
            status=RunStatus.succeeded,
            phase=None,
            elapsed_s=118,
            expected_s=120,
            log_tail=["outputs written", "manifest written"],
            reason=None,
            **common,
        ),
        Run(
            id="run-demo02",
            status=RunStatus.interrupted,
            phase="effect estimation",
            elapsed_s=64,
            expected_s=120,
            log_tail=["phase: nuisance models", "phase: effect estimation"],
            reason="This run was interrupted. Re-run (about 2 min).",
            **common,
        ),
    ]


def results(run_id: str) -> Results:
    threshold = 2.5
    few_clusters = ResultWarning(
        code="few_clusters", message="With only a few regions, the uncertainty range itself is uncertain."
    )

    def finding(fid: str, scope: str, label: str, roi: float, lo: float, hi: float, inc: float) -> Finding:
        return Finding(
            id=fid,
            scope=scope,
            label=label,
            roi=roi,
            ci_low=lo,
            ci_high=hi,
            threshold=threshold,
            verdict=verdict(lo, hi, threshold),
            incremental_revenue=inc,
            warnings=[few_clusters] if scope == "total" else [],
        )

    headline = finding("F-total", "total", "All regions, all weeks", 2.1, -0.4, 4.6, 412_000)
    breakdown = [
        finding("F-holiday", "season:holiday", "Holiday weeks", 3.4, 2.7, 4.1, 260_000),
        finding("F-low", "season:low", "January and February", 0.6, -1.2, 1.9, -38_000),
        finding("F-bayern", "region:Bayern", "Bayern", 2.4, 0.3, 4.5, 88_000),
    ]
    narrative = Narrative(
        source=NarrativeSource.ai,
        note=None,
        statements=[
            Statement(
                label=StatementLabel.inference,
                text="Each euro of discount brought back about €2.1, but the range runs from €−0.4 to €4.6, "
                "so against your break-even of €2.5 the answer is undetermined.",
                finding_ids=["F-total"],
                verification=None,
            ),
            Statement(
                label=StatementLabel.inference,
                text="Holiday-week discounts pay: about €3.4 back per euro, with the whole range above €2.5.",
                finding_ids=["F-holiday"],
                verification=None,
            ),
            Statement(
                label=StatementLabel.hypothesis,
                text="January discounts may pull sales forward rather than add new ones.",
                finding_ids=["F-low"],
                verification="Pause January discounts in two regions and compare with the others.",
            ),
        ],
    )
    return Results(run_id=run_id, currency="EUR", headline=headline, breakdown=breakdown, narrative=narrative)
