"""The synthetic market: a fictional snack brand sold in 8 regions over 156 weeks (design D14).

The panel has a known causal truth so that the benchmark (C14) can score an estimate against it.
Everything comes from one NumPy generator seeded by ``seed``, and every number is written with a
fixed number of decimals, so the same seed gives the same bytes and the same sha256.

The data-generating process, one row per region r and week t:

* Confounders, which drive both the discount and sales: the holiday season (the last 6 weeks of
  each year), a seasonal index that is lowest in January and February, weighted distribution
  (retailers that stock the brand also run more of its promotions) and media flighting (TV is
  booked around planned promotions). A competitor's promotions make the brand discount deeper
  and sell less; the unobserved-confounder switch leaves that column out of the panel.
* Treatment: the weekly discount rate (a share of the shelf price, in [0, 1]) and the discount
  spend it costs, ``SPEND_SHARE * rate * expected_baseline_revenue``.
* Effect: ``incremental_revenue = roi * spend``. With heterogeneity on, ``roi`` is higher in
  holiday weeks, negative in the low season (discounts there only pull sales forward) and differs
  a little by region. With it off, ``roi`` is ``FLAT_ROI`` everywhere.
* Mediator trap: a share ``MEDIATED_SHARE`` of the incremental revenue arrives through extra
  store traffic, so ``store_traffic`` is caused by the discount and must not be a control (C3 a).
* Outcome: ``revenue = truth_baseline_revenue + truth_incremental_revenue``, where the baseline
  is what the region would have sold that week with no discount, noise included.

The true total ROI is money over money: the sum of incremental revenue divided by the sum of
discount spend (rules/truth_sidecar.yaml, the G03 note's finding F1).
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

GENERATOR_NAME = "truelift.sample"
GENERATOR_VERSION = "1.0.0"
TRUTH_SCHEMA = "truelift.truth/1"

N_REGIONS = 8
N_WEEKS = 156
FIRST_WEEK = dt.date(2023, 1, 2)  # a Monday
HOLIDAY_WEEKS = range(46, 52)  # week-of-year index 0..51: the last 6 weeks of the year
LOW_SEASON_WEEKS = range(0, 8)  # January and February

SPEND_SHARE = 0.55  # share of the week's expected sales that is sold on the deal
MEDIATED_SHARE = 0.4  # share of the incremental revenue that arrives through store traffic
REVENUE_PER_VISIT = 25.0  # currency units per store visit
FLAT_ROI = 1.8  # roi everywhere when heterogeneity is off
SEGMENT_ROI = {"regular": 1.5, "holiday_weeks": 2.6, "low_season": -0.6}
REGION_ROI_SPREAD = 0.3  # with heterogeneity on, each region's roi moves by up to +/- this

PANEL_FILE = "panel.csv"
TRUTH_FILE = "truth.yaml"
DATE_COL = "week"
GEO_COL = "region"
TREATMENT_COL = "discount_rate"
SPEND_COL = "discount_spend"
OUTCOME_COL = "revenue"
MEDIATOR_COL = "store_traffic"
HIDDEN_CONFOUNDER = "competitor_promo"
OBSERVED_CONFOUNDERS = ["holiday", "season_index", "weighted_distribution", "media_grps"]
TRUTH_COLUMNS = ["truth_baseline_revenue", "truth_incremental_revenue", "truth_roi"]

# Column order and the decimals each column is written with. Fixed decimals keep the bytes stable
# across platforms, whose last-bit floating-point results can differ.
COLUMNS: dict[str, int | None] = {
    DATE_COL: None,
    GEO_COL: None,
    "population": 3,
    "weighted_distribution": 4,
    "media_grps": 2,
    "holiday": 0,
    "season_index": 4,
    HIDDEN_CONFOUNDER: 4,
    TREATMENT_COL: 4,
    SPEND_COL: 2,
    MEDIATOR_COL: 2,
    OUTCOME_COL: 4,
    "truth_baseline_revenue": 4,
    "truth_incremental_revenue": 4,
    "truth_roi": 4,
}


@dataclass(frozen=True)
class Switches:
    """Generator switches, recorded in truth.yaml (G04/A6, A7)."""

    unobserved_confounder: bool = False
    heterogeneity: bool = True


@dataclass(frozen=True)
class Market:
    """One generated market: the panel's columns, its truth and the switches that made it."""

    seed: int
    switches: Switches
    columns: dict[str, np.ndarray]
    true_roi: float
    roi_by_segment: dict[str, float]
    holiday: np.ndarray
    low_season: np.ndarray

    @property
    def panel_columns(self) -> list[str]:
        hidden = {HIDDEN_CONFOUNDER} if self.switches.unobserved_confounder else set()
        return [c for c in COLUMNS if c not in hidden]

    @property
    def confounders(self) -> list[str]:
        if self.switches.unobserved_confounder:
            return list(OBSERVED_CONFOUNDERS)
        return [*OBSERVED_CONFOUNDERS, HIDDEN_CONFOUNDER]


def _round(values: np.ndarray, decimals: int) -> np.ndarray:
    return np.round(values.astype(float), decimals)


def simulate(seed: int, switches: Switches | None = None) -> Market:
    """Draw one market. Pure: the same seed and switches always give the same arrays."""
    switches = switches or Switches()
    rng = np.random.default_rng(seed)
    shape = (N_REGIONS, N_WEEKS)

    t = np.arange(N_WEEKS)
    week_of_year = t % 52
    holiday_w = np.isin(week_of_year, HOLIDAY_WEEKS).astype(float)
    low_w = np.isin(week_of_year, LOW_SEASON_WEEKS)
    season_w = 1.0 - 0.15 * np.cos(2 * np.pi * (week_of_year - 4) / 52)
    holiday = np.broadcast_to(holiday_w, shape)
    low_season = np.broadcast_to(low_w, shape)
    season = _round(np.broadcast_to(season_w, shape), 4)

    population = _round(rng.uniform(0.6, 3.2, N_REGIONS), 3)[:, None] * np.ones(shape)
    dist_level = rng.uniform(0.55, 0.85, N_REGIONS)[:, None]
    distribution = _round(
        np.clip(dist_level + np.cumsum(rng.normal(0.0, 0.008, shape), axis=1), 0.35, 0.97), 4
    )

    competitor_on = rng.random(shape) < (0.25 + 0.25 * holiday)
    competitor = _round(np.where(competitor_on, rng.uniform(0.3, 1.0, shape), 0.0), 4)

    promo_p = np.clip(0.35 + 0.5 * holiday - 0.05 * low_season + 0.6 * (distribution - 0.7), 0.05, 0.95)
    promo = rng.random(shape) < promo_p
    media = _round(np.maximum(0.0, 40 + 70 * holiday + 30 * promo + rng.normal(0.0, 12.0, shape)), 2)

    depth = 0.06 + 0.05 * holiday + 0.05 * competitor + rng.normal(0.0, 0.015, shape)
    rate = _round(np.where(promo, np.clip(depth, 0.02, 0.35), 0.0), 4)

    # Expected sales per head are additive in the drivers, so a correctly specified linear model
    # (per head, with week fixed effects) can recover the truth; see truelift.sample.diagnostics.
    week_level = season * (1 + 0.45 * holiday)
    expected = (
        10_000
        * population
        * (week_level + 0.9 * (distribution - 0.7) + 0.0015 * (media - 40) - 0.12 * competitor)
    )
    spend = _round(SPEND_SHARE * rate * expected, 2)

    if switches.heterogeneity:
        segment = np.where(
            holiday > 0,
            SEGMENT_ROI["holiday_weeks"],
            np.where(low_season, SEGMENT_ROI["low_season"], SEGMENT_ROI["regular"]),
        )
        region_shift = _round(rng.uniform(-REGION_ROI_SPREAD, REGION_ROI_SPREAD, N_REGIONS), 3)[:, None]
        roi = _round(segment + region_shift, 4)
    else:
        roi = np.full(shape, FLAT_ROI)
    incremental = _round(roi * spend, 4)

    base_traffic = (
        400 * population * (0.3 + 0.8 * week_level + 0.5 * (distribution - 0.7) + 0.001 * (media - 40))
    )
    traffic_noise = rng.normal(0.0, 0.04, shape) * base_traffic
    induced_traffic = MEDIATED_SHARE * incremental / REVENUE_PER_VISIT
    traffic = _round(base_traffic + induced_traffic + traffic_noise, 2)

    # Revenue = baseline sales + the direct part of the effect + the value of the extra visits.
    # Written as baseline + incremental, where the baseline already holds the traffic noise.
    baseline = _round(expected * rng.lognormal(0.0, 0.04, shape) + REVENUE_PER_VISIT * traffic_noise, 4)
    revenue = _round(baseline + incremental, 4)

    true_roi = float(incremental.sum() / spend.sum())
    segments = {
        "holiday_weeks": holiday > 0,
        "low_season": low_season,
        "regular": (holiday == 0) & ~low_season,
    }
    by_segment = {name: float(incremental[m].sum() / spend[m].sum()) for name, m in segments.items()}

    weeks = np.array([(FIRST_WEEK + dt.timedelta(weeks=int(i))).isoformat() for i in t])
    columns = {
        DATE_COL: np.broadcast_to(weeks, shape),
        GEO_COL: np.broadcast_to(np.array([f"R{r + 1:02d}" for r in range(N_REGIONS)])[:, None], shape),
        "population": population,
        "weighted_distribution": distribution,
        "media_grps": media,
        "holiday": holiday,
        "season_index": season,
        HIDDEN_CONFOUNDER: competitor,
        TREATMENT_COL: rate,
        SPEND_COL: spend,
        MEDIATOR_COL: traffic,
        OUTCOME_COL: revenue,
        "truth_baseline_revenue": baseline,
        "truth_incremental_revenue": incremental,
        "truth_roi": roi,
    }
    # Rows are ordered region by region, then by week.
    flat = {name: np.asarray(values).reshape(-1) for name, values in columns.items()}
    return Market(
        seed=seed,
        switches=switches,
        columns=flat,
        true_roi=true_roi,
        roi_by_segment=by_segment,
        holiday=holiday.reshape(-1) > 0,
        low_season=low_season.reshape(-1),
    )


def _fmt(value: Any, decimals: int | None) -> str:
    if decimals is None:
        return str(value)
    text = f"{float(value):.{decimals}f}"
    # Never write a negative zero: it would differ from "0.0000" for no reason.
    return text[1:] if text.startswith("-") and float(text) == 0 else text


def panel_csv(market: Market) -> bytes:
    """The panel as CSV bytes: LF line ends, fixed decimals, no index."""
    names = market.panel_columns
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(names)
    for i in range(N_REGIONS * N_WEEKS):
        writer.writerow([_fmt(market.columns[c][i], COLUMNS[c]) for c in names])
    return buf.getvalue().encode("utf-8")


def truth_document(market: Market, panel_bytes: bytes) -> dict[str, Any]:
    """truth.yaml, in the shape rules/truth_sidecar.yaml fixes (C4, C14)."""
    hidden = []
    if market.switches.unobserved_confounder:
        hidden.append(
            {
                "name": HIDDEN_CONFOUNDER,
                "description": (
                    "A competitor's weekly promotion intensity. It deepens the brand's discounts and "
                    "lowers its sales, and the panel leaves it out."
                ),
            }
        )
    true_roi: dict[str, Any] = {
        "total": market.true_roi,
        "definition": "sum_incremental_revenue_over_sum_spend",
        "by_segment": dict(market.roi_by_segment),
    }
    return {
        "schema": TRUTH_SCHEMA,
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "seed": market.seed,
            "switches": {
                "unobserved_confounder": market.switches.unobserved_confounder,
                "heterogeneity": market.switches.heterogeneity,
            },
        },
        "panel": {
            "file": PANEL_FILE,
            "sha256": hashlib.sha256(panel_bytes).hexdigest(),
            "rows": N_REGIONS * N_WEEKS,
            "regions": N_REGIONS,
            "weeks": N_WEEKS,
            "date_col": DATE_COL,
            "geo_col": GEO_COL,
        },
        "treatment": {"column": TREATMENT_COL, "kind": "percentage", "spend_column": SPEND_COL},
        "outcome": {"column": OUTCOME_COL},
        "true_roi": true_roi,
        "truth_columns": list(TRUTH_COLUMNS),
        "hidden_confounders": hidden,
        "traps": {"mediators": [MEDIATOR_COL], "treatment_descendants": []},
        "confounders": market.confounders,
    }


def generate(seed: int, out: Path, switches: Switches | None = None) -> dict[str, Any]:
    """Write ``panel.csv`` and ``truth.yaml`` for one seed into ``out``; return the truth document."""
    market = simulate(seed, switches)
    data = panel_csv(market)
    truth = truth_document(market, data)
    out.mkdir(parents=True, exist_ok=True)
    (out / PANEL_FILE).write_bytes(data)
    header = (
        "# Ground truth for the truelift synthetic market (design D14, contracts C4 and C14).\n"
        "# Written by `python -m truelift.sample generate`; do not edit by hand.\n"
    )
    body = yaml.safe_dump(truth, sort_keys=False, allow_unicode=False, width=100)
    (out / TRUTH_FILE).write_bytes((header + body).encode("utf-8"))
    return truth


def generate_bundle(seeds: list[int], out: Path, switches: Switches | None = None) -> list[Path]:
    """Write one ``seed_NNN`` folder per seed under ``out`` (the coverage set, C14)."""
    folders = []
    for seed in seeds:
        folder = out / f"seed_{seed:03d}"
        generate(seed, folder, switches)
        folders.append(folder)
    return folders


def parse_seeds(text: str) -> list[int]:
    """``"1..20"`` or ``"1,2,5"`` (or a mix) to a sorted list of distinct seeds."""
    seeds: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if ".." in part:
            lo, hi = (int(x) for x in part.split("..", 1))
            if hi < lo:
                raise ValueError(f"empty seed range {part!r}")
            seeds.update(range(lo, hi + 1))
        elif part:
            seeds.add(int(part))
    if not seeds or min(seeds) < 0:
        raise ValueError(f"seeds must be non-negative integers, got {text!r}")
    return sorted(seeds)
