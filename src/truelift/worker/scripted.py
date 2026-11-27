"""A project on the synthetic market with a scripted DAG and mapping, for headless runs (C14).

``truelift sample-project --name demo --seed 1`` writes it; ``truelift run --project demo --dag v1
--profile quick`` then runs the pipeline with no browser and no model (G09/A10). G10's scripted
benchmark tier can reuse it.

The diagram is the synthetic market's known structure (``truelift.sample``): holiday weeks, the
seasonal index, weighted distribution, media and the competitor's promotions drive both the
discount and sales, and store traffic is the mediator trap that identification keeps out of the
controls (C3 a). Both the DAG and the mapping are confirmed by the script, standing in for the
interview (G13) and the mapping screen (G07). The panel summary is computed here with pandas
until G07's profile writes it.

The truth (``truth.yaml``) is not copied into the project: the scorer reads it separately (C4).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from truelift.causal.build import DagDraft
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.sample.generator import DATE_COL, PANEL_FILE, generate
from truelift.store import ProjectStore, VersionKind
from truelift.store.files import atomic_write
from truelift.worker.gate import DATA_DIR, data_fingerprint

TEMPLATE = "brand_via_retailers"

MAPPING_COLUMNS: list[dict[str, Any]] = [
    {"name": DATE_COL, "role": "date", "type": "date"},
    {"name": "region", "role": "region", "type": "key"},
    {"name": "revenue", "role": "outcome", "type": "money"},
    {"name": "discount_rate", "role": "treatment_rate", "type": "rate", "bounded_0_1": True},
    {"name": "discount_spend", "role": "treatment_spend", "type": "money"},
    {"name": "population", "role": "population", "type": "count"},
    {"name": "holiday", "role": "control", "type": "flag"},
    {"name": "season_index", "role": "control", "type": "index"},
    {"name": "weighted_distribution", "role": "control", "type": "rate", "bounded_0_1": True},
    {"name": "media_grps", "role": "control", "type": "index"},
    {"name": "competitor_promo", "role": "control", "type": "rate", "bounded_0_1": True},
    {"name": "store_traffic", "role": "control", "type": "count"},
]

# (node id, role, column, label)
_NODES = [
    ("discount", "treatment", "discount_rate", "Your discount"),
    ("sales", "outcome", "revenue", "Your sales"),
    ("holiday_weeks", "confounder", "holiday", "Holiday weeks"),
    ("season", "confounder", "season_index", "The time of year"),
    ("distribution", "confounder", "weighted_distribution", "How many shops stock your product"),
    ("media", "confounder", "media_grps", "Your advertising"),
    ("competitor_promo", "confounder", "competitor_promo", "Competitors' promotions"),
    ("store_traffic", "mediator", "store_traffic", "Visits to the shops"),
]
_CONFOUNDERS = ("holiday_weeks", "season", "distribution", "media", "competitor_promo")


def _label(node_id: str) -> str:
    return next(label for n, _, _, label in _NODES if n == node_id)


def scripted_dag() -> dict[str, Any]:
    edges: list[tuple[str, str]] = [("discount", "sales")]
    for c in _CONFOUNDERS:
        edges += [(c, "discount"), (c, "sales")]
    edges += [("discount", "store_traffic"), ("store_traffic", "sales")]
    draft = DagDraft.model_validate(
        {
            "template": TEMPLATE,
            "dag": {
                "treatment": "discount",
                "outcome": "sales",
                "nodes": [{"id": n, "role": r, "column": c, "label": label} for n, r, c, label in _NODES],
                "edges": [list(e) for e in edges],
            },
            "edges": [
                {"from": a, "to": b, "facts": [], "sentence": f"{_label(a)} affects {_label(b).lower()}."}
                for a, b in edges
            ],
        }
    )
    return draft.to_content()


def panel_summary(csv_path: Path) -> dict[str, Any]:
    """The panel facts identification compares with its thresholds (G07 computes them later)."""
    import pandas as pd

    df = pd.read_csv(csv_path)
    rate = df["discount_rate"]
    weeks, regions = df[DATE_COL].nunique(), df["region"].nunique()
    summary = PanelSummary(
        weeks=weeks,
        regions=regions,
        rows=len(df),
        treated_share=round(float((rate > 0).mean()), 4),
        untreated_share=round(float((rate == 0).mean()), 4),
        treatment_levels=int(rate[rate > 0].round(2).nunique()),
        gap_share=round(1 - len(df) / (weeks * regions), 4),
        levels={"region": sorted(str(v) for v in df["region"].unique())},
    )
    return summary.model_dump(mode="json")


def create_scripted_project(store: ProjectStore, name: str, seed: int) -> tuple[str, float]:
    """Create the project and return its ID and the true total ROI of the seed."""
    info = store.create(name)
    with tempfile.TemporaryDirectory() as tmp:
        truth = generate(seed, Path(tmp))
        with store.open(info.id) as folder:
            target = folder.root / DATA_DIR / "v1.csv"
            atomic_write(target, (Path(tmp) / PANEL_FILE).read_bytes())
    fingerprint = data_fingerprint(target)
    mapping = ColumnMapping.model_validate({"columns": MAPPING_COLUMNS}).model_dump(mode="json")
    mapping["panel"] = panel_summary(target)
    store.write_version(
        info.id, VersionKind.mapping, mapping, expected_current=None, data_fingerprint=fingerprint
    )
    store.confirm_version(info.id, VersionKind.mapping, 1)
    store.write_version(
        info.id, VersionKind.dag, scripted_dag(), expected_current=None, data_fingerprint=fingerprint
    )
    store.confirm_version(info.id, VersionKind.dag, 1)
    return info.id, float(truth["true_roi"]["total"])
