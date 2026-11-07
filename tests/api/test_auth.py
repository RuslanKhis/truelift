"""G02 A1–A3: launch token, Host and Origin checks, no CORS (C16; SB01, SB02, SB06, SB08)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from tests.api.support import BASE, ORIGIN, PORT, TOKEN, api_calls, make_settings, no_cors_headers
from truelift.api.app import create_app
from truelift.cli import launch_url

# --- A1: every /api route needs the token; SPA assets and /health stay public ----------------


def test_every_api_route_rejects_missing_token(app, anon):
    calls = api_calls(app)
    assert len(calls) >= 25, "route discovery found too few /api routes"
    for method, path in calls:
        r = anon.request(method, path)
        assert r.status_code == 401, (method, path, r.status_code)
        if method != "HEAD":
            assert r.json()["code"] == "unauthorized"
        assert r.headers["www-authenticate"].startswith("Bearer")
        assert no_cors_headers(r)


def test_every_api_route_rejects_wrong_token(app, anon):
    wrong = {"Authorization": "Bearer " + "x" * 43}
    for method, path in api_calls(app):
        r = anon.request(method, path, headers=wrong)
        assert r.status_code == 401, (method, path)


@pytest.mark.parametrize(
    "value",
    [
        f"Basic {TOKEN}",
        TOKEN,
        "Bearer",
        f"Bearer {TOKEN[:-1]}",
        f"Bearer {TOKEN}x",
    ],
)
def test_malformed_authorization_rejected(anon, value):
    assert anon.get("/api/projects", headers={"Authorization": value}).status_code == 401


def test_unknown_api_path_needs_token_then_404(anon, client):
    assert anon.get("/api/does/not/exist").status_code == 401
    r = client.get("/api/does/not/exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_no_token_configured_fails_closed(tmp_path: Path):
    app = create_app(make_settings(tmp_path, launch_token=None))
    with TestClient(app, base_url=BASE, headers={"Origin": ORIGIN}) as c:
        for method, path in api_calls(app):
            r = c.request(method, path, headers={"Authorization": "Bearer " + "a" * 43})
            assert r.status_code == 401, (method, path)
        assert c.get("/health").status_code == 200


def test_valid_token_accepted(client):
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json()[0]["id"] == "petfood-de"


def test_health_and_spa_are_public(tmp_path: Path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>shell</title>")
    (web / "assets" / "app.js").write_text("console.log(1)")
    app = create_app(make_settings(tmp_path))
    with TestClient(app, base_url=BASE) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert "shell" in c.get("/").text
        assert "shell" in c.get("/projects/petfood-de/interview").text  # client-side route
        js = c.get("/assets/app.js")
        assert js.status_code == 200 and js.text == "console.log(1)"
        assert c.get("/assets/missing.js").status_code == 404
        # No escape from the build directory.
        assert c.get("/%2e%2e/%2e%2e/pyproject.toml").status_code == 404


# --- A2: token only from the Authorization header; launch URL carries it in the fragment -----


@pytest.mark.parametrize("query", [f"token={TOKEN}", f"access_token={TOKEN}", "token=x", f"q={TOKEN}"])
def test_token_in_query_rejected_even_with_header(client, anon, query):
    for c in (anon, client):
        r = c.get(f"/api/projects?{query}")
        assert r.status_code == 401
        assert r.json()["code"] == "token_in_query"
        assert TOKEN not in r.text


def test_launch_url_has_token_only_in_fragment():
    url = launch_url(PORT, TOKEN)
    parts = urlsplit(url)
    assert parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.port == PORT
    assert parts.query == "" and parts.path == "/"
    assert parse_qs(parts.fragment) == {"token": [TOKEN]}


def test_token_never_in_responses(client, anon):
    for r in (client.get("/api/projects"), anon.get("/api/projects"), client.get("/"), client.get("/health")):
        assert TOKEN not in r.text
        assert all(TOKEN not in v for v in r.headers.values())


# --- A3: Host allowlist, same-origin for unsafe methods, no CORS ------------------------------


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        f"evil.example:{PORT}",
        "127.0.0.1:9999",
        f"192.168.1.5:{PORT}",
        f"localhost.evil:{PORT}",
    ],
)
def test_wrong_host_is_403_everywhere(client, host):
    for path in ("/api/projects", "/health", "/"):
        r = client.get(path, headers={"Host": host})
        assert r.status_code == 403, (host, path)
        assert r.json()["code"] == "host_not_allowed"


def test_localhost_host_allowed(client):
    assert client.get("/api/projects", headers={"Host": f"localhost:{PORT}"}).status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
@pytest.mark.parametrize("origin", ["http://evil.example", "null", f"http://127.0.0.1:{PORT + 1}", None])
def test_foreign_or_missing_origin_on_unsafe_method_is_403(client, method, origin):
    headers = {"Origin": origin} if origin else {}
    if origin is None:
        client.headers.pop("Origin")
    r = client.request(method, "/api/projects", headers=headers, json={"name": "x"})
    assert r.status_code == 403
    assert r.json()["code"] == "origin_not_allowed"
    assert no_cors_headers(r)


def test_same_origin_post_allowed(client):
    r = client.post(
        "/api/projects", json={"name": "Garden tools"}, headers={"Origin": f"http://localhost:{PORT}"}
    )
    assert r.status_code == 201


def test_no_cors_headers_on_preflight_or_reads(client):
    preflight = client.options(
        "/api/projects",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert no_cors_headers(preflight)
    assert preflight.status_code in (401, 404, 405)
    read = client.get("/api/projects", headers={"Origin": "http://evil.example"})
    assert no_cors_headers(read)


def test_dev_origins_only_in_dev_mode(tmp_path: Path):
    vite = "http://localhost:5173"
    for dev, expected in ((True, 201), (False, 403)):
        app = create_app(make_settings(tmp_path, dev=dev, dev_origins=(vite,)))
        with TestClient(app, base_url=BASE, headers={"Authorization": f"Bearer {TOKEN}"}) as c:
            r = c.post("/api/projects", json={"name": f"dev {dev}"}, headers={"Origin": vite})
            assert r.status_code == expected
