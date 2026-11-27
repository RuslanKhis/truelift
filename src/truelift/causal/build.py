"""The DAG builder: confirmed facts + a business-type template -> a DAG version (C1, C3; D3, D5).

Design section 5, "DAG construction (code)": start from the template for the business type, apply
confirmed facts as edge assertions (add, remove, reverse) and node mappings, and mark every edge
without a supporting fact as a template default (``assumed``). An agent cannot add an edge
without a fact: only facts the user confirmed reach this function, through the project store,
which applies a proposal only after the user accepts it (C11).

A fact's ``supports`` items (truelift.store.knowledge, G08 ruling R5) mean:

* ``edge(a -> b)``: ``a`` affects ``b``. Adds the arrow; if the opposite arrow is only a template
  default, it is removed (a reversal).
* ``no-edge(a -> b)``: ``a`` does not affect ``b``. Removes the arrow.
* ``node(a)``: the factor ``a`` belongs in the diagram (added if the template lacks it).
* ``node(a)`` together with exactly one ``column(c)`` in the same fact: ``a`` is measured by the
  column ``c`` of the user's file. A ``column(c)`` on its own describes a column and does not
  change the diagram.

Only facts with status ``confirmed`` are applied, in fact-ID order, so the same facts and template
always give the same content (G31/A1). Two confirmed facts that disagree about one arrow stop the
build with a message naming both facts. The discount and sales columns come from the confirmed
column mapping.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from truelift.causal.dag import Dag, DagError, NodeId
from truelift.causal.mapping import ColumnMapping
from truelift.causal.rules import NodeRole, Template
from truelift.store.knowledge import Fact, FactStatus

DRAFT_SCHEMA = "truelift.dag_version/1"

_SUPPORT = re.compile(
    r"^(?P<kind>edge|no-edge)\(\s*(?P<a>[A-Za-z0-9_]+)\s*->\s*(?P<b>[A-Za-z0-9_]+)\s*\)$"
    r"|^(?P<one>node|column)\(\s*(?P<x>[A-Za-z0-9_]+)\s*\)$"
)
_NODE_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class BuildError(ValueError):
    """The facts cannot be turned into a diagram. The message says why, in business words."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class EdgeBasis(_Strict):
    """Why an arrow is in the diagram: the confirmed facts that state it, or none (``assumed``)."""

    from_: NodeId = Field(alias="from")
    to: NodeId
    facts: list[str] = []
    sentence: str

    @property
    def basis(self) -> Literal["fact", "assumed"]:
        return "fact" if self.facts else "assumed"


class DagDraft(_Strict):
    """The ``content`` of ``dag/vN.yaml``: the template it started from, the diagram, and the
    basis of each arrow (in the diagram's edge order)."""

    schema_: Literal["truelift.dag_version/1"] = Field(default=DRAFT_SCHEMA, alias="schema")
    template: NodeId
    dag: Dag
    edges: list[EdgeBasis]

    def to_content(self) -> dict[str, Any]:
        return {
            "schema": self.schema_,
            "template": self.template,
            "dag": self.dag.to_content(),
            "edges": [e.model_dump(mode="json", by_alias=True) for e in self.edges],
        }

    @classmethod
    def from_content(cls, data: dict[str, Any]) -> DagDraft:
        dag = Dag.from_content(data.get("dag"))
        return cls.model_validate({**data, "dag": dag})


class Built(_Strict):
    draft: DagDraft
    cites: list[str]  # every fact the diagram depends on; a change to one makes it stale (C1)


def build_dag(
    template: Template,
    facts: Iterable[Fact],
    mapping: ColumnMapping,
    *,
    vocabulary: dict[str, str] | None = None,
) -> Built:
    """Build the diagram. ``vocabulary`` maps node IDs from other templates to their labels."""
    labels = {**(vocabulary or {}), **{n.id: n.label for n in template.nodes}}
    roles: dict[str, NodeRole | None] = {n.id: n.role for n in template.nodes}
    node_order = [n.id for n in template.nodes]
    sentences = {(e.from_, e.to): e.sentence for e in template.edges}
    template_order = [(e.from_, e.to) for e in template.edges]
    defaults = set(template.present_edges())

    asserted: dict[tuple[str, str], list[str]] = {}
    denied: dict[tuple[str, str], list[str]] = {}
    measured: dict[str, tuple[str, str]] = {}  # node -> (column, fact)
    cites: set[str] = set()

    def ensure(node: str, fact: Fact) -> None:
        if not _NODE_ID.match(node):
            raise BuildError(f"Fact {fact.id} names {node!r}, which is not a valid factor name.")
        if node not in roles:
            roles[node] = None
            node_order.append(node)

    for fact in sorted(facts, key=lambda f: (len(f.id), f.id)):
        if fact.status is not FactStatus.confirmed or not fact.supports:
            continue
        nodes_here: list[str] = []
        columns_here: list[str] = []
        for item in fact.supports:
            m = _SUPPORT.match(item.strip())
            if m is None:  # the store's parser already refuses these; never guess
                raise BuildError(f"Fact {fact.id} has a 'supports' item we cannot read: {item}.")
            if m["kind"]:
                a, b = m["a"], m["b"]
                ensure(a, fact)
                ensure(b, fact)
                (asserted if m["kind"] == "edge" else denied).setdefault((a, b), []).append(fact.id)
            elif m["one"] == "node":
                ensure(m["x"], fact)
                nodes_here.append(m["x"])
            else:
                columns_here.append(m["x"])
        if len(nodes_here) == 1 and len(columns_here) == 1:
            node, column = nodes_here[0], columns_here[0]
            if node in measured and measured[node][0] != column:
                other = measured[node][1]
                raise BuildError(
                    f"Facts {other} and {fact.id} name different columns for {_words(node, labels)}. "
                    "Keep one of them, then build again."
                )
            measured[node] = (column, fact.id)
        cites.add(fact.id)

    for pair, ids in asserted.items():
        if pair in denied:
            raise BuildError(
                f"Facts {', '.join(ids)} and {', '.join(denied[pair])} disagree about whether "
                f"{_words(pair[0], labels)} affects {_words(pair[1], labels)}. "
                "Keep one of them, then build again."
            )
        if (pair[1], pair[0]) in asserted:
            back = asserted[(pair[1], pair[0])]
            raise BuildError(
                f"Facts {', '.join(ids)} and {', '.join(back)} say {_words(pair[0], labels)} and "
                f"{_words(pair[1], labels)} each affect the other. Keep one direction, then build again."
            )
    key = (template.treatment, template.outcome)
    if key in denied:
        raise BuildError(
            f"Fact {', '.join(denied[key])} says the discount does not affect sales. That effect is what "
            "truelift measures, so the arrow stays; change the fact if it was meant differently."
        )

    edges = set(defaults) - set(denied)
    for a, b in asserted:
        edges.discard((b, a))  # a reversal of a template default
        edges.add((a, b))
    ordered = [e for e in template_order if e in edges]
    ordered += sorted(edges - set(ordered))

    # Columns: discount and sales from the confirmed mapping, other factors from facts.
    treatment_col = _mapped(mapping, ("treatment_rate", "treatment_spend"))
    outcome_col = _mapped(mapping, ("outcome",))
    if treatment_col is None or outcome_col is None:
        raise BuildError("Confirm which columns hold your sales and your discount first, then build again.")
    columns = {node: column for node, (column, _) in measured.items()}
    columns[template.treatment], columns[template.outcome] = treatment_col, outcome_col
    for node, (column, fact_id) in measured.items():
        if mapping.get(column) is None:
            raise BuildError(
                f"Fact {fact_id} says {_words(node, labels)} is measured by the column {column}, "
                "which is not in your file's column list."
            )

    graph = nx.DiGraph(ordered)
    graph.add_nodes_from(node_order)
    if not nx.is_directed_acyclic_graph(graph):
        loop = [a for a, _ in nx.find_cycle(graph)]
        words = " -> ".join(_words(n, labels) for n in [*loop, loop[0]])
        raise BuildError(
            f"The confirmed facts make a loop: {words}. Change one of these facts, then build again."
        )
    for node in node_order:
        if roles[node] is None:
            roles[node] = _infer_role(graph, node, template.treatment, template.outcome)

    try:
        dag = Dag.from_content(
            {
                "treatment": template.treatment,
                "outcome": template.outcome,
                "nodes": [
                    {
                        "id": n,
                        "role": roles[n],
                        "label": labels.get(n) or n.replace("_", " ").capitalize(),
                        **({"column": columns[n]} if n in columns else {}),
                    }
                    for n in node_order
                ],
                "edges": [list(e) for e in ordered],
            }
        )
    except DagError as exc:  # pragma: no cover - the checks above cover what Dag refuses
        raise BuildError(str(exc)) from exc

    basis = [
        EdgeBasis(
            from_=a,
            to=b,
            facts=sorted(set(asserted.get((a, b), [])), key=lambda f: (len(f), f)),
            sentence=sentences.get((a, b)) or f"{_words(a, labels, start=True)} affects {_words(b, labels)}.",
        )
        for a, b in ordered
    ]
    draft = DagDraft(template=template.id, dag=dag, edges=basis)
    return Built(draft=draft, cites=sorted(cites, key=lambda f: (len(f), f)))


def _mapped(mapping: ColumnMapping, roles: tuple[str, ...]) -> str | None:
    for role in roles:
        found = mapping.by_role(role)
        if found:
            return found[0].name
    return None


def _infer_role(graph: nx.DiGraph, node: str, t: str, y: str) -> NodeRole:
    """A role for a factor the template does not have, from where the facts put it."""
    if node in nx.descendants(graph, t):
        return "mediator"
    below = nx.descendants(graph, node)
    if t in below and y in below:
        return "confounder"
    return "predictor"


def _words(node: str, labels: dict[str, str], *, start: bool = False) -> str:
    label = labels.get(node) or node.replace("_", " ")
    if start:
        return label[:1].upper() + label[1:]
    if len(label) > 1 and label[0].isupper() and label[1].islower():
        return label[0].lower() + label[1:]
    return label
