"""The golden-case format (contracts C3 and C2; G05/A4).

Each ``tests/golden/<id>.yaml`` gives a confirmed DAG, a confirmed column mapping and a data
summary, and states what identification and the compiler must produce. Thao writes and verifies
them; G06's ``identify`` and ``compile`` must reproduce every expectation (G06/A2).

Lists in ``expected`` are sorted, so a case has exactly one correct form. Node IDs follow the
template vocabulary; column names are the user's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from truelift.causal.rules import (
    BLOCK_CODES,
    WARNING_CODES,
    MappingRole,
    NodeRole,
    Remedy,
    SemanticType,
    read_yaml,
)

GOLDEN_DIR = Path(__file__).resolve().parent

NodeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
Column = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]*$", max_length=64)]

# What a case can be about. A4 requires the first seven.
COVERS = (
    "mediator_trap",
    "unobserved_no_proxy",
    "proxy_accepted",
    "treatment_descendant",
    "collider",
    "low_variation",
    "percentage_with_spend",
    "backdoor",
    "risk_accepted",
    "panel_shape",
    "cate",
    "normalisation",
    "forbidden_column",
    "spend_treatment",
)
A4_REQUIRED = COVERS[:7]
CATE_WARNINGS = ("cate_capped", "cate_small_sample")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ProxyUse(_Strict):
    column: Column
    rule: NodeId


class Node(_Strict):
    id: NodeId
    role: NodeRole | None = None
    column: Column | None = None
    proxy: ProxyUse | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Node:
        if self.column and self.proxy:
            raise ValueError(f"node {self.id}: give a column or a proxy, not both")
        return self


class Dag(_Strict):
    treatment: NodeId
    outcome: NodeId
    nodes: list[Node]
    edges: list[tuple[NodeId, NodeId]]
    modifiers: list[NodeId] = []
    risk_accepted: list[NodeId] = []

    @model_validator(mode="after")
    def _well_formed(self) -> Dag:
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("dag.nodes: duplicate node id")
        for name in ("treatment", "outcome"):
            node = getattr(self, name)
            match = [n for n in self.nodes if n.id == node]
            if not match or match[0].role != name or match[0].column is None:
                raise ValueError(f"dag.{name}: {node!r} must be a node with role {name} and a column")
        known = set(ids)
        for a, b in self.edges:
            if a not in known or b not in known:
                raise ValueError(f"dag.edges: {a} -> {b} names an unknown node")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("dag.edges: duplicate edge")
        if (self.treatment, self.outcome) not in self.edges:
            raise ValueError("dag.edges: the treatment -> outcome edge is missing")
        for field in ("modifiers", "risk_accepted"):
            unknown = set(getattr(self, field)) - known
            if unknown:
                raise ValueError(f"dag.{field}: unknown nodes {sorted(unknown)}")
        return self

    def node(self, node_id: str) -> Node:
        return next(n for n in self.nodes if n.id == node_id)


class MappedColumn(_Strict):
    name: Column
    role: MappingRole
    type: SemanticType
    bounded_0_1: bool = False


class Mapping(_Strict):
    columns: list[MappedColumn] = Field(min_length=3)

    @model_validator(mode="after")
    def _well_formed(self) -> Mapping:
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("mapping.columns: duplicate column")
        for role in ("date", "region", "outcome", "population"):
            if sum(c.role == role for c in self.columns) > 1:
                raise ValueError(f"mapping.columns: more than one {role} column")
        for c in self.columns:
            if c.bounded_0_1 and c.type != "rate":
                raise ValueError(f"mapping.columns: {c.name}: only a rate can be bounded_0_1")
        return self

    def column(self, name: str) -> MappedColumn:
        return next(c for c in self.columns if c.name == name)

    def by_role(self, role: str) -> list[MappedColumn]:
        return [c for c in self.columns if c.role == role]


class DataSummary(_Strict):
    weeks: int = Field(ge=1)
    regions: int = Field(ge=1)
    rows: int = Field(ge=1)
    treated_share: float = Field(ge=0, le=1)
    untreated_share: float = Field(ge=0, le=1)
    treatment_levels: int = Field(ge=0)
    gap_share: float = Field(ge=0, le=1)


class Block(_Strict):
    code: Literal[BLOCK_CODES]  # type: ignore[valid-type]
    node_ids: list[NodeId] = []
    remedies: list[Remedy] = []


class Warning(_Strict):
    code: Literal[WARNING_CODES + CATE_WARNINGS]  # type: ignore[valid-type]
    subjects: list[str] = []


class Scalers(_Strict):
    median_normalize_cols: list[Column] = []
    population_median_normalize_cols: list[Column] = []


class Compile(_Strict):
    treatment_types: dict[Column, Literal["percentage", "spend"]] | None = None
    sales_col: Column | None = None
    treatment_spend_cols: dict[Column, Column] | None = None
    opt_threshold_roi: float | None = None
    scalers: Scalers | None = None
    error: Literal["missing_spend_column"] | None = None

    @model_validator(mode="after")
    def _error_or_config(self) -> Compile:
        if self.error and any(
            v is not None for v in (self.treatment_types, self.treatment_spend_cols, self.scalers)
        ):
            raise ValueError("expected.compile: an error case states no config fields")
        return self


class Expected(_Strict):
    decision: Literal["identified", "blocked"]
    blocks: list[Block] = []
    adjustment_set: list[NodeId] | None = None
    x_cols: list[Column] | None = None
    fixed_effects: list[Column] | None = None
    cate_covariates: list[Column] | None = None
    cate_degree: int | None = None
    warnings: list[Warning] | None = None
    compile: Compile | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Expected:
        identified_fields = ("adjustment_set", "x_cols", "fixed_effects", "cate_covariates", "warnings")
        if self.decision == "blocked":
            if not self.blocks:
                raise ValueError("expected: a blocked case lists its blocks")
            stated = [f for f in identified_fields if getattr(self, f) is not None]
            if stated or self.compile is not None:
                raise ValueError(f"expected: a blocked case states no run settings ({stated})")
        else:
            if self.blocks:
                raise ValueError("expected: an identified case has no blocks")
            missing = [f for f in identified_fields if getattr(self, f) is None]
            if missing:
                raise ValueError(f"expected: an identified case states {missing}")
            if bool(self.cate_covariates) != (self.cate_degree is not None):
                raise ValueError("expected: cate_degree is stated exactly when there are CATE covariates")
        _sorted("blocks", [(b.code, b.node_ids) for b in self.blocks])
        _sorted("warnings", [(w.code, w.subjects) for w in self.warnings or []])
        for name in ("adjustment_set", "x_cols", "fixed_effects", "cate_covariates"):
            _sorted(name, getattr(self, name) or [])
        for b in self.blocks:
            _sorted(f"blocks.{b.code}.node_ids", b.node_ids)
        for w in self.warnings or []:
            _sorted(f"warnings.{w.code}.subjects", w.subjects)
        if self.compile and self.compile.scalers:
            _sorted("scalers.median_normalize_cols", self.compile.scalers.median_normalize_cols)
            _sorted(
                "scalers.population_median_normalize_cols",
                self.compile.scalers.population_median_normalize_cols,
            )
        return self


class GoldenCase(_Strict):
    schema_: Literal["truelift.golden/1"] = Field(alias="schema")
    id: Annotated[str, StringConstraints(pattern=r"^g[0-9]{2}_[a-z0-9_]+$")]
    title: str = Field(min_length=10, max_length=120)
    covers: list[Literal[COVERS]] = Field(min_length=1)  # type: ignore[valid-type]
    template: NodeId | None = None
    rationale: str = Field(min_length=40)
    dag: Dag
    mapping: Mapping
    data: DataSummary
    margin: float | None = Field(default=None, gt=0, le=1)
    expected: Expected

    @model_validator(mode="after")
    def _columns_mapped(self) -> GoldenCase:
        mapped = {c.name for c in self.mapping.columns}
        for n in self.dag.nodes:
            col = n.column or (n.proxy.column if n.proxy else None)
            if col and col not in mapped:
                raise ValueError(f"node {n.id}: column {col!r} is not in the mapping")
        return self


def _sorted(name: str, values: list) -> None:
    if values != sorted(values):
        raise ValueError(f"expected.{name}: must be sorted")


def case_paths() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("g*.yaml"))


def load_case(path: Path) -> GoldenCase:
    return GoldenCase.model_validate(read_yaml(path))
