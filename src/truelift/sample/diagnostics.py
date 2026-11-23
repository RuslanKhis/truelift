"""Why the synthetic market needs a causal method: three OLS estimates of ROI (G04/A3, C3).

* ``naive``: revenue on discount spend alone; the slope reads as money ROI. The holiday season,
  distribution and region size drive both, so it is far from the truth.
* ``adjusted``: per head of population, revenue on spend with one slope per segment (holiday
  weeks, low season, other weeks), the observed confounders, and region and week fixed effects
  (week effects absorb the holiday and season columns, which every region shares). The panel's
  competitor column joins when the panel has it. The segment slopes are combined with spend
  weights into a total ROI, the same definition as the truth. This model matches the
  data-generating process, so with every confounder observed it lands near the truth.
* ``with_mediator``: ``adjusted`` plus ``store_traffic``. Traffic is caused by the discount, so
  controlling for it removes the part of the effect that travels through it (C3 a).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from truelift.sample.generator import (
    DATE_COL,
    GEO_COL,
    HIDDEN_CONFOUNDER,
    MEDIATOR_COL,
    OUTCOME_COL,
    SPEND_COL,
    Market,
)


@dataclass(frozen=True)
class Estimates:
    true_roi: float
    naive: float
    adjusted: float
    with_mediator: float

    @staticmethod
    def bias(estimate: float, truth: float) -> float:
        return (estimate - truth) / abs(truth)

    def table(self) -> list[str]:
        """Markdown rows for data/sample/README.md, rounded to two decimals."""
        rows = [
            ("True ROI, from the truth columns", self.true_roi),
            ("Naive OLS: revenue on discount spend", self.naive),
            ("OLS with the confounders, fixed effects and segment slopes", self.adjusted),
            ("The same, plus the mediator `store_traffic` as a control", self.with_mediator),
        ]
        lines = ["| Estimate | ROI | Bias |", "| --- | ---: | ---: |"]
        for i, (label, value) in enumerate(rows):
            bias = "—" if i == 0 else f"{self.bias(value, self.true_roi):+.0%}"
            lines.append(f"| {label} | {value:.2f} | {bias} |")
        return lines


def _dummies(labels: np.ndarray) -> list[np.ndarray]:
    levels = sorted(set(labels.tolist()))
    return [(labels == level).astype(float) for level in levels[1:]]


def _segment_roi(
    y: np.ndarray, spend: np.ndarray, segments: list[np.ndarray], controls: list[np.ndarray]
) -> float:
    """One spend slope per segment, combined with spend weights into money ROI."""
    slopes = [spend * seg for seg in segments]
    design = np.column_stack([np.ones_like(y), *slopes, *controls])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    weights = np.array([(spend * seg).sum() for seg in segments])
    return float(coef[1 : 1 + len(segments)] @ weights / weights.sum())


def estimate(market: Market) -> Estimates:
    cols = market.columns
    revenue = cols[OUTCOME_COL].astype(float)
    spend = cols[SPEND_COL].astype(float)
    naive_design = np.column_stack([np.ones_like(spend), spend])
    naive = float(np.linalg.lstsq(naive_design, revenue, rcond=None)[0][1])

    per_head = cols["population"].astype(float)
    y = revenue / per_head
    s = spend / per_head
    controls = [cols["weighted_distribution"].astype(float), cols["media_grps"].astype(float)]
    if not market.switches.unobserved_confounder:
        controls.append(cols[HIDDEN_CONFOUNDER].astype(float))
    controls += _dummies(cols[GEO_COL]) + _dummies(cols[DATE_COL])
    holiday = market.holiday.astype(float)
    low = market.low_season.astype(float)
    segments = [holiday, low, 1.0 - holiday - low]
    mediator = cols[MEDIATOR_COL].astype(float) / per_head
    return Estimates(
        true_roi=market.true_roi,
        naive=naive,
        adjusted=_segment_roi(y, s, segments, controls),
        with_mediator=_segment_roi(y, s, segments, controls + [mediator]),
    )
