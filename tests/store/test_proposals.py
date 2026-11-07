"""G08 A2, A4, A7 and A8: proposals change nothing until accepted, contradictions need their own
choice, stale versions are refused, and a batch is all-or-nothing (C11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.store.conftest import interview, snapshot
from truelift.store import (
    Conflict,
    FactStatus,
    ProjectStore,
    ProposalStatus,
    SaveFailed,
    Source,
    SourceKind,
    StaleVersion,
)
from truelift.store import files as files_mod
from truelift.store.files import JOURNAL_DIR
from truelift.store.knowledge import Document


def _propose(store: ProjectStore, project: str, text: str, turn: int = 1, **kw):
    kw.setdefault("file", "business.md")
    kw.setdefault("section", "How discounts are decided")
    return store.propose_fact(project, text=text, source=interview(turn, text.lower()), summary=text, **kw)


def _confirmed_fact(store: ProjectStore, project: str) -> str:
    """Confirm one fact through an accepted proposal; return its ID."""
    proposal = _propose(
        store, project, "We discount in holiday weeks.", turn=6, supports=["edge(holiday -> discount)"]
    )
    version = store.get(project).knowledge_version
    return store.decide(project, proposal.id, accept=True, knowledge_version=version).fact_id


# --- A2: nothing changes until accepted; rejecting changes no file ---------------------------


def test_a_proposal_changes_no_project_file(store, project, root: Path):
    before = snapshot(root)
    proposal = _propose(store, project, "We discount in holiday weeks.")
    assert proposal.id == "P001" and proposal.status is ProposalStatus.pending
    assert (root / "proposals" / "P001.yaml").is_file()
    assert snapshot(root) == before
    store.proposals(project)  # reading proposals does not apply them either
    assert snapshot(root) == before


def test_accept_applies_the_fact_and_bumps_the_version(store, project, root: Path):
    _propose(store, project, "We discount in holiday weeks.", turn=6, supports=["edge(holiday -> discount)"])
    decided = store.decide(project, "P001", accept=True, knowledge_version=0)
    fact = store.knowledge(project).fact(decided.fact_id)
    assert decided.status is ProposalStatus.accepted and fact.id == "F001"
    assert fact.status is FactStatus.confirmed and fact.section == "How discounts are decided"
    assert fact.source == Source(SourceKind.interview, 6, "we discount in holiday weeks.")
    assert store.get(project).knowledge_version == 1
    assert "- [F001] We discount in holiday weeks." in (root / "business.md").read_text()


def test_reject_leaves_every_project_file_byte_identical(store, project, root: Path):
    fact_id = _confirmed_fact(store, project)
    _propose(store, project, "We never discount.", fact_id=fact_id)
    _propose(store, project, "Black Friday is our biggest week.", file="market.md", section="Calendar")
    before = snapshot(root)
    for proposal_id in ("P002", "P003"):
        rejected = store.decide(project, proposal_id, accept=False, knowledge_version=1)
        assert rejected.status is ProposalStatus.rejected
    assert snapshot(root) == before


def test_api_accept_and_reject(client, api_store):
    project = client.post("/api/projects", json={"name": "Garden tools"}).json()["id"]
    root = api_store.projects_dir / project
    api_store.propose_fact(
        project,
        file="market.md",
        section="Calendar",
        text="Spring is the peak.",
        source=interview(3, "spring, by far"),
        summary="Spring peak",
    )
    api_store.propose_fact(
        project,
        file="market.md",
        section="Seasons",
        text="Winter is quiet.",
        source=Source(SourceKind.agent_suggestion),
        summary="Winter",
    )
    base = f"/api/projects/{project}/proposals"
    listed = client.get(base, params={"status": "pending"}).json()
    assert [p["id"] for p in listed] == ["P001", "P002"]
    assert listed[0]["source"] == {"turn": 3, "text": "spring, by far"} and listed[1]["source"] is None

    before = snapshot(root)
    r = client.post(f"{base}/P002/decision", json={"decision": "reject", "knowledge_version": 0})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert snapshot(root) == before

    r = client.post(f"{base}/P001/decision", json={"decision": "accept", "knowledge_version": 0})
    assert r.status_code == 200
    assert r.json()["status"] == "accepted" and r.json()["fact_id"] == "F001"
    assert client.get(f"/api/projects/{project}").json()["knowledge_version"] == 1
    assert "- [F001] Spring is the peak." in (root / "market.md").read_text()


# --- A4: contradictions ---------------------------------------------------------------------


def test_changing_a_confirmed_fact_is_a_contradiction(store, project):
    fact_id = _confirmed_fact(store, project)
    _propose(store, project, "We react to competitor promotions.", turn=15, fact_id=fact_id)
    view = store.proposal(project, "P002")
    assert view.contradiction is True
    assert view.contradicts == Source(SourceKind.interview, 6, "we discount in holiday weeks.")


def test_changing_an_assumed_fact_is_not_a_contradiction(store, project):
    proposal = store.propose_fact(
        project,
        file="business.md",
        section="Margin",
        text="Margin is 40%.",
        source=Source(SourceKind.template_default),
        summary="Margin",
        fact_status=FactStatus.assumed,
    )
    store.decide(project, proposal.id, accept=True, knowledge_version=0)
    _propose(store, project, "Margin is 35%.", fact_id="F001", section="Margin")
    assert store.proposal(project, "P002").contradiction is False
    store.decide(project, "P002", accept=True, knowledge_version=1)
    assert store.knowledge(project).fact("F001").text == "Margin is 35%."


def test_a_contradiction_needs_an_explicit_choice(store, project, root: Path):
    fact_id = _confirmed_fact(store, project)
    _propose(store, project, "We react to competitor promotions.", turn=15, fact_id=fact_id)
    before = snapshot(root, skip=())
    with pytest.raises(Conflict) as caught:
        store.decide(project, "P002", accept=True, knowledge_version=1)
    assert caught.value.code == "contradiction_choice_needed"
    assert snapshot(root, skip=()) == before

    decided = store.decide(project, "P002", accept=True, knowledge_version=1, resolves_contradiction=True)
    assert decided.contradiction is True
    assert decided.replaced.text == "We discount in holiday weeks."  # the audit trail keeps the old answer
    fact = store.knowledge(project).fact(fact_id)
    assert fact.text == "We react to competitor promotions." and fact.source.turn == 15
    view = store.proposal(project, "P002")
    assert view.contradiction and view.contradicts.turn == 6


def test_rejecting_a_contradiction_keeps_the_confirmed_fact(store, project, root: Path):
    fact_id = _confirmed_fact(store, project)
    _propose(store, project, "We never discount.", fact_id=fact_id)
    before = snapshot(root)
    store.decide(project, "P002", accept=False, knowledge_version=1)
    assert snapshot(root) == before
    assert store.proposal(project, "P002").contradiction is True


def test_a_batch_cannot_apply_a_contradiction(store, project, root: Path):
    fact_id = _confirmed_fact(store, project)
    _propose(store, project, "Black Friday is our biggest week.", file="market.md", section="Calendar")
    _propose(store, project, "We never discount.", fact_id=fact_id)
    before = snapshot(root, skip=())
    with pytest.raises(Conflict) as caught:
        store.accept_batch(project, ["P002", "P003"], knowledge_version=1)
    assert caught.value.code == "contradiction_in_batch" and "P003" in caught.value.message
    assert snapshot(root, skip=()) == before
    assert {v.proposal.status for v in store.proposals(project) if v.proposal.id != "P001"} == {
        ProposalStatus.pending
    }


def test_a_batch_that_conflicts_with_itself_is_refused(store, project, root: Path):
    _propose(store, project, "We discount in holiday weeks.")
    store.decide(project, "P001", accept=True, knowledge_version=0)
    # P002 confirms an edit; P003 edits the same fact again, so it would overwrite P002 silently.
    _propose(store, project, "We discount in holiday weeks and at month end.", fact_id="F001")
    store.decide(project, "P002", accept=True, knowledge_version=1, resolves_contradiction=True)
    _propose(store, project, "New fact.", file="data.md", section="Column meanings")
    _propose(store, project, "We discount only at month end.", fact_id="F001")
    before = snapshot(root, skip=())
    with pytest.raises(Conflict):
        store.accept_batch(project, ["P003", "P004"], knowledge_version=2)
    assert snapshot(root, skip=()) == before


def test_api_contradiction_flow(client, api_store):
    project = client.post("/api/projects", json={"name": "Garden tools"}).json()["id"]
    base = f"/api/projects/{project}/proposals"
    _confirmed_fact(api_store, project)
    _propose(api_store, project, "We never discount.", turn=15, fact_id="F001")
    listed = client.get(base, params={"status": "pending"}).json()
    assert listed[0]["contradiction"] is True
    assert listed[0]["contradicts"] == {"turn": 6, "text": "we discount in holiday weeks."}

    r = client.post(f"{base}/accept", json={"proposal_ids": ["P002"], "knowledge_version": 1})
    assert (r.status_code, r.json()["code"]) == (409, "contradiction_in_batch")
    r = client.post(f"{base}/P002/decision", json={"decision": "accept", "knowledge_version": 1})
    assert (r.status_code, r.json()["code"]) == (409, "contradiction_choice_needed")
    r = client.post(
        f"{base}/P002/decision",
        json={"decision": "accept", "knowledge_version": 1, "resolves_contradiction": True},
    )
    assert r.status_code == 200 and r.json()["contradiction"] is True


# --- A7 (knowledge): stale versions and repeated decisions -----------------------------------


def test_stale_knowledge_version_is_refused_and_writes_nothing(store, project, root: Path):
    _propose(store, project, "We discount in holiday weeks.")
    before = snapshot(root, skip=())
    for call in (
        lambda: store.decide(project, "P001", accept=True, knowledge_version=5),
        lambda: store.decide(project, "P001", accept=False, knowledge_version=5),
        lambda: store.accept_batch(project, ["P001"], knowledge_version=5),
    ):
        with pytest.raises(StaleVersion):
            call()
    assert snapshot(root, skip=()) == before


def test_a_decided_proposal_cannot_be_decided_again(store, project):
    _propose(store, project, "We discount in holiday weeks.")
    store.decide(project, "P001", accept=True, knowledge_version=0)
    with pytest.raises(Conflict) as caught:
        store.decide(project, "P001", accept=False, knowledge_version=1)
    assert caught.value.code == "already_decided"


def test_api_stale_version_is_409_and_unknown_ids_404(client, api_store):
    project = client.post("/api/projects", json={"name": "Garden tools"}).json()["id"]
    _propose(api_store, project, "We discount in holiday weeks.")
    base = f"/api/projects/{project}/proposals"
    r = client.post(f"{base}/P001/decision", json={"decision": "accept", "knowledge_version": 3})
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    r = client.post(f"{base}/P009/decision", json={"decision": "accept", "knowledge_version": 0})
    assert (r.status_code, r.json()["code"]) == (404, "proposal_not_found")
    r = client.get("/api/projects/no-such-project/proposals")
    assert (r.status_code, r.json()["code"]) == (404, "project_not_found")


# --- A8: a batch is all-or-nothing ----------------------------------------------------------


def _three(store, project):
    _propose(store, project, "We discount in holiday weeks.")
    _propose(store, project, "Christmas is the peak.", file="market.md", section="Calendar")
    _propose(store, project, "units means packs sold.", file="data.md", section="Column meanings")


def test_batch_applies_all(store, project):
    _three(store, project)
    decided = store.accept_batch(project, ["P001", "P002", "P003"], knowledge_version=0)
    assert [p.fact_id for p in decided] == ["F001", "F002", "F003"]
    assert set(store.knowledge(project).facts) == {"F001", "F002", "F003"}
    assert store.get(project).knowledge_version == 1


def test_failure_on_the_third_fact_applies_none(store, project, root: Path, monkeypatch):
    _three(store, project)
    before = snapshot(root, skip=())
    real = Document.upsert
    calls = []

    def failing(self, fact):
        calls.append(fact.id)
        if len(calls) == 3:
            raise RuntimeError("injected failure on the third fact")
        return real(self, fact)

    monkeypatch.setattr(Document, "upsert", failing)
    with pytest.raises(RuntimeError):
        store.accept_batch(project, ["P001", "P002", "P003"], knowledge_version=0)
    assert len(calls) == 3
    assert snapshot(root, skip=()) == before  # the first two are not applied, proposals still pending


def test_failure_while_writing_the_third_file_rolls_back(store, project, root: Path, monkeypatch):
    _three(store, project)
    before = snapshot(root, skip=())
    real = files_mod._replace
    targets: list[str] = []

    def failing(src, dst):
        if JOURNAL_DIR not in str(dst):
            targets.append(Path(dst).name)
            if len(targets) == 3:
                raise OSError(28, "No space left on device")
        return real(src, dst)

    monkeypatch.setattr(files_mod, "_replace", failing)
    with pytest.raises(SaveFailed):
        store.accept_batch(project, ["P001", "P002", "P003"], knowledge_version=0)
    assert targets[:2] == ["business.md", "market.md"]  # two files had been replaced before the failure
    assert snapshot(root, skip=()) == before
    assert not (root / JOURNAL_DIR).exists()


def test_a_crash_mid_batch_is_rolled_back_at_the_next_open(store, project, root: Path, monkeypatch):
    _three(store, project)
    before = snapshot(root, skip=())
    real = files_mod._replace
    targets: list[str] = []

    def crash(src, dst):
        if JOURNAL_DIR not in str(dst):
            targets.append(Path(dst).name)
            if len(targets) == 3:
                raise KeyboardInterrupt  # the process stops here
        return real(src, dst)

    monkeypatch.setattr(files_mod, "_replace", crash)
    monkeypatch.setattr(files_mod, "_rollback", lambda root: None)  # a crash runs no cleanup
    with pytest.raises(KeyboardInterrupt):
        store.accept_batch(project, ["P001", "P002", "P003"], knowledge_version=0)
    monkeypatch.undo()
    assert snapshot(root, skip=()) != before  # half-applied on disk, journal present
    assert (root / JOURNAL_DIR / "manifest.yaml").exists()

    assert store.knowledge(project).facts == {}  # the next open rolls back first
    assert snapshot(root, skip=()) == before
    assert not (root / JOURNAL_DIR).exists()


def test_api_batch(client, api_store):
    project = client.post("/api/projects", json={"name": "Garden tools"}).json()["id"]
    _three(api_store, project)
    base = f"/api/projects/{project}/proposals"
    r = client.post(f"{base}/accept", json={"proposal_ids": ["P001", "P003"], "knowledge_version": 0})
    assert r.status_code == 200
    assert [(p["id"], p["fact_id"], p["status"]) for p in r.json()] == [
        ("P001", "F001", "accepted"),
        ("P003", "F002", "accepted"),
    ]
    r = client.post(f"{base}/accept", json={"proposal_ids": ["P002", "P002"], "knowledge_version": 1})
    assert (r.status_code, r.json()["code"]) == (422, "invalid_proposal")


def test_proposal_text_cannot_inject_lines(store, project, root: Path):
    _propose(store, project, 'Holidays.\n- [F999] injected\n  status: confirmed · source: "x"')
    store.decide(project, "P001", accept=True, knowledge_version=0)
    knowledge = store.knowledge(project)
    assert knowledge.issues == () and set(knowledge.facts) == {"F001"}
