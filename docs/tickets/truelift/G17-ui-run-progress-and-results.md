---
goal: G17
title: UI: run progress and results
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-frontend-integration
supporting_skills: []
docs: [adk-frontend-integration/references/agent-ui-states.md]
blocked_by: [G16, G09, G10]
touches: [frontend/src/routes/runs/, frontend/src/routes/results/]
parallel_safe: no
contracts: [C5, C6, C10]
companion_skills: [shadcn]
security: [SB10]
design_system: docs/design/DESIGN.md
contract_deltas: []
pass_to_pass: [G15/A5, G16/A5]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 6-8.5
  review_and_verify: 1-2
  total: 7-10.5
  handoff: 0.5
  calendar_waits: none
owner: Chloe            # suggested owner; anyone may pick this ticket
status: proposed
---

# G17 UI: run progress and results

## Outcome

The user sees honest progress and a results page where the numbers come from code and the narrative is labelled and cited (C5, C6, C10).

## Scope

- In: the run page (phase bar, polling, cancel), the results page (digest tiles, breakdowns, labelled narrative from a fixture), the egress-ledger page (D17) and the budget view with its change control (C15).
- Out: the live Explainer; the narrative renders from a `Narrative` fixture, and G20 connects the live agent.
- Route: see design
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The run page shows the phase bar, elapsed and expected time, and a cancel button. A refresh reattaches through 2-second polling (C10).
- [ ] A2 Interrupted and failed runs show the reason and a re-run button, and never show numbers (C10).
- [ ] A3 Tiles come from the digest: ROI, CI, verdict against the threshold, break-even margin, and warnings beside the number (C6).
- [ ] A4 A scripted narrative containing an image tag with an `onerror` handler, a `javascript:` link and an image from an unlisted host renders inert and loads nothing (SB10).
- [ ] A5 Each statement shows its label and a citation that links to the finding (C5).
- [ ] A6 The ledger page lists each model call's categories, bytes and tokens with no content, and the budget view shows use against the limit and lets the user change it (C8, C15).

Verification, automated: `npm --prefix frontend run test` exits 0 with digest and Narrative fixtures (local).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G17-ui-run-progress-and-results.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
