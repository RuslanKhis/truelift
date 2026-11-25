"""G06/A6: a compiled config constructs doubleml-pipeline's orchestrator and scaler without fitting (C2).

The constructors run in a child process because lightgbm and xgboost need OpenMP: on macOS
without Homebrew's libomp the child points DYLD_FALLBACK_LIBRARY_PATH at scikit-learn's bundled
copy, which must be set before the interpreter starts (G03/A5). Nothing is fitted: the child only
builds the objects and reports what they hold. Offline.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.causal.support import FINGERPRINT, golden_inputs
from tests.golden.cases import GOLDEN_DIR, load_case
from truelift.causal.compile import PipelineConfig, Profile, compile_config
from truelift.causal.rules import load_rules

REPO = Path(__file__).resolve().parents[2]

_CHILD = r"""
import inspect, json, os, sys, warnings
warnings.simplefilter("error")  # a constructor warning (e.g. a forced optimizer) fails the test
from doubleml_pipeline.workflow import CausalWorkflowOrchestrator
from doubleml_pipeline.preprocessing.scalers import CausalDataScaler
from truelift.causal.compile import PipelineConfig

config = PipelineConfig.from_json(open(sys.argv[1], "rb").read())
out = sys.argv[2]
kwargs = config.orchestrator_kwargs(out, n_jobs=1)
params = inspect.signature(CausalWorkflowOrchestrator.__init__).parameters
unknown = sorted(set(kwargs) - set(params))
orch = CausalWorkflowOrchestrator(**kwargs)
scaler = CausalDataScaler(**config.scaler_kwargs())
held = {k: getattr(orch, k) for k in kwargs if hasattr(orch, k)}
json.dump({
    "unknown": unknown,
    "held": held,
    "simple_optimization": orch.simple_optimization,
    "scaler": {k: getattr(scaler, k) for k in config.scaler_kwargs()},
    "files": sorted(os.listdir(out)) if os.path.isdir(out) else [],
}, sys.stdout, default=str)
"""


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    if sys.platform == "darwin":
        spec = importlib.util.find_spec("sklearn")
        assert spec and spec.origin
        env["DYLD_FALLBACK_LIBRARY_PATH"] = str(Path(spec.origin).parent / ".dylibs")
    return env


@pytest.mark.parametrize(
    ("case_file", "profile"),
    [
        ("g18_percentage_with_spend.yaml", Profile.standard),  # percentage + spend, margin 0.4
        ("g20_spend_treatment.yaml", Profile.quick),  # spend treatment, no sales column
        ("g21_cate_modifiers.yaml", Profile.standard),  # CATE covariates and their basis
    ],
)
def test_compiled_config_constructs_the_pipeline(tmp_path: Path, case_file: str, profile: Profile) -> None:
    case = load_case(GOLDEN_DIR / case_file)
    dag, mapping, panel = golden_inputs(case)
    config = compile_config(
        dag, mapping, panel, load_rules(), profile=profile, data_fingerprint=FINGERPRINT, margin=case.margin
    )
    path = tmp_path / "config.json"
    path.write_bytes(config.to_json())
    out = tmp_path / "run"

    result = subprocess.run(
        [sys.executable, "-c", _CHILD, str(path), str(out)],
        cwd=REPO,
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout)

    assert report["unknown"] == []  # every compiled name is a G03 constructor parameter
    expected = PipelineConfig.from_json(path.read_bytes()).orchestrator_kwargs(str(out), n_jobs=1)
    held = report["held"]
    for key in (
        "y_col",
        "d_cols",
        "x_cols_list",
        "covariates_for_cate_list",
        "cate_structure_list",
        "ml_models_y",
        "ml_models_t",
        "n_folds_list",
        "treatment_types",
        "treatment_spend_cols",
        "sales_col",
        "opt_threshold_roi",
        "optimize",
        "run_sensitivity",
        "sensitivity_scope",
        "date_col",
        "geo_col",
        "time_budget",
    ):
        assert held[key] == expected[key], key
    assert report["simple_optimization"] is True
    assert report["scaler"]["median_normalize_cols"] == config.scaler.median_normalize_cols
    assert (
        report["scaler"]["population_median_normalize_cols"] == config.scaler.population_median_normalize_cols
    )
    # Not fitted: no results written.
    assert not [f for f in report["files"] if f.startswith(("step", "metadata"))]
