"""G09/A2, A3, A6, A7, A8, A9 through the API: the start-run gate, one run at a time, status,
cancel and results (C1, C10, SB19). The real app, middleware, store and worker processes run;
only the pipeline fit is scripted. Local."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.support import BASE, ORIGIN, TOKEN, make_settings
from tests.worker.support import FAST, fake_command, finished_run, wait_for
from truelift.api.app import create_app
from truelift.api.fakes import results as fake_results
from truelift.store import VersionKind
from truelift.worker.manager import RunManager
from truelift.worker.scripted import create_scripted_project, scripted_dag

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}


def _app(tmp_path: Path, mode: str) -> FastAPI:
    app = create_app(make_settings(tmp_path))
    app.state.runs = RunManager(app.state.store, limits=FAST, command=fake_command(mode))
    return app


@pytest.fixture
def sleepy(tmp_path: Path) -> Iterator[TestClient]:
    app = _app(tmp_path, "sleep")
    create_scripted_project(app.state.store, "demo", 1)
    with TestClient(app, base_url=BASE, headers=HEADERS, raise_server_exceptions=False) as client:
        yield client
    app.state.store.db.dispose()


@pytest.fixture
def quick(tmp_path: Path) -> Iterator[TestClient]:
    app = _app(tmp_path, "ok")
    create_scripted_project(app.state.store, "demo", 1)
    with TestClient(app, base_url=BASE, headers=HEADERS, raise_server_exceptions=False) as client:
        yield client
    app.state.store.db.dispose()


def _start(client: TestClient, version: int = 1) -> dict:
    response = client.post("/api/projects/demo/runs", json={"dag_version": version, "profile": "quick"})
    assert response.status_code == 202, response.text
    return response.json()


def test_start_poll_and_cancel(sleepy: TestClient) -> None:
    run = _start(sleepy)
    assert run["status"] == "running" and run["phases"][0] == "prepare" and run["expected_s"] == 125.0

    def in_phase_1() -> dict | None:
        body = sleepy.get(f"/api/runs/{run['id']}").json()
        return body if body["phase"] == "nuisance models" else None

    body = wait_for(in_phase_1)
    assert any("Phase 1" in line for line in body["log_tail"])
    listed = sleepy.get("/api/projects/demo/runs").json()
    assert [r["id"] for r in listed] == [run["id"]]

    second = sleepy.post("/api/projects/demo/runs", json={"dag_version": 1, "profile": "quick"})
    assert second.status_code == 409 and second.json()["code"] == "run_active"  # A6

    cancelled = sleepy.post(f"/api/runs/{run['id']}/cancel")
    assert cancelled.status_code == 200
    assert (
        cancelled.json()["status"] == "cancelled" and cancelled.json()["reason"] == "You cancelled this run."
    )
    again = sleepy.post(f"/api/runs/{run['id']}/cancel").json()
    assert again["status"] == "cancelled"  # idempotent (A9)
    results = sleepy.get(f"/api/runs/{run['id']}/results")
    assert results.status_code == 409 and results.json()["code"] == "run_not_succeeded"  # A3


def test_gate_refusals_are_409_with_a_plain_reason(quick: TestClient) -> None:
    store = quick.app.state.store
    content = scripted_dag()
    content["edges"][0]["sentence"] = "A reworded arrow."
    record = store.read_version("demo", VersionKind.mapping)
    store.write_version(
        "demo", VersionKind.dag, content, expected_current=1, data_fingerprint=record.data_fingerprint
    )
    stale = quick.post("/api/projects/demo/runs", json={"dag_version": 1, "profile": "quick"})
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    unconfirmed = quick.post("/api/projects/demo/runs", json={"dag_version": 2, "profile": "quick"})
    body = unconfirmed.json()
    assert unconfirmed.status_code == 409 and body["code"] == "dag_unconfirmed"
    assert set(body) <= {"code", "message", "request_id", "fields"} and "Traceback" not in body["message"]
    assert quick.get("/api/projects/demo/runs").json() == []


def test_unknown_project_and_run_are_404(quick: TestClient) -> None:
    response = quick.post("/api/projects/nowhere/runs", json={"dag_version": 1, "profile": "quick"})
    assert response.status_code == 404
    assert quick.get("/api/runs/run-nowhere1").status_code == 404
    assert quick.post("/api/runs/run-nowhere1/cancel").status_code == 404
    assert quick.get("/api/runs/run-nowhere1/results").status_code == 404


def test_a_succeeded_run_without_a_digest_has_no_results_yet(quick: TestClient) -> None:
    run = _start(quick)
    done = wait_for(lambda: (b := quick.get(f"/api/runs/{run['id']}").json())["status"] != "running" and b)
    assert done["status"] == "succeeded" and done["phase"] == "write outputs"
    # G10 adds digest.json to the manifest; until then a succeeded run serves no numbers.
    assert quick.get(f"/api/runs/{run['id']}/results").status_code == 409


def test_results_are_served_only_for_a_succeeded_run_with_its_manifest(quick: TestClient) -> None:
    store = quick.app.state.store
    digest = fake_results("run-demo01").model_copy(update={"run_id": "run-served01"}).model_dump_json()
    finished_run(store, "demo", "run-served01", digest=digest.encode())
    assert quick.get("/api/runs/run-served01/results").status_code == 200
    store.db.update_run("run-served01", status="failed")
    assert quick.get("/api/runs/run-served01/results").status_code == 409


def test_startup_reconciles_runs_left_running(tmp_path: Path) -> None:
    app = _app(tmp_path, "ok")
    create_scripted_project(app.state.store, "demo", 1)
    queued = app.state.runs.prepare("demo", 1, "quick")  # the previous backend died here
    app2 = _app(tmp_path, "ok")
    with TestClient(app2, base_url=BASE, headers=HEADERS) as client:
        body = client.get(f"/api/runs/{queued.id}").json()
    assert body["status"] == "interrupted" and body["reason"].startswith("This run was interrupted.")
    app.state.store.db.dispose()
    app2.state.store.db.dispose()


def test_demo_project_runs_still_come_from_the_fakes(quick: TestClient) -> None:
    response = quick.post("/api/projects/petfood-de/runs", json={"dag_version": 3, "profile": "quick"})
    assert response.status_code in (202, 409)
    assert quick.get("/api/runs/run-demo01").json()["status"] == "succeeded"
