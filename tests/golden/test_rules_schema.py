"""The rule files in rules/ load and say what C3 needs (G05/A1, A3). Offline."""

from __future__ import annotations

import re
import shutil
import typing
from pathlib import Path

import pytest
import yaml

from truelift.api import schemas as api
from truelift.causal import rules as r
from truelift.causal.rules import DEFAULT_ROOT, THRESHOLD_NAMES, RulesError, load_rules

PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
# Values code can fill into a message; anything else is a typo Thao would not see until runtime.
KNOWN_PLACEHOLDERS = {
    "node_labels", "node_label", "weeks", "regions", "rows", "share", "levels", "min", "max",
    "proxy_column", "caveat", "column", "kept", "dropped",
}  # fmt: skip


@pytest.fixture(scope="module")
def rules() -> r.RuleSet:
    return load_rules()


def raw(name: str) -> dict:
    return yaml.safe_load((DEFAULT_ROOT / "rules" / name).read_text())


def test_schema_rule_files_load(rules: r.RuleSet) -> None:
    assert rules.identification.adjustment.rule == "ancestral_v1"
    assert rules.proxies.proxies
    assert rules.truth_schema["properties"]["schema"]["const"] == "truelift.truth/1"


def test_schema_every_threshold_has_value_and_one_line_rationale() -> None:
    """A1: each threshold has a value and a one-line source or rationale."""
    thresholds = raw("identification.yaml")["thresholds"]
    assert set(thresholds) == set(THRESHOLD_NAMES)
    for name, t in thresholds.items():
        assert isinstance(t["value"], int | float), name
        rationale = t["rationale"]
        assert "\n" not in rationale.strip(), f"{name}: rationale must be one line"
        assert rationale.count(". ") <= 1, f"{name}: rationale must be one sentence or two at most"
        assert 20 <= len(rationale) <= 250, name


def test_schema_threshold_values_are_the_recorded_ones(rules: r.RuleSet) -> None:
    th = rules.identification.threshold
    assert (th("min_weeks"), th("min_regions"), th("min_rows")) == (52, 2, 200)
    assert (th("min_treated_share"), th("min_untreated_share")) == (0.10, 0.05)
    assert (th("min_treatment_levels"), th("max_gap_share")) == (3, 0.05)
    assert rules.identification.warnings["few_regions"].below == 30


def test_schema_block_and_warning_messages_use_known_placeholders(rules: r.RuleSet) -> None:
    messages = {f"blocks.{k}": b.message for k, b in rules.identification.blocks.items()}
    messages |= {f"warnings.{k}": w.message for k, w in rules.identification.warnings.items()}
    messages |= {f"cate.{k}": w.message for k, w in rules.cate.warnings.items()}
    for where, text in messages.items():
        unknown = set(PLACEHOLDER.findall(text)) - KNOWN_PLACEHOLDERS
        assert not unknown, f"{where}: unknown placeholder {unknown}"


def test_schema_node_blocks_name_the_missing_item(rules: r.RuleSet) -> None:
    """C3: a block about a node names it; the stand-in remedy is offered only by C3 b."""
    blocks = rules.identification.blocks
    for code in ("descendant_in_controls", "unobserved_confounder"):
        assert "{node_labels}" in blocks[code].message
    assert blocks["unobserved_confounder"].remedies == ["add_data", "use_proxy", "accept_risk"]
    assert all("use_proxy" not in b.remedies for k, b in blocks.items() if k != "unobserved_confounder")


def test_schema_every_proxy_has_a_caveat_and_known_conditions(rules: r.RuleSet) -> None:
    """A3: each proxy rule has a caveat the UI can show."""
    vocabulary = rules.node_vocabulary()
    for p in rules.proxies.proxies:
        assert len(p.caveat) >= 80, f"{p.id}: caveat too short to explain the risk"
        assert "\n" not in p.caveat
        assert set(p.conditions) <= set(rules.proxies.conditions)
        assert set(p.stands_for) <= vocabulary
    # Every proxy for something a discount could move is lagged or measured before the discount.
    for pid in ("competitor_price_index", "stock_cover", "previous_weeks_sales"):
        assert {"lagged_one_week", "start_of_week"} & set(rules.proxies.by_id(pid).conditions), pid


def test_schema_normalisation_matches_the_design_table(rules: r.RuleSet) -> None:
    n = rules.normalisation
    assert n.scaler_for("money", has_population=True, bounded_0_1=False) == "population_median_normalize_cols"
    assert n.scaler_for("money", has_population=False, bounded_0_1=False) == "median_normalize_cols"
    assert (
        n.scaler_for("volume", has_population=True, bounded_0_1=False) == "population_median_normalize_cols"
    )
    assert n.scaler_for("rate", has_population=True, bounded_0_1=True) == "none"
    assert n.scaler_for("rate", has_population=True, bounded_0_1=False) == "median_normalize_cols"
    assert n.scaler_for("index", has_population=True, bounded_0_1=False) == "median_normalize_cols"
    assert n.scaler_for("flag", has_population=True, bounded_0_1=False) == "none"
    for t in ("date", "key", "text"):
        assert n.scaler_for(t, has_population=True, bounded_0_1=False) == "not_a_feature"
    assert {"outcome", "treatment_rate", "treatment_spend"} <= set(n.never_scaled_roles)


def test_schema_cate_rules(rules: r.RuleSet) -> None:
    assert rules.cate.covariates.max_count.value == 3
    assert rules.cate.degree_for(999) <= 2  # doubleml-pipeline 0.2.3 warns above 2 under 1,000 rows
    assert rules.cate.degree_for(1248) == 2
    assert rules.cate.structure.type == "auto_additive"


def test_schema_vocabularies_match_the_api() -> None:
    """The causal core repeats the API's enums rather than importing the web layer."""
    pairs = [
        (r.NodeRole, api.NodeRole),
        (r.SemanticType, api.SemanticType),
        (r.MappingRole, api.Role),
        (r.Remedy, api.Remedy),
    ]
    for literal, enum in pairs:
        assert set(typing.get_args(literal)) == {e.value for e in enum}, enum.__name__


# --- the loader refuses bad files ---------------------------------------------------------


@pytest.fixture
def copy_root(tmp_path: Path) -> Path:
    for d in ("rules", "templates"):
        shutil.copytree(DEFAULT_ROOT / d, tmp_path / d)
    return tmp_path


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))


@pytest.mark.parametrize(
    ("file", "old", "new", "error"),
    [
        (
            "rules/identification.yaml",
            "  min_weeks:\n    value: 52\n    unit: weeks\n    rationale: >-\n"
            "      One full year, so that each season and holiday is seen at least once"
            " and can be told apart\n      from the discount calendar.\n",
            "  min_weeks:\n    value: 52\n    unit: weeks\n",
            "thresholds.min_weeks.rationale",
        ),
        ("rules/identification.yaml", "value: 0.10\n", "value: 10\n", "a share must lie in [0, 1]"),
        (
            "rules/identification.yaml",
            "  panel_gaps:\n",
            "  panel_holes:\n",
            "blocks: missing ['panel_gaps']",
        ),
        ("rules/identification.yaml", "  min_rows:\n", "  min_weeks:\n", "duplicate key 'min_weeks'"),
        ("rules/proxies.yaml", "stands_for: [market_demand]", "stands_for: [moon_phase]", "moon_phase"),
        ("rules/proxies.yaml", "conditions: [lagged_one_week]\n", "conditions: [same_week]\n", "same_week"),
        ("rules/normalisation.yaml", "  flag:\n", "  boolean:\n", "types"),
        (
            "rules/cate.yaml",
            "    value: 3\n    rationale: The pipeline",
            "    value: 1\n    rationale: The pipeline",
            "structure.df",
        ),
        (
            "templates/store_chain.yaml",
            "  - from: store_traffic\n    to: sales\n",
            "  - from: store_traffic\n    to: discount\n",
            "cycle",
        ),
        (
            "templates/store_chain.yaml",
            "id: weather, label: The weather, role: predictor",
            "id: weather, label: The weather, role: confounder",
            "role 'confounder'",
        ),
        (
            "templates/online_shop.yaml",
            "confirmed_by: [m5.discount_side_effects]\n",
            "confirmed_by: [discount_side_effects]\n",
            "confirmed_by",
        ),
        (
            "templates/food_service.yaml",
            "id: food_service\n",
            "id: restaurants\n",
            "must match the file name",
        ),
    ],
)
def test_schema_loader_rejects_invalid_files(
    copy_root: Path, file: str, old: str, new: str, error: str
) -> None:
    _edit(copy_root / file, old, new)
    with pytest.raises(RulesError) as exc:
        load_rules(copy_root)
    assert error in str(exc.value)
    assert Path(file).name in str(exc.value)
