"""G06/A3 and A5: the compiled config is canonical, deterministic and follows the design's table (C2).

A3's second OS comes from CI: the committed reference ``fixtures/g18_standard.config.json`` is
compared byte for byte on Linux (``make check``) and macOS (the ``causal-macos`` job).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.causal.support import FINGERPRINT, golden_inputs
from tests.golden.cases import GOLDEN_DIR, load_case
from truelift.causal.compile import (
    COMPILER_VERSION,
    CompileError,
    PipelineConfig,
    Profile,
    compile_config,
)
from truelift.causal.dag import Dag
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.causal.rules import RuleSet, load_rules

REPO = Path(__file__).resolve().parents[2]
REFERENCE = Path(__file__).resolve().parent / "fixtures" / "g18_standard.config.json"
G18 = GOLDEN_DIR / "g18_percentage_with_spend.yaml"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return load_rules()


def _compile(rules: RuleSet, dag=None, mapping=None, panel=None, **kw) -> PipelineConfig:
    case = load_case(G18)
    d, m, p = golden_inputs(case)
    args = {"profile": Profile.standard, "data_fingerprint": FINGERPRINT, "margin": case.margin} | kw
    return compile_config(dag or d, mapping or m, panel or p, rules, **args)


# --- A3: canonical and deterministic ------------------------------------------------------


def test_config_matches_the_committed_reference_bytes(rules: RuleSet) -> None:
    assert _compile(rules).to_json() == REFERENCE.read_bytes()


def test_config_json_is_canonical(rules: RuleSet) -> None:
    raw = _compile(rules).to_json()
    data = json.loads(raw)
    assert raw == (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    assert data["compiler_version"] == COMPILER_VERSION
    assert data["data_fingerprint"] == FINGERPRINT
    assert PipelineConfig.from_json(raw).to_json() == raw


_CHILD = """
import sys
from pathlib import Path
from tests.causal.support import FINGERPRINT, golden_inputs
from tests.golden.cases import load_case
from truelift.causal.compile import Profile, compile_config
from truelift.causal.rules import load_rules
case = load_case(Path(sys.argv[1]))
d, m, p = golden_inputs(case)
c = compile_config(
    d, m, p, load_rules(), profile=Profile.standard, data_fingerprint=FINGERPRINT, margin=case.margin
)
sys.stdout.write(c.sha256())
"""


def test_two_processes_give_byte_identical_configs(rules: RuleSet) -> None:
    here = _compile(rules).sha256()
    shas = []
    for seed in ("1", "2"):  # different hash seeds: set and dict order must not leak into the bytes
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run(
            [sys.executable, "-c", _CHILD, str(G18)],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        shas.append(out.stdout)
    assert shas == [here, here]


def test_a_fact_the_dag_does_not_use_leaves_the_config_unchanged(rules: RuleSet) -> None:
    case = load_case(G18)
    dag, mapping, panel = golden_inputs(case)
    reference = _compile(rules).to_json()

    content = dag.to_content()
    # 1. A wording change: labels are for people, not for the pipeline.
    relabelled = json.loads(json.dumps(content))
    relabelled["nodes"][2]["label"] = "Bank holidays and Christmas"
    # 2. A factor the user mentioned that leads to neither the discount nor sales.
    unused = json.loads(json.dumps(content))
    unused["nodes"].append({"id": "weather", "role": "predictor", "label": "The weather"})
    # 3. Something sales cause (it is downstream of everything the analysis uses).
    downstream = json.loads(json.dumps(content))
    downstream["nodes"].append({"id": "store_traffic", "role": "mediator"})
    downstream["edges"].append(["sales", "store_traffic"])
    for variant in (relabelled, unused, downstream):
        assert _compile(rules, dag=Dag.from_content(variant)).to_json() == reference

    # 4. A column in the file that no node uses.
    extra = ColumnMapping.model_validate(
        {"columns": [*mapping.model_dump()["columns"], {"name": "notes", "role": "ignore", "type": "text"}]}
    )
    assert _compile(rules, mapping=extra).to_json() == reference

    # Controls: inputs the config does depend on change it.
    assert _compile(rules, margin=0.5).to_json() != reference
    assert _compile(rules, profile=Profile.quick).to_json() != reference
    assert _compile(rules, data_fingerprint="sha256:" + "1" * 64).to_json() != reference
    confounder = json.loads(json.dumps(content))
    confounder["nodes"].append({"id": "season", "role": "confounder", "column": "season_index"})
    confounder["edges"] += [["season", "discount"], ["season", "sales"]]
    more = ColumnMapping.model_validate(
        {
            "columns": [
                *mapping.model_dump()["columns"],
                {"name": "season_index", "role": "control", "type": "index"},
            ]
        }
    )
    assert _compile(rules, dag=Dag.from_content(confounder), mapping=more).to_json() != reference


# --- A5: percentage treatment, spend, sales and the margin threshold ----------------------


def test_percentage_treatment_with_spend_and_margin(rules: RuleSet) -> None:
    orch = _compile(rules).orchestrator
    assert orch.treatment_types == {"discount_rate": "percentage"}
    assert orch.sales_col == "revenue"
    assert orch.treatment_spend_cols == {"discount_rate": "discount_spend"}
    assert orch.opt_threshold_roi == 2.5
    assert orch.optimize is True


def test_unknown_margin_defaults_to_break_even_one_marked_assumed(rules: RuleSet) -> None:
    config = _compile(rules, margin=None)
    assert config.orchestrator.opt_threshold_roi == 1.0
    assert config.opt_threshold_roi_assumed is True
    assert _compile(rules).opt_threshold_roi_assumed is False


@pytest.mark.parametrize("margin", [0.0, -0.1, 1.5])
def test_invalid_margin_is_refused(rules: RuleSet, margin: float) -> None:
    with pytest.raises(CompileError) as err:
        _compile(rules, margin=margin)
    assert err.value.code == "invalid_margin"


def test_profiles_set_learners_folds_and_sensitivity(rules: RuleSet) -> None:
    quick, standard = _compile(rules, profile=Profile.quick), _compile(rules)
    assert quick.orchestrator.ml_models_y == ["lgbm"] and quick.orchestrator.n_folds_list == [5]
    assert (quick.run.top_n, quick.run.n_reps, quick.orchestrator.time_budget) == (1, 3, 10)
    assert quick.orchestrator.run_sensitivity is False
    assert standard.orchestrator.ml_models_t == [
        "lgbm",
        "xgboost",
    ] and standard.orchestrator.n_folds_list == [3, 5]
    assert (standard.run.top_n, standard.run.n_reps, standard.orchestrator.time_budget) == (3, 10, 30)
    assert standard.orchestrator.run_sensitivity is True
    assert standard.orchestrator.sensitivity_scope == ["total", "geo"]


def test_accepted_risk_turns_sensitivity_on_even_in_quick(rules: RuleSet) -> None:
    case = load_case(GOLDEN_DIR / "g09_risk_accepted.yaml")
    dag, mapping, panel = golden_inputs(case)
    config = compile_config(dag, mapping, panel, rules, profile=Profile.quick, data_fingerprint=FINGERPRINT)
    assert config.orchestrator.run_sensitivity is True


def test_region_dummies_are_named_from_the_profiled_levels(rules: RuleSet) -> None:
    config = _compile(rules)
    assert config.dummies[0].column == "region"
    assert config.dummies[0].names == [f"region_R{i:02d}" for i in range(1, 9)]
    case = load_case(G18)
    _, mapping, panel = golden_inputs(case)
    with pytest.raises(CompileError) as err:
        _compile(rules, panel=PanelSummary(**(panel.model_dump() | {"levels": {}})))
    assert err.value.code == "missing_levels"


def test_ground_truth_never_reaches_the_pipeline_settings(rules: RuleSet) -> None:
    case = load_case(GOLDEN_DIR / "g24_forbidden_truth_column.yaml")
    dag, mapping, panel = golden_inputs(case)
    raw = compile_config(
        dag, mapping, panel, rules, profile=Profile.standard, data_fingerprint=FINGERPRINT
    ).to_json()
    assert b"truth_" not in raw
    assert b"ground_truth" not in raw
