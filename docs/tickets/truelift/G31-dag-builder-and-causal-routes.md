---
goal: G31
title: DAG builder and causal API routes
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-workflow-design
supporting_skills: [adk-fastapi-backend]
docs: []
blocked_by: [G06, G08]
touches: [src/truelift/causal/build.py, src/truelift/api/routes/dag.py, src/truelift/api/routes/results.py, tests/causal/test_build.py, tests/api/test_dag_routes.py]
parallel_safe: no
contracts: [C1, C3]
companion_skills: [fastapi]
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G06/A1, G08/A1]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 1.5-3
  review_and_verify: 0.5-1
  total: 2-4
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: proposed
---

# G31 DAG builder and causal API routes

## Outcome

Confirmed facts plus a business-type template become a DAG version in code, and the real DAG, identification and results routes replace the G02 stubs (C1, C3; D3, D5). Added after the independent plan review, 2026-11-07.

## Scope

- In: `causal/build.py` applies confirmed facts from the G08 store to a G05 template as edge assertions and node mappings, marking unsupported edges `assumed` (design §5, "DAG construction"). Routes for DAG versions, identification results and the run digest replace the G02 stubs.
- Out: the interviewer (G13) and the narrative (G14).
- Route: `causal/build.py` called by the store's confirm route; `api/routes/dag.py` and `api/routes/results.py`.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 Building from the same facts and template gives a byte-identical `dag/vN.yaml`; each edge cites its supporting fact ID or is marked `assumed` (C3).
- [ ] A2 An edge cannot appear without a confirmed fact or a template default; a rejected proposal changes nothing in the built DAG (C1, C3).
- [ ] A3 The DAG and identification routes return the current version and its block reasons in business words; the results route serves the digest, and each matches the generated client with no drift (C3).

Verification, automated: `uv run pytest tests/causal/test_build.py tests/api/test_dag_routes.py` exits 0 (offline).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G31-dag-builder-and-causal-routes.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
