"""Loader for the econometric rule files in ``rules/`` and the DAG templates in ``templates/``.

Thao owns those files (design D3, D18); code enforces them. This module only reads and validates
them: a malformed file raises :class:`RulesError` naming the file and the field, never a partial
rule set. Identification and compilation (G06) and the DAG builder (G31) consume the result.

Validation goes beyond types: every threshold carries a rationale, every proxy a caveat, block
messages cover every block code, and each template's default graph is acyclic and agrees with
the roles it gives its nodes (a "confounder" really leads to both the discount and sales).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

# Repository root when running from source (phase 1). src/truelift/causal/rules.py -> repo.
DEFAULT_ROOT = Path(__file__).resolve().parents[3]

NodeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
SlotId = Annotated[str, StringConstraints(pattern=r"^m[1-8]\.[a-z][a-z0-9_]*$", max_length=64)]
Text = Annotated[str, StringConstraints(min_length=10, max_length=600)]

# Vocabularies shared with the API (truelift.api.schemas); a test keeps them equal. They are
# repeated here so the causal core does not import the web layer.
NodeRole = Literal["treatment", "outcome", "confounder", "mediator", "modifier", "predictor"]
SemanticType = Literal["date", "key", "money", "volume", "rate", "index", "flag", "count", "text"]
MappingRole = Literal[
    "date",
    "region",
    "category",
    "outcome",
    "treatment_rate",
    "treatment_spend",
    "population",
    "control",
    "ignore",
]
Remedy = Literal["add_data", "use_proxy", "accept_risk"]

THRESHOLD_NAMES = (
    "min_weeks",
    "min_regions",
    "min_rows",
    "min_treated_share",
    "min_untreated_share",
    "min_treatment_levels",
    "max_gap_share",
)
BLOCK_CODES = (
    "descendant_in_controls",
    "unobserved_confounder",
    "too_few_weeks",
    "too_few_regions",
    "too_few_rows",
    "too_few_treated_rows",
    "too_few_untreated_rows",
    "too_few_treatment_levels",
    "panel_gaps",
)
WARNING_CODES = ("few_regions", "proxy_used", "risk_accepted", "forbidden_excluded", "left_out")


class RulesError(ValueError):
    """A rule or template file is missing or invalid. The message names the file and the field."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# --- rules/identification.yaml ------------------------------------------------------------


class AdjustmentRule(_Strict):
    rule: Literal["ancestral_v1"]
    description: Text
    source: Text


class Threshold(_Strict):
    value: float
    unit: str = Field(min_length=1)
    rationale: Text


class WarningRule(_Strict):
    message: Text
    below: int | None = None
    unit: str | None = None
    rationale: Text | None = None


class ControlRule(_Strict):
    value: float = Field(gt=0)
    rationale: Text


class BlockRule(_Strict):
    contract: Literal["C3a", "C3b", "C3c", "C3d"]
    message: Text
    remedies: list[Remedy]


class Identification(_Strict):
    schema_: Literal["truelift.rules.identification/1"] = Field(alias="schema")
    adjustment: AdjustmentRule
    thresholds: dict[str, Threshold]
    warnings: dict[str, WarningRule]
    controls: dict[Literal["max_predictors", "drop_vif_above"], ControlRule]
    blocks: dict[str, BlockRule]

    @model_validator(mode="after")
    def _complete(self) -> Identification:
        _same_keys("thresholds", self.thresholds, THRESHOLD_NAMES)
        _same_keys("blocks", self.blocks, BLOCK_CODES)
        _same_keys("warnings", self.warnings, WARNING_CODES)
        _same_keys("controls", self.controls, ("max_predictors", "drop_vif_above"))
        for name, t in self.thresholds.items():
            share = "share" in name
            if share and not 0 <= t.value <= 1:
                raise ValueError(f"thresholds.{name}: a share must lie in [0, 1]")
            if not share and (t.value < 1 or t.value != int(t.value)):
                raise ValueError(f"thresholds.{name}: a count must be a whole number of at least 1")
        if self.warnings["few_regions"].below is None:
            raise ValueError("warnings.few_regions: needs 'below'")
        return self

    def threshold(self, name: str) -> float:
        return self.thresholds[name].value


# --- rules/proxies.yaml -------------------------------------------------------------------


class ProxyRule(_Strict):
    id: NodeId
    stands_for: list[NodeId] = Field(min_length=1)
    column_examples: list[str] = Field(min_length=1)
    semantic_types: list[SemanticType] = Field(min_length=1)
    conditions: list[str]
    strength: Literal["partial", "weak"]
    caveat: Text


class Proxies(_Strict):
    schema_: Literal["truelift.rules.proxies/1"] = Field(alias="schema")
    conditions: dict[NodeId, Text]
    proxies: list[ProxyRule] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Proxies:
        _unique("proxies", (p.id for p in self.proxies))
        for p in self.proxies:
            unknown = sorted(set(p.conditions) - set(self.conditions))
            if unknown:
                raise ValueError(f"proxies.{p.id}.conditions: unknown condition {unknown}")
        return self

    def for_node(self, node_id: str) -> list[ProxyRule]:
        return [p for p in self.proxies if node_id in p.stands_for]

    def by_id(self, proxy_id: str) -> ProxyRule:
        for p in self.proxies:
            if p.id == proxy_id:
                return p
        raise KeyError(proxy_id)


# --- rules/normalisation.yaml -------------------------------------------------------------

Scaler = Literal["population_median_normalize_cols", "median_normalize_cols", "none", "not_a_feature"]


class TypeRule(_Strict):
    with_population: Scaler
    without_population: Scaler
    bounded_0_1: Scaler | None = None
    rationale: str = Field(min_length=5)


class Normalisation(_Strict):
    schema_: Literal["truelift.rules.normalisation/1"] = Field(alias="schema")
    applies_to: list[Literal["x_cols", "cate_covariates"]]
    never_scaled_roles: list[MappingRole]
    forbidden_scalers: dict[Literal["standardize_cols", "population_standardize_cols", "min_max_cols"], Text]
    types: dict[SemanticType, TypeRule]

    @model_validator(mode="after")
    def _complete(self) -> Normalisation:
        _same_keys("types", self.types, SemanticType.__args__)
        _same_keys(
            "forbidden_scalers",
            self.forbidden_scalers,
            ("standardize_cols", "population_standardize_cols", "min_max_cols"),
        )
        for name, rule in self.types.items():
            if rule.without_population == "population_median_normalize_cols":
                raise ValueError(f"types.{name}: per-capita scaling needs a population column")
        return self

    def scaler_for(self, semantic_type: str, *, has_population: bool, bounded_0_1: bool) -> str:
        rule = self.types[semantic_type]  # type: ignore[index]
        if bounded_0_1 and rule.bounded_0_1 is not None:
            return rule.bounded_0_1
        return rule.with_population if has_population else rule.without_population


# --- rules/cate.yaml ----------------------------------------------------------------------


class CateCovariates(_Strict):
    eligible: Text
    max_count: ControlRule
    order: Text


class CateDegree(_Strict):
    default: int = Field(ge=1, le=3)
    small_sample_rows: int = Field(ge=1)
    small_sample_max: int = Field(ge=1, le=3)
    rationale: Text


class CateStructure(_Strict):
    type: Literal["auto_additive"]
    df: ControlRule
    include_intercept: bool
    degree: CateDegree

    @model_validator(mode="after")
    def _df_fits_degree(self) -> CateStructure:
        # patsy's bs needs df >= degree + include_intercept.
        if self.df.value < self.degree.default + int(self.include_intercept):
            raise ValueError("structure.df: must be at least the degree (plus 1 with an intercept)")
        return self


class Cate(_Strict):
    schema_: Literal["truelift.rules.cate/1"] = Field(alias="schema")
    covariates: CateCovariates
    structure: CateStructure
    warnings: dict[Literal["cate_capped", "cate_small_sample"], WarningRule]

    @model_validator(mode="after")
    def _complete(self) -> Cate:
        _same_keys("warnings", self.warnings, ("cate_capped", "cate_small_sample"))
        return self

    def degree_for(self, rows: int) -> int:
        d = self.structure.degree
        return min(d.default, d.small_sample_max) if rows < d.small_sample_rows else d.default


# --- templates/*.yaml ---------------------------------------------------------------------


class TemplateNode(_Strict):
    id: NodeId
    label: str = Field(min_length=3, max_length=120)
    role: NodeRole
    usually_observed: bool
    may_modify_effect: bool = False


class TemplateEdge(_Strict):
    from_: NodeId = Field(alias="from")
    to: NodeId
    default: Literal["present", "absent"]
    sentence: Text
    confirmed_by: list[SlotId] = Field(min_length=1)


class Template(_Strict):
    schema_: Literal["truelift.template/1"] = Field(alias="schema")
    id: NodeId
    title: str = Field(min_length=5, max_length=120)
    description: Text
    treatment: NodeId
    outcome: NodeId
    nodes: list[TemplateNode] = Field(min_length=3)
    edges: list[TemplateEdge] = Field(min_length=2)

    @model_validator(mode="after")
    def _graph(self) -> Template:
        _unique("nodes", (n.id for n in self.nodes))
        _unique("edges", (f"{e.from_} -> {e.to}" for e in self.edges))
        roles = {n.id: n.role for n in self.nodes}
        for role, node in (("treatment", self.treatment), ("outcome", self.outcome)):
            holders = [n for n, r in roles.items() if r == role]
            if holders != [node]:
                raise ValueError(f"exactly one node, {node!r}, must have role {role}; found {holders}")
        for e in self.edges:
            for end in (e.from_, e.to):
                if end not in roles:
                    raise ValueError(f"edge {e.from_} -> {e.to}: unknown node {end!r}")
            if e.from_ == e.to:
                raise ValueError(f"edge {e.from_} -> {e.to}: a node cannot cause itself")
            if e.from_ == self.outcome:
                raise ValueError(f"edge {e.from_} -> {e.to}: nothing in the same week is caused by sales")
        every = _children(self.edges)
        _acyclic(roles, every)
        present = _children(e for e in self.edges if e.default == "present")
        if self.outcome not in present.get(self.treatment, set()):
            raise ValueError(f"the edge {self.treatment} -> {self.outcome} must be present by default")
        _check_roles(self, present)
        return self

    def present_edges(self) -> list[tuple[str, str]]:
        return [(e.from_, e.to) for e in self.edges if e.default == "present"]

    def slot_ids(self) -> set[str]:
        return {s for e in self.edges for s in e.confirmed_by}


def _children(edges: Iterable[TemplateEdge]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for e in edges:
        out.setdefault(e.from_, set()).add(e.to)
    return out


def _reach(start: str, children: dict[str, set[str]], *, avoid: str | None = None) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child != avoid and child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _acyclic(nodes: Iterable[str], children: dict[str, set[str]]) -> None:
    for n in nodes:
        if n in _reach(n, children):
            raise ValueError(f"the graph has a cycle through {n!r}")


def _check_roles(t: Template, present: dict[str, set[str]]) -> None:
    """Each node's role must match where it sits in the default graph."""
    after_treatment = _reach(t.treatment, present)
    for n in t.nodes:
        if n.role in ("treatment", "outcome"):
            continue
        reach = _reach(n.id, present)
        reach_outcome_directly = t.outcome in _reach(n.id, present, avoid=t.treatment)
        caused_by_treatment = n.id in after_treatment
        ok = {
            "confounder": t.treatment in reach and reach_outcome_directly and not caused_by_treatment,
            "mediator": caused_by_treatment and t.outcome in reach,
            "predictor": reach_outcome_directly and t.treatment not in reach and not caused_by_treatment,
            "modifier": t.outcome in reach and not caused_by_treatment,
        }[n.role]
        if not ok:
            raise ValueError(f"node {n.id!r}: its default edges do not fit the role {n.role!r}")
        if n.may_modify_effect and caused_by_treatment:
            raise ValueError(f"node {n.id!r}: something the discount causes cannot modify its effect")


# --- loading ------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleSet:
    identification: Identification
    proxies: Proxies
    normalisation: Normalisation
    cate: Cate
    templates: dict[str, Template]
    truth_schema: dict[str, Any]

    def node_vocabulary(self) -> set[str]:
        return {n.id for t in self.templates.values() for n in t.nodes}


class _UniqueKeyLoader(yaml.SafeLoader):
    """A safe loader that refuses duplicate keys, which PyYAML would otherwise drop silently."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def read_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RulesError(f"{path.name}: file not found") from exc
    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" line {mark.line + 1}" if mark is not None else ""
        raise RulesError(f"{path.name}{where}: not valid YAML ({getattr(exc, 'problem', exc)})") from exc


def _parse[M: BaseModel](model: type[M], path: Path, data: Any) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"]) or "(top level)"
        raise RulesError(f"{path.name}: {loc}: {first['msg']}") from exc


def load_rules(root: Path | None = None) -> RuleSet:
    """Read and validate every rule file and template under ``root`` (the repository by default)."""
    root = root or DEFAULT_ROOT
    rules_dir, templates_dir = root / "rules", root / "templates"

    def load[M: BaseModel](model: type[M], name: str) -> M:
        path = rules_dir / name
        return _parse(model, path, read_yaml(path))

    identification = load(Identification, "identification.yaml")
    proxies = load(Proxies, "proxies.yaml")
    normalisation = load(Normalisation, "normalisation.yaml")
    cate = load(Cate, "cate.yaml")
    truth_schema = load_truth_schema(rules_dir / "truth_sidecar.yaml")

    templates: dict[str, Template] = {}
    for path in sorted(templates_dir.glob("*.yaml")):
        data = read_yaml(path)
        # templates/ also holds other files (G12's slots.yaml); only business templates load here.
        if not isinstance(data, dict) or data.get("schema") != "truelift.template/1":
            continue
        template = _parse(Template, path, data)
        if template.id != path.stem:
            raise RulesError(f"{path.name}: id {template.id!r} must match the file name")
        templates[template.id] = template
    if not templates:
        raise RulesError(f"{templates_dir.name}/: no business templates found")

    _check_shared_vocabulary(templates)
    vocabulary = {n.id for t in templates.values() for n in t.nodes}
    for p in proxies.proxies:
        unknown = sorted(set(p.stands_for) - vocabulary)
        if unknown:
            raise RulesError(f"proxies.yaml: proxies.{p.id}.stands_for: no template has node {unknown}")
    return RuleSet(identification, proxies, normalisation, cate, templates, truth_schema)


def _check_shared_vocabulary(templates: dict[str, Template]) -> None:
    """The same node ID means the same kind of thing in every template (proxies rely on it)."""
    seen: dict[str, tuple[str, str]] = {}
    for t in templates.values():
        for n in t.nodes:
            # Confounder, predictor and modifier may differ by business; these three may not.
            kind = n.role if n.role in ("treatment", "outcome", "mediator") else "pre-treatment factor"
            if n.id in seen and seen[n.id][0] != kind:
                raise RulesError(
                    f"{t.id}.yaml: node {n.id!r} is a {kind} here but a {seen[n.id][0]} "
                    f"in {seen[n.id][1]}.yaml"
                )
            seen.setdefault(n.id, (kind, t.id))


# --- rules/truth_sidecar.yaml -------------------------------------------------------------


def load_truth_schema(path: Path | None = None) -> dict[str, Any]:
    path = path or DEFAULT_ROOT / "rules" / "truth_sidecar.yaml"
    schema = read_yaml(path)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # jsonschema.SchemaError
        raise RulesError(f"{path.name}: not a valid JSON Schema ({exc})") from exc
    return schema


def validate_truth(data: Any, schema: dict[str, Any] | None = None) -> list[str]:
    """Problems with a truth.yaml document, one line each, as ``path: message``; empty when valid."""
    validator = Draft202012Validator(schema or load_truth_schema())
    problems = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        loc = "/".join(str(p) for p in err.absolute_path) or "(top level)"
        problems.append(f"{loc}: {err.message}")
    return problems


# --- helpers ------------------------------------------------------------------------------


def _same_keys(field: str, mapping: dict[str, Any], expected: Iterable[str]) -> None:
    missing = sorted(set(expected) - set(mapping))
    extra = sorted(set(mapping) - set(expected))
    if missing or extra:
        raise ValueError(f"{field}: missing {missing}, unexpected {extra}")


def _unique(field: str, values: Iterable[str]) -> None:
    seen: set[str] = set()
    for v in values:
        if v in seen:
            raise ValueError(f"{field}: {v!r} appears twice")
        seen.add(v)
