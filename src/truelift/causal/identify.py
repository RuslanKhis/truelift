"""Identification: may this DAG, mapping and panel be estimated, and with which controls? (C3, D3)

Pure code, no model. The rules come from ``rules/identification.yaml`` and ``rules/cate.yaml``
(Thao's, D18); the golden cases in ``tests/golden`` pin the expected answers (G05/A4, G06/A2).

The run is blocked when

* (C3a) something the discount causes is labelled as a confounder, predictor or modifier, or
  named as an effect modifier (G05 ruling R4; a node correctly labelled ``mediator`` is left out
  without a block);
* (C3b) a back-door path stays open given the adjustment set, because a node on it has no
  column, no accepted proxy and no explicit risk acceptance. One block per such node;
* (C3c, C3d) panel size, treatment variation or gaps miss a threshold.

The adjustment set follows ``adjustment.rule: ancestral_v1``: every node with usable data that is
an ancestor of the discount or of sales, minus the discount, sales and anything the discount
causes. Its validity is checked with networkx d-separation on the graph with the discount's
outgoing arrows removed (the back-door graph). Ground-truth columns never count as data (C4).

Every block and warning carries a message in business words, filled from the rule file.
"""

from __future__ import annotations

from typing import Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict

from truelift.causal.dag import Dag
from truelift.causal.forbidden import DEFAULT, DenyList
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.causal.rules import Remedy, RuleSet

CONTROL_ROLES = ("confounder", "predictor", "modifier")
TREATMENT_ROLES = ("treatment_rate", "treatment_spend")
# Mapping roles whose columns are never data for a DAG node.
NOT_DATA_ROLES = ("ignore", "date", "outcome", "treatment_rate", "treatment_spend")


class IdentifyInputError(ValueError):
    """The DAG and the mapping do not fit together (a missing column, an invalid stand-in)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Block(_Strict):
    code: str
    contract: str
    node_ids: list[str]
    remedies: list[Remedy]
    message: str


class Notice(_Strict):
    """A warning shown beside the result; it never blocks (C6)."""

    code: str
    subjects: list[str]
    message: str


class Identification(_Strict):
    decision: Literal["identified", "blocked"]
    blocks: list[Block] = []
    adjustment_set: list[str] = []
    x_cols: list[str] = []
    fixed_effects: list[str] = []
    cate_covariates: list[str] = []
    cate_degree: int | None = None
    warnings: list[Notice] = []
    risk_accepted: list[str] = []

    @property
    def identified(self) -> bool:
        return self.decision == "identified"


def identify(
    dag: Dag,
    mapping: ColumnMapping,
    panel: PanelSummary,
    rules: RuleSet,
    *,
    deny: DenyList = DEFAULT,
) -> Identification:
    t, y = dag.treatment, dag.outcome
    graph = dag.graph()
    words = _Words(dag, rules)
    data_col, forbidden_cols = _data_columns(dag, mapping, rules, deny)
    after_t = nx.descendants(graph, t)
    blocks: list[Block] = []

    # C3a: something the discount causes is used to explain the discount or sales.
    for n in dag.nodes:
        if n.id in after_t and (n.role in CONTROL_ROLES or n.id in dag.modifiers):
            blocks.append(words.block("descendant_in_controls", [n.id], node_labels=words.label(n.id)))

    # C3b: the ancestral adjustment set must close every back-door path.
    relevant = nx.ancestors(graph, t) | nx.ancestors(graph, y)
    relevant -= after_t | {t, y}
    z = {n for n in relevant if n in data_col}
    accepted = set(dag.risk_accepted)
    backdoor = graph.copy()
    backdoor.remove_edges_from(list(graph.out_edges(t)))
    if not nx.is_d_separator(backdoor, {t}, {y}, z | accepted):
        missing: set[str] = set()
        for path in _open_backdoor_paths(backdoor, t, y, z | accepted):
            missing |= {n for n in path[1:-1] if n not in data_col and n not in accepted}
        for node in sorted(missing):
            remedies = [
                r
                for r in rules.identification.blocks["unobserved_confounder"].remedies
                if r != "use_proxy" or rules.proxies.for_node(node)
            ]
            blocks.append(
                words.block("unobserved_confounder", [node], remedies=remedies, node_labels=words.label(node))
            )

    # C3c, C3d: panel size, treatment variation and gaps.
    blocks += _threshold_blocks(panel, rules, words)
    blocks.sort(key=lambda b: (b.code, b.node_ids))
    if blocks:
        return Identification(decision="blocked", blocks=blocks)

    adjustment = sorted(z)
    x_cols = sorted(data_col[n] for n in adjustment)
    fixed = sorted(c.name for c in mapping.columns if c.role in ("region", "category"))
    notices = [words.notice("forbidden_excluded", [c], column=c) for c in sorted(forbidden_cols)]

    few = rules.identification.warnings["few_regions"].below
    if few is not None and panel.regions < few:
        notices.append(words.notice("few_regions", [], regions=_count(panel.regions)))
    proxied = sorted(n.id for n in dag.nodes if n.proxy and n.id in z)
    if proxied:
        text = " ".join(
            words.fill(
                rules.identification.warnings["proxy_used"].message,
                proxy_column=dag.node(n).proxy.column,  # type: ignore[union-attr]
                node_label=words.label(n),
                caveat=rules.proxies.by_id(dag.node(n).proxy.rule).caveat,  # type: ignore[union-attr]
            )
            for n in proxied
        )
        notices.append(Notice(code="proxy_used", subjects=proxied, message=text))
    if accepted:
        notices.append(
            words.notice("risk_accepted", sorted(accepted), node_label=words.labels(sorted(accepted)))
        )
    left_out = sorted(
        n.id for n in dag.nodes if n.role in CONTROL_ROLES and n.id in data_col and n.id not in z | after_t
    )
    if left_out:
        notices.append(words.notice("left_out", left_out, node_labels=words.labels(left_out)))

    # CATE covariates (rules/cate.yaml): confirmed modifiers with data, not caused by the discount.
    eligible = sorted(data_col[m] for m in dag.modifiers if m in data_col and m not in after_t)
    cap = int(rules.cate.covariates.max_count.value)
    cate, dropped = eligible[:cap], eligible[cap:]
    if dropped:
        notices.append(
            words.notice("cate_capped", dropped, kept=_join(cate), dropped=_join(dropped), source="cate")
        )
    degree = None
    if cate:
        degree = rules.cate.degree_for(panel.rows)
        if panel.rows < rules.cate.structure.degree.small_sample_rows:
            notices.append(words.notice("cate_small_sample", [], rows=_count(panel.rows), source="cate"))
    notices.sort(key=lambda w: (w.code, w.subjects))

    return Identification(
        decision="identified",
        adjustment_set=adjustment,
        x_cols=x_cols,
        fixed_effects=fixed,
        cate_covariates=cate,
        cate_degree=degree,
        warnings=notices,
        risk_accepted=sorted(accepted),
    )


# --- data sources -------------------------------------------------------------------------


def _data_columns(
    dag: Dag, mapping: ColumnMapping, rules: RuleSet, deny: DenyList
) -> tuple[dict[str, str], set[str]]:
    """Node ID -> the column that measures it (own column or accepted proxy), and the
    ground-truth columns that were excluded. Raises IdentifyInputError on a mismatch."""
    for name, roles in ((dag.treatment, TREATMENT_ROLES), (dag.outcome, ("outcome",))):
        column = dag.node(name).column
        mapped = mapping.get(column) if column else None
        if mapped is None or mapped.role not in roles:
            raise IdentifyInputError(f"{column!r} must be mapped as {' or '.join(roles)} for node {name!r}")
        if deny.is_forbidden(mapped.name):
            raise IdentifyInputError(f"{mapped.name!r} is ground truth and cannot be the {name} column")

    data_col: dict[str, str] = {}
    forbidden: set[str] = set()
    for n in dag.nodes:
        if n.id in (dag.treatment, dag.outcome):
            continue
        if n.column:
            mapped = mapping.get(n.column)
            if mapped is None:
                raise IdentifyInputError(f"node {n.id!r}: column {n.column!r} is not in the mapping")
            if deny.is_forbidden(n.column):
                forbidden.add(n.column)
            elif mapped.role not in NOT_DATA_ROLES:
                data_col[n.id] = n.column
        elif n.proxy:
            mapped = mapping.get(n.proxy.column)
            if mapped is None:
                raise IdentifyInputError(
                    f"node {n.id!r}: stand-in column {n.proxy.column!r} is not in the mapping"
                )
            try:
                rule = rules.proxies.by_id(n.proxy.rule)
            except KeyError:
                raise IdentifyInputError(f"node {n.id!r}: no stand-in rule {n.proxy.rule!r}") from None
            if n.id not in rule.stands_for:
                raise IdentifyInputError(f"node {n.id!r}: stand-in rule {rule.id!r} does not cover it")
            if mapped.type not in rule.semantic_types:
                raise IdentifyInputError(
                    f"node {n.id!r}: stand-in {mapped.name!r} is a {mapped.type}, rule {rule.id!r} needs "
                    f"{' or '.join(rule.semantic_types)}"
                )
            if deny.is_forbidden(mapped.name):
                forbidden.add(mapped.name)
            elif mapped.role not in NOT_DATA_ROLES:
                data_col[n.id] = mapped.name
    return data_col, forbidden


# --- back-door paths ----------------------------------------------------------------------


def _open_backdoor_paths(backdoor: nx.DiGraph, t: str, y: str, z: set[str]) -> list[list[str]]:
    """Every simple path from t to y in the back-door graph that is open given z.

    In the back-door graph the treatment has no outgoing arrows, so every path from it starts
    with an arrow into it. Diagrams here have tens of nodes, so enumerating paths is affordable.
    """

    def is_open(path: list[str]) -> bool:
        for prev, node, nxt in zip(path, path[1:], path[2:], strict=False):
            if backdoor.has_edge(prev, node) and backdoor.has_edge(nxt, node):  # a collider
                if not ({node} | nx.descendants(backdoor, node)) & z:
                    return False
            elif node in z:
                return False
        return True

    undirected = backdoor.to_undirected(as_view=True)
    return [p for p in nx.all_simple_paths(undirected, t, y) if is_open(p)]


def _threshold_blocks(panel: PanelSummary, rules: RuleSet, words: _Words) -> list[Block]:
    th = rules.identification.threshold
    checks = [
        (
            "too_few_weeks",
            panel.weeks < th("min_weeks"),
            {"weeks": _count(panel.weeks), "min": _count(th("min_weeks"))},
        ),
        (
            "too_few_regions",
            panel.regions < th("min_regions"),
            {"regions": _count(panel.regions), "min": _count(th("min_regions"))},
        ),
        (
            "too_few_rows",
            panel.rows < th("min_rows"),
            {"rows": _count(panel.rows), "min": _count(th("min_rows"))},
        ),
        (
            "too_few_treated_rows",
            panel.treated_share < th("min_treated_share"),
            {"share": _pct(panel.treated_share), "min": _pct(th("min_treated_share"))},
        ),
        (
            "too_few_untreated_rows",
            panel.untreated_share < th("min_untreated_share"),
            {"share": _pct(panel.untreated_share), "min": _pct(th("min_untreated_share"))},
        ),
        (
            "too_few_treatment_levels",
            panel.treatment_levels < th("min_treatment_levels"),
            {"levels": _count(panel.treatment_levels), "min": _count(th("min_treatment_levels"))},
        ),
        (
            "panel_gaps",
            panel.gap_share > th("max_gap_share"),
            {"share": _pct(panel.gap_share), "max": _pct(th("max_gap_share"))},
        ),
    ]
    return [words.block(code, [], **values) for code, failed, values in checks if failed]


# --- business words -----------------------------------------------------------------------


class _Words:
    """Fills the rule file's messages with node labels and numbers."""

    def __init__(self, dag: Dag, rules: RuleSet):
        self.dag, self.rules = dag, rules
        self.vocabulary = {n.id: n.label for t in rules.templates.values() for n in t.nodes}

    def label(self, node_id: str) -> str:
        return _mid_sentence(self.dag.label_of(node_id, self.vocabulary))

    def labels(self, node_ids: list[str]) -> str:
        return _join([self.label(n) for n in node_ids])

    def block(
        self, code: str, node_ids: list[str], *, remedies: list[Remedy] | None = None, **values: str
    ) -> Block:
        rule = self.rules.identification.blocks[code]
        return Block(
            code=code,
            contract=rule.contract,
            node_ids=node_ids,
            remedies=list(rule.remedies if remedies is None else remedies),
            message=self.fill(rule.message, **values),
        )

    def notice(
        self, code: str, subjects: list[str], *, source: str = "identification", **values: str
    ) -> Notice:
        table = self.rules.cate.warnings if source == "cate" else self.rules.identification.warnings
        return Notice(code=code, subjects=subjects, message=self.fill(table[code].message, **values))

    @staticmethod
    def fill(template: str, **values: str) -> str:
        text = " ".join(template.format_map(values).split())
        # A sentence that opens with a node's words starts with a capital; one that opens with a
        # column name keeps the column exactly as the user's file spells it.
        if template.lstrip().startswith("{node_label"):
            text = text[:1].upper() + text[1:]
        return text


def _mid_sentence(label: str) -> str:
    """'The time of year' -> 'the time of year', but keep 'TV' or 'GRPs' as written."""
    if len(label) > 1 and label[0].isupper() and label[1].islower():
        return label[0].lower() + label[1:]
    return label


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _count(value: float) -> str:
    return f"{int(value):,}"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}".rstrip("0").rstrip(".") + "%"
