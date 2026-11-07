"""The G02 stub routes answer with contract-valid fake data and the documented error codes."""

from __future__ import annotations

import pytest

from tests.api.support import api_calls

P = "/api/projects/petfood-de"


def test_every_get_route_answers(app, client):
    for method, path in api_calls(app):
        if method != "GET" or path.endswith("/x"):
            continue
        params = {"provider": "gemini"} if path.endswith("/disclosure") else None
        r = client.get(path, params=params)
        assert r.status_code == 200, (path, r.status_code, r.text)


def test_create_project_and_conflict(client):
    r = client.post("/api/projects", json={"name": "Garden tools DE"})
    assert r.status_code == 201 and r.json()["id"] == "garden-tools-de" and r.json()["stage"] == "setup"
    assert client.post("/api/projects", json={"name": "Garden tools DE"}).status_code == 409
    assert {p["id"] for p in client.get("/api/projects").json()} == {"petfood-de", "garden-tools-de"}
    assert client.get("/api/projects/nope").status_code == 404


def test_proposal_decision_and_stale_version(client):
    version = client.get(P).json()["knowledge_version"]
    assert (
        client.post(
            f"{P}/proposals/P005/decision", json={"decision": "accept", "knowledge_version": 0}
        ).status_code
        == 409
    )
    r = client.post(f"{P}/proposals/P005/decision", json={"decision": "accept", "knowledge_version": version})
    assert r.json()["status"] == "accepted"
    assert client.get(P).json()["knowledge_version"] == version + 1
    again = client.post(
        f"{P}/proposals/P005/decision", json={"decision": "reject", "knowledge_version": version + 1}
    )
    assert again.json()["code"] == "already_decided"
    pending = client.get(f"{P}/proposals", params={"status": "pending"}).json()
    assert [p["id"] for p in pending] == ["P006"] and pending[0]["contradiction"] is True


@pytest.mark.parametrize(
    ("filename", "status", "code"),
    [
        ("sales_panel.csv", 201, None),
        ("sales_panel.xlsx", 422, "not_csv"),
        ("duplicate_keys.csv", 422, "duplicate_keys"),
        ("not_weekly.csv", 422, "not_weekly"),
    ],
)
def test_upload_outcomes(client, filename, status, code):
    r = client.post(f"{P}/data", files={"file": (filename, b"week,region\n2025-01-06,Bayern\n", "text/csv")})
    assert r.status_code == status
    if code:
        assert r.json()["code"] == code and r.json()["message"]


def test_empty_upload_rejected(client):
    r = client.post(f"{P}/data", files={"file": ("panel.csv", b"", "text/csv")})
    assert r.json()["code"] == "empty_file"


def test_mapping_validation_blocks_confirm(client):
    mapping = client.get(f"{P}/mapping").json()
    r = client.put(
        f"{P}/mapping",
        json={
            "expected_version": mapping["version"],
            "roles": [
                {"column": "week", "role": "date"},
                {"column": "discount_spend", "role": "treatment_rate"},
                {"column": "truth_roi", "role": "control"},
            ],
        },
    )
    checks = {c["column"]: c for c in r.json()["roles"]}
    assert checks["week"]["ok"] is True
    assert checks["discount_spend"]["ok"] is False and "between 0 and 1" in checks["discount_spend"]["reason"]
    assert checks["truth_roi"]["ok"] is False
    v = r.json()["version"]
    assert client.post(f"{P}/mapping/confirm", json={"version": v}).json()["code"] == "mapping_invalid"
    assert client.post(f"{P}/mapping/confirm", json={"version": v - 1}).status_code == 409


def test_dag_opinions_and_confirm(client):
    dag = client.get(f"{P}/dag").json()
    v = dag["version"]
    assert client.post(f"{P}/dag/confirm", json={"version": v}).json()["code"] == "edges_unreviewed"
    for edge in dag["edges"]:
        r = client.put(f"{P}/dag/edges/{edge['id']}/opinion", json={"opinion": "agree", "dag_version": v})
        assert r.json()["opinion"] == "agree"
    assert client.post(f"{P}/dag/confirm", json={"version": v}).json()["status"] == "confirmed"
    ident = client.get(f"{P}/dag/identification").json()
    assert ident["identified"] is False and ident["blocks"][0]["remedies"]


def test_run_lifecycle(client):
    v = client.get(f"{P}/dag").json()["version"]
    run = client.post(f"{P}/runs", json={"dag_version": v, "profile": "quick"})
    assert run.status_code == 202
    run_id = run.json()["id"]
    second = client.post(f"{P}/runs", json={"dag_version": v, "profile": "quick"})
    assert second.status_code == 409 and second.json()["code"] == "run_active"
    assert client.get(f"/api/runs/{run_id}/results").json()["code"] == "run_not_succeeded"
    cancelled = client.post(f"/api/runs/{run_id}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert client.post(f"/api/runs/{run_id}/cancel").json()["status"] == "cancelled"  # idempotent
    assert client.post(f"{P}/runs", json={"dag_version": v, "profile": "quick"}).status_code == 202


def test_results_only_for_succeeded_runs(client):
    ok = client.get("/api/runs/run-demo01/results").json()
    assert ok["headline"]["verdict"] == "undetermined"
    assert {s["label"] for s in ok["narrative"]["statements"]} == {"inference", "hypothesis"}
    interrupted = client.get("/api/runs/run-demo02/results")
    assert interrupted.status_code == 409
    assert client.get("/api/runs/run-demo02").json()["reason"].startswith("This run was interrupted")


def test_consent_and_budget(client):
    d = client.get(f"{P}/disclosure", params={"provider": "gemini"}).json()
    assert (
        client.post(f"{P}/consent", json={"provider": "gemini", "disclosure_version": "old"}).status_code
        == 409
    )
    r = client.post(f"{P}/consent", json={"provider": "gemini", "disclosure_version": d["version"]})
    assert r.status_code == 200
    assert client.put(f"{P}/budget", json={"token_budget": 100_000}).json()["ai_state"] == "budget_paused"
    assert client.put("/api/setup/key", json={"provider": "claude", "api_key": "x" * 20}).status_code == 204
