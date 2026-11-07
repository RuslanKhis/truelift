---
goal: G15
title: UI: shell, setup and consent, upload and mapping
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-frontend-integration
supporting_skills: []
docs: [adk-frontend-integration/references/frontend-quality.md]
blocked_by: [G02]
touches: [frontend/src/app/, frontend/src/routes/setup/, frontend/src/routes/data/, frontend/package.json, frontend/package-lock.json, docs/design/DESIGN.md]
parallel_safe: no
contracts: [C7, C8, C12]
companion_skills: [react-router, vercel-react-best-practices, shadcn]
security: [SB10]
design_system: docs/design/DESIGN.md
contract_deltas: []
pass_to_pass: [G02/A8]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 5-7
  review_and_verify: 1-2
  total: 6-9
  handoff: 0.5
  calendar_waits: none
owner: Chloe            # suggested owner; anyone may pick this ticket
status: proposed
---

# G15 UI: shell, setup and consent, upload and mapping

## Outcome

A CMO can set up a key, see exactly what will be shared, upload data and confirm a valid mapping (C7, C8, C12; D17).

## Scope

- In: Vite, React and TS SPA in `frontend/`, with React Router in data mode and TanStack Query over the generated client. House `DESIGN.md` copied to `docs/design/DESIGN.md`. Launch-token handling (fragment → `sessionStorage` → header).
- Route: Vite, React and TS SPA in `frontend/`, with React Router in data mode and TanStack Query over the generated client. House `DESIGN.md` copied to `docs/design/DESIGN.md`. Launch-token handling (fragment → `sessionStorage` → header).
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The app shell renders with the house theme and no default shadcn tokens. All calls go through the generated client (C12).
- [ ] A2 Setup: choose a provider; the key is sent once to the backend and never kept in browser storage; the disclosure screen renders the example payload the stub API returns for the uploaded file; consent is recorded (C8, C7). The real payload is checked in G20/A1.
- [ ] A3 Upload shows progress, and every rejection reason in the stub API's error contract appears in plain language (C12). G20/A1 checks real G07 reasons.
- [ ] A4 Mapping review shows each column's role and the stub's per-role validation errors inline; Confirm stays disabled until every role is valid (C12).
- [ ] A6 The "AI unavailable" and "AI paused: budget reached" banners render from the stub stream's events, and the deterministic screens stay usable (C15).
- [ ] A5 All server text renders as text (SB10).

Verification, automated: `npm --prefix frontend run test` and `npm --prefix frontend run build` exit 0 against the G02 stub API (local).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G15-ui-shell-setup-and-consent-upload-and-mapping.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
