"""G02 A4–A6: ADK paths unreachable, security headers, docs only in dev, limits and generic errors
(SB05, SB07, SB09, SB13)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.api.support import BASE, ORIGIN, TOKEN, make_settings
from truelift.api.app import create_app
from truelift.api.settings import Settings
from truelift.api.spa import PLACEHOLDER_SHELL

ADK_PATHS = [
    "/run",
    "/run_sse",
    "/run_live",
    "/list-apps",
    "/apps/truelift/users/u1/sessions",
    "/apps/truelift/users/u1/sessions/s1",
    "/dev-ui/",
    "/builder/save",
]

# --- A4: ADK's own routes are not there and cause no model call --------------------------------


def test_adk_server_never_mounted(app):
    assert "google.adk.cli.fast_api" not in sys.modules
    paths = set(app.openapi()["paths"])
    for adk_path in (
        "/run",
        "/run_sse",
        "/run_live",
        "/list-apps",
        "/apps/{app_name}/users/{user_id}/sessions",
    ):
        assert adk_path not in paths


def test_adk_paths_return_shell_or_404_and_no_model_call(client, monkeypatch):
    from google.adk.runners import Runner

    calls: list[str] = []

    async def _count(*args, **kwargs):  # pragma: no cover - must never run
        calls.append("run_async")
        if False:
            yield None

    monkeypatch.setattr(Runner, "run_async", _count)
    monkeypatch.setattr(Runner, "run", lambda *a, **k: calls.append("run"))

    body = {
        "appName": "truelift",
        "userId": "u1",
        "sessionId": "s1",
        "newMessage": {"parts": [{"text": "hi"}]},
    }
    for path in ADK_PATHS:
        for accept in ("text/html", "application/json"):
            r = client.get(path, headers={"Accept": accept})
            assert r.status_code in (200, 404), (path, r.status_code)
            if r.status_code == 200:
                assert r.text == PLACEHOLDER_SHELL
        r = client.post(path, json=body)
        assert r.status_code == 404, path
        assert r.json()["code"] == "not_found"
        # Under /api the same names are a JSON 404, never the shell.
        r = client.post("/api" + path, json=body)
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")
    assert calls == []


# --- A5: security headers; docs and schema only in dev ---------------------------------------


@pytest.mark.parametrize("path", ["/", "/health", "/api/projects", "/api/nope", "/openapi.json"])
def test_security_headers_everywhere(client, path):
    r = client.get(path)
    assert r.headers["x-content-type-options"] == "nosniff"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"
    if path.startswith("/api"):
        assert r.headers["cache-control"] == "no-store"


def test_docs_and_schema_not_served_by_default(client):
    assert client.get("/openapi.json").status_code == 404
    for path in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        r = client.get(path)
        assert "swagger" not in r.text.lower() and "redoc" not in r.text.lower()
        assert "openapi" not in r.text.lower()


def test_docs_and_schema_served_with_truelift_dev(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRUELIFT_DEV", "1")
    s = Settings.from_env(port=8765, launch_token=TOKEN)
    app = create_app(make_settings(tmp_path, dev=s.dev))
    with TestClient(app, base_url=BASE) as c:
        assert c.get("/openapi.json").json()["info"]["title"] == "truelift"
        assert "swagger" in c.get("/docs").text.lower()
    monkeypatch.setenv("TRUELIFT_DEV", "0")
    assert Settings.from_env(port=8765, launch_token=TOKEN).dev is False


# --- A6: oversize and malformed bodies; generic 500 with a request ID ------------------------


def test_oversize_body_with_length_is_413(client):
    r = client.post(
        "/api/projects",
        content=b"{" + b" " * (1024 * 1024 + 10) + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"


def test_oversize_chunked_body_is_413(client):
    def chunks():
        for _ in range(40):
            yield b" " * 65536

    r = client.post("/api/projects", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_oversize_upload_is_413(tmp_path: Path):
    app = create_app(make_settings(tmp_path, max_upload_bytes=4096))
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
    with TestClient(app, base_url=BASE, headers=headers) as c:
        big = ("week,region\n" + "2025-01-06,Bayern\n" * 1000).encode()
        r = c.post("/api/projects/petfood-de/data", files={"file": ("panel.csv", big, "text/csv")})
        assert r.status_code == 413
        ok = c.post(
            "/api/projects/petfood-de/data", files={"file": ("panel.csv", b"week\n2025-01-06\n", "text/csv")}
        )
        assert ok.status_code == 201


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("POST", "/api/projects", {"content": b"{not json", "headers": {"Content-Type": "application/json"}}),
        ("POST", "/api/projects", {"json": {"name": "x", "owner": "someone"}}),
        ("POST", "/api/projects", {"json": {"name": "x" * 81}}),
        ("POST", "/api/projects", {"json": {}}),
        ("GET", "/api/projects/Not_Valid!", {}),
        ("GET", "/api/runs/run-1234%2F..%2Fetc", {}),
        ("GET", "/api/runs/run-X", {}),
        ("PUT", "/api/projects/petfood-de/budget", {"json": {"token_budget": 10**12}}),
        ("POST", "/api/projects/petfood-de/agent/messages", {"json": {"text": "x" * 8001}}),
    ],
)
def test_malformed_input_is_422_or_404(client, method, path, kwargs):
    r = client.request(method, path, **kwargs)
    assert r.status_code in (404, 422), r.status_code
    body = r.json()
    assert set(body) <= {"code", "message", "request_id", "fields"}


def test_validation_error_does_not_echo_input(client):
    secret = "not-a-real-key-but-private-0123456789"
    r = client.put("/api/setup/key", json={"provider": "gemini", "api_key": secret, "extra": secret})
    assert r.status_code == 422
    assert secret not in r.text
    assert r.json()["fields"][0]["loc"] == ["body", "extra"]


def _add_failing_route(app, exc: Exception) -> None:
    def boom() -> None:
        raise exc

    app.router.routes.insert(0, APIRoute("/api/boom", boom, methods=["GET"]))


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("secret detail at /Users/someone/projects/petfood"),
        sqlite3.OperationalError("database is locked: SELECT * FROM consent WHERE provider='gemini'"),
    ],
)
def test_unexpected_error_is_generic_500_with_request_id(app, client, exc):
    _add_failing_route(app, exc)
    r = client.get("/api/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "internal_error"
    assert body["request_id"] == r.headers["x-request-id"]
    assert len(body["request_id"]) == 32
    for leak in ("Traceback", "secret detail", "SELECT", "database is locked", "/Users/", 'File "'):
        assert leak not in r.text
    assert r.headers["x-content-type-options"] == "nosniff"


def test_request_id_is_server_generated(client):
    a = client.get("/api/projects", headers={"X-Request-ID": "attacker-chosen"})
    b = client.get("/api/projects")
    assert a.headers["x-request-id"] != "attacker-chosen"
    assert a.headers["x-request-id"] != b.headers["x-request-id"]
