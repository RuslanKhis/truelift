"""G31/A1 and A2: the DAG builder turns confirmed facts and a template into a DAG version (C1, C3).

A1: the same facts and template give byte-identical content (and, under the same clock, a
byte-identical ``dag/vN.yaml``); each edge cites its supporting facts or is ``assumed``.
A2: no edge appears without a confirmed fact or a template default; unconfirmed facts and a
rejected proposal change nothing. Offline.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from truelift.causal.build import BuildError, DagDraft, build_dag
from truelift.causal.mapping import ColumnMapping
from truelift.causal.rules import RuleSet, load_rules
from truelift.store import ProjectStore, VersionKind
from truelift.store.db import StateDb
from truelift.store.knowledge import Fact, FactStatus, Source, SourceKind

RULES: RuleSet = load_rules()
TEMPLATE = RULES.templates["store_chain"]
VOCABULARY = {n.id: n.label for t in RULES.templates.values() for n in t.nodes}
MAPPING = ColumnMapping.model_validate(
    {
        "columns": [
            {"name": "week", "role": "date", "type": "date"},
            {"name": "region", "role": "region", "type": "key"},
            {"name": "revenue", "role": "outcome", "type": "money"},
            {"name": "discount_rate", "role": "treatment_rate", "type": "rate", "bounded_0_1": True},
            {"name": "discount_spend", "role": "treatment_spend", "type": "money"},
            {"name": "holiday", "role": "control", "type": "flag"},
            {"name": "media_grps", "role": "control", "type": "index"},
        ]
    }
)


def fact(fid: str, *supports: str, status: FactStatus = FactStatus.confirmed) -> Fact:
    return Fact(
        id=fid,
        text=f"Statement {fid} from the interview.",
        status=status,
        source=Source(SourceKind.interview, 3, "as the user said it"),
        supports=supports,
    )


FACTS = [
    fact("F001", "edge(competitor_promo -> discount)"),  # adds a template edge that is absent by default
    fact("F002", "no-edge(inventory_age -> discount)"),  # removes a default
    fact("F003", "node(holiday_weeks)", "column(holiday)"),  # a node measured by a column
    fact("F004", "edge(loyalty_app -> sales)"),  # a factor no template has
    fact("F005", "edge(media -> sales)"),  # confirms a default
    fact("F006", "column(revenue)"),  # describes a column only
]


def build(facts=FACTS, mapping=MAPPING):
    return build_dag(TEMPLATE, facts, mapping, vocabulary=VOCABULARY)


def edges(built) -> dict[tuple[str, str], list[str]]:
    return {(e.from_, e.to): e.facts for e in built.draft.edges}


# --- A1 -----------------------------------------------------------------------------------


def test_same_facts_and_template_give_byte_identical_content() -> None:
    first = build()
    shuffled = FACTS[:]
    random.Random(7).shuffle(shuffled)
    second = build(shuffled)
    dump = lambda b: yaml.safe_dump(b.draft.to_content(), sort_keys=False, allow_unicode=True)  # noqa: E731
    assert dump(first) == dump(second)
    assert first.cites == second.cites
    assert DagDraft.from_content(yaml.safe_load(dump(first))) == first.draft  # the stored form reads back


def test_same_facts_write_a_byte_identical_version_file(tmp_path: Path) -> None:
    clock = lambda: datetime(2026, 11, 27, 9, 0, tzinfo=UTC)  # noqa: E731
    files = []
    for name in ("a", "b"):
        store = ProjectStore(tmp_path / name / "projects", StateDb(tmp_path / name / "state.db"), clock=clock)
        pid = store.create("Pet food").id
        built = build()
        store.write_version(
            pid, VersionKind.dag, built.draft.to_content(), expected_current=None, cites=built.cites
        )
        files.append((tmp_path / name / "projects" / pid / "dag" / "v1.yaml").read_bytes())
    assert files[0] == files[1]


def test_each_edge_cites_its_fact_or_is_assumed() -> None:
    built = build()
    got = edges(built)
    assert got[("competitor_promo", "discount")] == ["F001"]
    assert got[("media", "sales")] == ["F005"]
    assert got[("loyalty_app", "sales")] == ["F004"]
    assert got[("holiday_weeks", "discount")] == []  # a template default nobody confirmed
    for e in built.draft.edges:
        assert e.basis == ("fact" if e.facts else "assumed")
        assert e.sentence.endswith(".")
    assert built.cites == ["F001", "F002", "F003", "F004", "F005", "F006"]


def test_facts_shape_the_diagram() -> None:
    built = build()
    got = edges(built)
    dag = built.draft.dag
    assert ("inventory_age", "discount") not in got  # removed by F002
    assert ("inventory_age", "sales") in got  # the rest of the template stays
    assert dag.node("holiday_weeks").column == "holiday"
    assert dag.node("discount").column == "discount_rate" and dag.node("sales").column == "revenue"
    assert dag.node("loyalty_app").role == "predictor"  # inferred: it only drives sales
    assert dag.node("loyalty_app").label == "Loyalty app"
    assert built.draft.template == "store_chain"
    # The order is the template's, then added edges by name.
    order = [(e.from_, e.to) for e in built.draft.edges]
    assert order[0] == ("discount", "sales") and order[-1] == ("loyalty_app", "sales")


def test_a_reversal_replaces_the_template_default() -> None:
    built = build([fact("F010", "edge(store_traffic -> discount)")])
    got = edges(built)
    assert ("store_traffic", "discount") in got
    assert ("discount", "store_traffic") not in got
    assert built.draft.dag.node("store_traffic").role == "mediator"  # the template's label stays


def test_a_factor_from_another_template_keeps_its_words() -> None:
    other = next(
        (n for t in RULES.templates.values() for n in t.nodes if n.id not in {m.id for m in TEMPLATE.nodes}),
        None,
    )
    assert other is not None
    built = build([fact("F011", f"edge({other.id} -> sales)")])
    assert built.draft.dag.node(other.id).label == other.label


# --- A2 -----------------------------------------------------------------------------------


def test_no_edge_without_a_confirmed_fact_or_a_template_default() -> None:
    defaults = set(TEMPLATE.present_edges())
    built = build()
    for e in built.draft.edges:
        assert (e.from_, e.to) in defaults or e.facts, (e.from_, e.to)


@pytest.mark.parametrize("status", [FactStatus.assumed, FactStatus.unknown, FactStatus.contradicted])
def test_unconfirmed_facts_change_nothing(status: FactStatus) -> None:
    baseline = build([])
    noisy = build(
        [
            fact("F020", "edge(competitor_promo -> discount)", status=status),
            fact("F021", "no-edge(media -> discount)", status=status),
            fact("F022", "edge(agent_idea -> sales)", status=status),
        ]
    )
    assert noisy.draft.to_content() == baseline.draft.to_content()
    assert noisy.cites == []
    assert set(edges(baseline)) == set(TEMPLATE.present_edges())


# --- refusals -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("facts", "words"),
    [
        (
            [fact("F001", "edge(media -> discount)"), fact("F002", "no-edge(media -> discount)")],
            "F001 and F002 disagree",
        ),
        (
            [fact("F001", "edge(media -> weather)"), fact("F002", "edge(weather -> media)")],
            "each affect the other",
        ),
        ([fact("F001", "no-edge(discount -> sales)")], "that effect is what truelift measures"),
        ([fact("F001", "edge(sales -> season)")], "loop"),
        ([fact("F001", "node(media)", "column(tv_spend)")], "not in your file's column list"),
        (
            [
                fact("F001", "node(media)", "column(media_grps)"),
                fact("F002", "node(media)", "column(holiday)"),
            ],
            "different columns",
        ),
    ],
)
def test_contradictions_and_impossible_facts_are_refused_in_business_words(facts, words) -> None:
    with pytest.raises(BuildError) as err:
        build(facts)
    message = str(err.value)
    assert words.lower() in message.lower()
    for node in ("holiday_weeks", "store_traffic", "recent_sales_trend"):  # factors in words, not IDs
        assert node not in message


def test_the_discount_and_sales_columns_must_be_mapped_first() -> None:
    partial = ColumnMapping.model_validate(
        {"columns": [c for c in MAPPING.model_dump()["columns"] if c["role"] not in ("outcome",)]}
    )
    with pytest.raises(BuildError, match="sales and your discount"):
        build(mapping=partial)
