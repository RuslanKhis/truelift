---
goal: G03
title: Pipeline feasibility spike
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-engineer
supporting_skills: [adk-model-and-output-contracts (LiteLlm per-call key)]
docs: [adk-model-and-output-contracts/references/failover-and-providers.md]
blocked_by: [G01]
touches: [docs/research/pipeline-spike.md, scripts/spike/]
parallel_safe: no
contracts: [C2, C9, C7]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2]
phase: 1
type: discovery
profile: MVP or pilot
estimate:
  hands_on: 2-4
  review_and_verify: 0.5-1
  total: 2.5-5
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: ready
---

# G03 Pipeline feasibility spike

## Outcome

Do the pipeline's real interface, runtime and variability match the design's assumptions (D7, D9, C9)?

## Scope

- In: - Install `doubleml-pipeline==0.2.3` in a uv venv on Python 3.12 (Mac arm64). - Construct the orchestrator from a hand-written config on the private CSV and on a quick stand-in synthetic panel. - Run Quick once and Standard three times. - Inspect the output layout. - Try LiteLLM with a per-call key.
- Stopping condition: 5 h, or a blocker recorded together with an alternative (Python 3.11 pin, or conda).
- Expected evidence: `docs/research/pipeline-spike.md` (public; no private config or data quoted, numbers only).
- Route: see design
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 The public note lists the installed versions, the constructor and `run_full_pipeline` parameters as used on the stand-in synthetic panel (the private-CSV config stays in `private/`), the output files the digest will read, and confirms that `doubleml_pipeline.agent` is absent (C2).
- [ ] A2 Wall-clock time and peak RAM for Quick and Standard on the reference Mac, with CPU count. These set D9 and the caps in G09 (C9).
- [ ] A3 Three repeated Standard runs on the stand-in panel: the spread of total ROI and of the CI bounds (private-CSV results stay in `private/`). The note proposes the tolerance δ for C9 and says whether saved hyperparameters can be reused (C9).
- [ ] A4 Claude via ADK `LiteLlm` works with the key passed per call and no environment variable; Gemini works with the key passed per call (C7).
- [ ] A5 macOS `libomp` requirement for lightgbm and xgboost: needed or not, and the fix (feeds G23) (floor)

Verification, automated: `uv run python scripts/spike/run_profiles.py` exits 0 locally; `make check` exits 0 (the guard passes on the note).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G03-pipeline-feasibility-spike.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
