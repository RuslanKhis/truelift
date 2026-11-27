"""G09/A2: the run gate refuses with a plain reason, and the worker re-checks before fitting (C1).

The gate is called in process here (offline); the worker's re-check runs in a real worker process.
"""

from __future__ import annotations

import copy

import pytest

from tests.store.conftest import interview
from tests.worker.support import manager
from truelift.causal.rules import load_rules
from truelift.store import FactStatus, ProjectStore, VersionKind
from truelift.worker.gate import GateRefused, admit
from truelift.worker.layout import RunFolder
from truelift.worker.scripted import scripted_dag

RULES = load_rules()


def _admit(store: ProjectStore, project: str, version: int = 1):
    with store.open(project) as folder:
        return admit(folder, version, "quick", RULES)


def _refusal(store: ProjectStore, project: str, version: int = 1) -> GateRefused:
    with pytest.raises(GateRefused) as info:
        _admit(store, project, version)
    return info.value


def _fingerprint(store: ProjectStore, project: str) -> str:
    record = store.read_version(project, VersionKind.mapping)
    assert record is not None and record.data_fingerprint
    return record.data_fingerprint


def _new_dag(store: ProjectStore, project: str, content: dict, *, cites: tuple[str, ...] = ()) -> int:
    current = store.read_version(project, VersionKind.dag)
    return store.write_version(
        project,
        VersionKind.dag,
        content,
        expected_current=current.version if current else None,
        cites=cites,
        data_fingerprint=_fingerprint(store, project),
    )


def test_confirmed_identified_inputs_are_admitted(store, project) -> None:
    admitted = _admit(store, project)
    assert admitted.inputs.dag_version == 1 and admitted.inputs.data_file == "data/v1.csv"
    assert admitted.inputs.config_sha256 == admitted.config.sha256()
    # The mediator trap stays out of the controls (C3 a).
    assert "store_traffic" not in admitted.config.orchestrator.x_cols_list[0]


def test_unconfirmed_dag_is_refused(store, project) -> None:
    content = scripted_dag()
    content["edges"][0]["sentence"] = "A reworded arrow."
    version = _new_dag(store, project, content)
    refusal = _refusal(store, project, version)
    assert refusal.code == "dag_unconfirmed" and "confirm your DAG" in refusal.message


def test_an_older_dag_version_is_refused(store, project) -> None:
    content = scripted_dag()
    content["edges"][0]["sentence"] = "A reworded arrow."
    _new_dag(store, project, content)
    assert _refusal(store, project, 1).code == "stale_version"


def test_dag_file_changed_after_confirmation_is_refused(store, project) -> None:
    path = store.projects_dir / project / "dag" / "v1.yaml"
    path.write_bytes(path.read_bytes() + b"\n# edited by hand\n")
    refusal = _refusal(store, project)
    assert refusal.code == "dag_stale" and "changed after you confirmed it" in refusal.message


def test_dag_is_stale_when_a_fact_it_depends_on_changes(store, project) -> None:
    def accept(**kwargs) -> str:
        proposal = store.propose_fact(project, file="business.md", source=interview(1, "yes"), **kwargs)
        version = store.get(project).knowledge_version
        return store.decide(
            project, proposal.id, accept=True, knowledge_version=version, resolves_contradiction=True
        ).fact_id

    fact_id = accept(
        text="Holiday weeks drive our discounts.", summary="holiday", supports=["node(holiday_weeks)"]
    )
    version = _new_dag(store, project, scripted_dag(), cites=(fact_id,))
    store.confirm_version(project, VersionKind.dag, version)
    assert _admit(store, project, version).inputs.dag_version == version

    accept(
        text="Holiday weeks do not drive our discounts.",
        summary="changed",
        fact_id=fact_id,
        fact_status=FactStatus.confirmed,
    )
    refusal = _refusal(store, project, version)
    assert refusal.code == "dag_stale" and "1 answer it depends on changed" in refusal.message


def test_unconfirmed_mapping_is_refused(store, project) -> None:
    record = store.read_version(project, VersionKind.mapping)
    content = copy.deepcopy(record.content)
    content["columns"] = [c for c in content["columns"] if c["name"] != "store_traffic"]
    store.write_version(
        project, VersionKind.mapping, content, expected_current=1, data_fingerprint=record.data_fingerprint
    )
    assert _refusal(store, project).code == "mapping_unconfirmed"


def test_data_file_changed_after_confirmation_is_refused(store, project) -> None:
    path = store.projects_dir / project / "data" / "v1.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    refusal = _refusal(store, project)
    assert refusal.code == "data_changed" and "has changed" in refusal.message


def test_unidentified_dag_is_refused_with_business_reasons(store, project) -> None:
    content = scripted_dag()
    for node in content["dag"]["nodes"]:
        if node["id"] == "competitor_promo":
            node.pop("column")  # a confounder with no data, no stand-in and no accepted risk
    version = _new_dag(store, project, content)
    store.confirm_version(project, VersionKind.dag, version)
    refusal = _refusal(store, project, version)
    assert refusal.code == "not_identified"
    assert "Competitors' promotions" in refusal.message and "competitor_promo" not in refusal.message


def test_worker_rechecks_the_hashes_before_fitting(store, project) -> None:
    """The app admitted the run; the data changed before the worker started. The worker
    refuses, fits nothing and writes no manifest."""
    m = manager(store, "ok")
    row = m.prepare(project, 1, "quick")
    data = store.projects_dir / project / "data" / "v1.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    m.launch(row)
    final = m.wait(row.id, timeout=60)
    assert final is not None and final.status == "failed"
    assert "data file you confirmed is missing or has changed" in (final.reason or "")
    folder = RunFolder(store.projects_dir / project / "runs" / row.id)
    assert folder.config.is_file() and folder.env.is_file()
    assert not folder.work.exists() and not folder.manifest.exists()
