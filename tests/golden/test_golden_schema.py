"""The golden cases parse and cover what C3 requires (G05/A4). Offline.

G06 runs the same cases through ``truelift.causal.identify`` and ``compile`` (G06/A2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.golden.cases import A4_REQUIRED, GoldenCase, case_paths, load_case
from truelift.causal.rules import RuleSet, load_rules

PATHS = case_paths()


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return load_rules()


@pytest.fixture(scope="module")
def cases() -> list[GoldenCase]:
    return [load_case(p) for p in PATHS]


def test_schema_at_least_fifteen_golden_cases() -> None:
    assert len(PATHS) >= 15


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_schema_golden_case(path: Path, rules: RuleSet) -> None:
    case = load_case(path)
    assert case.id == path.stem
    if case.template:
        assert case.template in rules.templates
    for n in case.dag.nodes:
        if n.proxy:
            assert rules.proxies.by_id(n.proxy.rule)
    # Every case states its expected outcome.
    if case.expected.decision == "identified":
        assert case.expected.adjustment_set is not None and case.expected.x_cols is not None
    else:
        assert case.expected.blocks


def test_schema_golden_cases_cover_a4(cases: list[GoldenCase]) -> None:
    covered = {c for case in cases for c in case.covers}
    assert set(A4_REQUIRED) <= covered, sorted(set(A4_REQUIRED) - covered)


def test_schema_golden_cases_cover_every_block_code(cases: list[GoldenCase], rules: RuleSet) -> None:
    seen = {b.code for case in cases for b in case.expected.blocks}
    assert seen == set(rules.identification.blocks)


def test_schema_golden_cases_use_every_template(cases: list[GoldenCase], rules: RuleSet) -> None:
    assert {c.template for c in cases} >= set(rules.templates)
