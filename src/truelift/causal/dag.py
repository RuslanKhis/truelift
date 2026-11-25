"""The causal diagram (DAG) a user confirms, with a canonical YAML form (contract C3, decision D3).

A ``Dag`` names one treatment (the discount) and one outcome (sales), the other nodes with their
role and data source (a column, an accepted proxy, or nothing), the directed edges, the confirmed
effect modifiers and the nodes whose missing data the user explicitly accepted as a risk.

It is the ``content`` of ``dag/vN.yaml`` (``truelift.store.versions``). :meth:`Dag.to_yaml` is the
canonical text: parsing it and writing it again gives the same bytes (G06/A1), so content hashes
(C1) are stable. A graph with a cycle is refused with a message that names the loop.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import networkx as nx
import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from truelift.causal.rules import NodeRole, RulesError, parse_yaml

DAG_SCHEMA = "truelift.dag/1"

NodeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
# A column name as the user's file has it: no control characters, at most 128 characters.
Column = Annotated[str, StringConstraints(pattern=r"^[^\x00-\x1f\x7f]+$", min_length=1, max_length=128)]


class DagError(ValueError):
    """The DAG is malformed. The message says what is wrong in words a user can act on."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ProxyUse(_Strict):
    """An accepted stand-in: ``column`` measures the node, under rule ``rule`` of rules/proxies.yaml."""

    column: Column
    rule: NodeId


class DagNode(_Strict):
    id: NodeId
    role: NodeRole | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    column: Column | None = None
    proxy: ProxyUse | None = None

    @model_validator(mode="after")
    def _one_source(self) -> DagNode:
        if self.column and self.proxy:
            raise ValueError(f"node {self.id}: give a column or a stand-in, not both")
        return self


class Dag(_Strict):
    schema_: Literal["truelift.dag/1"] = Field(default=DAG_SCHEMA, alias="schema")
    treatment: NodeId
    outcome: NodeId
    nodes: list[DagNode] = Field(min_length=2)
    edges: list[tuple[NodeId, NodeId]] = Field(min_length=1)
    modifiers: list[NodeId] = []
    risk_accepted: list[NodeId] = []

    @model_validator(mode="after")
    def _well_formed(self) -> Dag:
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("nodes: the same node appears twice")
        if self.treatment == self.outcome:
            raise ValueError("the discount and sales must be different nodes")
        for name in ("treatment", "outcome"):
            node_id = getattr(self, name)
            match = [n for n in self.nodes if n.id == node_id]
            if not match or match[0].role != name or match[0].column is None:
                raise ValueError(f"{name}: {node_id!r} must be a node with role {name} and a column")
        for n in self.nodes:
            if n.role in ("treatment", "outcome") and n.id not in (self.treatment, self.outcome):
                raise ValueError(f"node {n.id}: only one treatment and one outcome are allowed (v1)")
        known = set(ids)
        for a, b in self.edges:
            if a not in known or b not in known:
                raise ValueError(f"edges: {a} -> {b} names a node that is not in the diagram")
            if a == b:
                raise ValueError(f"edges: {a} -> {b}: a factor cannot cause itself")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("edges: the same arrow appears twice")
        if (self.treatment, self.outcome) not in self.edges:
            raise ValueError(f"edges: the arrow {self.treatment} -> {self.outcome} is missing")
        for field in ("modifiers", "risk_accepted"):
            unknown = sorted(set(getattr(self, field)) - known)
            if unknown:
                raise ValueError(f"{field}: {unknown} are not in the diagram")
            if len(set(getattr(self, field))) != len(getattr(self, field)):
                raise ValueError(f"{field}: a node appears twice")
        graph = self.graph()
        if not nx.is_directed_acyclic_graph(graph):
            loop = [a for a, _ in nx.find_cycle(graph)]
            words = " -> ".join(self.label_of(n) for n in [*loop, loop[0]])
            raise ValueError(
                f"The diagram has a loop: {words}. Something cannot be its own cause; "
                "remove or reverse one of these arrows."
            )
        return self

    # --- access ---------------------------------------------------------------------------

    def graph(self) -> nx.DiGraph:
        g = nx.DiGraph()
        g.add_nodes_from(n.id for n in self.nodes)
        g.add_edges_from(self.edges)
        return g

    def node(self, node_id: str) -> DagNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def label_of(self, node_id: str, vocabulary: dict[str, str] | None = None) -> str:
        """The node's words: its own label, else the template's, else its ID with spaces."""
        try:
            own = self.node(node_id).label
        except KeyError:
            own = None
        return own or (vocabulary or {}).get(node_id) or node_id.replace("_", " ")

    # --- canonical YAML -------------------------------------------------------------------

    def to_content(self) -> dict[str, Any]:
        """The plain data stored as a DAG version's ``content`` (truelift.store.versions)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def to_yaml(self) -> str:
        """The canonical text. ``Dag.from_yaml(d.to_yaml()).to_yaml() == d.to_yaml()``."""
        return yaml.safe_dump(
            self.to_content(), sort_keys=False, allow_unicode=True, default_flow_style=None, width=100
        )

    @classmethod
    def from_content(cls, data: Any) -> Dag:
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            msg = first["msg"].removeprefix("Value error, ")
            raise DagError(f"{loc}: {msg}" if loc else msg) from exc

    @classmethod
    def from_yaml(cls, text: str) -> Dag:
        try:
            data = parse_yaml(text, "DAG")
        except RulesError as exc:
            raise DagError(str(exc)) from exc
        return cls.from_content(data)
