"""G06/A1: a DAG's YAML round-trips byte-identically, and a cycle is refused with a message (C3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.causal.support import golden_inputs
from tests.golden.cases import case_paths, load_case
from truelift.causal.dag import Dag, DagError

PATHS = case_paths()


def _dag(**changes) -> dict:
    base = {
        "treatment": "discount",
        "outcome": "sales",
        "nodes": [
            {"id": "discount", "role": "treatment", "label": "Your discount", "column": "discount_rate"},
            {"id": "sales", "role": "outcome", "label": "Your sales", "column": "revenue"},
            {"id": "holiday_weeks", "role": "confounder", "label": "Holiday weeks", "column": "holiday"},
            {"id": "store_traffic", "role": "mediator", "label": "Store traffic"},
            {
                "id": "market_demand",
                "role": "confounder",
                "proxy": {"column": "cat_sales", "rule": "category_sales_excl_own"},
            },
        ],
        "edges": [
            ["discount", "sales"],
            ["holiday_weeks", "discount"],
            ["holiday_weeks", "sales"],
            ["discount", "store_traffic"],
            ["store_traffic", "sales"],
            ["market_demand", "discount"],
            ["market_demand", "sales"],
        ],
        "modifiers": ["holiday_weeks"],
        "risk_accepted": [],
    }
    return base | changes


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_golden_dag_round_trips_byte_identically(path: Path) -> None:
    dag, _, _ = golden_inputs(load_case(path))
    text = dag.to_yaml()
    again = Dag.from_yaml(text)
    assert again == dag
    assert again.to_yaml() == text
    assert text.encode("utf-8") == Dag.from_yaml(text).to_yaml().encode("utf-8")


def test_round_trip_keeps_labels_proxies_and_order() -> None:
    dag = Dag.from_content(_dag())
    text = dag.to_yaml()
    assert text.startswith("schema: truelift.dag/1\n")
    assert "proxy: {column: cat_sales, rule: category_sales_excl_own}" in text
    assert Dag.from_yaml(text).to_yaml() == text
    # The store keeps the same plain data as the version's content.
    assert Dag.from_content(dag.to_content()) == dag


def test_awkward_column_names_survive_the_round_trip() -> None:
    nodes = _dag()["nodes"]
    nodes[2] = nodes[2] | {"column": "yes"}  # YAML 1.1 would read a bare yes as true
    nodes[0] = nodes[0] | {"column": "Rabatt %: Anteil"}
    dag = Dag.from_content(_dag(nodes=nodes))
    again = Dag.from_yaml(dag.to_yaml())
    assert again.node("holiday_weeks").column == "yes"
    assert again.node("discount").column == "Rabatt %: Anteil"
    assert again.to_yaml() == dag.to_yaml()


def test_a_cycle_is_refused_with_a_message_naming_the_loop() -> None:
    edges = _dag()["edges"] + [["sales", "holiday_weeks"]]
    with pytest.raises(DagError) as err:
        Dag.from_content(_dag(edges=edges))
    msg = str(err.value)
    assert "loop" in msg
    for words in ("Your sales", "Holiday weeks"):
        assert words in msg
    # Control: the same diagram without the extra arrow is accepted.
    Dag.from_content(_dag())


def test_a_cycle_in_yaml_text_is_refused_too() -> None:
    text = (
        Dag.from_content(_dag())
        .to_yaml()
        .replace("- [discount, sales]", "- [discount, sales]\n- [sales, discount]")
    )
    with pytest.raises(DagError, match="loop"):
        Dag.from_yaml(text)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"edges": [["holiday_weeks", "discount"]]}, "arrow discount -> sales is missing"),
        ({"edges": _dag()["edges"] + [["ghost", "sales"]]}, "not in the diagram"),
        ({"edges": _dag()["edges"] + [["discount", "sales"]]}, "appears twice"),
        ({"edges": _dag()["edges"] + [["sales", "sales"]]}, "cannot cause itself"),
        ({"modifiers": ["nobody"]}, "not in the diagram"),
        ({"treatment": "holiday_weeks"}, "role treatment"),
    ],
)
def test_malformed_dags_are_refused(changes: dict, message: str) -> None:
    with pytest.raises(DagError, match=message):
        Dag.from_content(_dag(**changes))


def test_duplicate_yaml_keys_are_refused() -> None:
    with pytest.raises(DagError, match="duplicate key"):
        Dag.from_yaml("treatment: discount\ntreatment: sales\n")
