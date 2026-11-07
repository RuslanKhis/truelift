---
goal: G06
title: Causal core: DAG, identification and config compiler
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-workflow-design
supporting_skills: []
docs: [adk-workflow-design/references/validation.md]
blocked_by: [G03, G05]
touches: [.github/workflows/ci.yml, src/truelift/causal/, tests/causal/]
parallel_safe: no
contracts: [C2, C3, C4]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2, G05/A4]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 4-6
  review_and_verify: 1-2
  total: 5-8
  handoff: 0.5
  calendar_waits: Thao's code-owner review (D18)
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: proposed
---

# G06 Causal core: DAG, identification and config compiler

## Outcome

A pure, tested library turns a DAG plus mapping into an identification verdict and a pipeline config (C2, C3, C4; D3).

## Scope

- In: - `causal/dag.py`: pydantic models with a YAML round trip and networkx. - `identify.py`: descendants of the treatment; backdoor check via `networkx` d-separation on the graph with the treatment's out-edges removed; unobserved nodes on open paths; rule thresholds. - `compile.py`: the table in design §5, producing `PipelineConfig` as canonical JSON with sorted keys. - `forbidden.py`: the deny-list. It holds the truth prefix only base64-encoded, like the guard, and a test asserts the two encoded constants are equal (D13, revised 2026-11-07).
- Route: - `causal/dag.py`: pydantic models with a YAML round trip and networkx. - `identify.py`: descendants of the treatment; backdoor check via `networkx` d-separation on the graph with the treatment's out-edges removed; unobserved nodes on open paths; rule thresholds. - `compile.py`: the table in design §5, producing `PipelineConfig` as canonical JSON with sorted keys. - `forbidden.py`: the deny-list, holding the prefix only encoded (D13).
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 A DAG YAML round-trips byte-identically. A cycle is rejected with a message (C3).
- [ ] A2 All golden cases from G05 pass, and every block reason is a business-language sentence naming the missing item (C3).
- [ ] A3 The same inputs give a byte-identical config JSON in two processes and on two OSes (CI matrix). Changing a fact the DAG does not use leaves the config unchanged (C2).
- [ ] A4 A Hypothesis property test over random DAGs finds no descendant of the treatment, no outcome and no forbidden column in `x_cols` or the CATE covariates (C3, C4).
- [ ] A5 A percentage treatment yields `treatment_types='percentage'` plus `sales_col` and the spend column. A margin of 0.4 gives `opt_threshold_roi=2.5` (C2).
- [ ] A6 The compiled config constructs `CausalWorkflowOrchestrator` and `CausalDataScaler` without fitting, using the G03 parameter names (C2).

Verification, automated: `uv run pytest tests/causal tests/golden` exits 0 on macOS and Linux CI (offline).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G06-causal-core-dag-identification-and-config-compil.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
