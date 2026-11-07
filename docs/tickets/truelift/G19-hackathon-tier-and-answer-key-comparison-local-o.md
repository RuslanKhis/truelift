---
goal: G19
title: Hackathon tier and answer-key comparison (local only)
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: []
docs: [adk-agent-evaluation/references/result-auditing.md]
blocked_by: [G18]
touches: [tests/private/]
parallel_safe: no
contracts: [C14, C13]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2, G01/A3, G18/A1]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 1-1.5
  total: 4-6.5
  handoff: 0.5
  calendar_waits: none
owner: Thao            # suggested owner; anyone may pick this ticket
status: proposed
---

# G19 Hackathon tier and answer-key comparison (local only)

## Outcome

The agent-built config is proven on the private dataset, and its differences from the expert answer are explained, with nothing leaking (C14, C13).

## Scope

- In: `tests/private/` reads `private/benchmark.yaml`, which points to the CSV, the persona, `answer_key.yaml` (written by Thao from the notebook, stored privately) and the truth column prefix.
- Route: `tests/private/` reads `private/benchmark.yaml`, which points to the CSV, the persona, `answer_key.yaml` (written by Thao from the notebook, stored privately) and the truth column prefix.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 Five repetitions on a core developer's machine: the CI covers 2.50 in 5/5 and the median point estimate is within ±25%, or a shortfall is recorded with a diagnosis comparing it with the expert's 1.64 (C14).
- [ ] A2 `private/answer-key-comparison.md` explains every difference between the agent and the expert in `x_cols`, CATE covariates and normalisation. This plan's evidence records only the number of differences and whether C14 passed; the numbers stay in `private/` (C13).
- [ ] A3 The guard and gitleaks are clean on the branch, and `git status` shows nothing under `private/` tracked (C13).

Verification, automated: `uv run pytest -m private` exits 0 on a core developer's machine with `private/benchmark.yaml` present (local only); `make check` exits 0.
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G19-hackathon-tier-and-answer-key-comparison-local-o.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
