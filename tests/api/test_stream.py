"""G02 A7 and the stream contract: one agent message at a time per project (C15); the fake stream
replays a recorded, schema-valid event file (A8 floor)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from tests.api.support import ORIGIN, TOKEN, make_settings
from truelift.api.app import create_app
from truelift.api.stream import AGENT_EVENT, SCENARIOS, TERMINAL_TYPES, load_recording
from truelift.cli import bind_loopback

MESSAGES = "/api/projects/petfood-de/agent/messages"


def parse_sse(text: str) -> list[dict]:
    frames = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        data = json.loads(fields["data"])
        assert fields["event"] == data["type"]
        assert fields["id"] == str(data["seq"])
        frames.append(data)
    return frames


def check_turn(events: list[dict]) -> None:
    for e in events:
        AGENT_EVENT.validate_python(e)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "turn_started"
    assert events[-1]["type"] in TERMINAL_TYPES
    assert not any(e["type"] in TERMINAL_TYPES for e in events[:-1])
    assert len({e["turn_id"] for e in events}) == 1


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_recordings_are_valid(scenario):
    events = load_recording(scenario)
    check_turn(events)


@pytest.mark.parametrize(
    ("text", "must_have"),
    [
        ("What makes you decide to run a discount?", "proposal_created"),
        ("/scenario ai_unavailable", "ai_status"),
        ("/scenario budget_paused", "ai_status"),
        ("/scenario turn_failed", "turn_failed"),
    ],
)
def test_stream_replays_recording(client, app, text, must_have):
    r = client.post(MESSAGES, json={"text": text})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    events = parse_sse(r.text)
    check_turn(events)
    assert must_have in {e["type"] for e in events}
    assert events[0]["turn_id"].startswith("t-") and events[0]["turn_id"] != "t-recorded"
    assert app.state.agent_busy == set()


def test_budget_paused_banner_event(client):
    events = parse_sse(client.post(MESSAGES, json={"text": "/scenario budget_paused"}).text)
    status = next(e for e in events if e["type"] == "ai_status")
    assert status["state"] == "budget_paused"


def test_second_message_while_busy_is_409(client, app):
    app.state.agent_busy.add("petfood-de")
    r = client.post(MESSAGES, json={"text": "hello"})
    assert r.status_code == 409
    assert r.json()["code"] == "agent_busy"
    app.state.agent_busy.clear()
    assert client.post(MESSAGES, json={"text": "hello"}).status_code == 200


def test_unknown_project_is_404(client):
    assert client.post("/api/projects/other/agent/messages", json={"text": "hi"}).status_code == 404


# --- A7 over a real socket: two concurrent sends on one project --------------------------------


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[str, object]]:
    sock = bind_loopback(0)
    port = sock.getsockname()[1]
    app = create_app(make_settings(tmp_path, port=port, fake_stream_delay_s=0.15))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", ws="none"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def _headers(base: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Origin": base}


def test_concurrent_second_send_is_409_over_real_socket(live_server):
    base, app = live_server
    with httpx.Client(base_url=base, headers=_headers(base), timeout=10) as c:
        with c.stream("POST", MESSAGES, json={"text": "first"}) as first:
            assert first.status_code == 200
            lines = first.iter_lines()  # keep the iterator: dropping it closes the stream
            assert next(lines).startswith("id: 1")
            second = c.post(MESSAGES, json={"text": "second"})
            assert second.status_code == 409
            assert second.json()["code"] == "agent_busy"
            rest = "\n".join(lines)  # the first turn still completes
        assert "turn_finished" in rest
        assert app.state.agent_busy == set()
        assert c.post(MESSAGES, json={"text": "third"}).status_code == 200


def test_client_disconnect_releases_admission(live_server):
    base, app = live_server
    with httpx.Client(base_url=base, headers=_headers(base), timeout=10) as c:
        with c.stream("POST", MESSAGES, json={"text": "first"}) as first:
            lines = first.iter_lines()
            next(lines)
            assert app.state.agent_busy == {"petfood-de"}
        # Closed after one event; the server notices the disconnect and releases admission.
        deadline = time.monotonic() + 5
        while app.state.agent_busy and time.monotonic() < deadline:
            time.sleep(0.05)
        assert app.state.agent_busy == set()
        assert c.post(MESSAGES, json={"text": "again"}).status_code == 200


def test_origin_constant_matches_base():
    assert ORIGIN.startswith("http://127.0.0.1:")
