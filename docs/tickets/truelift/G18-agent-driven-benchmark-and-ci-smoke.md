---
goal: G18
title: Agent-driven benchmark and CI smoke
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: [adk-release-engineering (CI gate)]
docs: [adk-agent-evaluation/references/live-evaluations.md, adk-release-engineering/references/ci-eval-gates.md]
blocked_by: [G13, G10]
touches: [src/truelift/bench/harness.py, .github/workflows/bench.yml, tests/bench/]
parallel_safe: no
contracts: [C14, C2]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G06/A3, G10/A4, G13/A2]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 1-2
  total: 4-7
  handoff: 0.5
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: proposed
---

# G18 Agent-driven benchmark and CI smoke

## Outcome

The whole agent-built path is scored against the truth on every PR (smoke) and at the milestone (full tier) (C14, C2; D15, D16).

## Scope

- In: `bench/harness.py` runs the persona through the real Interviewer, then the store, `identify`, `compile`, the worker, the digest and the scorer. A CI job runs on GitHub Actions with Python 3.12 and Quick mode.
- Route: `bench/harness.py` runs the persona through the real Interviewer, then the store, `identify`, `compile`, the worker, the digest and the scorer. A CI job runs on GitHub Actions with Python 3.12 and Quick mode.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 `truelift bench --persona data/sample/persona_cmo.yaml --seed 1 --replay` runs on every PR in under 20 minutes and fails the build on a scorer regression or a config mismatch (C14).
- [ ] A2 Synthetic tier with the **agent-built** config (Standard, 20 seeds): coverage ≥ 80% and median |error| ≤ 20%, or a recorded shortfall (C14).
- [ ] A3 The agent-built config equals the persona's golden config as canonical JSON, on replay and on one live Gemini run (C2).
- [ ] A4 One live Gemini and one live Claude persona run, each under a 60-call cap. Recordings are refreshed and the cost is recorded against the $20/month budget (C14).

Verification, automated: `uv run truelift bench --persona data/sample/persona_cmo.yaml --seed 1 --replay` exits 0 in CI (offline); full tier run locally; live runs under cap (authorised live).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G18-agent-driven-benchmark-and-ci-smoke.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
