---
goal: G10
title: Findings digest, verdicts, scorer and deterministic synthetic tier
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: [adk-model-and-output-contracts (digest schema)]
docs: [adk-agent-evaluation/references/result-auditing.md]
blocked_by: [G04, G09]
touches: [src/truelift/explain/digest.py, src/truelift/explain/verdicts.py, src/truelift/bench/score.py, tests/explain/test_digest.py, bench-results/]
parallel_safe: no
contracts: [C5, C6, C10, C14]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G09/A3, G04/A2]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 1-2
  total: 4-7
  handoff: 0.5
  calendar_waits: none
owner: Thao            # suggested owner; anyone may pick this ticket
status: proposed
---

# G10 Findings digest, verdicts, scorer and deterministic synthetic tier

## Outcome

Pipeline outputs become an ID'd, verdict-bearing digest. The econometric core is proven against the truth before any LLM is involved (C5, C6, C10, C14; D10).

## Scope

- In: `explain/digest.py` reads the step-4 consolidated CSVs, `metadata.json` and the sensitivity metrics named in G03/A1. `explain/verdicts.py`. `bench/score.py`. The `truelift bench score` CLI.
- Route: `explain/digest.py` reads the step-4 consolidated CSVs, `metadata.json` and the sensitivity metrics named in G03/A1. `explain/verdicts.py`. `bench/score.py`. The `truelift bench score` CLI.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 `digest.json` validates against its schema. Each finding has an ID and covers either data facts (spend total, rows, weeks, regions) or estimates: total ROI with CI, incremental revenue, per region, per CATE bucket, and warnings for few clusters, n < 1000 and the sensitivity robustness value (C5).
- [ ] A2 The verdict function returns worth / not worth / undetermined against the threshold, with unit tests at the boundaries (C6).
- [ ] A3 A missing or garbled expected file raises a digest error and the run becomes `failed`, never partial (C10).
- [ ] A4 The scorer reports point error, whether the CI covers the truth, and the verdict sign versus `truth.yaml`, as JSON (C14).
- [ ] A5 Synthetic tier with a **scripted** DAG (Standard, 20 seeds): coverage ≥ 80% and median |error| ≤ 20%, or a recorded shortfall with a diagnosis (C14).
- [ ] A6 ROI is always incremental revenue ÷ the sum of the spend column. The per-raw-unit `total_estimated_roi` is never labelled as money (C5).

Verification, automated: `uv run pytest tests/explain/test_digest.py` exits 0 (offline); `uv run truelift bench --scripted-dag --seeds 1-20 --profile standard` writes a report (local, hours).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G10-findings-digest-verdicts-scorer-and-deterministi.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
