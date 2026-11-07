"""G08 A6 and A7: DAG and mapping versions are written before the pointer moves; changing a fact
that a confirmed DAG cites makes it stale; stale writes and confirmations are refused (C11, C1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.store.conftest import NOW, interview
from truelift.store import Conflict, ProjectStore, SaveFailed, StaleVersion, VersionKind, VersionStatus
from truelift.store import files as files_mod
from truelift.store.folder import ProjectFolder
from truelift.store.versions import Versions

DAG = VersionKind.dag
EDGES = {"edges": [{"source": "holiday", "target": "discount", "fact_ids": ["F001"]}]}


def _fact(store: ProjectStore, project: str, text: str, turn: int) -> str:
    proposal = store.propose_fact(
        project,
        file="business.md",
        section="How discounts are decided",
        text=text,
        source=interview(turn, text),
        summary=text,
    )
    version = store.get(project).knowledge_version
    return store.decide(project, proposal.id, accept=True, knowledge_version=version).fact_id


def _listing(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


# --- A6: version before pointer -------------------------------------------------------------


def test_versions_are_immutable_files_with_a_pointer(store, project, root: Path):
    assert store.write_version(project, DAG, EDGES, expected_current=None, cites=["F001"]) == 1
    v1 = (root / "dag" / "v1.yaml").read_bytes()
    assert store.write_version(project, DAG, {"edges": []}, expected_current=1) == 2
    assert (root / "dag" / "v1.yaml").read_bytes() == v1
    assert (root / "dag" / "current").read_text() == "v2\n"
    record = Versions(ProjectFolder(root), DAG).read(1)
    assert record.content == EDGES and record.cites == ("F001",) and record.created_at == NOW.isoformat()
    assert store.get(project).dag_version == 2


def test_the_version_is_written_before_the_pointer(store, project, monkeypatch):
    order: list[str] = []
    real = files_mod._replace
    monkeypatch.setattr(
        files_mod, "_replace", lambda src, dst: (order.append(Path(dst).name), real(src, dst))
    )
    store.write_version(
        project, VersionKind.mapping, {"roles": {}}, expected_current=None, data_fingerprint="sha256:x"
    )
    assert order == ["v1.yaml", "current"]


def test_failure_writing_the_version_leaves_the_pointer(store, project, root: Path, monkeypatch):
    store.write_version(project, DAG, EDGES, expected_current=None)
    before = _listing(root / "dag")
    monkeypatch.setattr(files_mod, "_replace", lambda *a: (_ for _ in ()).throw(OSError(28, "full")))
    with pytest.raises(SaveFailed):
        store.write_version(project, DAG, {"edges": []}, expected_current=1)
    assert _listing(root / "dag") == before


def test_failure_moving_the_pointer_keeps_the_previous_version_current(
    store, project, root: Path, monkeypatch
):
    store.write_version(project, DAG, EDGES, expected_current=None)
    real = files_mod._replace

    def fail_pointer(src, dst):
        if Path(dst).name == "current":
            raise OSError(28, "No space left on device")
        return real(src, dst)

    monkeypatch.setattr(files_mod, "_replace", fail_pointer)
    with pytest.raises(SaveFailed):
        store.write_version(project, DAG, {"edges": []}, expected_current=1)
    monkeypatch.undo()
    assert store.get(project).dag_version == 1  # v2 exists on disk but never became current
    assert (root / "dag" / "v2.yaml").exists()
    orphan = (root / "dag" / "v2.yaml").read_bytes()
    assert store.write_version(project, DAG, {"edges": ["retry"]}, expected_current=1) == 3
    assert (root / "dag" / "v2.yaml").read_bytes() == orphan  # never overwritten


# --- A6: staleness --------------------------------------------------------------------------


def test_changing_a_cited_fact_marks_the_confirmed_dag_stale(store, project):
    cited = _fact(store, project, "We discount in holiday weeks.", 6)
    other = _fact(store, project, "Ageing stock triggers discounts.", 7)
    version = store.write_version(project, DAG, EDGES, expected_current=None, cites=[cited])
    assert store.version_status(project, DAG, version) is VersionStatus.draft
    store.confirm_version(project, DAG, version)
    assert store.version_status(project, DAG, version) is VersionStatus.confirmed

    # A change to a fact the DAG does not cite leaves it confirmed.
    store.propose_fact(
        project,
        file="business.md",
        text="Stock older than 6 months triggers discounts.",
        source=interview(8, "six months"),
        summary="Stock",
        fact_id=other,
    )
    store.decide(project, "P003", accept=True, knowledge_version=2, resolves_contradiction=True)
    assert store.version_status(project, DAG, version) is VersionStatus.confirmed

    store.propose_fact(
        project,
        file="business.md",
        text="We discount in holiday weeks and at month end.",
        source=interview(15, "month end too"),
        summary="Month end",
        fact_id=cited,
    )
    store.decide(project, "P004", accept=True, knowledge_version=3, resolves_contradiction=True)
    assert store.version_status(project, DAG, version) is VersionStatus.stale
    with store.open(project) as folder:
        assert Versions(folder, DAG).stale_facts(version, folder.knowledge().facts) == [cited]


def test_hand_edits_also_make_it_stale(store, project, root: Path):
    cited = _fact(store, project, "We discount in holiday weeks.", 6)
    version = store.write_version(project, DAG, EDGES, expected_current=None, cites=[cited])
    store.confirm_version(project, DAG, version)
    business = (root / "business.md").read_text()
    (root / "business.md").write_text(business.replace("holiday weeks.", "holiday weeks only."))
    assert store.version_status(project, DAG, version) is VersionStatus.stale
    (root / "business.md").write_text(business)
    assert store.version_status(project, DAG, version) is VersionStatus.confirmed
    dag_file = root / "dag" / f"v{version}.yaml"
    dag_file.write_text(dag_file.read_text().replace("holiday", "weather"))
    assert store.version_status(project, DAG, version) is VersionStatus.stale


def test_mapping_versions_confirm_and_keep_the_fingerprint(store, project):
    version = store.write_version(
        project,
        VersionKind.mapping,
        {"roles": {"week": "date"}},
        expected_current=None,
        data_fingerprint="sha256:ab",
    )
    store.confirm_version(project, VersionKind.mapping, version)
    assert store.version_status(project, VersionKind.mapping, version) is VersionStatus.confirmed
    with store.open(project) as folder:
        assert Versions(folder, VersionKind.mapping).read(version).data_fingerprint == "sha256:ab"
    assert store.get(project).mapping_version == 1


# --- A7: stale writes and confirmations -----------------------------------------------------


def test_a_write_with_a_stale_version_is_refused(store, project, root: Path):
    store.write_version(project, DAG, EDGES, expected_current=None)
    store.write_version(project, DAG, {"edges": []}, expected_current=1)
    before = _listing(root / "dag")
    for expected in (None, 1, 3):
        with pytest.raises(StaleVersion):
            store.write_version(project, DAG, {"edges": ["late"]}, expected_current=expected)
    assert _listing(root / "dag") == before


def test_confirming_a_version_that_is_no_longer_current_is_refused(store, project, root: Path):
    cited = _fact(store, project, "We discount in holiday weeks.", 6)
    store.write_version(project, DAG, EDGES, expected_current=None, cites=[cited])
    store.write_version(project, DAG, EDGES, expected_current=1, cites=[cited])
    before = _listing(root / "dag")
    with pytest.raises(StaleVersion) as caught:
        store.confirm_version(project, DAG, 1)
    assert caught.value.status == 409
    assert _listing(root / "dag") == before
    assert store.version_status(project, DAG, 1) is VersionStatus.draft


def test_confirming_a_dag_that_cites_a_missing_fact_is_refused(store, project):
    version = store.write_version(project, DAG, EDGES, expected_current=None, cites=["F042"])
    with pytest.raises(Conflict) as caught:
        store.confirm_version(project, DAG, version)
    assert caught.value.code == "facts_missing"
