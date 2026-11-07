"""A quick stand-in synthetic panel for the G03 spike.

This is not the product's synthetic market (``truelift.sample``, G04). It only has the
same shape (8 regions x 156 weeks, a weekly discount rate plus discount spend) and a few
confounders, so the pipeline can be timed and its run-to-run spread measured on public
data. The true total ROI is computed from the generating process.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_REGIONS = 8
N_WEEKS = 156
EFFECT_PER_RATE = 1.5  # incremental revenue per unit discount rate, per unit of region size


def make_panel(seed: int = 7) -> tuple[pd.DataFrame, dict[str, float]]:
    rng = np.random.default_rng(seed)
    size = rng.uniform(0.5, 3.0, N_REGIONS)  # region size, in millions of people
    t = np.arange(N_WEEKS)
    week_of_year = t % 52 + 1
    holiday = (week_of_year >= 47).astype(float)
    season = np.sin(2 * np.pi * t / 52)

    rows = []
    for r in range(N_REGIONS):
        distribution = np.clip(0.6 + 0.2 * rng.random() + np.cumsum(rng.normal(0, 0.01, N_WEEKS)), 0.3, 0.98)
        media = np.maximum(0.0, 50 + 80 * holiday + 20 * season + rng.normal(0, 15, N_WEEKS))
        rate = 0.04 + 0.08 * holiday + 0.0006 * (media - 50) + rng.normal(0, 0.03, N_WEEKS)
        off = (rng.random(N_WEEKS) < 0.3) & (holiday == 0)
        rate = np.where(off, 0.0, np.clip(rate, 0.0, 0.4))
        baseline = size[r] * 1000 * (1 + 0.3 * holiday + 0.5 * distribution + 0.002 * media + 0.1 * season)
        spend = 0.5 * rate * baseline
        incremental = EFFECT_PER_RATE * rate * size[r] * 1000
        revenue = baseline * rng.lognormal(0, 0.05, N_WEEKS) + incremental
        rows.append(
            pd.DataFrame(
                {
                    "week": pd.date_range("2023-01-02", periods=N_WEEKS, freq="W-MON"),
                    "region": f"R{r + 1}",
                    "population": size[r],
                    "distribution": distribution,
                    "media_grps": media,
                    "holiday": holiday,
                    "season": season,
                    "discount_rate": rate,
                    "discount_spend": spend,
                    "revenue": revenue,
                    "_incremental": incremental,
                }
            )
        )
    df = pd.concat(rows, ignore_index=True)
    for r in range(N_REGIONS):
        df[f"region_R{r + 1}"] = (df["region"] == f"R{r + 1}").astype(float)
    truth = {"total_roi": float(df["_incremental"].sum() / df["discount_spend"].sum())}
    return df.drop(columns="_incremental"), truth


def standin_config() -> dict:
    """Constructor arguments the compiler (G06) would emit for this panel."""
    return {
        "y_col": "revenue",
        "sales_col": "revenue",
        "d_cols": ["discount_rate"],
        "treatment_types": {"discount_rate": "percentage"},
        "treatment_spend_cols": {"discount_rate": "discount_spend"},
        "x_cols_list": [
            ["population", "distribution", "media_grps", "holiday", "season"]
            + [f"region_R{r + 1}" for r in range(N_REGIONS)]
        ],
        "covariates_for_cate_list": [[]],
        "date_col": "week",
        "geo_col": "region",
        "optimize": True,
        "opt_threshold_roi": 1.0,
        "scaler": {"median_normalize_cols": ["media_grps"]},
    }
