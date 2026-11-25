"""G06/A2 and A5: identify() and compile_config() reproduce every golden case of G05 (C3, C2).

Each block reason must also be a business-language sentence that names what is missing. Offline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.causal.support import FINGERPRINT, golden_inputs
from tests.golden.cases import case_paths, load_case
from truelift.causal.compile import CompileError, Profile, compile_config
from truelift.causal.identify import identify
from truelift.causal.rules import RuleSet, load_rules

PATHS = case_paths()
# A snake_case identifier or a leftover placeholder must never reach the user.
_CODE_WORD = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b|[{}]")


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return load_rules()


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_identify_matches_golden_case(path: Path, rules: RuleSet) -> None:
    case = load_case(path)
    exp = case.expected
    dag, mapping, panel = golden_inputs(case)
    got = identify(dag, mapping, panel, rules)

    assert got.decision == exp.decision
    assert [(b.code, b.node_ids, b.remedies) for b in got.blocks] == [
        (b.code, b.node_ids, b.remedies) for b in exp.blocks
    ]
    if exp.decision == "identified":
        assert got.adjustment_set == exp.adjustment_set
        assert got.x_cols == exp.x_cols
        assert got.fixed_effects == exp.fixed_effects
        assert got.cate_covariates == exp.cate_covariates
        assert got.cate_degree == exp.cate_degree
        assert [(w.code, w.subjects) for w in got.warnings] == [
            (w.code, w.subjects) for w in exp.warnings or []
        ]


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_compile_matches_golden_case(path: Path, rules: RuleSet) -> None:
    case = load_case(path)
    dag, mapping, panel = golden_inputs(case)
    want = case.expected.compile

    def run():
        return compile_config(
            dag,
            mapping,
            panel,
            rules,
            profile=Profile.standard,
            data_fingerprint=FINGERPRINT,
            margin=case.margin,
        )

    if case.expected.decision == "blocked":
        with pytest.raises(CompileError) as err:
            run()
        assert err.value.code == "not_identified"
        return
    if want is not None and want.error:
        with pytest.raises(CompileError) as err:
            run()
        assert err.value.code == want.error
        assert not _CODE_WORD.search(err.value.message), err.value.message
        return
    config = run()
    orch = config.orchestrator
    exp = case.expected
    # x_cols_list is the adjustment set's columns plus the region (and category) dummies.
    dummies = [n for d in config.dummies for n in d.names]
    assert orch.x_cols_list == [exp.x_cols + dummies]
    assert [d.column for d in config.dummies] == exp.fixed_effects
    assert orch.covariates_for_cate_list == [exp.cate_covariates]
    if exp.cate_degree is not None:
        assert orch.cate_structure_list[0]["degree"] == exp.cate_degree
    if want is not None:
        assert orch.treatment_types == want.treatment_types
        assert orch.sales_col == want.sales_col
        assert orch.treatment_spend_cols == want.treatment_spend_cols
        assert orch.opt_threshold_roi == want.opt_threshold_roi
        if want.scalers is not None:
            assert config.scaler.median_normalize_cols == want.scalers.median_normalize_cols
            assert (
                config.scaler.population_median_normalize_cols
                == want.scalers.population_median_normalize_cols
            )


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_every_reason_is_a_business_sentence_naming_the_missing_item(path: Path, rules: RuleSet) -> None:
    case = load_case(path)
    dag, mapping, panel = golden_inputs(case)
    got = identify(dag, mapping, panel, rules)
    vocabulary = {n.id: n.label for t in rules.templates.values() for n in t.nodes}

    columns = sorted((c.name for c in mapping.columns), key=len, reverse=True)
    for item in [*got.blocks, *got.warnings]:
        text = item.message
        assert text.rstrip().endswith("."), text
        # The user's own column names may appear verbatim; any other code word may not.
        words = text
        for name in columns:
            words = words.replace(name, "COLUMN")
        assert words[:1].isupper() or words[:1].isdigit(), text
        assert not _CODE_WORD.search(words), f"{item.code}: code words in {text!r}"
    for w in got.warnings:  # column names are quoted exactly as the file spells them
        for subject in w.subjects:
            if mapping.get(subject):
                assert subject in w.message, (w.code, subject, w.message)
    for block in got.blocks:
        for node in block.node_ids:  # the node is named in words, not by its ID
            label = dag.label_of(node, vocabulary)
            assert label.lower() in block.message.lower(), (block.code, label, block.message)
        numbers = {
            "too_few_weeks": [panel.weeks],
            "too_few_regions": [panel.regions],
            "too_few_rows": [panel.rows],
            "too_few_treatment_levels": [panel.treatment_levels],
        }.get(block.code, [])
        for n in numbers:
            assert f"{n:,}" in block.message, (block.code, block.message)
        if block.code in ("too_few_treated_rows", "too_few_untreated_rows", "panel_gaps"):
            assert "%" in block.message


def test_golden_set_exercises_every_block_and_both_decisions(rules: RuleSet) -> None:
    codes, decisions = set(), set()
    for path in PATHS:
        dag, mapping, panel = golden_inputs(load_case(path))
        got = identify(dag, mapping, panel, rules)
        decisions.add(got.decision)
        codes |= {b.code for b in got.blocks}
    assert decisions == {"identified", "blocked"}
    assert codes == set(rules.identification.blocks)
