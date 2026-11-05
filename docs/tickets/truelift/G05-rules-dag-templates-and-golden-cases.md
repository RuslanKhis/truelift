---
goal: G05
title: Rules, DAG templates and golden cases
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: []
docs: [adk-agent-evaluation/references/deterministic-tests.md]
blocked_by: [G01]
touches: [rules/, templates/, tests/golden/]
parallel_safe: no
contracts: [C3, C2]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 4-6
  review_and_verify: 1-2
  total: 5-8
  handoff: 0.25
  calendar_waits: none
owner: Thao
status: ready
---

# G05 Rules, DAG templates and golden cases

## Outcome

Econometric knowledge is written as data that code enforces and Thao verifies (C3, C2; D3, D18).

## Scope

- In: - `rules/identification.yaml`: minimum weeks, regions and rows; treatment-variation thresholds. - `rules/proxies.yaml`. - `rules/normalisation.yaml`: semantic type → scaler list. - `rules/cate.yaml`: maximum covariates and degree rule. - `templates/*.yaml`: one per business type, in Thao's own words, with nodes, roles, default edges and the slots that confirm each edge. - `tests/golden/*.yaml`: at least 15 cases, each giving a DAG plus mapping and the expected decision, adjustment set and `x_cols`/CATE.
- Route: YAML schemas as in design §5. A small loader with pydantic validation.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 Each threshold in `rules/identification.yaml` has a value and a one-line source or rationale (C3).
- [ ] A2 The templates cover the five business types and validate against the schema (C3).
- [ ] A3 Each proxy rule has a caveat text the UI can show (C3).
- [ ] A4 At least 15 golden cases, including a mediator trap, an unobserved confounder with no proxy, a proxy accepted, a descendant of the treatment, a collider, low variation and a percentage treatment with spend. Each states its expected outcome (C3, C2).
- [ ] A5 CODEOWNERS makes Thao a required reviewer for `rules/`, `templates/` and `src/truelift/causal/` (C3).

Verification, automated: `uv run pytest tests/golden -k schema` exits 0 (offline).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G05-rules-dag-templates-and-golden-cases.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
