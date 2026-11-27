"""G31/A2 and A3: the real DAG, identification and results routes (C1, C3, C10).

A real project is made through the API; facts arrive the way the interviewer will send them
(a proposal the user accepts or rejects); the confirmed column mapping, which G07 will write, is
put in place through the store, and the run folder a G09 worker will write is simulated in the
results tests (labelled there). The real app, middleware, store and causal core run. Offline.
"""

from __future__ import annotations

import json

import pytest

from truelift.api.fakes import results as fake_results
from truelift.api.routes.dag import edge_id
from truelift.store import ProjectStore, Source, SourceKind, VersionKind

COLUMNS = [
    {"name": "week", "role": "date", "type": "date"},
    {"name": "region", "role": "region", "type": "key"},
    {"name": "revenue", "role": "outcome", "type": "money"},
    {"name": "discount_rate", "role": "treatment_rate", "type": "rate", "bounded_0_1": True},
    {"name": "discount_spend", "role": "treatment_spend", "type": "money"},
    {"name": "population", "role": "population", "type": "count"},
    {"name": "holiday", "role": "control", "type": "flag"},
    {"name": "media_grps", "role": "control", "type": "index"},
]
PANEL = {
    "weeks": 156,
    "regions": 8,
    "rows": 1248,
    "treated_share": 0.35,
    "untreated_share": 0.4,
    "treatment_levels": 6,
    "gap_share": 0.0,
    "levels": {"region": [f"R{i}" for i in range(1, 9)]},
}
FINGERPRINT = "sha256:" + "a" * 64
# Facts that leave holiday weeks and advertising as the only causes of the discount, both measured.
IDENTIFIABLE = [
    *(
        f"no-edge({n} -> discount)"
        for n in (
            "season",
            "market_demand",
            "inventory_age",
            "recent_sales_trend",
            "store_count",
            "local_events",
        )
    ),
]


@pytest.fixture
def store(app) -> ProjectStore:
    return app.state.store


@pytest.fixture
def project(client, store) -> str:
    response = client.post("/api/projects", json={"name": "Pet food chain"})
    assert response.status_code == 201
    return response.json()["id"]


def map_columns(store: ProjectStore, pid: str, *, panel: bool = True) -> None:
    current = store.read_version(pid, VersionKind.mapping)
    content = {"columns": COLUMNS, **({"panel": PANEL} if panel else {})}
    store.write_version(
        pid,
        VersionKind.mapping,
        content,
        expected_current=current.version if current else None,
        data_fingerprint=FINGERPRINT,
    )


def add_fact(store: ProjectStore, pid: str, text: str, *supports: str, accept: bool = True) -> str:
    proposal = store.propose_fact(
        pid,
        file="business.md",
        text=text,
        source=Source(SourceKind.interview, 4, "what the user said"),
        summary=text,
        supports=list(supports),
    )
    decided = store.decide(
        pid, proposal.id, accept=accept, knowledge_version=store.get(pid).knowledge_version
    )
    return decided.fact_id  # assigned when the proposal is accepted


def build(client, pid: str, version: int | None = None, template: str | None = "store_chain"):
    body = {"dag_version": version} | ({"template": template} if template else {})
    return client.post(f"/api/projects/{pid}/dag/build", json=body)


def edge_map(dag: dict) -> dict[tuple[str, str], dict]:
    return {(e["source"], e["target"]): e for e in dag["edges"]}


# --- build and read ------------------------------------------------------------------------


def test_no_diagram_before_the_first_build(client, project) -> None:
    response = client.get(f"/api/projects/{project}/dag")
    assert response.status_code == 404
    assert response.json()["code"] == "dag_not_found"


def test_build_needs_confirmed_columns_and_a_template(client, store, project) -> None:
    assert build(client, project).json()["code"] == "mapping_needed"
    map_columns(store, project)
    response = build(client, project, template=None)
    assert response.status_code == 422 and response.json()["code"] == "template_needed"
    assert build(client, project, template="no_such_business").json()["code"] == "unknown_template"


def test_build_returns_the_version_with_fact_or_assumed_edges(client, store, project) -> None:
    map_columns(store, project)
    fid = add_fact(store, project, "We match competitor promotions.", "edge(competitor_promo -> discount)")
    response = build(client, project)
    assert response.status_code == 200, response.text
    dag = response.json()
    assert (dag["version"], dag["status"], dag["template"]) == (1, "draft", "store_chain")
    edges = edge_map(dag)
    promo = edges[("competitor_promo", "discount")]
    assert (promo["basis"], promo["fact_ids"]) == ("fact", [fid])
    assert promo["id"] == edge_id("competitor_promo", "discount")
    holiday = edges[("holiday_weeks", "discount")]
    assert (holiday["basis"], holiday["fact_ids"]) == ("assumed", [])
    assert all(e["opinion"] is None for e in dag["edges"])
    assert client.get(f"/api/projects/{project}/dag").json() == dag
    # The version cites the fact and records the mapping's data fingerprint (C1).
    record = store.read_version(project, VersionKind.dag)
    assert record.cites == (fid,) and record.data_fingerprint == FINGERPRINT


def test_rebuilding_from_unchanged_facts_writes_no_new_version(client, store, project) -> None:
    map_columns(store, project)
    first = build(client, project).json()
    again = build(client, project, version=1)
    assert again.status_code == 200 and again.json() == first
    assert store.read_version(project, VersionKind.dag).version == 1
    assert build(client, project, version=None).json()["code"] == "stale_version"


def test_a_rejected_proposal_changes_nothing_and_an_accepted_one_makes_a_new_version(
    client, store, project
) -> None:
    map_columns(store, project)
    first = build(client, project).json()
    add_fact(
        store,
        project,
        "Competitor promotions drive our discounts.",
        "edge(competitor_promo -> discount)",
        accept=False,
    )
    assert build(client, project, version=1).json() == first  # A2
    fid = add_fact(
        store, project, "Ageing stock does not change when we discount.", "no-edge(inventory_age -> discount)"
    )
    second = build(client, project, version=1).json()
    assert second["version"] == 2
    assert ("inventory_age", "discount") in edge_map(first)
    assert ("inventory_age", "discount") not in edge_map(second)
    assert store.read_version(project, VersionKind.dag).cites == (fid,)


def test_conflicting_facts_stop_the_build_in_business_words(client, store, project) -> None:
    map_columns(store, project)
    add_fact(store, project, "Advertising drives our discounts.", "edge(media -> discount)")
    add_fact(store, project, "Advertising has nothing to do with discounts.", "no-edge(media -> discount)")
    response = build(client, project)
    assert response.status_code == 409
    body = response.json()
    assert (
        body["code"] == "dag_build_failed"
        and "disagree" in body["message"]
        and "your advertising" in body["message"]
    )


# --- opinions and confirmation -------------------------------------------------------------


def _answer_all(client, pid: str, dag: dict, opinion: str = "agree") -> None:
    for e in dag["edges"]:
        r = client.put(
            f"/api/projects/{pid}/dag/edges/{e['id']}/opinion",
            json={"opinion": opinion, "dag_version": dag["version"]},
        )
        assert r.status_code == 200 and r.json()["opinion"] == opinion


def test_confirm_needs_every_edge_answered_and_none_disputed(client, store, project) -> None:
    map_columns(store, project)
    fid = add_fact(
        store, project, "Holiday weeks are marked in our file.", "node(holiday_weeks)", "column(holiday)"
    )
    dag = build(client, project).json()
    confirm = lambda: client.post(f"/api/projects/{project}/dag/confirm", json={"version": dag["version"]})  # noqa: E731
    assert confirm().json()["code"] == "edges_unreviewed"
    _answer_all(client, project, dag)
    first = dag["edges"][0]["id"]
    client.put(
        f"/api/projects/{project}/dag/edges/{first}/opinion", json={"opinion": "disagree", "dag_version": 1}
    )
    disputed = confirm()
    assert disputed.status_code == 409 and disputed.json()["code"] == "edges_disputed"
    client.put(
        f"/api/projects/{project}/dag/edges/{first}/opinion", json={"opinion": "agree", "dag_version": 1}
    )
    confirmed = confirm()
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    # Opinions sit beside the version: its content hash did not change, so it stays confirmed.
    assert client.get(f"/api/projects/{project}/dag").json()["status"] == "confirmed"
    # A change to a cited fact makes the confirmed version stale (C1).
    proposal = store.propose_fact(
        project,
        file="business.md",
        text="Holiday weeks are in the column holiday_flag.",
        source=Source(SourceKind.interview, 9, "it's the flag column"),
        summary="Changed column",
        fact_id=fid,
        supports=["node(holiday_weeks)", "column(holiday)"],
    )
    store.decide(
        project,
        proposal.id,
        accept=True,
        knowledge_version=store.get(project).knowledge_version,
        resolves_contradiction=True,
    )
    assert client.get(f"/api/projects/{project}/dag").json()["status"] == "stale"


def test_opinions_refuse_a_stale_version_and_an_unknown_edge(client, store, project) -> None:
    map_columns(store, project)
    dag = build(client, project).json()
    eid = dag["edges"][0]["id"]
    stale = client.put(
        f"/api/projects/{project}/dag/edges/{eid}/opinion", json={"opinion": "agree", "dag_version": 2}
    )
    assert stale.status_code == 409
    missing = client.put(
        f"/api/projects/{project}/dag/edges/e-unknown/opinion", json={"opinion": "agree", "dag_version": 1}
    )
    assert missing.status_code == 404 and missing.json()["code"] == "edge_not_found"


# --- identification ------------------------------------------------------------------------


def test_identification_blocks_with_business_reasons(client, store, project) -> None:
    map_columns(store, project)
    build(client, project)
    response = client.get(f"/api/projects/{project}/dag/identification")
    assert response.status_code == 200
    ident = response.json()
    assert ident["dag_version"] == 1 and ident["identified"] is False
    by_node = {b["node_ids"][0]: b for b in ident["blocks"] if b["code"] == "unobserved_confounder"}
    assert "inventory_age" in by_node
    message = by_node["inventory_age"]["message"]
    assert message.startswith("Ageing stock affects both when you discount and how much you sell")
    assert "inventory_age" not in message
    assert by_node["inventory_age"]["remedies"][0] == "add_data"


def test_identification_passes_once_the_facts_close_every_back_door(client, store, project) -> None:
    map_columns(store, project)
    add_fact(store, project, "Only holidays and advertising decide our discount weeks.", *IDENTIFIABLE)
    add_fact(store, project, "Holiday weeks are flagged.", "node(holiday_weeks)", "column(holiday)")
    add_fact(store, project, "Advertising is in GRPs.", "node(media)", "column(media_grps)")
    build(client, project)
    ident = client.get(f"/api/projects/{project}/dag/identification").json()
    assert ident["identified"] is True, ident["blocks"]
    assert ident["adjustment_set"] == ["holiday_weeks", "media"]
    assert ident["blocks"] == []


def test_identification_needs_the_panel_profile(client, store, project) -> None:
    map_columns(store, project, panel=False)
    build(client, project)
    response = client.get(f"/api/projects/{project}/dag/identification")
    assert response.status_code == 409 and response.json()["code"] == "profile_needed"


def test_demo_project_still_answers_from_the_fakes(client) -> None:
    dag = client.get("/api/projects/petfood-de/dag").json()
    assert dag["version"] >= 1 and dag["edges"]
    assert client.post("/api/projects/petfood-de/dag/build", json={}).json() == dag


# --- results (C10) -------------------------------------------------------------------------


def _write_run(client, pid: str, run_id: str, *, manifest: bool = True, tamper: bool = False) -> None:
    """A run folder as a succeeded G09 run leaves it, with digest.json listed in its manifest."""
    from tests.worker.support import finished_run

    store = client.app.state.store
    digest = fake_results("run-demo01").model_copy(update={"run_id": run_id})
    folder = finished_run(store, pid, run_id, digest=digest.model_dump_json().encode())
    if tamper:
        (folder.root / "digest.json").write_bytes(digest.model_dump_json().encode() + b" ")
    if not manifest:
        folder.manifest.unlink()


def test_results_serve_the_digest_of_a_finished_run(client, project) -> None:
    _write_run(client, project, "run-real0001")
    response = client.get("/api/runs/run-real0001/results")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-real0001" and body["headline"]["verdict"]


@pytest.mark.parametrize(("manifest", "tamper"), [(False, False), (True, True)])
def test_no_results_without_a_matching_manifest(client, project, manifest, tamper) -> None:
    _write_run(client, project, "run-real0002", manifest=manifest, tamper=tamper)
    response = client.get("/api/runs/run-real0002/results")
    assert response.status_code == 409 and response.json()["code"] == "run_not_succeeded"


def test_unknown_run_is_404(client, project) -> None:
    assert client.get("/api/runs/run-nowhere1/results").status_code == 404


# --- A3: the routes are in the generated client --------------------------------------------


def test_routes_are_in_the_committed_openapi_and_client() -> None:
    from tests.conftest import REPO_ROOT

    spec = json.loads((REPO_ROOT / "openapi.json").read_text())
    for path in (
        "/api/projects/{project_id}/dag",
        "/api/projects/{project_id}/dag/build",
        "/api/projects/{project_id}/dag/identification",
        "/api/runs/{run_id}/results",
    ):
        assert path in spec["paths"], path
    sdk = (REPO_ROOT / "frontend" / "src" / "client" / "sdk.gen.ts").read_text()
    assert "dagBuild" in sdk
