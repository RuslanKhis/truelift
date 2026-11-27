---
goal: G11
title: Model gateway: keys, consent, payload limits and budget
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-operational-guardrails
supporting_skills: [adk-tool-auth-and-secrets (key storage), adk-model-and-output-contracts (model IDs), protect-adk-sensitive-data (payload projection)]
docs: [adk-operational-guardrails/references/token-budgets.md, adk-operational-guardrails/references/runtime-bounds.md]
blocked_by: [G02, G03, G06, G08]
touches: [src/truelift/agents/gateway.py, src/truelift/models.yaml, src/truelift/api/routes/setup.py, tests/agents/test_gateway.py]
parallel_safe: no
contracts: [C7, C8, C15]
companion_skills: []
security: [SB14, SB19]
design_system: none
contract_deltas: ["C16: PUT /api/setup/key documents a 503 keychain_unavailable response (additive; openapi.json and frontend/src/client regenerated)"]
pass_to_pass: [G01/A2, G02/A1, G02/A7]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3.5-6
  review_and_verify: 1-2
  total: 4.5-8
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: verified_local
---

# G11 Model gateway: keys, consent, payload limits and budget

## Outcome

Every LLM call goes through one gate that holds the key, consent, payload limits and budget (C7, C8, C15; D7, D17).

## Scope

- In: `agents/gateway.py`, which provides a model factory (native Gemini or `LiteLlm`, IDs from `models.yaml`) and a `before_model_callback` (consent version, payload categories and byte cap, token budget). `keyring` storage. A logging redaction filter. The ledger table. Key and consent routes.
- Route: `agents/gateway.py`, which provides a model factory (native Gemini or `LiteLlm`, IDs from `models.yaml`) and a `before_model_callback` (consent version, payload categories and byte cap, token budget). `keyring` storage. A logging redaction filter. The ledger table. Key and consent routes.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The key is stored only in the keychain. Logs captured during a scripted session, `state.db`, project files, captured model requests and error bodies contain no key substring (C7, SB14).
- [ ] A2 No model call happens before consent for the current disclosure version and provider. A version bump forces re-consent (C8).
- [ ] A3 A payload holds only the allowed categories and at most 20 sample rows, with forbidden columns removed. An oversized payload is refused. Each call writes a ledger row with categories, bytes and tokens, and no content (C8).
- [ ] A4 An invalid or revoked key produces a "key rejected" setup prompt, and the key is never echoed (C7).
- [ ] A5 `max_llm_calls` stops a looping scripted agent. When the project budget runs out, AI features pause while mapping, DAG, runs and results tiles keep working. A 429 gets at most 2 retries, then a pause (C15, SB19).
- [ ] A6 When the provider times out or is unavailable, the agent waits up to 60 s and then shows an "AI unavailable" banner. Deterministic flows continue (C15).
- [ ] A7 When the keychain is unavailable or locked, the gateway falls back to the per-provider environment variable (`TRUELIFT_GEMINI_API_KEY`, `TRUELIFT_ANTHROPIC_API_KEY`) only, never to a file, with a clear message. A saved key is read back to verify it (C7).
- [ ] A8 Native Gemini and Claude via `LiteLlm` both pass the same recorded-reply suite. IDs come from `models.yaml` (C8).
- [ ] A9 A socket-level test shows the provider is the only network destination during a scripted session; LiteLLM's remote cost-map fetch is disabled (`LITELLM_LOCAL_MODEL_COST_MAP=True`) (C8).
- [ ] A10 A 400, a safety block and a context-too-long reply each produce a plain message and no retry loop (C15).
- [ ] A11 A lost response (timeout after send) charges an estimated token count to the budget, so a missing `usage_metadata` cannot bypass C15 (C15).

Verification, automated: `uv run pytest tests/agents/test_gateway.py` exits 0 on recorded replies (offline).
Verification, manual: none.

## Evidence

Built on branch `g11-model-gateway` from `ddcd3d7`, 2026-11-27, Ruslan's machine (Apple M1, macOS 13.2.1, Python 3.12.16, google-adk 2.12.0, google-genai 2.34.0, litellm 1.106.2, keyring 25.7.0). No test makes a network call or reads the real keychain.

- `src/truelift/models.yaml`: the pinned model IDs (`gemini-3.8-flash` native, `claude-sonnet-5-5` through LiteLlm), keychain accounts, environment variables, provider hosts and the limits (`max_llm_calls` 12, budget 2,000,000 tokens, reply cap 4096, request cap 256 KiB, 2 retries, 60 s deadline).
- `src/truelift/agents/`:
  - `gateway.py`: the catalogue, `Gateway` (keys, consent, budget, ledger, provider-error classification, `run_config()` with `max_llm_calls`) and `Gate` (one project and provider: `model()` and `before_model_callback`).
  - `gated_model.py`: `GatedLlm`, the ADK model object. It wraps native `Gemini` or `LiteLlm` and, on every provider attempt, checks, reserves, calls, retries and settles.
  - `keys.py`: the keyring store with the environment-variable fallback.
  - `payload.py`: the disclosed categories, the payload builder and the request inspector.
  - `redaction.py`: the record-factory log scrubber.
  - Nothing in the package imports ADK at import time.
- `src/truelift/store/db.py`: the `consents`, `ai_budgets`, `egress_ledger` and `app_settings` tables and their queries. `reserve_call` checks the budget and inserts the ledger row in one `BEGIN IMMEDIATE`.
- `src/truelift/api/routes/setup.py`: real projects use the gateway (setup, key, disclosure, consent, usage, budget, ledger); the demo project keeps the G02 fakes. `src/truelift/api/app.py` installs redaction and builds the gateway.
- `src/truelift/__init__.py`: sets `LITELLM_LOCAL_MODEL_COST_MAP=True`, forced, at package import.
- `pyproject.toml` and `uv.lock`: `keyring>=25.7` (`uv add`). pip-audit is clean.
- Tests: `tests/agents/test_gateway.py` has 62 cases, with recorded replies in `tests/agents/fixtures/replies/{gemini,claude}/`. `tests/agents/support.py` uses the real ADK `Gemini` and the real `google-genai` client over `httpx.MockTransport`, and the real ADK `LiteLlm` over a `LiteLLMClient` stand-in that returns real `litellm.ModelResponse` objects. The replies are written in each provider's wire shape; they were not captured from a live call. `tests/conftest.py` has an autouse in-memory keyring and clears `TRUELIFT_*_API_KEY`.

Results (tier, outcome). Verification: `uv run pytest tests/agents/test_gateway.py` at 21:56 gave 62 passed in 20.8 s. `make check` gave 619 passed and 1 skipped (private), with the guard, ruff, client drift, pip-audit and npm audit (high) all passing. `make dist` gave a clean guard, and the wheel contains `models.yaml`.

- pass_to_pass G01/A2, G02/A1 and G02/A7: `uv run pytest tests/test_guard.py tests/api` gave 165 passed and 1 skipped before the change. After it, the same command (and `make check`) passes once the client is regenerated; only `test_committed_openapi_matches_code` failed until then (expected drift).
- A1: `offline, pass`. Both providers ran a scripted session with a random canary key: a reply, a 400 whose provider text quotes the key, then a 401. DEBUG logging was on for LiteLLM, google_genai, google_adk, httpx and truelift, plus a `logger.exception` with the key in its message and its exception. The canary was found in none of these: the captured log records, stdout and stderr, every file under the test's state and project folders (`state.db` and WAL included), the captured request bodies and URLs, and the fully formatted exception chain. The key is in the keychain backend only, and the provider got the right key in its header. The redaction filter scrubs Google-shaped keys in messages and exceptions. `PUT /setup/key` never echoes the key, and no file holds it.
- A2: `offline, pass`. With no consent the call is refused (`consent_needed`), with zero provider calls and no ledger row. Consent is per provider. Bumping `DISCLOSURE_VERSION` refuses the next call until consent is given again, and an old version gives 409 `disclosure_changed` on the API.
- A3: `offline, pass`. `build_payload` drops ground-truth columns and refuses more than 20 rows. The request inspector refuses a file part, a tool result without an envelope, an unknown category, 21 rows, a forbidden column and malformed envelope JSON. A forbidden payload and an oversized request (cap 4096 in the test) are refused with zero provider calls and no ledger row. A ledger row holds categories, bytes and tokens; `state.db` holds none of the sample values or reply text.
- A4: `offline, pass` for Gemini 400 "API key not valid", Gemini 403, Claude 401 and Claude 403. Each makes one attempt with no retry and gives `key_rejected` with "The provider rejected your API key. Add a new key in Setup…". Setup then shows the provider as not configured, `ai_state` is `no_key`, and calls are refused locally until a new key is saved.
- A5: `offline, pass`. A model that loops on a tool call stops after `max_llm_calls` (4 in the test) model calls, for both providers. `gateway_error_for` maps ADK's `LlmCallsLimitExceededError` to `call_limit`. When the budget is reached, or the estimate does not fit, the AI pauses ("AI paused: budget reached") with zero provider calls. A 429 gets 1 + 2 attempts and then `rate_limited`, and those rows are not charged; a 429 followed by a reply succeeds. On a scripted real project with `ai_state` `budget_paused`, the project, DAG, identification, runs and ledger routes still return 200.
- A6: `offline, pass`. A provider that hangs ends at the deadline (0.5 s in the test; 60 s pinned in `models.yaml`) with "AI unavailable…" after one attempt. A 503 is retried twice and then `unavailable`. The deterministic routes work as in A5.
- A7: `offline, pass`. When the backend is keyring's `fail` backend, a locked keychain (`KeyringLocked`) or a file-backed `keyrings.alt` backend, saving raises a message that names `TRUELIFT_GEMINI_API_KEY`. Reads use the environment variable only, and nothing is written to the file backend. A backend that drops the write fails the read-back. A locked keychain on the API gives 503 `keychain_unavailable` with no echo and no file. An environment-only key drives a session.
- A8: `offline, pass`. Native Gemini and Claude via LiteLlm pass the same suite: a text reply, a tool call then text, and the error, timeout and usage cases above. The requests use `models/gemini-3.8-flash` and `anthropic/claude-sonnet-5-5` from `models.yaml`, with `num_retries=0` and no SDK retry options.
- A9: `offline, pass`. A subprocess patches `socket.getaddrinfo` and `socket.connect` to record and refuse every destination, then imports truelift and LiteLLM and runs a session per provider through the real SDK HTTP paths. The only hosts tried are `generativelanguage.googleapis.com` and `api.anthropic.com`, and nothing is contacted at import time. LiteLLM reports its cost map as `local`, env-forced. When the probe imported LiteLLM *before* truelift, LiteLLM tried `raw.githubusercontent.com` (see R10).
- A10: `offline, pass` for both providers. A 400, a safety block (Gemini `SAFETY`, LiteLLM `content_filter`) and a context-too-long reply each make one attempt and give a plain message that does not quote the provider text.
- A11: `offline, pass` for both providers. A hung call leaves its ledger row `lost`, charged at ceil(bytes / 3) + 4096 tokens, and `tokens_used` includes it. A reply without usage stays `estimated` at its estimate. A connection that never opened is `not_sent` with 0 bytes and 0 tokens.

Contracts and security rules:

- C7: evidenced offline; G11/A1, A4, A7.
- C8: evidenced offline; G11/A2, A3, A9 (G20/A1, local, still planned).
- C15: evidenced offline; G11/A5, A6, A10, A11.
- SB14: evidenced offline; G11/A1.
- SB19: evidenced offline; G11/A5.

Companion skills: none. Skills: adk-engineer 2026.10.28. Primary: adk-operational-guardrails 2026.10.28 (token budgets, runtime bounds). Supporting, all 2026.10.28: adk-tool-auth-and-secrets, adk-model-and-output-contracts (failover-and-providers) and protect-adk-sensitive-data (boundaries: logging, before_model_callback).

Scope and changes outside `touches`:

- `src/truelift/agents/{__init__,gated_model,keys,payload,redaction}.py`, `src/truelift/store/db.py`, `src/truelift/api/app.py`, `src/truelift/__init__.py`, `pyproject.toml`, `uv.lock`.
- `openapi.json` and `frontend/src/client/types.gen.ts` (the 503 on `PUT /setup/key`).
- `tests/conftest.py` (the in-memory keyring), `tests/agents/support.py` and fixtures.
- `docs/architecture/truelift.md`: the Evidence cells of C7, C8 and C15 only.

Rulings (for the designer's checkpoint):

- R1. The gate runs in two places. `before_model_callback` makes the early checks; `GatedLlm`, the model object, runs every check again at the provider boundary on every attempt. This is because ADK 2.12 skips agent callbacks when a plugin's `before_model_callback` answers. Cost if wrong: none, beyond a second cheap check.
- R2. No new `AiState` and no schema field.
  - A rejected key becomes `no_key` with the "rejected" message, and `key_configured: false`, so setup asks for a key.
  - A rate limit after its retries becomes `unavailable` with "AI paused: the provider is limiting requests…".
  - If the UI needs a distinct "key rejected" badge, that is a contract change (`ProviderInfo.key_rejected`) for G16 or G15.
- R3. 5xx and transport errors are retried like a 429: at most 2 retries, all inside the 60 s deadline. Retry delays are 2 s and 6 s. Cost if wrong: up to two more provider attempts per failed call.
- R4. The budget estimate is ceil(request bytes / 3) input tokens plus the reply cap (4096). It is charged in the ledger before the request leaves, and the provider's usage replaces it on the reply. Admission refuses an attempt whose estimate would pass the budget, so the AI pauses a little before the exact limit. A 4xx rejection (400, 401, 403, 429) is recorded with 0 tokens, as providers do not bill it.
- R5. The model's own earlier turns (text, thoughts and function calls) carry no disclosure category. The system instruction is code-owned text: it counts towards the byte cap and has no category. A tool result must carry the `truelift_data` envelope or the call is refused, so G13 and G14 tools return `Payload(...).as_tool_result(...)`.
- R6. The rejected-key flag lives in process memory. It is cleared by saving a new key or by restarting the app.
- R7. The key is fetched from the keychain on every provider attempt and passed only to that attempt's model object (D7 "per call").
- R8. `PUT /setup/key` checks only the key's length, not its format, so a new provider key format is not refused. A wrong key is found by the first call (A4).
- R9. The active provider is the one whose key was saved last (`app_settings`), and otherwise the first configured provider in `models.yaml` order.
- R10. `LITELLM_LOCAL_MODEL_COST_MAP` is forced in `truelift/__init__.py`. A process that imports `litellm` before `truelift` would still fetch the cost map; A9 found this. Every truelift entry point imports `truelift` first.
- R11. The disclosure's example payload for a real project uses the mapping's columns only. Summary statistics and sample rows join when G07 writes the profile.

Specialist controls left out deliberately:

- The agent stream still replays fakes. G13 builds its agent with `gateway.gate(...)`, passes `gateway.run_config()` and maps `gateway_error_for(exc)` to the `ai_status` and `turn_failed` events.
- Currency cost: budgets are in tokens, as C15 says.
- Cross-model failover (D7's fallback choice).
- A key-verification call at save time.
- A ledger page in the UI (D17's screen: G15 shows the stub; the route is real now).
- Scrubbing of library `print()` output (LiteLLM's verbose mode is off by default; A1 checked stdout and stderr).

Human effort still owed: about 1–2 h.

- Review `agents/gated_model.py` (the attempt loop, settle on close and cancel) and `agents/gateway.py:classify_failure`.
- Review rulings R1–R11 and the C16 delta.
- Tell Chloe about R2 (setup states) and the 503 on the key route (#17 G16).
- Optionally, run one live smoke per provider with real keys through the gateway: a few short calls, well under one US cent. G18/A4 owns that live check.

actual: not reported.

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G11-model-gateway-keys-consent-payload-limits-and-bu.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
