"""Every golden expectation agrees with an independent reference (tests/golden/oracle.py).

This checks Thao's expectations before G06 builds against them: a disagreement means the case
or the oracle is wrong and must be settled by Thao, not by loosening either. Offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.golden import oracle
from tests.golden.cases import case_paths, load_case
from truelift.causal.rules import RuleSet, load_rules

PATHS = case_paths()


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return load_rules()


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_oracle_agrees_with_golden_case(path: Path, rules: RuleSet) -> None:
    case = load_case(path)
    exp = case.expected.model_dump()
    got = oracle.analyse(case, rules)

    assert got.decision == exp["decision"]
    assert got.blocks == exp["blocks"]
    for name in ("adjustment_set", "x_cols", "fixed_effects", "cate_covariates", "cate_degree", "warnings"):
        assert getattr(got, name) == exp[name], name
    want = exp["compile"]
    if want is not None and want["error"]:
        assert got.compile == {"error": want["error"]}
    elif want is not None:
        for key in ("treatment_types", "sales_col", "treatment_spend_cols", "opt_threshold_roi", "scalers"):
            assert got.compile[key] == want[key], key
    if any(b["code"] == "unobserved_confounder" for b in exp["blocks"]):
        assert got.no_valid_set_exists, "a smaller set of the available columns would have worked"


# --- the oracle's own d-separation on graphs with known answers ---------------------------


def test_oracle_d_separation_basics() -> None:
    chain = [("a", "b"), ("b", "c")]
    assert not oracle.d_separated(chain, "a", "c", set())
    assert oracle.d_separated(chain, "a", "c", {"b"})
    fork = [("b", "a"), ("b", "c")]
    assert not oracle.d_separated(fork, "a", "c", set())
    assert oracle.d_separated(fork, "a", "c", {"b"})
    collider = [("a", "b"), ("c", "b"), ("b", "d")]
    assert oracle.d_separated(collider, "a", "c", set())
    assert not oracle.d_separated(collider, "a", "c", {"b"})
    assert not oracle.d_separated(collider, "a", "c", {"d"})  # a descendant of the collider


def test_oracle_open_paths_match_d_separation() -> None:
    m_bias = [("t", "y"), ("u1", "t"), ("u1", "c"), ("u2", "c"), ("u2", "y")]
    assert oracle.open_backdoor_paths(m_bias, "t", "y", set()) == []
    assert oracle.open_backdoor_paths(m_bias, "t", "y", {"c"}) == [["t", "u1", "c", "u2", "y"]]
