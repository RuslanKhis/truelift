"""The agent message stream. Stub (G02): replays a recorded event file. G13 plugs in the Interviewer.

One message at a time per project: a second concurrent message gets 409 ``agent_busy`` before
any model work starts, so a double send cannot double model spend (C15). The admission is
released when the stream ends for any reason (finished, failed, client gone).

Fake scenarios: a message ``/scenario <name>`` replays ``fixtures/agent_<name>.jsonl``; any
other text replays ``interview``. See ``truelift.api.stream`` for the event contract.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from truelift.api.errors import ApiError
from truelift.api.routes import DemoProject
from truelift.api.schemas import AgentMessageIn
from truelift.api.stream import SCENARIOS, AgentStreamResponse, load_recording, replay

# Kept out of the OpenAPI paths on purpose (see truelift.api.stream).
router = APIRouter(tags=["agent"], include_in_schema=False)


def _scenario(text: str) -> str:
    head, _, name = text.strip().partition(" ")
    return name.strip() if head == "/scenario" and name.strip() in SCENARIOS else "interview"


@router.post("/projects/{project_id}/agent/messages")
async def post_agent_message(
    project_id: DemoProject, body: AgentMessageIn, request: Request
) -> AgentStreamResponse:
    busy: set[str] = request.app.state.agent_busy
    if project_id in busy:
        raise ApiError(409, "agent_busy", "The assistant is still answering your last message.")
    # Single event loop: check-then-add has no await between, so it is atomic.
    busy.add(project_id)
    try:
        events = load_recording(_scenario(body.text))
    except Exception:
        busy.discard(project_id)
        raise
    turn_id = "t-" + uuid.uuid4().hex[:12]
    delay = request.app.state.settings.fake_stream_delay_s
    return AgentStreamResponse(replay(events, turn_id, delay), on_close=lambda: busy.discard(project_id))
