---
goal: G20
title: End-to-end journey and demo script
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: []
docs: [adk-frontend-integration/references/demo-readiness.md]
blocked_by: [G17, G18, G14, G13]
touches: [frontend/e2e/, scripts/demo/]
parallel_safe: no
contracts: [C1, C5, C6, C8, C10]
companion_skills: [playwright-cli]
security: []
design_system: docs/design/DESIGN.md
contract_deltas: []
pass_to_pass: [G09/A3, G13/A2, G14/A3, G17/A4]
phase: 1
type: journey
profile: MVP or pilot
estimate:
  hands_on: 3-4
  review_and_verify: 1-1.5
  total: 4-5.5
  handoff: 0.5
  calendar_waits: none
owner: Chloe
status: ready
---

# G20 End-to-end journey and demo script

## Outcome

The design §2 journey runs in a real browser against the real API, the agents and the worker, with the model replaced by recordings (C1, C5, C6, C8, C10).

## Scope

- In: 
- Route: see design
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 A Playwright journey on synthetic seed 1 covers setup → consent → upload → mapping → scripted interview → edge cards → identification → Quick run → results with a labelled narrative (C1, C5, C6, C8).
- [ ] A2 A refresh during the run reattaches. Killing the backend shows `interrupted` after restart (C10).
- [ ] A3 `make demo-reset && make demo-replay` reproduces the golden path with no live model calls. Screenshots come from the current build (floor)
- [ ] A4 Every earlier goal's offline suite passes on the same commit (floor)

Verification, automated: `make e2e` exits 0 against the real API with recorded model replies (local).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G20-end-to-end-journey-and-demo-script.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
