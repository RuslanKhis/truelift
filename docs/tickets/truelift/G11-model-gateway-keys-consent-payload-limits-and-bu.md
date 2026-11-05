---
goal: G11
title: Model gateway: keys, consent, payload limits and budget
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-operational-guardrails
supporting_skills: [adk-tool-auth-and-secrets (key storage), adk-model-and-output-contracts (model IDs), protect-adk-sensitive-data (payload projection)]
docs: [adk-operational-guardrails/references/token-budgets.md, adk-operational-guardrails/references/runtime-bounds.md]
blocked_by: [G02, G03]
touches: [src/truelift/agents/gateway.py, src/truelift/models.yaml, src/truelift/api/routes/setup.py, tests/agents/test_gateway.py]
parallel_safe: no
contracts: [C7, C8, C15]
companion_skills: []
security: [SB14, SB19]
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2, G02/A1, G02/A7]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 1-2
  total: 4-7
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: ready
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

Verification, automated: `uv run pytest tests/agents/test_gateway.py` exits 0 on recorded replies (offline).
Verification, manual: none.

## Evidence

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
