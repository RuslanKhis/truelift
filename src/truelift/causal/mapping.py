"""What identification and the compiler read about the data: column roles and a panel summary.

``ColumnMapping`` is the confirmed mapping (one role and semantic type per column; G07 validates
the values against the file, C12). ``PanelSummary`` holds the panel facts the thresholds in
``rules/identification.yaml`` compare against, which G07's profile measures, plus the levels of
the region (and category) columns, so the compiled config can name the fixed-effect dummies
without reading the file.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from truelift.causal.dag import Column
from truelift.causal.rules import MappingRole, SemanticType


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MappedColumn(_Strict):
    name: Column
    role: MappingRole
    type: SemanticType
    bounded_0_1: bool = False


SINGLE_ROLES = ("date", "region", "category", "outcome", "population")


class ColumnMapping(_Strict):
    columns: list[MappedColumn] = Field(min_length=3)

    @model_validator(mode="after")
    def _well_formed(self) -> ColumnMapping:
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("columns: the same column is mapped twice")
        for role in SINGLE_ROLES:
            if sum(c.role == role for c in self.columns) > 1:
                raise ValueError(f"columns: more than one {role} column")
        for c in self.columns:
            if c.bounded_0_1 and c.type != "rate":
                raise ValueError(f"columns: {c.name}: only a rate can be bounded to [0, 1]")
        return self

    def get(self, name: str) -> MappedColumn | None:
        return next((c for c in self.columns if c.name == name), None)

    def by_role(self, role: str) -> list[MappedColumn]:
        return [c for c in self.columns if c.role == role]

    def one(self, role: str) -> MappedColumn | None:
        found = self.by_role(role)
        return found[0] if found else None


class PanelSummary(_Strict):
    weeks: int = Field(ge=1)
    regions: int = Field(ge=1)
    rows: int = Field(ge=1)
    treated_share: float = Field(ge=0, le=1)
    untreated_share: float = Field(ge=0, le=1)
    treatment_levels: int = Field(ge=0)
    gap_share: float = Field(ge=0, le=1)
    # Distinct values of each region or category column, for the fixed-effect dummies (C2).
    levels: dict[str, list[str]] = {}

    @model_validator(mode="after")
    def _levels(self) -> PanelSummary:
        for column, values in self.levels.items():
            if len(values) != len(set(values)) or not values:
                raise ValueError(f"levels.{column}: list each value once")
        return self
