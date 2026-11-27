"""``GatedLlm``: the ADK model object every agent uses (D7; C7, C8, C15; G11/A3, A5, A6, A10, A11).

It wraps the provider's ADK model (native ``Gemini`` or ``LiteLlm``) and, for every provider
attempt, in this order:

1. checks key, consent and payload (``Gateway.check``) and the budget, writing the attempt's
   ledger row with its estimate *before* the request leaves (``Gateway.reserve``);
2. fetches the key and builds the provider model with it (no environment variable, no cache);
3. calls the provider inside one deadline for the whole call, retries included
   (``call_deadline_s``, 60 s): a 429 or an unavailable provider is retried at most
   ``max_retries`` times, but only before the first reply chunk has been yielded;
4. settles the ledger row with the provider's usage, or keeps the estimate when the reply had
   no usage or never arrived (A11).

A 400, a safety block or a context-too-long reply ends the call with a plain ``GatewayError`` and
no retry (A10). A rejected key marks the provider so setup asks for a new key (A4).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import ConfigDict

from truelift.agents.gateway import Failure, Gate, GatewayError, classify_failure

_SAFETY = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.SPII,
    types.FinishReason.RECITATION,
    types.FinishReason.IMAGE_SAFETY,
}
# A blocked prompt comes back as ``error_code`` (finish or block reason) with no content.
_SAFETY_CODES = {r.value for r in _SAFETY} | {r.value for r in types.BlockedReason} - {
    "BLOCKED_REASON_UNSPECIFIED"
}


def request_parts(llm_request: LlmRequest) -> tuple[list[dict[str, Any]], str, Any]:
    """The request as JSON-shaped parts: (contents, system instruction text, tool declarations)."""
    contents = [c.model_dump(mode="json", exclude_none=True) for c in llm_request.contents or []]
    config = llm_request.config
    system = ""
    tools: Any = None
    if config is not None:
        si = config.system_instruction
        if isinstance(si, str):
            system = si
        elif isinstance(si, types.Content):
            system = "".join(p.text or "" for p in si.parts or [])
        elif si is not None:
            system = str(si)
        if config.tools:
            tools = [
                t.model_dump(mode="json", exclude_none=True) if hasattr(t, "model_dump") else str(t)
                for t in config.tools
            ]
    return contents, system, tools


def _usage(response: LlmResponse) -> tuple[int, int] | None:
    meta = response.usage_metadata
    if meta is None:
        return None
    prompt = meta.prompt_token_count or 0
    output = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
    if prompt == 0 and output == 0:
        if not meta.total_token_count:
            return None
        return meta.total_token_count, 0
    return prompt, output


def _blocked(response: LlmResponse) -> bool:
    if response.finish_reason in _SAFETY:
        return True
    code = response.error_code
    code = getattr(code, "value", code)
    return (
        code is not None and str(code) in _SAFETY_CODES and not (response.content and response.content.parts)
    )


class GatedLlm(BaseLlm):
    """See the module docstring. ``model`` is the pinned model ID (for ADK and traces)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    gate: Gate

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        gw = self.gate.gateway
        limits = gw.catalog.limits
        spec = gw.catalog.spec(self.gate.provider)
        config = llm_request.config or types.GenerateContentConfig()
        if not config.max_output_tokens:
            config.max_output_tokens = limits.max_output_tokens
        llm_request.config = config
        llm_request.model = spec.litellm_model if spec.adk == "litellm" else spec.model_id
        sleep = gw.sleep or asyncio.sleep
        deadline = time.monotonic() + limits.call_deadline_s
        attempt = 0
        while True:
            contents, system, tools = request_parts(llm_request)
            shape = gw.check(self.gate.project_id, self.gate.provider, contents, system, tools)
            found = gw.keys.get(self.gate.provider)
            if found is None:
                raise GatewayError("no_key")
            reservation = gw.reserve(
                self.gate.project_id, self.gate.provider, shape, config.max_output_tokens
            )
            failure: Failure | None = None
            yielded = False
            usage: tuple[int, int] | None = None
            settled = False
            agen = gw.provider_model(spec, found[0]).generate_content_async(llm_request, stream=stream)
            del found
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        async with asyncio.timeout(remaining):
                            response = await anext(agen)
                    except StopAsyncIteration:
                        break
                    usage = _usage(response) or usage
                    if _blocked(response):
                        gw.settle(reservation, usage)
                        settled = True
                        raise GatewayError("safety_blocked")
                    yielded = True
                    yield response
                gw.settle(reservation, usage)
                settled = True
                return
            except GatewayError:
                raise
            except Exception as exc:  # provider or transport failure: classify, never log the text
                failure = classify_failure(exc)
                gw.fail(reservation, failure)
                settled = True
            finally:
                if not settled:
                    # Closed or cancelled mid-call: keep what the reply reported, else the
                    # estimate stays charged (A11).
                    if usage is not None:
                        gw.settle(reservation, usage)
                    else:
                        gw.db.settle_call(reservation.ledger_id, status="lost")
                await agen.aclose()
            assert failure is not None
            if failure.code == "key_rejected":
                gw.mark_key_rejected(self.gate.provider)
            remaining = deadline - time.monotonic()
            if not failure.retry or yielded or attempt >= limits.max_retries or remaining <= 0:
                raise GatewayError(failure.code) from None
            delays = limits.retry_delays_s or (0.0,)
            delay = delays[min(attempt, len(delays) - 1)]
            if delay >= remaining:
                raise GatewayError(failure.code) from None
            attempt += 1
            await sleep(delay)

    async def connect(self, llm_request: LlmRequest):  # type: ignore[override]
        raise NotImplementedError("live connections do not go through the gateway")
