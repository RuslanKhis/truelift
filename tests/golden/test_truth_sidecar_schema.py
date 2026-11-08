"""rules/truth_sidecar.yaml validates the truth.yaml that G04 writes and G06 reads (G05/A6, C4).

Offline. G04's real seed-1 file is checked by test_schema_committed_sample_truth once it lands.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from truelift.causal.rules import DEFAULT_ROOT, load_truth_schema, validate_truth

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "truth_seed1.yaml"
SAMPLE = DEFAULT_ROOT / "data" / "sample" / "truth.yaml"


@pytest.fixture(scope="module")
def schema() -> dict:
    return load_truth_schema()


@pytest.fixture
def truth() -> dict:
    return yaml.safe_load(FIXTURE.read_text())


def test_schema_seed1_truth_shape_is_valid(schema: dict, truth: dict) -> None:
    assert validate_truth(truth, schema) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d["truth_columns"].append("baseline_revenue"), "truth_columns/3"),
        (lambda d: d.pop("true_roi"), "'true_roi' is a required property"),
        (lambda d: d["true_roi"].update(definition="incremental_kpi_over_rate"), "true_roi/definition"),
        (lambda d: d["treatment"].update(kind="rate"), "treatment/kind"),
        (lambda d: d.update(notes="free text"), "Additional properties"),
        (lambda d: d["generator"]["switches"].update(unobserved_confounder=True), "hidden_confounders"),
        (lambda d: d["true_roi"].pop("by_segment"), "by_segment"),
        (lambda d: d["panel"].update(sha256="abc"), "panel/sha256"),
    ],
    ids=[
        "truth-column-without-prefix",
        "no-true-roi",
        "roi-over-rate",
        "unknown-treatment-kind",
        "extra-field",
        "hidden-switch-without-names",
        "heterogeneity-without-segments",
        "bad-hash",
    ],
)
def test_schema_truth_sidecar_rejects(schema: dict, truth: dict, change, problem: str) -> None:
    bad = copy.deepcopy(truth)
    change(bad)
    problems = validate_truth(bad, schema)
    assert any(problem in p for p in problems), problems


def test_schema_hidden_confounder_shape(schema: dict, truth: dict) -> None:
    hidden = copy.deepcopy(truth)
    hidden["generator"]["switches"]["unobserved_confounder"] = True
    hidden["hidden_confounders"] = [{"name": "market_demand", "description": "Weekly category demand."}]
    assert validate_truth(hidden, schema) == []


def test_schema_committed_sample_truth(schema: dict) -> None:
    if not SAMPLE.exists():
        pytest.skip("data/sample/truth.yaml is written by G04 and not committed yet")
    assert validate_truth(yaml.safe_load(SAMPLE.read_text()), schema) == []
