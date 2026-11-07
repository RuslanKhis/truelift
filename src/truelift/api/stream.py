"""The agent stream contract: Server-Sent Events read with ``fetch`` (C15; G13 and G16 use it).

``POST /api/projects/{project_id}/agent/messages`` answers ``text/event-stream``. Each SSE frame is::

    id: <seq>
    event: <type>
    data: <one AgentEvent as JSON>

The route is kept out of the OpenAPI paths (the generated SSE helper retries, and a message is not
idempotent), but ``AgentEvent`` and its members are added to the OpenAPI components, so the
generated client exports their TypeScript types. The browser still validates every event at run
time (G16, zod).

Turn order: ``turn_started``, then any of ``text_delta``, ``text_done``, ``tool_started``,
``tool_finished``, ``proposal_created`` and ``ai_status``, then exactly one terminal event,
``turn_finished`` or ``turn_failed``. ``seq`` starts at 1 and increases by 1.

G02 serves a fake replay of a recorded event file; G13 replaces it with the real Interviewer.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from importlib import resources
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from truelift.api.schemas import AiState, Proposal


class _Event(BaseModel):
    seq: int = Field(ge=1)
    turn_id: str


class TurnStarted(_Event):
    type: Literal["turn_started"] = "turn_started"


class TextDelta(_Event):
    type: Literal["text_delta"] = "text_delta"
    message_id: str
    delta: str


class TextDone(_Event):
    """The complete text of a message. Replaces the deltas; never append it to them."""

    type: Literal["text_done"] = "text_done"
    message_id: str
    text: str


class ToolStarted(_Event):
    type: Literal["tool_started"] = "tool_started"
    call_id: str
    tool: str
    title: str = Field(description='Shown as "Running <title>…".')


class ToolFinished(_Event):
    type: Literal["tool_finished"] = "tool_finished"
    call_id: str
    tool: str
    ok: bool
    summary: str


class ProposalCreated(_Event):
    type: Literal["proposal_created"] = "proposal_created"
    proposal: Proposal


class AiStatusChanged(_Event):
    """Drives the "AI unavailable" and "AI paused: budget reached" banners (C15)."""

    type: Literal["ai_status"] = "ai_status"
    state: AiState
    message: str


class TurnFinished(_Event):
    type: Literal["turn_finished"] = "turn_finished"


class TurnFailed(_Event):
    """Keep any text already shown; mark the turn failed."""

    type: Literal["turn_failed"] = "turn_failed"
    code: str
    message: str


AgentEvent = Annotated[
    TurnStarted
    | TextDelta
    | TextDone
    | ToolStarted
    | ToolFinished
    | ProposalCreated
    | AiStatusChanged
    | TurnFinished
    | TurnFailed,
    Field(discriminator="type"),
]
AGENT_EVENT = TypeAdapter(AgentEvent)
TERMINAL_TYPES = frozenset({"turn_finished", "turn_failed"})

# Fake scenarios: a message "/scenario <name>" replays fixtures/agent_<name>.jsonl.
SCENARIOS = ("interview", "ai_unavailable", "budget_paused", "turn_failed")


def load_recording(scenario: str) -> list[dict[str, Any]]:
    """Read and validate a recorded event file. Raises on any invalid or out-of-order event."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    text = resources.files("truelift.api.fixtures").joinpath(f"agent_{scenario}.jsonl").read_text("utf-8")
    events = [AGENT_EVENT.validate_python(json.loads(line)) for line in text.splitlines() if line.strip()]
    if not events or events[0].type != "turn_started" or events[-1].type not in TERMINAL_TYPES:
        raise ValueError(f"recording {scenario!r} must start with turn_started and end with a terminal event")
    if any(e.type in TERMINAL_TYPES for e in events[:-1]):
        raise ValueError(f"recording {scenario!r} has a terminal event before the end")
    if [e.seq for e in events] != list(range(1, len(events) + 1)):
        raise ValueError(f"recording {scenario!r} seq must run 1..n")
    return [e.model_dump(mode="json") for e in events]


def sse_frame(event: dict[str, Any]) -> bytes:
    data = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {data}\n\n".encode()


async def replay(events: list[dict[str, Any]], turn_id: str, delay_s: float) -> AsyncIterator[bytes]:
    for event in events:
        if delay_s:
            await asyncio.sleep(delay_s)
        yield sse_frame({**event, "turn_id": turn_id})


class AgentStreamResponse(StreamingResponse):
    """An SSE response that always runs ``on_close``: after the last event, on client disconnect,
    on error, and even when the body iterator never started. The admission lock is released there."""

    media_type = "text/event-stream"

    def __init__(self, content: AsyncIterator[bytes], on_close: Callable[[], Awaitable[None] | None]) -> None:
        super().__init__(
            content,
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
        self._on_close = on_close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            result = self._on_close()
            if result is not None:
                await result
