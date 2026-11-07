---
goal: G22
title: Presentation to organisers: technical
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-presenter
supporting_skills: []
docs: [adk-presenter/references/stage-outlines.md, adk-presenter/references/audiences-and-questions.md]
blocked_by: [G19, G20]
touches: [docs/presentations/truelift-organisers-technical.md]
parallel_safe: no
contracts: [C14, C3]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: []
phase: 1
type: presentation
profile: MVP or pilot
estimate:
  hands_on: 2.5-4
  review_and_verify: 0.5-1
  total: 3-5
  handoff: 0.5
  calendar_waits: none
owner: Thao            # suggested owner; anyone may pick this ticket
status: proposed
---

# G22 Presentation to organisers: technical

## Outcome

The organisers can judge the econometric soundness: identification rules, compiler mapping, benchmark design and the answer-key outcome (C14, C3).

## Scope

- In: the technical deck outline for the organisers: identification rules, compiler mapping, benchmark design and the answer-key outcome as counts and allowed numbers.
- Route: see design
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The outline passes the deck check, and every claim cites plan evidence (C14).
- [ ] A2 The answer-key comparison is presented only as counts and the allowed numbers (C3).

Verification, automated: The presenter's deck check passes on the outline. Manual: Ruslan checks it for private material.
Verification, manual: see above.

## Evidence

## Run this ticket

```text
/adk-presenter Prepare G22 from docs/tickets/truelift/G22-presentation-to-organisers-technical.md (audience: hackathon organisers). Cite only evidence recorded in the tickets and the plan.
```
