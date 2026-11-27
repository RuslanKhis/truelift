---
goal: G09
title: Pipeline worker and run lifecycle
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-workflow-design
supporting_skills: [adk-operational-guardrails (one run at a time, caps)]
docs: [adk-workflow-design/references/runtime.md]
blocked_by: [G04, G06, G08]
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
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: verified_local
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

- [x] A1 A run writes `config.json`, then `env.json` (versions from the lock, platform, CPU count, `n_jobs`, seeds), then `log.txt`, `status.json`, `work/` and finally `manifest.json` (C9, C10).
- [x] A2 The gate refuses with a reason when the DAG is unconfirmed, identification fails, the mapping is unconfirmed, a hash changed after confirmation, or the DAG is stale. The worker re-checks the hashes before fitting (C1).
- [x] A3 Killing the worker mid-run sets `failed` or `interrupted`. The results API returns nothing for that run, and outputs without a manifest are never read (C10).
- [x] A4 A pipeline `ValueError` sets `failed` with a plain reason and keeps the config (C10).
- [x] A5 Exceeding the per-profile wall-clock cap (3× the G03 median) sets `failed` with "took too long" (C10).
- [x] A6 A second run while one is active is refused (C10, SB19).
- [x] A7 The status endpoint returns the phase, elapsed time and a log tail, so a page refresh reattaches (C10).
- [x] A8 After a backend restart or a database write failure during a run, startup marks rows that are queued or running with no live worker as `interrupted` (C10).
- [x] A9 Cancel kills the process group and sets `cancelled`; outputs are not shown. A repeated cancel is idempotent (C10).
- [x] A10 `truelift run` on synthetic seed 1 with a scripted DAG and the Quick profile completes headless (C14).

Verification, automated: `uv run pytest tests/worker` exits 0 (local, spawns real processes); `uv run truelift run --project demo --dag v1 --profile quick` exits 0 on synthetic seed 1.
Verification, manual: none.

## Evidence

Built on branch `g09-pipeline-worker` from `a892e3a`, 2026-11-27, Ruslan's machine (Apple M1, 8 cores, macOS 13.2.1, Python 3.12.16, doubleml-pipeline 0.2.3). Plain Python, subprocess and FastAPI: no model, no ADK code and no network in any test.

- `src/truelift/worker/`: `gate.py` (the run gate, C1), `layout.py` (run folder, status, manifest), `phases.py` (log parser), `job.py` (the worker process, `python -m truelift.worker <run_id> --run-dir <dir>`), `manager.py` (one run at a time, spawn in a new session, watcher with the wall-clock cap, cancel, startup reconciliation, shutdown), `scripted.py` (synthetic seed project with a scripted, confirmed DAG and mapping).
- `src/truelift/store/db.py`: the `runs` table and its queries. `insert_run_if_idle` checks for an active run inside `BEGIN IMMEDIATE`, so two processes on one `state.db` cannot both start a run.
- `src/truelift/api/routes/runs.py`: real projects go through the gate and the manager. The demo project keeps the G02 fakes. `src/truelift/api/routes/results.py`: results need a `succeeded` row, a manifest that still verifies, and `digest.json` listed in it. `src/truelift/api/app.py`: reconcile at startup and stop workers at shutdown (lifespan).
- `src/truelift/cli.py`: `truelift sample-project` and `truelift run`.
- Tests: `tests/worker/` (39). The lifecycle tests spawn the production worker in its own process group, with only the pipeline fit scripted (`tests/worker/fake_worker.py`). `test_pipeline_errors.py` runs the real pipeline.

Results (tier, outcome):

- pass_to_pass G06/A3 and G08/A6: `uv run pytest tests/causal/test_compile.py tests/store/test_versions.py` gave 23 passed on the base (tracked changes stashed; run **after** the change was written, not before) and 23 passed with the change.
- A1: `local, pass`. The run folder is written in this order:
  1. the app writes `config.json` (canonical, C2) and `run.json` (the admitted hashes);
  2. the worker writes `env.json`: versions of the pinned packages, `lock_sha256`, platform, CPU count, `n_jobs`, the pipeline's fixed seeds, the config hash and the data fingerprint;
  3. then `log.txt` (fds 1 and 2), then `status.json`, then `work/`;
  4. `manifest.json` last, by atomic rename.

  The test records the files present when the fit starts (all of them except the manifest) and checks the manifest's mtime against every file it lists.
- A2: `offline, pass` (gate) and `local, pass` (worker re-check). Each refusal is a 409 with a plain reason and creates no run:
  - an unconfirmed DAG;
  - an older DAG version;
  - a DAG file edited after confirmation;
  - a DAG whose cited fact changed ("1 answer it depends on changed");
  - an unconfirmed mapping;
  - an edited data file;
  - an unidentified DAG, with the business reason ("Competitors' promotions…", no node IDs).

  When the data changes between the app's gate and the worker start, the worker refuses before fitting: `failed`, no `work/` and no manifest.
- A3: `local, pass`. A worker killed from outside (SIGKILL to its group) or killing itself becomes `failed` with "The analysis process stopped unexpectedly." Neither leaves a manifest, and the results API answers 409. A `succeeded` row whose manifest is missing, or whose outputs changed after it was written, serves no results.
- A4: `local, pass`. A scripted `ValueError` and the **real** pipeline's own `ValueError` (a mapped column missing from the file) both set `failed`. The reason is "The analysis could not run on this data: The following user-specified column(s) were not found… media_grps". The config is kept and the traceback stays in `log.txt`.
- A5: `local, pass`. A run over a 3 s cap becomes `failed` with "took too long", and its process is gone. Default caps are Quick 390 s and Standard 630 s (G03 R2), with the expected times 125 s and 208 s (G03 M1, M2).
- A6: `local, pass`. A second start is refused (`RunActive`; through the API 409 `run_active`), including from a second `StateDb` on the same file.
- A7: `local, pass`. `GET /api/runs/{id}` from a new client and a new manager returns the phase parsed from the log (`nuisance models`), the profile's phases, elapsed and expected time, and the log tail.
- A8: `local, pass`. Each of these becomes `interrupted` ("This run was interrupted. Run it again (about 2 min).") at startup:
  - a live worker whose watcher is gone (the worker is killed, not re-adopted);
  - a queued row that was never spawned;
  - a run whose end could not be written (an `OperationalError` injected on the terminal update).

  A queued row watched by another live truelift process is left alone. The app's lifespan reconciles at startup (API test), and shutdown stops workers as `interrupted`.
- A9: `local, pass`. Cancel kills the whole process group, including a child that stands in for loky's workers, and sets `cancelled`. No manifest is written and results answer 409. A repeated cancel returns the same row with the same `finished_at`. Cancelling a finished run changes nothing.
- A10: `local, pass`. `uv run truelift sample-project --name demo --seed 1`, then `uv run truelift run --project demo --dag v1 --profile quick` exited 0 after 148 s. `TRUELIFT_PROJECTS_DIR` and `TRUELIFT_STATE_DIR` pointed at `/tmp/g09-a10`, deleted afterwards. Phases printed: prepare 0 s, nuisance models 4 s, effect estimation 40 s, consolidate results 48 s, write outputs 148 s. The manifest lists 148 files. The headline from `consolidated_1a_full_df.csv` by the G03 R4 formula is ROI 2.42 [0.40, 4.44] against the seed's true 2.01; the CI covers it. This is informational only: G10 scores it.
- Verification: `uv run pytest tests/worker` 39 passed, exit 0. `make check` exit 0: guard clean (273 files), ruff clean, 557 passed and 1 skipped, `client-check: no drift` (the routes' OpenAPI is unchanged), pip-audit clean (2 named ignores), npm audit below its threshold (8 moderate, existing frontend tooling).

Contracts:

- C1: `local`, G09/A2. Gate in the start route under the project lock, with the worker's re-check before fitting.
- C9: `local`, G09/A1. `env.json` is written before fitting. The "not reproducible: versions differ" flag is not built (see below).
- C10: `local`, G09/A3–A9.
- C14: `local`, G09/A10 (the headless path only). The tiers are G10, G18 and G19.
- SB19: `local`, G09/A6.

Companion skills: none named. Skills: adk-engineer 2026.10.28, adk-workflow-design 2026.10.28 (primary; ordinary Python, no ADK orchestration involved), adk-operational-guardrails 2026.10.28 (supporting: one run at a time, cap).

Measurements:

- M1: Quick wall clock 148 s (n=1, synthetic seed 1, end to end through `truelift run`, including about 100 s of Phase 4 charts and the HTML report); baseline: G03 M1 125 s on the stand-in panel; window 2026-11-27; method: the run row's `started_at` to `finished_at`; owner Ruslan; build doubleml-pipeline 0.2.3, lock `ff951b18…`.
- M2: run folder 216 MB for one Quick run, of which the HTML report is about 122 MB; baseline: design §6 assumption of 10–100 MB per run; same window, owner and build.

Scope and changes outside `touches`:

- `src/truelift/store/db.py` (the `runs` table), `src/truelift/api/routes/results.py` (runs-table check, G31 R5), `src/truelift/api/app.py` (manager and lifespan), `src/truelift/cli.py` (`run`, `sample-project`).
- `tests/api/test_dag_routes.py`: the G31 results tests now make a real `succeeded` row and manifest (`tests/worker/support.finished_run`), because results now require both.
- `AGENTS.md`: two rows in the commands table. `docs/architecture/truelift.md`: the Evidence cells of C1, C9 and C10 only.

Rulings (for the designer's checkpoint):

- R1. Data files live in `<project>/data/*.csv`, and a data fingerprint is `sha256:<hex>` of the file's bytes. The gate finds the file by its fingerprint, so an edited file is refused. **G07 must write uploads and fingerprints this way** (pass to Chloe with G31 R3). Cost if wrong: every real run is refused with `data_changed`.
- R2. The margin is not read from `business.md` yet, so `opt_threshold_roi` is 1.0, marked assumed. A margin fact convention needs G12/G13 (slot) and a compiler input. Cost if wrong: the verdict threshold ignores the user's margin.
- R3. Manifest `truelift.manifest/1` hashes every run file except `log.txt` and `status.json`. `succeeded` needs exit 0 and a manifest whose every hash matches. **G10** builds `digest.json` and must get it into the manifest before the run is shown as succeeded. Either `_finalize` builds the digest and rewrites the manifest, or G10 changes this rule. Cost if wrong: succeeded runs show no results.
- R4. A worker killed by a signal the app did not send is `failed` ("stopped unexpectedly"). A backend restart gives `interrupted`, a cancel gives `cancelled`, and a timeout gives `failed` ("took too long").
- R5. The phases shown are `prepare`, `nuisance models`, `effect estimation`, `consolidate results`, `sensitivity` (only when it runs) and `write outputs`. They are parsed from the pipeline's `=== Phase N` banners and its "Running Sensitivity Analysis" line. G17 renders the run's own `phases`; the G02 fake list stays as it was.
- R6. One active run per `state.db`, which is one per machine with default settings. Two `TRUELIFT_STATE_DIR` values on one machine are not guarded.
- R7. A worker is live only when its pid is alive **and** `status.json` names that pid with a heartbeat under 30 s old, so a reused pid is never killed. A run watched by another live truelift process (the app or `truelift run`) is left alone at startup.
- R8. The worker's environment drops `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` (C7, defence in depth). On macOS it sets `DYLD_FALLBACK_LIBRARY_PATH` to scikit-learn's bundled libomp when it is unset (G03/A5).
- R9. The run folder is about twice the design's assumed size because of the HTML report (M2). A "delete run" action (design §7) or skipping the report needs a decision.

Specialist controls left out deliberately:

- re-adopting a live worker after a restart (design §3, G25);
- the "not reproducible: versions differ" comparison of `env.json` between runs, for C9's failure behaviour (needs the run comparison view, phase 2);
- process-group kill on Windows (phase 1 is macOS and Linux; G23);
- a RAM cap (G03 measured ≤ 2.8 GB).

Human effort still owed: about 1–2 h. Review `worker/manager.py` (kill and reconcile paths) and rulings R1–R9. Pass R1 to Chloe for G07 (#8) and R3 to Thao for G10 (#11). Optionally, re-run A10 on a busy machine to check the 390 s cap.

actual: not reported.

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
