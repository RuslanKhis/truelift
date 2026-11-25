"""The config compiler: DAG + mapping + panel + run profile -> ``PipelineConfig`` (C2, C3, C4; D3).

The pipeline config is a pure function of (DAG version, mapping, data fingerprint, run profile,
compiler version), emitted as canonical JSON: sorted keys, fixed separators, UTF-8, one trailing
newline. The same inputs give the same bytes in any process on any OS (G06/A3). No LLM writes a
field: this module is the only constructor of ``PipelineConfig`` in the product, and agents have
no tool that reaches it.

The rules follow the design's table (section 5, "DAG and mapping -> doubleml-pipeline"):

* ``y_col`` is the outcome column. A rate treatment in [0, 1] compiles as ``'percentage'`` with
  ``sales_col`` and the spend column; a money treatment compiles as ``'spend'`` and is its own
  spend column. A rate without a spend column is the compile error ``missing_spend_column``.
* ``x_cols_list`` is the identified adjustment set's columns plus one dummy per region (and
  category) level. Never a descendant of the discount, the outcome or a ground-truth column.
* ``covariates_for_cate_list`` holds the CATE covariates identification chose; ``[[]]`` when
  there are none (ATE only). ``cate_structure_list`` comes from ``rules/cate.yaml``.
* Scaler lists come from each control's semantic type through ``rules/normalisation.yaml``.
* ``opt_threshold_roi`` is ``1 / margin``; 1.0, marked assumed, when the margin is unknown.
* Learners, folds, ``time_budget``, ``top_n`` and ``n_reps`` come from the run profile (D9, with
  the values G03 measured). Sensitivity is on in Standard, and whenever a risk was accepted.
* ``ground_truth_*`` and ``saturation_config`` are never set (C4; saturation is G27).
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from truelift.causal.dag import Dag
from truelift.causal.forbidden import DEFAULT, DenyList
from truelift.causal.identify import Identification, identify
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.causal.rules import RuleSet

# Bump when the output for the same inputs changes, so runs record which compiler made them.
COMPILER_VERSION = "1"
CONFIG_SCHEMA = "truelift.pipeline_config/1"


class Profile(StrEnum):
    quick = "quick"
    standard = "standard"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ProfileSettings(_Strict):
    ml_models: list[str]
    n_folds: list[int]
    time_budget: int
    top_n: int
    n_reps: int
    run_sensitivity: bool


# D9 run profiles with the values G03 measured (G03 ruling R1, accepted 2026-11-07).
PROFILES: dict[Profile, ProfileSettings] = {
    Profile.quick: ProfileSettings(
        ml_models=["lgbm"], n_folds=[5], time_budget=10, top_n=1, n_reps=3, run_sensitivity=False
    ),
    Profile.standard: ProfileSettings(
        ml_models=["lgbm", "xgboost"],
        n_folds=[3, 5],
        time_budget=30,
        top_n=3,
        n_reps=10,
        run_sensitivity=True,
    ),
}
SENSITIVITY_SCOPE = ["total", "geo"]

CompileErrorCode = Literal[
    "not_identified",
    "missing_spend_column",
    "ambiguous_spend_column",
    "treatment_not_a_rate",
    "missing_date_column",
    "missing_region_column",
    "missing_levels",
    "dummy_name_clash",
    "not_a_feature",
    "forbidden_column",
    "invalid_margin",
]

_MESSAGES: dict[str, str] = {
    "missing_spend_column": (
        "Your discount is recorded as a rate. To work out the return on each euro of discount we "
        "also need what the discounts cost each week: map a discount spend column."
    ),
    "ambiguous_spend_column": "More than one column is mapped as discount spend. Keep one.",
    "treatment_not_a_rate": (
        "The discount column is mapped as a rate but its values are not limited to 0-1. Map it as a "
        "rate between 0 and 1, or as money spent."
    ),
    "missing_date_column": "No column is mapped as the week. Map the date column.",
    "missing_region_column": "No column is mapped as the region. Map the region column.",
    "missing_levels": "The data profile does not list the values of {column}. Upload the file again.",
    "dummy_name_clash": "{name} is already a column in your file, so it cannot name a region. Rename it.",
    "not_a_feature": (
        "{column} is mapped as a {type}, which cannot be used to explain sales. Change its type."
    ),
    "forbidden_column": "{column} is ground truth and cannot be used in the analysis.",
    "invalid_margin": "The gross margin must be a share between 0 and 1, for example 0.4 for 40%.",
}


class CompileError(ValueError):
    """The inputs cannot be compiled. ``code`` is stable; ``message`` is in business words."""

    def __init__(self, code: CompileErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _error(code: CompileErrorCode, **values: str) -> CompileError:
    return CompileError(code, _MESSAGES[code].format_map(values))


class OrchestratorSettings(_Strict):
    """Keyword arguments of ``doubleml_pipeline.workflow.CausalWorkflowOrchestrator`` (0.2.3).

    ``output_dir`` and ``n_jobs`` belong to the run, not the config; G09's worker adds them.
    """

    y_col: str
    d_cols: list[str]
    x_cols_list: list[list[str]]
    ml_models_y: list[str]
    ml_models_t: list[str]
    n_folds_list: list[int]
    covariates_for_cate_list: list[list[str]]
    cate_structure_list: list[dict[str, Any]]
    time_budget: int
    date_col: str
    geo_col: str
    item_col: str | None
    run_sensitivity: bool
    sensitivity_scope: list[str]
    treatment_types: dict[str, Literal["percentage", "spend"]]
    treatment_spend_cols: dict[str, str]
    sales_col: str | None
    optimize: bool
    opt_threshold_roi: float


class ScalerSettings(_Strict):
    """Keyword arguments of ``doubleml_pipeline.preprocessing.scalers.CausalDataScaler`` (0.2.3)."""

    median_normalize_cols: list[str] = []
    population_median_normalize_cols: list[str] = []
    population_col: str | None = None


class RunSettings(_Strict):
    """Keyword arguments of ``run_full_pipeline`` that the config fixes."""

    top_n: int
    n_reps: int


class Dummies(_Strict):
    """One 0/1 column per level of a region or category column, named ``<column>_<level>``."""

    column: str
    levels: list[str]
    names: list[str]


class PipelineConfig(_Strict):
    schema_: Literal["truelift.pipeline_config/1"] = Field(default=CONFIG_SCHEMA, alias="schema")
    compiler_version: str
    profile: Profile
    data_fingerprint: str
    controls: list[str]
    dummies: list[Dummies]
    opt_threshold_roi_assumed: bool
    orchestrator: OrchestratorSettings
    scaler: ScalerSettings
    run: RunSettings

    def to_json(self) -> bytes:
        """The canonical JSON bytes (C2)."""
        data = self.model_dump(mode="json", by_alias=True)
        text = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        return (text + "\n").encode("utf-8")

    def sha256(self) -> str:
        return hashlib.sha256(self.to_json()).hexdigest()

    @classmethod
    def from_json(cls, raw: bytes | str) -> PipelineConfig:
        """Read a compiled config back (the worker, G09). Refuses unknown fields."""
        return cls.model_validate(json.loads(raw))

    def orchestrator_kwargs(self, output_dir: str, n_jobs: int = -1) -> dict[str, Any]:
        kwargs = self.orchestrator.model_dump()
        if kwargs["item_col"] is None:
            del kwargs["item_col"]
        return {**kwargs, "output_dir": output_dir, "n_jobs": n_jobs}

    def scaler_kwargs(self) -> dict[str, Any]:
        kwargs = self.scaler.model_dump()
        if kwargs["population_col"] is None:
            del kwargs["population_col"]
        return kwargs


def compile_config(
    dag: Dag,
    mapping: ColumnMapping,
    panel: PanelSummary,
    rules: RuleSet,
    *,
    profile: Profile,
    data_fingerprint: str,
    margin: float | None = None,
    deny: DenyList = DEFAULT,
) -> PipelineConfig:
    """Compile the pipeline config, or raise :class:`CompileError` with a business-language reason."""
    ident = identify(dag, mapping, panel, rules, deny=deny)
    if not ident.identified:
        raise CompileError("not_identified", " ".join(b.message for b in ident.blocks))
    return _compile(ident, dag, mapping, panel, rules, Profile(profile), data_fingerprint, margin, deny)


def _compile(
    ident: Identification,
    dag: Dag,
    mapping: ColumnMapping,
    panel: PanelSummary,
    rules: RuleSet,
    profile: Profile,
    data_fingerprint: str,
    margin: float | None,
    deny: DenyList,
) -> PipelineConfig:
    if margin is not None and not 0 < margin <= 1:
        raise _error("invalid_margin")
    y_col = dag.node(dag.outcome).column
    t = mapping.get(dag.node(dag.treatment).column or "")
    assert y_col is not None and t is not None  # identify() checked both

    # Treatment kind, spend and sales columns.
    if t.role == "treatment_rate":
        if t.type != "rate" or not t.bounded_0_1:
            raise _error("treatment_not_a_rate")
        spend = mapping.by_role("treatment_spend")
        if not spend:
            raise _error("missing_spend_column")
        if len(spend) > 1:
            raise _error("ambiguous_spend_column")
        kind, spend_col, sales_col = "percentage", spend[0].name, y_col
    else:
        kind, spend_col, sales_col = "spend", t.name, None

    date, geo, item = mapping.one("date"), mapping.one("region"), mapping.one("category")
    if date is None:
        raise _error("missing_date_column")
    if geo is None:
        raise _error("missing_region_column")
    population = mapping.one("population")
    for c in (spend_col, sales_col, date.name, geo.name, item.name if item else None):
        if c and deny.is_forbidden(c):
            raise _error("forbidden_column", column=c)

    # Fixed effects as dummies, named from the profiled levels.
    taken = {c.name for c in mapping.columns}
    dummies: list[Dummies] = []
    for column in ident.fixed_effects:
        levels = panel.levels.get(column)
        if not levels:
            raise _error("missing_levels", column=column)
        ordered = sorted(levels)
        names = [f"{column}_{level}" for level in ordered]
        for name in names:
            if name in taken:
                raise _error("dummy_name_clash", name=name)
            taken.add(name)
        dummies.append(Dummies(column=column, levels=ordered, names=names))

    # Scalers for controls and CATE covariates only (G05 ruling R6).
    scaler_lists: dict[str, list[str]] = {"median_normalize_cols": [], "population_median_normalize_cols": []}
    for name in sorted(set(ident.x_cols) | set(ident.cate_covariates)):
        col = mapping.get(name)
        assert col is not None
        scaler = rules.normalisation.scaler_for(
            col.type, has_population=population is not None, bounded_0_1=col.bounded_0_1
        )
        if scaler == "not_a_feature":
            raise _error("not_a_feature", column=name, type=col.type)
        if scaler != "none":
            scaler_lists[scaler].append(name)

    settings = PROFILES[profile]
    structure = rules.cate.structure
    degree = ident.cate_degree or rules.cate.degree_for(panel.rows)
    threshold = round(1 / margin, 6) if margin is not None else 1.0
    orchestrator = OrchestratorSettings(
        y_col=y_col,
        d_cols=[t.name],
        x_cols_list=[ident.x_cols + [n for d in dummies for n in d.names]],
        ml_models_y=settings.ml_models,
        ml_models_t=settings.ml_models,
        n_folds_list=settings.n_folds,
        covariates_for_cate_list=[ident.cate_covariates],
        cate_structure_list=[
            {
                "type": structure.type,
                "df": int(structure.df.value),
                "degree": degree,
                "include_intercept": structure.include_intercept,
            }
        ],
        time_budget=settings.time_budget,
        date_col=date.name,
        geo_col=geo.name,
        item_col=item.name if item else None,
        run_sensitivity=settings.run_sensitivity or bool(ident.risk_accepted),
        sensitivity_scope=SENSITIVITY_SCOPE,
        treatment_types={t.name: kind},
        treatment_spend_cols={t.name: spend_col},
        sales_col=sales_col,
        optimize=True,
        opt_threshold_roi=threshold,
    )
    return PipelineConfig(
        compiler_version=COMPILER_VERSION,
        profile=profile,
        data_fingerprint=data_fingerprint,
        controls=ident.x_cols,
        dummies=dummies,
        opt_threshold_roi_assumed=margin is None,
        orchestrator=orchestrator,
        scaler=ScalerSettings(**scaler_lists, population_col=population.name if population else None),
        run=RunSettings(top_n=settings.top_n, n_reps=settings.n_reps),
    )
