---
goal: G09
title: Pipeline worker and run lifecycle
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-workflow-design
supporting_skills: [adk-operational-guardrails (one run at a time, caps)]
docs: [adk-workflow-design/references/runtime.md]
blocked_by: [G06, G08]
touches: [src/truelift/worker/, src/truelift/api/routes/runs.py, tests/worker/]
parallel_safe: no
contracts: [C1, C9, C10, C14]
companion_skills: []
security: [SB19]
design_system: none
contract_deltas: []
pass_to_pass: [G06/A3, G08/A6]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 4-6
  review_and_verify: 1-2
  total: 5-8
  handoff: none
  calendar_waits: none
owner: Ruslan
status: ready
---

# G09 Pipeline worker and run lifecycle

## Outcome

Runs are gated, isolated and durable, and never show partial results. A headless scripted-DAG run works end to end (C1, C9, C10, C14; D8, D9).

## Scope

- In: `worker/__main__.py` (spawned with `start_new_session=True`), `status.json` heartbeats, a log parser for phase markers, the manifest written last, the runs table, startup reconciliation, the run gate in the start route, the `truelift run` CLI.
- Route: `worker/__main__.py` (spawned with `start_new_session=True`), `status.json` heartbeats, a log parser for phase markers, the manifest written last, the runs table, startup reconciliation, the run gate in the start route, the `truelift run` CLI.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 A run writes `config.json`, then `env.json` (versions from the lock, platform, CPU count, `n_jobs`, seeds), then `log.txt`, `status.json`, `work/` and finally `manifest.json` (C9, C10).
- [ ] A2 The gate refuses with a reason when the DAG is unconfirmed, identification fails, the mapping is unconfirmed, a hash changed after confirmation, or the DAG is stale. The worker re-checks the hashes before fitting (C1).
- [ ] A3 Killing the worker mid-run sets `failed` or `interrupted`. The results API returns nothing for that run, and outputs without a manifest are never read (C10).
- [ ] A4 A pipeline `ValueError` sets `failed` with a plain reason and keeps the config (C10).
- [ ] A5 Exceeding the per-profile wall-clock cap (3× the G03 median) sets `failed` with "took too long" (C10).
- [ ] A6 A second run while one is active is refused (C10, SB19).
- [ ] A7 The status endpoint returns the phase, elapsed time and a log tail, so a page refresh reattaches (C10).
- [ ] A8 After a backend restart or a database write failure during a run, startup marks rows that are queued or running with no live worker as `interrupted` (C10).
- [ ] A9 Cancel kills the process group and sets `cancelled`; outputs are not shown. A repeated cancel is idempotent (C10).
- [ ] A10 `truelift run` on synthetic seed 1 with a scripted DAG and the Quick profile completes headless (C14).

Verification, automated: `uv run pytest tests/worker` exits 0 (local, spawns real processes); `uv run truelift run --project demo --dag v1 --profile quick` exits 0 on synthetic seed 1.
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G09-pipeline-worker-and-run-lifecycle.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
