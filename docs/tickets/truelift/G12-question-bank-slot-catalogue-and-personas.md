---
goal: G12
title: Question bank, slot catalogue and personas
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-instructions
supporting_skills: [adk-agent-evaluation (personas)]
docs: [adk-agent-instructions/references/exemplars.md, adk-agent-instructions/references/instruction-vs-code.md]
blocked_by: [G05]
touches: [templates/slots.yaml, data/sample/persona_cmo.yaml, data/sample/personas/]
parallel_safe: no
contracts: [C3, C11, C14, C13]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2, G05/A2]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 4-6
  review_and_verify: 1-2
  total: 5-8
  handoff: none
  calendar_waits: none
owner: Thao
status: ready
---

# G12 Question bank, slot catalogue and personas

## Outcome

The interview's content, meaning that each slot and what it establishes in the DAG, is defined by the econometrician and testable with personas (C3, C11, C14, C13; D5, D18).

## Scope

- In: `templates/slots.yaml` (modules 1–8 from design §5, each slot with its DAG meaning, whether it is required, its unknown policy and two to three example phrasings that are not leading); `data/sample/persona_cmo.yaml` (answers for the synthetic market); three difficult variants (says "I don't know", contradicts an earlier answer, names a confounder that has no data); the hackathon persona written **only** in `private/`.
- Route: see design
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 Every template edge is confirmable by at least one slot, and every slot names its DAG effect (C3).
- [ ] A2 Each slot has phrasing guidance: an open question first, balanced options including "not sure", and no hint about which answer passes (C11).
- [ ] A3 The synthetic persona answers every required slot. The hackathon persona exists only under `private/`, and the guard passes (C14, C13).
- [ ] A4 The three difficult variants exist with their expected outcomes: unknown → assumed and shown; contradiction → choice card; missing confounder → block with options (C11).

Verification, automated: `uv run pytest tests/golden -k slots` exits 0 (offline); `make check` exits 0. Manual: Ruslan reads the phrasing guidance for leading questions.
Verification, manual: see above.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G12-question-bank-slot-catalogue-and-personas.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
