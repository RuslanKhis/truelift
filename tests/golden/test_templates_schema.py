"""The business-type templates cover the five types and validate (G05/A2). Offline."""

from __future__ import annotations

import pytest

from truelift.causal.rules import RuleSet, load_rules

BUSINESS_TYPES = {"brand_via_retailers", "store_chain", "online_shop", "food_service", "subscription_service"}

# The interview slots the templates rely on. G12 defines each of them in templates/slots.yaml;
# a slot added or renamed here is a change G12 must follow.
SLOT_IDS = {
    "m2.calendar_events", "m2.local_events", "m2.macro_conditions", "m2.seasons", "m2.weather",
    "m3.competitor_response", "m3.discount_drivers", "m3.media_alignment", "m3.retailer_calendar",
    "m3.slow_sales_response", "m3.stock_clearance",
    "m4.competitor_activity", "m4.distribution", "m4.media", "m4.price_changes", "m4.sales_drivers",
    "m4.store_network",
    "m5.discount_side_effects",
}  # fmt: skip


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return load_rules()


def test_schema_templates_cover_the_five_business_types(rules: RuleSet) -> None:
    assert set(rules.templates) == BUSINESS_TYPES


@pytest.mark.parametrize("template_id", sorted(BUSINESS_TYPES))
def test_schema_template_shape(rules: RuleSet, template_id: str) -> None:
    t = rules.templates[template_id]
    assert (t.treatment, t.outcome) == ("discount", "sales")
    roles = {n.role for n in t.nodes}
    # Every business has something that drives both (C3 b) and something the discount causes
    # (the mediator trap, C3 a), so the interview always asks about both.
    assert {"confounder", "mediator"} <= roles
    assert any(n.may_modify_effect for n in t.nodes), "module 6 needs at least one candidate"
    assert any(e.default == "absent" for e in t.edges), "at least one edge is only asked about"
    sentences = [e.sentence for e in t.edges]
    assert len(sentences) == len(set(sentences))


def test_schema_template_slots_are_the_g12_handoff(rules: RuleSet) -> None:
    used = set().union(*(t.slot_ids() for t in rules.templates.values()))
    assert used == SLOT_IDS


def test_schema_every_unobserved_confounder_has_a_route(rules: RuleSet) -> None:
    """A confounder that is usually unobserved has a proxy rule, or the block offers only data
    or risk acceptance. This records which ones have no stand-in today."""
    without_proxy = sorted(
        {
            n.id
            for t in rules.templates.values()
            for n in t.nodes
            if n.role == "confounder" and not n.usually_observed and not rules.proxies.for_node(n.id)
        }
    )
    assert without_proxy == ["delivery_platform_promos", "retailer_promo_calendar"]
