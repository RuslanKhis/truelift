---
goal: G04
title: Synthetic market generator and truth
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: []
docs: [adk-agent-evaluation/references/evaluation-design.md]
blocked_by: [G01]
touches: [src/truelift/sample/, data/sample/, tests/sample/]
parallel_safe: no
contracts: [C14, C4, C3]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2, G01/A6]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 5-8
  review_and_verify: 1-2
  total: 6-10
  handoff: 0.25
  calendar_waits: none
owner: Thao            # suggested owner; anyone may pick this ticket
status: ready
---

# G04 Synthetic market generator and truth

## Outcome

A public panel with known truth and built-in traps powers the quickstart, CI and coverage measurement (C14, C4, C3; D14).

## Scope

- In: `truelift.sample` generator (fictional market, 8 regions × 156 weeks, one category), `truth.yaml`, seed-1 sample committed under `data/sample/`, `data/sample/README.md` describing the data-generating process in prose. Excluded: personas (G12).
- Route: NumPy generator with a seed. Truth columns named `truth_*`. Generator switches for the unobserved confounder and for heterogeneity.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 `python -m truelift.sample generate --seed N --out DIR` writes the panel and `truth.yaml`. The same seed gives an identical sha256 (C14).
- [ ] A2 True ROI recomputed from the truth columns equals the generator's analytic value within 1e-6 (C14).
- [ ] A3 The README records these numbers: naive OLS of sales on discount is biased by more than 30%, and adding the mediator to the controls biases the estimate (C3).
- [ ] A4 Every truth column is listed in `truth.yaml` and uses the `truth_` prefix (C4).
- [ ] A5 `generate-bundle --seeds 1..20` produces the coverage set in under 2 minutes. Only seed 1 is committed, under 5 MB (C14).
- [ ] A6 Region × week heterogeneity is documented: festival weeks have higher ROI and the low season has negative ROI (C14).

Verification, automated: `uv run pytest tests/sample` exits 0 (offline).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G04-synthetic-market-generator-and-truth.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
