"""G06/A4: over random DAGs, no descendant of the discount, no outcome and no ground-truth column
ever reaches ``x_cols`` or the CATE covariates (C3, C4). Hypothesis, derandomised for CI.

It also checks soundness: whenever identification passes, the chosen controls (plus accepted
risks) close every back-door path in the diagram.
"""

from __future__ import annotations

import networkx as nx
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from truelift.causal import forbidden
from truelift.causal.compile import Profile, compile_config
from truelift.causal.dag import Dag
from truelift.causal.forbidden import DenyList
from truelift.causal.identify import identify
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.causal.rules import load_rules

RULES = load_rules()
PRIVATE_PREFIX = forbidden.FORBIDDEN_PREFIXES[1]  # decoded at runtime; never spelled here
SOURCES = ("column", "column", "column", "none", "truth", "private", "sidecar")
ROLES = ("confounder", "predictor", "modifier", "mediator", None)
TYPES = ("money", "volume", "rate", "index", "flag", "count")


@st.composite
def scenarios(draw):
    others = [f"n{i}" for i in range(draw(st.integers(0, 7)))]
    order = draw(st.permutations(["discount", "sales", *others]))
    if order.index("discount") > order.index("sales"):
        i, j = order.index("discount"), order.index("sales")
        order[i], order[j] = order[j], order[i]
    edges = [("discount", "sales")]
    for i, a in enumerate(order):
        for b in order[i + 1 :]:
            if (a, b) != ("discount", "sales") and draw(st.booleans()) and draw(st.booleans()):
                edges.append((a, b))

    nodes = [
        {"id": "discount", "role": "treatment", "column": "discount_rate"},
        {"id": "sales", "role": "outcome", "column": "revenue"},
    ]
    columns = [
        {"name": "week", "role": "date", "type": "date"},
        {"name": "region", "role": "region", "type": "key"},
        {"name": "revenue", "role": "outcome", "type": "money"},
        {"name": "discount_rate", "role": "treatment_rate", "type": "rate", "bounded_0_1": True},
        {"name": "discount_spend", "role": "treatment_spend", "type": "money"},
        {"name": "population", "role": "population", "type": "count"},
    ]
    sidecar, ground_truth = [], set()
    for n in others:
        node = {"id": n, "role": draw(st.sampled_from(ROLES))}
        source = draw(st.sampled_from(SOURCES))
        name = {
            "column": f"c_{n}",
            "truth": f"truth_{n}",
            "private": draw(st.sampled_from([PRIVATE_PREFIX, PRIVATE_PREFIX.upper()])) + f"_{n}",
            "sidecar": f"hidden_{n}",
        }.get(source)
        if name:
            node["column"] = name
            columns.append({"name": name, "role": "control", "type": draw(st.sampled_from(TYPES))})
        if source == "sidecar":
            sidecar.append(name)
        if source in ("truth", "private", "sidecar"):
            ground_truth.add(name)
        nodes.append(node)
    modifiers = draw(st.lists(st.sampled_from(others), unique=True)) if others else []
    accepted = draw(st.lists(st.sampled_from(others), unique=True, max_size=2)) if others else []
    dag = Dag.from_content(
        {
            "treatment": "discount",
            "outcome": "sales",
            "nodes": nodes,
            "edges": edges,
            "modifiers": modifiers,
            "risk_accepted": accepted,
        }
    )
    rows = draw(st.sampled_from([800, 1248]))
    panel = PanelSummary(
        weeks=156,
        regions=8,
        rows=rows,
        treated_share=0.35,
        untreated_share=0.4,
        treatment_levels=6,
        gap_share=0.0,
        levels={"region": [f"R{i}" for i in range(1, 9)]},
    )
    return dag, ColumnMapping.model_validate({"columns": columns}), panel, DenyList(sidecar), ground_truth


@settings(max_examples=400, derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenarios())
def test_no_descendant_outcome_or_ground_truth_in_controls_or_cate(scenario) -> None:
    # ground_truth is the scenario's own record of which columns it made as ground truth, so the
    # check does not trust the deny-list under test.
    dag, mapping, panel, deny, ground_truth = scenario
    got = identify(dag, mapping, panel, RULES, deny=deny)
    if not got.identified:
        assert got.blocks and not got.x_cols and not got.cate_covariates
        return

    graph = dag.graph()
    after = nx.descendants(graph, "discount")
    banned = {"revenue", "discount_rate", "discount_spend"} | ground_truth
    banned |= {dag.node(n).column for n in after if dag.node(n).column}
    for used in (got.x_cols, got.cate_covariates):
        assert not set(used) & banned
    assert not set(got.adjustment_set) & (after | {"discount", "sales"})

    # Soundness: the controls plus accepted risks satisfy the back-door criterion.
    backdoor = graph.copy()
    backdoor.remove_edges_from(list(graph.out_edges("discount")))
    assert nx.is_d_separator(
        backdoor, {"discount"}, {"sales"}, set(got.adjustment_set) | set(dag.risk_accepted)
    )

    # The compiled config inherits all of it.
    config = compile_config(
        dag, mapping, panel, RULES, profile=Profile.quick, data_fingerprint="sha256:x", deny=deny
    )
    x_cols = config.orchestrator.x_cols_list[0]
    cate = config.orchestrator.covariates_for_cate_list[0]
    for used in (x_cols, cate):
        assert not set(used) & banned
    assert set(x_cols) == set(got.x_cols) | {f"region_R{i}" for i in range(1, 9)}
