---
goal: G02
title: API skeleton, localhost auth, stream contract and generated client
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-fastapi-backend
supporting_skills: [adk-frontend-integration (stream event schema)]
docs: [adk-fastapi-backend/references/identity.md, adk-fastapi-backend/references/contract-and-client.md, adk-frontend-integration/references/json-api.md]
blocked_by: [G01]
touches: [src/truelift/api/, src/truelift/cli.py, frontend/src/client/, openapi.json, tests/api/]
parallel_safe: no
contracts: [C16, C15]
companion_skills: [fastapi]
security: [SB01, SB02, SB05, SB06, SB07, SB08, SB09, SB13]
design_system: none
contract_deltas: []
pass_to_pass: [G01/A1, G01/A2]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 2-3
  review_and_verify: 1-2
  total: 3-5
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: verified_local
---

# G02 API skeleton, localhost auth, stream contract and generated client

## Outcome

Chloe can build every screen against a real, authenticated API, a fake agent stream and a typed client (C16, C15; D12).

## Scope

- In: FastAPI app factory; `truelift` CLI launcher (free port, token, browser open); auth, Host and Origin middleware; error handler; security headers; stub routes with fake data for projects, upload, mapping, proposals, DAG, identification, runs and results; the agent stream event schema (SSE over `fetch`) with a fake replay stream; OpenAPI dump; `@hey-api/openapi-ts` client generation; drift check. Real handlers arrive in G07–G14.
- Route: `src/truelift/api/{app,auth,errors}.py`. The ADK Runner is used in process only from G13. `get_fast_api_app` is never mounted.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [x] A1 With no token or a wrong token, every `/api` route returns 401. The SPA assets and `/health` stay public (C16, SB01).
- [x] A2 The token is accepted only from the `Authorization` header. A token in a query string is rejected. The launch URL carries it only in the fragment (C16, SB02, SB08).
- [x] A3 A wrong `Host` returns 403. A foreign `Origin` on POST, PUT or DELETE returns 403. No CORS headers are emitted (C16, SB06).
- [x] A4 `/run`, `/run_sse`, `/apps/...` and `/list-apps` return the SPA shell or 404 and cause no model call (SB05).
- [x] A5 `nosniff`, a CSP with `default-src 'self'` and `frame-ancestors 'none'` are present. `/docs` and `/openapi.json` are served only with `TRUELIFT_DEV=1` (SB07).
- [x] A6 Oversize or malformed bodies return 413 or 422. A forced exception or a database error returns a generic 500 with a request ID and no stack trace (SB09, SB13).
- [x] A7 A second concurrent agent message on the same project returns 409, so a double send cannot double model spend (C15).
- [x] A8 `make check` regenerates the client from the offline OpenAPI dump and fails on drift. The fake stream replays a recorded event file (floor)

Verification, automated: `uv run pytest tests/api` exits 0; `make check` exits 0 with no client drift (offline).
Verification, manual: none.

## Evidence

Run on 2026-11-07, macOS (darwin 22.3.0, arm64), CPython 3.12.16, Node 22.23.3, npm 10.9.9. Branch `g02-api-skeleton`, changes uncommitted.

Locked versions: google-adk 2.12.0, fastapi 0.141.1, starlette 1.10.0, pydantic 2.14.3, uvicorn 0.54.0, python-multipart 0.0.33, httpx 0.28.1 (dev); `@hey-api/openapi-ts` 0.99.0, typescript 5.9.3, js-yaml 4.3.2 (override).

Commands and results:
- `uv run --locked pytest tests/api`: local, pass (105 tests). Full suite in `make check`: 148 passed, 1 skipped (`private materials absent`).
- `make check`: local, pass, exit 0. Guard clean (100 files), ruff clean, `client-check: no drift`, pip-audit "No known vulnerabilities found, 1 ignored" (see Rulings), npm audit "found 0 vulnerabilities".
- `make dist`: local, pass. Guard `--dist` clean (77 package members).
- pass_to_pass G01/A1, G01/A2 (`tests/test_guard.py`): offline, pass before and after the change (43 passed, 1 skipped before).
- Launcher smoke, `uv run truelift --no-browser`: local, pass. It listened on `127.0.0.1:<free port>` only (lsof). `/health` 200, `/api/projects` 401 without the token and 200 with it, `Host: evil.example` 403, `/` shell 200, SSE replay gave 12 frames. The token appeared once in the output, in the printed link.
- `gitleaks dir`: 5 hits, all in the ignored `tests/__pycache__/test_guard…pyc` (G01's fake keys, constant-folded). None are in a tracked or new file. The CI git scan does not read ignored files.

Acceptance:
- A1: local, pass. `test_auth.py::test_every_api_route_rejects_missing_token` and `…wrong_token` cover all 27 documented `/api` operations, the stream route and the `/api` catch-all, for every method. `test_no_token_configured_fails_closed`. `test_health_and_spa_are_public` covers `/health`, the shell, a client route, an asset, a missing asset (404) and a traversal attempt (404).
- A2: local, pass. `test_token_in_query_rejected_even_with_header` (4 forms, 401 `token_in_query`), `test_malformed_authorization_rejected` (5 forms), `test_launch_url_has_token_only_in_fragment`, `test_token_never_in_responses`.
- A3: local, pass. `test_wrong_host_is_403_everywhere` (5 hosts × 3 paths), `test_foreign_or_missing_origin_on_unsafe_method_is_403` (4 methods × 4 origins, including `null` and missing), `test_no_cors_headers_on_preflight_or_reads`, and `no_cors_headers` asserted on every 401 in A1.
- A4: local (mocked), pass. `test_adk_paths_return_shell_or_404_and_no_model_call`: 8 ADK paths × GET (HTML and JSON Accept) give the shell or 404; POST gives a JSON 404, also under `/api`. `Runner.run_async` and `Runner.run` are patched to count calls: 0 calls. `test_adk_server_never_mounted`: `google.adk.cli.fast_api` is not imported and no ADK path is in the schema.
- A5: local, pass. `test_security_headers_everywhere` (5 paths: `nosniff`, a CSP with `default-src 'self'` and `frame-ancestors 'none'`, `no-referrer`, `DENY`, and `no-store` on `/api`). `test_docs_and_schema_not_served_by_default`. `test_docs_and_schema_served_with_truelift_dev`.
- A6: local, pass. 413 for an oversize body with Content-Length, a chunked body without it, and an upload over its cap. 422 or 404 for 9 malformed inputs. `test_validation_error_does_not_echo_input`. `test_unexpected_error_is_generic_500_with_request_id` for a RuntimeError and a `sqlite3.OperationalError`: generic body, the request ID equals `X-Request-ID`, and no traceback, SQL or path appears.
- A7: local, pass. `test_concurrent_second_send_is_409_over_real_socket` (a real uvicorn server on loopback: the second send during an open stream gets 409 `agent_busy`, the first turn completes, and a third send gets 200). `test_client_disconnect_releases_admission`. `test_second_message_while_busy_is_409`.
- A8: local, pass. `make check` → `client-check` dumps `openapi.json` offline into `build/contract/`, regenerates the client there and diffs both against the committed copies. `test_committed_openapi_matches_code`. `test_dump_needs_no_network` (`socket.connect` refused). `test_recordings_are_valid` and `test_stream_replays_recording` (4 recorded files replayed; each event validates against `AgentEvent`; order and `seq` are checked).

Contracts and security rules:
- C16: evidenced, local; G02/A1–A3 (plus A5, A6). The loopback bind is checked by `test_bind_loopback_only` and the launcher smoke.
- C15: evidenced, local; G02/A7 (one agent message at a time per project). The budget and `max_llm_calls` parts stay with G11/A5.
- SB01: evidenced, local; A1 (`/api` routes, Build: launch token, fail closed).
- SB02: evidenced, local; A2 (identity, Minimal: launch token, not an IdP).
- SB05: evidenced, local; A4 (ADK runtime: Runner patched to count calls, so the "no model call" half is local (mocked)).
- SB06: evidenced, local; A3 (no CORS, Host and Origin checks).
- SB07: evidenced, local; A5 (`nosniff`, CSP, `frame-ancestors`; docs only in dev).
- SB08: evidenced, local; A2 (bearer only in the header; token only in the launch fragment).
- SB09: evidenced, local; A6 (body caps, bounded and strict models).
- SB13: evidenced, local; A6 (generic 500 with a request ID).

Companion skills loaded: `fastapi` from the FastAPI 0.141.1 wheel (`fastapi/.agents/skills/fastapi`, SKILL.md and `references/streaming.md`). Specialists: `adk-fastapi-backend` 2026.10.28, which matches `adk-engineer`. Supporting skill: `adk-frontend-integration` (json-api, agent-ui-states). The other companion pins were resolved and written to AGENTS.md; this ticket did not load them.

What was built:
- `src/truelift/api/`: `app.py` (factory, middleware order, `/api` router behind the token, OpenAPI with stream event components); `auth.py` (Host, Origin and token-in-URL middleware; bearer dependency); `errors.py` (`ErrorBody`, request ID, handlers); `middleware.py` (headers, body caps); `spa.py`; `settings.py`; `schemas.py`; `stream.py`; `fakes.py`; `routes/{projects,setup,intake,dag,runs,results,agent}.py`; `fixtures/agent_*.jsonl`; `openapi_dump.py`.
- `src/truelift/cli.py`: the `truelift` entry point.
- `openapi.json`; `frontend/{package.json,package-lock.json,openapi-ts.config.ts,src/client/}`.
- `tests/api/`; `tests/__init__.py`.
- `Makefile` (`client`, `client-check`, npm audit); `.github/workflows/ci.yml` (setup-node pinned by SHA); `pyproject.toml`, `uv.lock`; the AGENTS.md companion table and API contract notes; the plan's companion section now links to AGENTS.md.

Rulings (what, why, cost if wrong):
- R1 **Audit exception (accepted by Ruslan, 2026-11-07).** `--ignore-vuln CVE-2026-114603` (GHSA-xcq7-p3pf-p88h, medium: unbounded tracestate parsing in opentelemetry-api ≤ 1.45.0). google-adk 2.12.0 caps opentelemetry-api at ≤ 1.42.1. Only google-adk 2.14.0 (released 2026-11-07) allows the fix, and moving the ADK pin is a release-unit decision. Nothing in G02 extracts W3C trace context from requests. If wrong: a local DoS through a crafted trace header, and it can only be reached with the token. Remove the exception when ADK moves to 2.14 or later.
- R2 (accepted by Ruslan, 2026-11-07) A state-changing request with **no** `Origin` header is refused (403), not only a foreign one. This is the literal reading of C16, "require a same-origin Origin". Browsers send `Origin` on same-origin POST. If wrong: a non-browser client must set `Origin`; tests do.
- R3 The agent stream route is kept out of the OpenAPI paths. `AgentEvent` and its 9 members are added to the components, so the client exports their types and no generated SSE helper retries a non-idempotent send. If wrong: G16 writes its own `fetch` reader, which it planned to do anyway.
- R4 Stub scope widened. Beyond the routes listed in Scope, G02 also stubs setup, key, disclosure, consent, usage, budget and ledger, because G15 (A2, A6) and G17 (A6) build against the stub API and are not blocked by G11. G11 replaces them.
- R5 G02 creates `frontend/package.json` and `package-lock.json` (the openapi-ts and typescript pins, plus the `js-yaml` 4.3.2 override for three high advisories). G15 lists these paths in `touches` and extends them.
- R6 Dev mode only: `TRUELIFT_DEV_ORIGINS` adds Vite's origin and host to the allowlists, so the Vite dev server can proxy `/api`. It is ignored unless `TRUELIFT_DEV=1`.

Deferred, with trigger:
- oasdiff breaking-change check: needs `openapi.json` on main as the base. Add it in CI after this merges (G07 or a small follow-up).
- Schemathesis over the non-agent routes: when the G07/G08 handlers replace the stubs.
- HSTS: n/a (plain HTTP on loopback).
- SB14 security logging: G11.
- The real `fetch` and SSE client in a browser: G15 and G16.

Findings for other tickets:
- `.gitignore` has `runs/`, which also ignores `frontend/src/routes/runs/` (G17 `touches`). Anchor it to `/runs/` or `/projects/*/runs/` before G17.
- Starlette 1.10 warns that `httpx` with its test client is deprecated in favour of `httpx2`. The tests pass on httpx 0.28.1; the warning is recorded and the client is not changed.

Estimate check: within 3–5 h. No new ticket needed.

Human effort still owed (about 1–1.5 h review):
- Read `auth.py`, `middleware.py`, `errors.py` and `stream.py`.
- Walk Chloe through the stream contract and the fake triggers.
- Confirm that CI passes with setup-node on the PR. `.github/` is a code-owner path.

manual: none listed.
actual: 0.5 h (Ruslan, reported 2026-11-07)

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G02-api-skeleton-localhost-auth-stream-contract-and.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
