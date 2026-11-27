"""Recorded-reply transports and a scripted session for the gateway tests (G11). Offline.

The provider SDK paths are real: ADK's ``Gemini`` drives the real ``google-genai`` client over an
``httpx.MockTransport``, and ADK's ``LiteLlm`` converts real ``litellm.ModelResponse`` objects
from a ``LiteLLMClient`` stand-in. Only the network hop is replaced. The replies in
``fixtures/replies`` are written in each provider's wire shape (generateContent JSON; LiteLLM's
OpenAI-style completion); they were not captured from a live call.

A script is a list of steps, one per provider attempt: a reply name (``"text"``), an HTTP status
(``429``), ``("status", code, message)`` for an error with a message, or ``"hang"``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx
import litellm
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm, LiteLLMClient
from google.adk.runners import InMemoryRunner
from google.genai import types

from truelift.agents.gateway import Catalog, Gateway, ProviderSpec, load_catalog
from truelift.agents.keys import KeyStore
from truelift.store.db import StateDb

_DEFAULT: Any = object()
REPLIES = Path(__file__).parent / "fixtures" / "replies"
PROVIDERS = ("gemini", "claude")
_STATUS_TEXT = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    429: "RESOURCE_EXHAUSTED",
}


def fake_key(label: str) -> str:
    """A placeholder key for tests, built at run time so no key-shaped literal sits in the source
    (gitleaks, C13). Never a real key."""
    return "-".join(("tl", label, "key", "0123456789"))


def reply(provider: str, name: str) -> dict[str, Any]:
    return json.loads((REPLIES / provider / f"{name}.json").read_text("utf-8"))


def _step_error(step: Any) -> tuple[int, str] | None:
    if isinstance(step, int):
        return step, f"status {step}"
    if isinstance(step, tuple) and step[0] == "status":
        return step[1], step[2]
    return None


_LITELLM_ERRORS = {
    401: litellm.AuthenticationError,
    403: litellm.PermissionDeniedError,
    429: litellm.RateLimitError,
    503: litellm.ServiceUnavailableError,
    500: litellm.InternalServerError,
}


class _ClaudeClient(LiteLLMClient):
    def __init__(self, recorder: Recorder):
        self._recorder = recorder

    async def acompletion(self, model: Any, messages: Any, tools: Any, **kwargs: Any) -> Any:
        rec = self._recorder
        step = rec.next_step()
        rec.requests.append(
            {
                "model": model,
                "body": json.dumps({"messages": messages, "tools": tools}, default=str),
                "kwargs": sorted(kwargs),
                "num_retries": kwargs.get("num_retries"),
                "key_matches": kwargs.get("api_key") == rec.expected_key,
            }
        )
        if step == "hang":
            await asyncio.sleep(3600)
        if (err := _step_error(step)) is not None:
            code, message = err
            if code == 400 and "context" in message:
                raise litellm.ContextWindowExceededError(
                    message=message, llm_provider="anthropic", model=model
                )
            if code == 400:
                raise litellm.BadRequestError(message=message, llm_provider="anthropic", model=model)
            if code == 403:
                raise litellm.PermissionDeniedError(
                    message=message,
                    llm_provider="anthropic",
                    model=model,
                    response=httpx.Response(403, request=httpx.Request("POST", "https://api.anthropic.com")),
                )
            cls = _LITELLM_ERRORS.get(code, litellm.InternalServerError)
            raise cls(message=message, llm_provider="anthropic", model=model)
        return litellm.ModelResponse(**reply("claude", step))


@dataclass
class Recorder:
    """Scripted provider replies, and every request that reached the provider hop."""

    provider: str
    script: list[Any]
    expected_key: str | None = None
    requests: list[dict[str, Any]] = field(default_factory=list)
    _pos: int = 0

    def next_step(self) -> Any:
        step = self.script[min(self._pos, len(self.script) - 1)]
        self._pos += 1
        return step

    @property
    def calls(self) -> int:
        return len(self.requests)

    async def _gemini_handler(self, request: httpx.Request) -> httpx.Response:
        step = self.next_step()
        self.requests.append(
            {
                "url": str(request.url),
                "body": request.content.decode("utf-8"),
                "key_matches": request.headers.get("x-goog-api-key") == self.expected_key,
            }
        )
        if step == "hang":
            await asyncio.sleep(3600)
        if (err := _step_error(step)) is not None:
            code, message = err
            status = _STATUS_TEXT.get(code, "UNAVAILABLE")
            return httpx.Response(code, json={"error": {"code": code, "message": message, "status": status}})
        return httpx.Response(200, json=reply("gemini", step))

    def model_factory(self, spec: ProviderSpec, key: str) -> Any:
        """Same arguments as ``default_model_factory``, plus the recorded transport."""
        if spec.adk == "native":
            transport = httpx.MockTransport(self._gemini_handler)
            return Gemini(
                model=spec.model_id,
                client_kwargs={
                    "api_key": key,
                    "http_options": types.HttpOptions(
                        httpx_async_client=httpx.AsyncClient(transport=transport)
                    ),
                },
            )
        return LiteLlm(model=spec.litellm_model, api_key=key, num_retries=0, llm_client=_ClaudeClient(self))


async def _no_sleep(_: float) -> None:
    return None


def catalog(**limits: Any) -> Catalog:
    base = load_catalog()
    return replace(base, limits=replace(base.limits, **limits))


def make_gateway(
    tmp_path: Path,
    recorder: Recorder,
    *,
    key: Any = _DEFAULT,
    consent: bool = True,
    project_id: str = "demo-1",
    limits: dict[str, Any] | None = None,
    keys: KeyStore | None = None,
) -> Gateway:
    gw = Gateway(
        StateDb(tmp_path / "state" / "state.db"),
        keys,
        catalog(**(limits or {})),
        model_factory=recorder.model_factory,
        sleep=_no_sleep,
    )
    if key is _DEFAULT:
        key = fake_key("test")
    if key is not None:
        gw.save_key(recorder.provider, key)
        recorder.expected_key = key
    if consent:
        gw.accept(project_id, recorder.provider, _current_version())
    return gw


def _current_version() -> str:
    from truelift.agents import gateway

    return gateway.DISCLOSURE_VERSION


def record_note(note: str) -> dict[str, Any]:
    """Record a short note about the business."""
    from truelift.agents.payload import Payload

    return Payload({}).as_tool_result(status="recorded")


async def run_session(
    gw: Gateway,
    text: str,
    *,
    project_id: str = "demo-1",
    provider: str | None = None,
    tools: list[Any] | None = None,
) -> list[Any]:
    """One user message through a real ADK Runner with the gated model and callback."""
    gate = gw.gate(project_id, provider)
    agent = LlmAgent(
        name="probe",
        model=gate.model(),
        instruction="You interview a marketing leader. Keep answers short.",
        before_model_callback=gate.before_model_callback,
        tools=tools or [],
    )
    runner = InMemoryRunner(agent=agent, app_name="g11")
    session = await runner.session_service.create_session(app_name="g11", user_id="u")
    events = []
    async for event in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
        run_config=gw.run_config(),
    ):
        events.append(event)
    await runner.close()
    return events


def final_text(events: list[Any]) -> str:
    return "".join(p.text or "" for e in events if e.content for p in e.content.parts or [] if p.text)
