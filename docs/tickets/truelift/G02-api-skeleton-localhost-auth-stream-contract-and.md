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
status: ready
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

- [ ] A1 With no token or a wrong token, every `/api` route returns 401. The SPA assets and `/health` stay public (C16, SB01).
- [ ] A2 The token is accepted only from the `Authorization` header. A token in a query string is rejected. The launch URL carries it only in the fragment (C16, SB02, SB08).
- [ ] A3 A wrong `Host` returns 403. A foreign `Origin` on POST, PUT or DELETE returns 403. No CORS headers are emitted (C16, SB06).
- [ ] A4 `/run`, `/run_sse`, `/apps/...` and `/list-apps` return the SPA shell or 404 and cause no model call (SB05).
- [ ] A5 `nosniff`, a CSP with `default-src 'self'` and `frame-ancestors 'none'` are present. `/docs` and `/openapi.json` are served only with `TRUELIFT_DEV=1` (SB07).
- [ ] A6 Oversize or malformed bodies return 413 or 422. A forced exception or a database error returns a generic 500 with a request ID and no stack trace (SB09, SB13).
- [ ] A7 A second concurrent agent message on the same project returns 409, so a double send cannot double model spend (C15).
- [ ] A8 `make check` regenerates the client from the offline OpenAPI dump and fails on drift. The fake stream replays a recorded event file (floor)

Verification, automated: `uv run pytest tests/api` exits 0; `make check` exits 0 with no client drift (offline).
Verification, manual: none.

## Evidence

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
