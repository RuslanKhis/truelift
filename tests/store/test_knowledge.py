"""G08 A1 and A3: the knowledge format round-trips byte for byte, a new project has the D4
layout, and a broken hand edit is an error with its file and line that drops no fact (C11)."""

from __future__ import annotations

import pytest

from tests.store.conftest import NOW, interview, snapshot
from truelift.store import FactStatus, ParseFailed, ProjectStore
from truelift.store.knowledge import (
    KNOWLEDGE_FILES,
    Fact,
    Source,
    SourceKind,
    fact_lines,
    load_knowledge,
    new_file,
    parse,
)

# The example from design §5 ("Knowledge file example (D4)"), verbatim.
D4_EXAMPLE = """---
project: petfood-de
schema: truelift.knowledge/1
---
# How discounts are decided
- [F012] We discount mostly in holiday weeks (Black Friday, Christmas) and when stock is ageing.
  status: confirmed · source: interview t14 "mostly around Black Friday and when stock gets old" · 2026-11-05
  supports: edge(holiday_weeks -> discount), edge(inventory_age -> discount)
- [F013] Competitor promotions do not influence our discount calendar.
  status: assumed · source: template default · supports: no-edge(competitor_promo -> discount)
"""

HAND_EDITED = """---
project: petfood-de
schema: truelift.knowledge/1
owner: marketing   # an extra key the user added
---

# Business model

We sell dry and wet food through supermarkets and our own shop.
Ümlauts, “quotes” and emoji 🐕 stay as they are.

- [F001] Most sales go through supermarket chains.
  status: confirmed · source: interview t2 "about 80% is retail · the rest online" · 2026-11-01
- [F002] Online sales grow every year.
    status: unknown · source: agent suggestion

## Channels
- [F003] TV runs in autumn.
  supports: node(tv) · status: assumed · 2026-10-30 · source: data profile
- [F004] Margin is about 40%.
  status: confirmed · source: interview t9 "roughly forty percent"
  supports: column(margin)

Trailing prose without a newline"""


@pytest.mark.parametrize(
    "text",
    [
        D4_EXAMPLE,
        HAND_EDITED,
        D4_EXAMPLE.replace("\n", "\r\n"),
        HAND_EDITED.replace("\n", "\r\n"),
        D4_EXAMPLE.rstrip("\n"),
        D4_EXAMPLE + "\n\n\n",
        new_file("business.md", "garden-tools"),
    ],
    ids=["d4", "hand-edited", "d4-crlf", "hand-crlf", "no-final-newline", "trailing-blanks", "new-file"],
)
def test_parse_then_render_is_byte_identical(text):
    doc = parse(text, "business.md")
    assert doc.issues == ()
    assert doc.render() == text
    assert doc.render().encode() == text.encode()


def test_d4_example_parses_into_its_facts():
    doc = parse(D4_EXAMPLE, "business.md")
    f12, f13 = doc.facts
    assert f12.id == "F012" and f12.status is FactStatus.confirmed
    assert f12.source == Source(
        SourceKind.interview, 14, "mostly around Black Friday and when stock gets old"
    )
    assert f12.date == "2026-11-05"
    assert f12.supports == ("edge(holiday_weeks -> discount)", "edge(inventory_age -> discount)")
    assert f12.section == "How discounts are decided"
    assert f13.status is FactStatus.assumed and f13.source.kind is SourceKind.template_default
    assert f13.supports == ("no-edge(competitor_promo -> discount)",)


def test_hand_edited_metadata_in_any_order_and_quotes_with_separators():
    facts = {f.id: f for f in parse(HAND_EDITED, "business.md").facts}
    assert facts["F001"].source.quote == "about 80% is retail · the rest online"
    assert facts["F003"].supports == ("node(tv)",) and facts["F003"].section == "Channels"
    assert facts["F004"].date is None


def test_writer_produces_the_d4_layout():
    doc = parse(D4_EXAMPLE, "business.md")
    f12 = doc.get("F012")
    assert "".join(fact_lines(f12)) == "".join(D4_EXAMPLE.splitlines(keepends=True)[5:8])


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_changing_one_fact_rewrites_only_its_lines(newline):
    text = HAND_EDITED.replace("\n", newline)
    doc = parse(text, "business.md")
    f002 = doc.get("F002")
    changed = Fact(
        f002.id, "Online sales doubled since 2024.", FactStatus.confirmed, interview(20, "doubled")
    )
    new = doc.upsert(changed)
    before, after = text.splitlines(keepends=True), new.render().splitlines(keepends=True)
    start = 13  # F002 occupies lines 14-15 (0-based 13-14) before and after
    assert after[:start] == before[:start]
    assert after[start:15] == list(fact_lines(changed, newline))
    assert after[15:] == before[15:]
    assert new.get("F002").text == "Online sales doubled since 2024."


def test_new_fact_goes_to_the_end_of_its_section():
    doc = parse(new_file("market.md", "p"), "market.md")
    first = Fact(
        "F001", "Christmas is the peak.", FactStatus.confirmed, interview(3, "christmas"), section="Calendar"
    )
    second = Fact(
        "F002",
        "Easter is small.",
        FactStatus.assumed,
        Source(SourceKind.template_default),
        None,
        (),
        "Calendar",
    )
    doc = doc.upsert(first).upsert(second)
    lines = doc.render().splitlines()
    calendar = lines.index("# Calendar")
    assert lines[calendar + 1].startswith("- [F001]") and lines[calendar + 3].startswith("- [F002]")
    assert lines[calendar + 5] == "" and lines[calendar + 6] == "# Seasons"
    assert parse(doc.render(), "market.md").issues == ()


def test_new_fact_in_an_unknown_section_or_after_text_without_newline():
    doc = parse(HAND_EDITED, "business.md")
    fact = Fact(
        "F009",
        "Discount depth is set centrally.",
        FactStatus.confirmed,
        interview(4, "central"),
        section="Pricing",
    )
    rendered = doc.upsert(fact).render()
    assert rendered.startswith(HAND_EDITED)  # nothing above changed
    assert rendered.endswith(
        "\n\n# Pricing\n- [F009] Discount depth is set centrally.\n"
        '  status: confirmed · source: interview t4 "central"\n'
    )


# --- A1: a new project lays out its folder --------------------------------------------------


def test_create_lays_out_the_project_folder(store: ProjectStore):
    info = store.create("Garden tools DE")
    root = store.projects_dir / "garden-tools-de"
    assert info.id == "garden-tools-de" and info.knowledge_version == 0
    for name in ("business.md", "market.md", "data.md", "project.yaml"):
        assert (root / name).is_file()
    for name in ("dag", "mapping", "proposals", "runs"):
        assert (root / name).is_dir()
    for name in KNOWLEDGE_FILES:
        text = (root / name).read_text()
        doc = parse(text, name)
        assert doc.issues == () and doc.render() == text
    assert [p.name for p in store.projects_dir.iterdir()] == ["garden-tools-de"]  # no temp folder left


def test_project_files_round_trip_after_accepted_changes(store: ProjectStore, project, root):
    store.propose_fact(
        project,
        file="business.md",
        section="Channels",
        text="Most sales are retail.",
        source=interview(2, "mostly retail"),
        summary="Retail",
    )
    store.decide(project, "P001", accept=True, knowledge_version=0)
    for name in KNOWLEDGE_FILES:
        raw = (root / name).read_bytes()
        assert parse(raw.decode(), name).render().encode() == raw


def test_create_conflicts_and_reserved_ids(store: ProjectStore):
    store.create("Garden tools")
    from truelift.store import Conflict

    with pytest.raises(Conflict):
        store.create("garden  tools!")
    with pytest.raises(Conflict):
        store.create("Petfood DE")  # the demo project's reserved ID


def test_api_creates_and_lists_a_real_project(client):
    r = client.post("/api/projects", json={"name": "Garden tools DE"})
    assert r.status_code == 201
    assert r.json()["knowledge_version"] == 0 and r.json()["dag_version"] is None
    assert {p["id"] for p in client.get("/api/projects").json()} == {"petfood-de", "garden-tools-de"}
    assert client.get("/api/projects/garden-tools-de").json()["name"] == "Garden tools DE"
    assert client.get("/api/projects/nope").json()["code"] == "project_not_found"


# --- A3: broken hand edits ------------------------------------------------------------------

BROKEN = [
    ("- [F12] Short ID.\n  status: confirmed · source: data profile\n", 5, "must look like"),
    ("- We discount in winter.\n", 5, "no fact ID"),
    ("- [F020] Winter discounts.\n  status: maybe · source: data profile\n", 6, "Unknown status"),
    ("- [F020] Winter discounts.\n  status: confirmed\n", 5, "no source"),
    ("- [F020] Winter discounts.\n  status: confirmed · source: a friend\n", 6, "Unknown source"),
    ("- [F020] Winter discounts.\n  status: confirmed · source: data profile · owner: me\n", 6, "Expected"),
    (
        "- [F020] Winter discounts.\n  status: confirmed · source: data profile\n  supports: edge(a, b)\n",
        7,
        "supports",
    ),
    ("\n  status: confirmed\n", 6, "does not belong"),
    ("- [F012] Duplicate.\n  status: assumed · source: template default\n", 8, "used twice"),
]


@pytest.mark.parametrize(("insert", "line", "message"), BROKEN)
def test_broken_hand_edit_names_file_and_line_and_drops_no_fact(insert, line, message):
    lines = D4_EXAMPLE.splitlines(keepends=True)
    text = "".join(lines[:4]) + insert + "".join(lines[4:])
    doc = parse(text, "business.md")
    assert doc.issues, "a broken edit must be reported"
    issue = doc.issues[0]
    assert (issue.file, issue.line) == ("business.md", line)
    assert message in issue.message
    # The good facts are all still there, and the text is kept as it was.
    assert {"F012", "F013"} <= {f.id for f in doc.facts}
    assert doc.render() == text
    with pytest.raises(ParseFailed):
        doc.upsert(doc.get("F013"))


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("# No front matter\n", 1),
        ("---\nschema: truelift.knowledge/1\n# never closed\n", 1),
        ("---\nschema: [unclosed\n---\n", 3),  # YAML reports the end of the block
        ("---\nschema: other/1\n---\n", 1),
    ],
)
def test_front_matter_errors(text, line):
    issues = parse(text, "market.md").issues
    assert issues and issues[0].line == line and issues[0].file == "market.md"


def test_ids_shared_across_files_are_an_error():
    business = D4_EXAMPLE
    market = D4_EXAMPLE.replace("# How discounts are decided", "# Calendar")
    knowledge = load_knowledge({"business.md": business, "market.md": market})
    assert {(i.file, i.line) for i in knowledge.issues} == {("market.md", 6), ("market.md", 9)}


def test_store_refuses_to_write_a_broken_file_and_leaves_it_unchanged(store: ProjectStore, project, root):
    store.propose_fact(
        project,
        file="market.md",
        section="Calendar",
        text="Christmas is the peak.",
        source=interview(3, "christmas"),
        summary="Christmas",
    )
    broken = (root / "business.md").read_text() + "- [F07] typo in the ID\n  status: confirmed\n"
    (root / "business.md").write_text(broken)
    before = snapshot(root, skip=())
    with pytest.raises(ParseFailed) as caught:
        store.decide(project, "P001", accept=True, knowledge_version=0)
    issue = caught.value.issues[0]
    assert issue.file == "business.md" and issue.line == broken.count("\n") - 1
    assert snapshot(root, skip=()) == before


def test_api_shows_the_parse_error_with_file_and_line(client, api_store):
    project = client.post("/api/projects", json={"name": "Garden tools"}).json()["id"]
    root = api_store.projects_dir / project
    api_store.propose_fact(
        project,
        file="data.md",
        section="Column meanings",
        text="units means packs sold.",
        source=interview(1, "packs"),
        summary="units",
    )
    (root / "data.md").write_text((root / "data.md").read_text() + "- missing ID\n")
    r = client.post(
        f"/api/projects/{project}/proposals/P001/decision",
        json={"decision": "accept", "knowledge_version": 0},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "parse_error"
    assert body["fields"] == [
        {"loc": ["data.md", 9], "message": "This bullet has no fact ID. Start it like '- [F001] …'."}
    ]
    assert "data.md line 9" in body["message"]


def test_invalid_utf8_is_reported_with_its_line(store: ProjectStore, project, root):
    (root / "market.md").write_bytes((root / "market.md").read_bytes() + b"caf\xe9\n")
    issues = store.knowledge(project).issues
    assert [(i.file, i.line) for i in issues] == [("market.md", 15)]


def test_now_is_used_for_dates(store: ProjectStore, project):
    store.propose_fact(
        project,
        file="business.md",
        section="Margin",
        text="Margin is 40%.",
        source=interview(9, "forty"),
        summary="Margin",
    )
    store.decide(project, "P001", accept=True, knowledge_version=0)
    assert store.knowledge(project).fact("F001").date == NOW.date().isoformat()
