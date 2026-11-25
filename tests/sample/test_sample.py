"""The synthetic market generator and its truth (G04; contracts C14, C4, C3). Offline."""

from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from truelift.causal.rules import DEFAULT_ROOT, validate_truth
from truelift.sample.diagnostics import Estimates, estimate
from truelift.sample.generator import (
    FLAT_ROI,
    HIDDEN_CONFOUNDER,
    MEDIATOR_COL,
    N_REGIONS,
    N_WEEKS,
    Switches,
    generate,
    parse_seeds,
    simulate,
)

SAMPLE = DEFAULT_ROOT / "data" / "sample"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "truelift.sample", *args], capture_output=True, text=True, check=True
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_panel(folder: Path) -> tuple[list[str], dict[str, list[str]]]:
    with (folder / "panel.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    return header, {name: [r[i] for r in body] for i, name in enumerate(header)}


def read_truth(folder: Path) -> dict:
    return yaml.safe_load((folder / "truth.yaml").read_text(encoding="utf-8"))


def floats(values: list[str]) -> list[float]:
    return [float(v) for v in values]


# --- A1: the CLI writes the panel and truth.yaml; the same seed gives the same sha256 -------------


def test_cli_same_seed_same_sha256(tmp_path: Path) -> None:
    run_cli("generate", "--seed", "7", "--out", str(tmp_path / "a"))
    run_cli("generate", "--seed", "7", "--out", str(tmp_path / "b"))
    run_cli("generate", "--seed", "8", "--out", str(tmp_path / "c"))
    a, b, c = (sha256(tmp_path / x / "panel.csv") for x in "abc")
    assert a == b != c
    assert (tmp_path / "a" / "truth.yaml").read_bytes() == (tmp_path / "b" / "truth.yaml").read_bytes()
    assert read_truth(tmp_path / "a")["panel"]["sha256"] == a


def test_committed_sample_is_seed_1(tmp_path: Path) -> None:
    generate(1, tmp_path)
    for name in ("panel.csv", "truth.yaml"):
        assert (SAMPLE / name).read_bytes() == (tmp_path / name).read_bytes(), (
            f"data/sample/{name} is stale: run `uv run python -m truelift.sample generate --seed 1 "
            "--out data/sample`"
        )
    assert read_truth(SAMPLE)["panel"]["sha256"] == sha256(SAMPLE / "panel.csv")


def test_panel_shape() -> None:
    header, cols = read_panel(SAMPLE)
    truth = read_truth(SAMPLE)
    assert len(cols["week"]) == truth["panel"]["rows"] == N_REGIONS * N_WEEKS
    assert len(set(cols["region"])) == N_REGIONS and len(set(cols["week"])) == N_WEEKS
    assert len(set(zip(cols["region"], cols["week"], strict=True))) == N_REGIONS * N_WEEKS
    rates = floats(cols["discount_rate"])
    assert all(0.0 <= r <= 1.0 for r in rates)
    assert 0.2 < sum(r > 0 for r in rates) / len(rates) < 0.8


# --- A2: true ROI recomputed from the truth columns equals the analytic value -----------------------


def test_true_roi_recomputed_from_truth_columns() -> None:
    _, cols = read_panel(SAMPLE)
    truth = read_truth(SAMPLE)
    spend = floats(cols["discount_spend"])
    incremental = floats(cols["truth_incremental_revenue"])
    analytic = simulate(1).true_roi
    assert truth["true_roi"]["total"] == analytic
    assert abs(sum(incremental) / sum(spend) - analytic) < 1e-6
    # Each row: incremental = roi x spend, and revenue = baseline + incremental.
    roi = floats(cols["truth_roi"])
    assert all(abs(i - r * s) < 1e-3 for i, r, s in zip(incremental, roi, spend, strict=True))
    revenue, baseline = floats(cols["revenue"]), floats(cols["truth_baseline_revenue"])
    assert all(abs(y - b - i) < 1e-3 for y, b, i in zip(revenue, baseline, incremental, strict=True))


@pytest.mark.parametrize("seed", [2, 11, 20])
def test_true_roi_recomputed_other_seeds(tmp_path: Path, seed: int) -> None:
    truth = generate(seed, tmp_path)
    _, cols = read_panel(tmp_path)
    recomputed = sum(floats(cols["truth_incremental_revenue"])) / sum(floats(cols["discount_spend"]))
    assert abs(recomputed - truth["true_roi"]["total"]) < 1e-6


# --- A3: naive OLS is biased by more than 30%; the mediator biases the estimate --------------------


@pytest.fixture(scope="module")
def seed1() -> Estimates:
    return estimate(simulate(1))


def test_naive_ols_biased_over_30_percent(seed1: Estimates) -> None:
    assert abs(seed1.bias(seed1.naive, seed1.true_roi)) > 0.30


def test_mediator_control_biases_estimate(seed1: Estimates) -> None:
    adjusted = seed1.bias(seed1.adjusted, seed1.true_roi)
    mediated = seed1.bias(seed1.with_mediator, seed1.true_roi)
    assert abs(adjusted) < 0.15, "the correctly adjusted reference should land near the truth"
    assert mediated < -0.25 and abs(mediated) > abs(adjusted) + 0.2


@pytest.mark.parametrize("seed", range(2, 7))
def test_traps_hold_across_seeds(seed: int) -> None:
    e = estimate(simulate(seed))
    assert e.bias(e.naive, e.true_roi) > 0.30
    assert e.with_mediator < e.adjusted - 0.2 * e.true_roi


def test_readme_records_the_numbers(seed1: Estimates) -> None:
    readme = (SAMPLE / "README.md").read_text(encoding="utf-8")
    for line in seed1.table():
        assert line in readme, f"README table out of date; expected the row: {line}"
    hidden = estimate(simulate(1, Switches(unobserved_confounder=True)))
    expected = f"reads {hidden.adjusted:.2f} ({hidden.bias(hidden.adjusted, hidden.true_roi):+.0%})"
    assert expected in readme


# --- A4: every truth column is listed in truth.yaml and uses the truth_ prefix ----------------------


@pytest.mark.parametrize(
    "switches",
    [Switches(), Switches(unobserved_confounder=True), Switches(heterogeneity=False)],
    ids=["default", "hidden-confounder", "no-heterogeneity"],
)
def test_truth_columns_listed_and_prefixed(tmp_path: Path, switches: Switches) -> None:
    truth = generate(3, tmp_path, switches)
    header, _ = read_panel(tmp_path)
    assert validate_truth(truth) == []
    assert all(c.startswith("truth_") for c in truth["truth_columns"])
    assert {c for c in header if c.startswith("truth_")} == set(truth["truth_columns"])
    assert set(truth["truth_columns"]) <= set(header)
    named = {truth["treatment"]["column"], truth["treatment"]["spend_column"], truth["outcome"]["column"]}
    named |= set(truth["confounders"]) | set(truth["traps"]["mediators"])
    assert named <= set(header) and not named & set(truth["truth_columns"])


def test_committed_truth_is_valid() -> None:
    assert validate_truth(read_truth(SAMPLE)) == []


# --- A5: the 20-seed coverage set in under 2 minutes; only seed 1 committed, under 5 MB -------------


def test_bundle_of_20_seeds_under_2_minutes(tmp_path: Path) -> None:
    started = time.perf_counter()
    run_cli("generate-bundle", "--seeds", "1..20", "--out", str(tmp_path))
    assert time.perf_counter() - started < 120
    folders = sorted(p for p in tmp_path.iterdir() if p.is_dir())
    assert [p.name for p in folders] == [f"seed_{s:03d}" for s in range(1, 21)]
    assert len({sha256(p / "panel.csv") for p in folders}) == 20
    assert (folders[0] / "panel.csv").read_bytes() == (SAMPLE / "panel.csv").read_bytes()
    assert all(read_truth(p)["generator"]["seed"] == int(p.name[5:]) for p in folders)


def test_only_seed_1_committed_under_5_mb() -> None:
    files = [p for p in SAMPLE.rglob("*") if p.is_file()]
    assert [p.name for p in files if p.suffix == ".csv"] == ["panel.csv"]
    assert sum(p.stat().st_size for p in files) < 5 * 1024 * 1024
    assert read_truth(SAMPLE)["generator"]["seed"] == 1


def test_parse_seeds() -> None:
    assert parse_seeds("1..20") == list(range(1, 21))
    assert parse_seeds("3, 1,2..4") == [1, 2, 3, 4]
    for bad in ("", "5..1", "-1"):
        with pytest.raises(ValueError):
            parse_seeds(bad)


# --- A6: holiday weeks have higher ROI, the low season negative ROI ---------------------------------


def test_heterogeneity_documented() -> None:
    truth = read_truth(SAMPLE)
    seg = truth["true_roi"]["by_segment"]
    total = truth["true_roi"]["total"]
    assert seg["holiday_weeks"] > seg["regular"] > 0 > seg["low_season"]
    assert seg["holiday_weeks"] > total
    readme = (SAMPLE / "README.md").read_text(encoding="utf-8")
    for label, key in (
        ("Holiday weeks", "holiday_weeks"),
        ("Other weeks", "regular"),
        ("Low season", "low_season"),
    ):
        assert f"| {label} | {seg[key]:.2f} |" in readme
    assert f"| All weeks | {total:.2f} |" in readme


def test_heterogeneity_off_gives_one_roi(tmp_path: Path) -> None:
    truth = generate(1, tmp_path, Switches(heterogeneity=False))
    _, cols = read_panel(tmp_path)
    assert set(floats(cols["truth_roi"])) == {FLAT_ROI}
    assert abs(truth["true_roi"]["total"] - FLAT_ROI) < 1e-6
    assert all(abs(v - FLAT_ROI) < 1e-6 for v in truth["true_roi"]["by_segment"].values())


# --- A7: the unobserved-confounder switch drops the column and records it as hidden -----------------


def test_hidden_confounder_switch(tmp_path: Path) -> None:
    run_cli("generate", "--seed", "1", "--out", str(tmp_path), "--hidden-confounder")
    header, cols = read_panel(tmp_path)
    truth = read_truth(tmp_path)
    assert HIDDEN_CONFOUNDER not in header
    assert truth["generator"]["switches"]["unobserved_confounder"] is True
    assert [h["name"] for h in truth["hidden_confounders"]] == [HIDDEN_CONFOUNDER]
    assert HIDDEN_CONFOUNDER not in truth["confounders"]
    assert validate_truth(truth) == []
    # Same market otherwise: only the column is gone.
    full_header, full = read_panel(SAMPLE)
    assert [c for c in full_header if c != HIDDEN_CONFOUNDER] == header
    assert all(cols[c] == full[c] for c in header)
    assert read_truth(SAMPLE)["hidden_confounders"] == []


def test_mediator_is_recorded_as_a_trap() -> None:
    truth = read_truth(SAMPLE)
    assert truth["traps"]["mediators"] == [MEDIATOR_COL]
    assert MEDIATOR_COL not in truth["confounders"]
