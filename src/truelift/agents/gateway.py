"""The model gateway: one gate for every LLM call (D7; C7, C8, C15; SB14, SB19; G11).

Agents get their model and their callback from here and nowhere else::

    gate = gateway.gate(project_id)              # provider: the active one
    agent = LlmAgent(model=gate.model(), before_model_callback=gate.before_model_callback, ...)
    runner.run_async(..., run_config=gateway.run_config())

The gate decides, before each provider attempt:

* **Key** (C7): fetched from the keychain (or the user's environment variable) at call time and
  handed only to the provider model object. A key the provider rejected stays rejected until the
  user saves a new one.
* **Consent** (C8): the project accepted the current disclosure version for this provider.
* **Payload** (C8): only disclosed categories, at most 20 sample rows, no ground-truth column,
  at most ``max_request_bytes`` (``truelift.agents.payload``).
* **Budget** (C15): the attempt's conservative estimate fits the project's token budget. The
  estimate is charged in the ledger *before* the request leaves; the provider's usage replaces it
  when the reply arrives. A lost reply keeps the estimate (A11).

``before_model_callback`` runs the first three checks early; ``GatedLlm`` (``gated_model``), the
model object itself, runs all four at the provider boundary, so a plugin that short-circuits
callbacks (ADK 2.12 skips agent callbacks then) cannot bypass them. Retries, the 60 s deadline
and the mapping of provider errors to plain messages live there too.

Every refusal and failure is a ``GatewayError`` with a static code, an ``AiState`` for the
banner and a plain message; none carries the key, the payload or provider error text.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any

import yaml

from truelift.agents import payload as payload_mod
from truelift.agents import redaction
from truelift.agents.keys import KeySlot, KeyStore
from truelift.agents.payload import CATEGORIES, PayloadRefused, RequestShape
from truelift.api.schemas import AiState
from truelift.store.db import ConsentRow, LedgerRow, StateDb

if TYPE_CHECKING:
    from google.adk.agents.run_config import RunConfig
    from google.adk.models.base_llm import BaseLlm

    from truelift.agents.gated_model import GatedLlm

# Bump on any change to what may be shared (categories, limits, wording): every project must
# consent again before its next call (C8, G11/A2).
DISCLOSURE_VERSION = "2026-11-1"
RETENTION_NOTE = "The provider keeps requests according to its own terms for API use."


# --- the pinned catalogue (models.yaml) -----------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    label: str
    model_id: str
    adk: str  # "native" (ADK Gemini) or "litellm"
    keyring_account: str
    env_var: str
    host: str
    litellm_model: str | None = None


@dataclass(frozen=True)
class Limits:
    max_llm_calls: int
    default_token_budget: int
    max_output_tokens: int
    max_request_bytes: int
    max_retries: int
    retry_delays_s: tuple[float, ...]
    call_deadline_s: float
    bytes_per_token_estimate: int

    def __post_init__(self) -> None:
        # max_llm_calls <= 0 disables ADK's bound; refuse that (runtime-bounds).
        if self.max_llm_calls <= 0 or self.max_retries < 0 or self.call_deadline_s <= 0:
            raise ValueError("models.yaml: limits must be positive")


@dataclass(frozen=True)
class Catalog:
    providers: dict[str, ProviderSpec]
    order: tuple[str, ...]
    limits: Limits

    def spec(self, provider: str) -> ProviderSpec:
        return self.providers[provider]

    def key_slots(self) -> dict[str, KeySlot]:
        return {p: KeySlot(p, s.keyring_account, s.env_var) for p, s in self.providers.items()}


def parse_catalog(raw: Mapping[str, Any]) -> Catalog:
    providers = {
        name: ProviderSpec(provider=name, **{k: v for k, v in spec.items()})
        for name, spec in raw["providers"].items()
    }
    for spec in providers.values():
        if spec.adk not in ("native", "litellm") or (spec.adk == "litellm" and not spec.litellm_model):
            raise ValueError(f"models.yaml: provider {spec.provider} has an unknown adapter")
    limits = dict(raw["limits"])
    limits["retry_delays_s"] = tuple(float(d) for d in limits["retry_delays_s"])
    order = tuple(raw.get("order") or providers)
    if set(order) != set(providers):
        raise ValueError("models.yaml: order must list every provider")
    return Catalog(providers, order, Limits(**limits))


@cache
def load_catalog() -> Catalog:
    text = resources.files("truelift").joinpath("models.yaml").read_text("utf-8")
    return parse_catalog(yaml.safe_load(text))


# --- errors ---------------------------------------------------------------------------------

_MESSAGES: dict[str, tuple[AiState, str]] = {
    "no_key": (AiState.no_key, "Add an API key in Setup to use the AI assistant."),
    "key_rejected": (
        AiState.no_key,
        "The provider rejected your API key. Add a new key in Setup. Everything else keeps working.",
    ),
    "consent_needed": (
        AiState.consent_needed,
        "Review what will be shared before the AI assistant can continue.",
    ),
    "payload_refused": (
        AiState.available,
        "The assistant tried to share something that is not on the disclosure list, so nothing was sent.",
    ),
    "payload_too_large": (
        AiState.available,
        "This request is larger than truelift sends to the AI provider, so nothing was sent.",
    ),
    "budget_paused": (AiState.budget_paused, "AI paused: budget reached. Raise it or continue without AI."),
    "rate_limited": (
        AiState.unavailable,
        "AI paused: the provider is limiting requests. Try again in a minute. Everything else keeps working.",
    ),
    "unavailable": (
        AiState.unavailable,
        "AI unavailable: the provider did not answer. Try again later. Everything else keeps working.",
    ),
    "invalid_request": (AiState.available, "The AI provider could not process this request."),
    "safety_blocked": (AiState.available, "The AI provider declined to answer this request."),
    "context_too_long": (
        AiState.available,
        "The conversation is too long for the AI model. Start a new interview session.",
    ),
    "call_limit": (
        AiState.available,
        "The assistant stopped after too many steps on one message. Try asking again more simply.",
    ),
}


class GatewayError(Exception):
    """A refused or failed model call. ``str()`` is the static message; nothing else is attached."""

    def __init__(self, code: str):
        state, message = _MESSAGES[code]
        super().__init__(message)
        self.code = code
        self.ai_state = state
        self.message = message


_PAYLOAD_CODES = {"too_large": "payload_too_large"}


def gateway_error_for(exc: BaseException) -> GatewayError | None:
    """The gateway error for an exception that ends an agent turn, or None for a bug.

    G13 maps the result to the stream's ``ai_status`` and ``turn_failed`` events. ADK's
    ``LlmCallsLimitExceededError`` (``max_llm_calls``) becomes ``call_limit``."""
    if isinstance(exc, GatewayError):
        return exc
    if type(exc).__name__ == "LlmCallsLimitExceededError":
        return GatewayError("call_limit")
    return None


# --- provider error classification ----------------------------------------------------------

_CONTEXT_RE = re.compile(r"(context|token)[^.]{0,80}(exceed|too long|limit|maximum)", re.IGNORECASE)
_KEY_RE = re.compile(r"api[ _-]?key|API_KEY_INVALID|x-api-key|authentication", re.IGNORECASE)
_TRANSPORT_UNSENT = {"ConnectError", "ConnectTimeout", "gaierror", "ConnectionRefusedError"}
_TRANSPORT_LOST = {
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "TimeoutException",
    "ReadError",
    "RemoteProtocolError",
    "NetworkError",
    "Timeout",
    "APITimeoutError",
    "APIConnectionError",
    "ServerDisconnectedError",
    "ClientConnectionError",
}


@dataclass(frozen=True)
class Failure:
    """How a provider attempt failed: the error code, whether to retry, and what to charge."""

    code: str
    retry: bool
    # "rejected": not billed (4xx); "lost": estimate stays charged; "not_sent": nothing left.
    charge: str


def _names(exc: BaseException) -> set[str]:
    return {t.__name__ for t in type(exc).__mro__}


def _status(exc: BaseException) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_failure(exc: BaseException) -> Failure:
    """Map a provider or transport exception to a ``Failure``. Reads the exception text only to
    tell a context-length or key error from another 400; never logs or returns it."""
    names = _names(exc)
    status = _status(exc)
    text = str(exc)[:2000]
    if isinstance(exc, TimeoutError) and not (names & _TRANSPORT_UNSENT):
        return Failure("unavailable", retry=True, charge="lost")
    if "ContextWindowExceededError" in names or (status in (400, 413) and _CONTEXT_RE.search(text)):
        return Failure("context_too_long", retry=False, charge="rejected")
    if "ContentPolicyViolationError" in names:
        return Failure("safety_blocked", retry=False, charge="rejected")
    if (
        status in (401, 403)
        or names & {"AuthenticationError", "PermissionDeniedError"}
        or (status == 400 and _KEY_RE.search(text))
    ):
        return Failure("key_rejected", retry=False, charge="rejected")
    if status == 429 or "RateLimitError" in names:
        return Failure("rate_limited", retry=True, charge="rejected")
    if names & _TRANSPORT_UNSENT:
        return Failure("unavailable", retry=True, charge="not_sent")
    if (status is not None and status >= 500) or names & {"ServiceUnavailableError", "InternalServerError"}:
        return Failure("unavailable", retry=True, charge="lost")
    if names & _TRANSPORT_LOST or isinstance(exc, OSError):
        return Failure("unavailable", retry=True, charge="lost")
    if (status is not None and 400 <= status < 500) or "BadRequestError" in names:
        return Failure("invalid_request", retry=False, charge="rejected")
    # Unknown: treat the reply as lost (charge the estimate) and do not retry.
    return Failure("unavailable", retry=False, charge="lost")


# --- the gateway service --------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderState:
    provider: str
    label: str
    model_id: str
    key_configured: bool
    key_rejected: bool


@dataclass(frozen=True)
class UsageView:
    tokens_used: int
    token_budget: int
    ai_state: AiState


@dataclass(frozen=True)
class Reservation:
    ledger_id: int
    input_estimate: int
    output_estimate: int


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Gateway:
    """Keys, consent, budget and ledger for every project, and the factory of gated models.

    ``model_factory(spec, key)`` builds the provider model (ADK ``Gemini`` or ``LiteLlm``) for one
    attempt; tests pass one that wires a recorded-reply transport. ``sleep`` paces retries."""

    def __init__(
        self,
        db: StateDb,
        keys: KeyStore | None = None,
        catalog: Catalog | None = None,
        *,
        model_factory: Callable[[ProviderSpec, str], BaseLlm] | None = None,
        sleep: Callable[[float], Any] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ):
        # Every process that can call a model scrubs keys from its logs (C7, SB14).
        redaction.install()
        self.db = db
        self.catalog = catalog or load_catalog()
        self.keys = keys or KeyStore(self.catalog.key_slots())
        self.model_factory = model_factory
        self.sleep = sleep
        self.clock = clock
        # Providers whose key was rejected in this process; cleared by saving a new key.
        self._rejected: set[str] = set()

    # --- setup ---------------------------------------------------------------------------

    def providers(self) -> list[ProviderState]:
        out = []
        for name in self.catalog.order:
            spec = self.catalog.spec(name)
            rejected = name in self._rejected
            out.append(
                ProviderState(
                    provider=name,
                    label=spec.label,
                    model_id=spec.model_id,
                    key_configured=self.keys.status(name).configured and not rejected,
                    key_rejected=rejected,
                )
            )
        return out

    def active_provider(self) -> str | None:
        chosen = self.db.setting("active_provider")
        if chosen in self.catalog.providers:
            return chosen
        for state in self.providers():
            if state.key_configured:
                return state.provider
        return None

    def save_key(self, provider: str, key: str) -> None:
        """Store the key in the keychain (read back to verify) and make the provider active.
        Raises ``KeychainUnavailable``; the key is never stored anywhere else."""
        self.keys.save(provider, key)
        self._rejected.discard(provider)
        self.db.set_setting("active_provider", provider)

    def mark_key_rejected(self, provider: str) -> None:
        self._rejected.add(provider)

    def disclosure_categories(self) -> list[tuple[str, str, str]]:
        return [(cid, title, desc) for cid, (title, desc) in CATEGORIES.items()]

    def accept(self, project_id: str, provider: str, version: str) -> ConsentRow:
        """Record consent to ``version``. Raises ``ValueError`` when it is not the current one."""
        if version != DISCLOSURE_VERSION:
            raise ValueError("disclosure changed")
        row = ConsentRow(project_id, provider, version, self.clock())
        self.db.set_consent(row)
        return row

    def has_consent(self, project_id: str, provider: str) -> bool:
        row = self.db.consent(project_id, provider)
        return row is not None and row.disclosure_version == DISCLOSURE_VERSION

    def token_budget(self, project_id: str) -> int:
        value = self.db.token_budget(project_id)
        return value if value is not None else self.catalog.limits.default_token_budget

    def set_budget(self, project_id: str, token_budget: int) -> None:
        self.db.set_token_budget(project_id, token_budget)

    def usage(self, project_id: str, provider: str | None = None) -> UsageView:
        used = self.db.tokens_used(project_id)
        budget = self.token_budget(project_id)
        provider = provider or self.active_provider()
        if provider is None or provider in self._rejected or not self.keys.status(provider).configured:
            state = AiState.no_key
        elif not self.has_consent(project_id, provider):
            state = AiState.consent_needed
        elif used >= budget:
            state = AiState.budget_paused
        else:
            state = AiState.available
        return UsageView(used, budget, state)

    def ledger(self, project_id: str) -> list[LedgerRow]:
        return self.db.ledger_rows(project_id)

    # --- admission (called per attempt) -------------------------------------------------

    def check(
        self,
        project_id: str,
        provider: str,
        contents: list[dict[str, Any]],
        system_instruction: str = "",
        tools: Any = None,
    ) -> RequestShape:
        """Key, consent and payload checks; no write. Raises ``GatewayError``."""
        if provider in self._rejected:
            raise GatewayError("key_rejected")
        if not self.keys.status(provider).configured:
            raise GatewayError("no_key")
        if not self.has_consent(project_id, provider):
            raise GatewayError("consent_needed")
        try:
            return payload_mod.inspect_request(
                contents, system_instruction, tools, max_bytes=self.catalog.limits.max_request_bytes
            )
        except PayloadRefused as exc:
            raise GatewayError(_PAYLOAD_CODES.get(exc.code, "payload_refused")) from None

    def reserve(
        self, project_id: str, provider: str, shape: RequestShape, max_output_tokens: int
    ) -> Reservation:
        """Charge the attempt's estimate and write its ledger row before it is sent (C15, A11)."""
        limits = self.catalog.limits
        input_estimate = math.ceil(shape.bytes / limits.bytes_per_token_estimate)
        row = LedgerRow(
            id=0,
            project_id=project_id,
            at=self.clock(),
            provider=provider,
            model_id=self.catalog.spec(provider).model_id,
            categories=json.dumps(list(shape.categories)),
            bytes_sent=shape.bytes,
            input_tokens=input_estimate,
            output_tokens=max_output_tokens,
            status="sent",
        )
        ledger_id = self.db.reserve_call(row, self.token_budget(project_id))
        if ledger_id is None:
            raise GatewayError("budget_paused")
        return Reservation(ledger_id, input_estimate, max_output_tokens)

    def settle(self, reservation: Reservation, usage: tuple[int, int] | None) -> None:
        """The provider's usage replaces the estimate; no usage keeps the estimate (A11)."""
        if usage is None:
            self.db.settle_call(reservation.ledger_id, status="estimated")
        else:
            self.db.settle_call(
                reservation.ledger_id, input_tokens=usage[0], output_tokens=usage[1], status="settled"
            )

    def fail(self, reservation: Reservation, failure: Failure) -> None:
        if failure.charge == "lost":
            self.db.settle_call(reservation.ledger_id, status="lost")
        elif failure.charge == "not_sent":
            self.db.settle_call(
                reservation.ledger_id, bytes_sent=0, input_tokens=0, output_tokens=0, status="not_sent"
            )
        else:
            self.db.settle_call(reservation.ledger_id, input_tokens=0, output_tokens=0, status="rejected")

    # --- models -------------------------------------------------------------------------

    def gate(self, project_id: str, provider: str | None = None) -> Gate:
        provider = provider or self.active_provider()
        if provider is None:
            raise GatewayError("no_key")
        return Gate(self, project_id, provider)

    def run_config(self, **kwargs: Any) -> RunConfig:
        """ADK ``RunConfig`` with the pinned ``max_llm_calls`` (C15)."""
        from google.adk.agents.run_config import RunConfig

        return RunConfig(max_llm_calls=self.catalog.limits.max_llm_calls, **kwargs)

    def provider_model(self, spec: ProviderSpec, key: str) -> BaseLlm:
        """The provider's ADK model for one attempt, with the key passed in (C7, D7)."""
        if self.model_factory is not None:
            return self.model_factory(spec, key)
        return default_model_factory(spec, key)


def default_model_factory(spec: ProviderSpec, key: str) -> BaseLlm:
    """ADK's native Gemini, or LiteLlm, with the key per call and no SDK retries of its own: the
    gateway counts every attempt (C15). No provider environment variable is read (G03/A4)."""
    if spec.adk == "native":
        from google.adk.models.google_llm import Gemini

        return Gemini(model=spec.model_id, client_kwargs={"api_key": key})
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(model=spec.litellm_model, api_key=key, num_retries=0)


@dataclass(frozen=True)
class Gate:
    """The gateway bound to one project and provider: its model and its callback."""

    gateway: Gateway
    project_id: str
    provider: str

    def model(self) -> GatedLlm:
        from truelift.agents.gated_model import GatedLlm

        return GatedLlm(model=self.gateway.catalog.spec(self.provider).model_id, gate=self)

    def before_model_callback(self, callback_context: Any, llm_request: Any) -> None:
        """ADK ``before_model_callback``: refuse early when there is no key or consent, or the
        payload is not allowed (C8). Returns None to let the call proceed to ``GatedLlm``."""
        from truelift.agents.gated_model import request_parts

        contents, system, tools = request_parts(llm_request)
        self.gateway.check(self.project_id, self.provider, contents, system, tools)
        return None
