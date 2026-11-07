---
goal: G14
title: Explainer agent with grounded narrative
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-model-and-output-contracts
supporting_skills: [adk-agent-instructions (prompt)]
docs: [adk-model-and-output-contracts/references/validation-and-repair.md, adk-model-and-output-contracts/references/output-contracts.md]
blocked_by: [G10, G11]
touches: [src/truelift/agents/explainer.py, src/truelift/prompts/explainer.md, src/truelift/explain/validate.py, src/truelift/explain/template.py, tests/explain/test_validate.py]
parallel_safe: no
contracts: [C5, C6]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G10/A1, G10/A2, G11/A3]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 1-2
  total: 4-7
  handoff: 0.5
  calendar_waits: Thao's review (G14/A5)
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: proposed
---

# G14 Explainer agent with grounded narrative

## Outcome

Plain-language explanations in which every statement is labelled, cited and number-checked (C5, C6; D2, D10).

## Scope

- In: An `LlmAgent` in `agents/explainer.py` with `get_findings` and `output_schema=Narrative`. `explain/validate.py` and `explain/template.py`. Label and verdict wording adapted from the pipeline's `causal-insights` skill (Apache-2.0), with attribution in `NOTICE`.
- Route: An `LlmAgent` in `agents/explainer.py` with `get_findings` and `output_schema=Narrative`. `explain/validate.py` and `explain/template.py`. Label and verdict wording adapted from the pipeline's `causal-insights` skill (Apache-2.0), with attribution in `NOTICE`.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The agent has only `get_findings` and the `Narrative` schema (C5).
- [ ] A2 The validator enforces one label per statement, at least one valid finding ID, numbers matching the cited values after rounding, and a verification step on each hypothesis (C5).
- [ ] A3 Each scripted bad output (prose, fenced JSON, unknown finding ID, invented number) triggers one repair attempt, then the template narrative with a note (C5).
- [ ] A4 A recommendation to cut or increase on an undetermined segment is rejected, and verdict words must match the computed verdict (C6).
- [ ] A5 Thao reviews ten statements from a synthetic run and finds no econometric misstatement; the review is recorded (C5).

Verification, automated: `uv run pytest tests/explain/test_validate.py` exits 0 on scripted outputs (offline). Manual: Thao reviews ten statements (A5).
Verification, manual: see above.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G14-explainer-agent-with-grounded-narrative.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
