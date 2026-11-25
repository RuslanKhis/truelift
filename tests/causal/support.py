"""Turn a golden case (tests/golden) into the causal core's inputs."""

from __future__ import annotations

from tests.golden.cases import GoldenCase
from truelift.causal.dag import Dag
from truelift.causal.mapping import ColumnMapping, PanelSummary

FINGERPRINT = "sha256:" + "0" * 64


def golden_inputs(case: GoldenCase) -> tuple[Dag, ColumnMapping, PanelSummary]:
    dag = Dag.from_content(case.dag.model_dump(mode="json"))
    mapping = ColumnMapping.model_validate(case.mapping.model_dump(mode="json"))
    levels = {
        c.name: [f"R{i:02d}" for i in range(1, case.data.regions + 1)] for c in mapping.by_role("region")
    }
    levels |= {c.name: ["C1", "C2"] for c in mapping.by_role("category")}
    panel = PanelSummary(**case.data.model_dump(), levels=levels)
    return dag, mapping, panel
