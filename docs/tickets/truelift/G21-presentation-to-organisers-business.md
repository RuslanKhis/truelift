---
goal: G21
title: Presentation to organisers: business
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-presenter
supporting_skills: []
docs: [adk-presenter/references/stage-outlines.md, adk-presenter/references/audiences-and-questions.md]
blocked_by: [G19, G20]
touches: [docs/presentations/truelift-organisers-business.md]
parallel_safe: no
contracts: [C14]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: []
phase: 1
type: presentation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 0.5-1
  total: 3.5-6
  handoff: 0.5
  calendar_waits: none
owner: Chloe            # suggested owner; anyone may pick this ticket
status: ready
---

# G21 Presentation to organisers: business

## Outcome

The organisers understand what a CMO gets, see the demo, and see the benchmark evidence (C14).

Owner note: Chloe prepares; Ruslan presenting is still to be confirmed.

## Scope

- In: 
- Route: see design
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The outline passes the presenter's deck check, and every claim cites evidence recorded in this plan (G10, G18, G19, G20) (C14).
- [ ] A2 One rehearsal is held. No private material appears in the slides; only the allowed numbers do (C14).

Verification, automated: The presenter's deck check passes on the outline. Manual: one rehearsal with Ruslan and Thao.
Verification, manual: see above.

## Evidence

## Run this ticket

```text
/adk-presenter Prepare G21 from docs/tickets/truelift/G21-presentation-to-organisers-business.md (audience: hackathon organisers). Cite only evidence recorded in the tickets and the plan.
```
