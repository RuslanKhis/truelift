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
status: done
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

- [x] A1 The public note lists the installed versions, the constructor and `run_full_pipeline` parameters as used on the stand-in synthetic panel (the private-CSV config stays in `private/`), the output files the digest will read, and confirms that `doubleml_pipeline.agent` is absent (C2).
- [x] A2 Wall-clock time and peak RAM for Quick and Standard on the reference Mac, with CPU count. These set D9 and the caps in G09 (C9).
- [x] A3 Three repeated Standard runs on the stand-in panel: the spread of total ROI and of the CI bounds (private-CSV results stay in `private/`). The note proposes the tolerance δ for C9 and says whether saved hyperparameters can be reused (C9).
- [x] A4 Claude via ADK `LiteLlm` works with the key passed per call and no environment variable; Gemini works with the key passed per call (C7).
- [x] A5 macOS `libomp` requirement for lightgbm and xgboost: needed or not, and the fix (feeds G23) (floor)

Verification, automated: `uv run python scripts/spike/run_profiles.py` exits 0 locally; `make check` exits 0 (the guard passes on the note).
Verification, manual: none.

## Evidence

Note: [docs/research/pipeline-spike.md](../../research/pipeline-spike.md). Scripts: `scripts/spike/` (`run_profiles.py`, `standin_panel.py`, `_omp.py`, `llm_keys.py`). Reference Mac: Apple M1, 8 cores, 16 GB, macOS 13.2.1, Python 3.12.16. All runs 2026-11-07, Ruslan's machine.

- A1: `local, pass`. Versions, constructor and `run_full_pipeline` parameters as used on the stand-in panel, and the output files the digest reads are in the note. `find_spec("doubleml_pipeline.agent")` is `None` (C2). The private-CSV config is `private/spike_config.json`.
- A2: `local, pass`. Quick 125/126 s (stand-in), 96 s (private CSV); Standard 228–234 s (stand-in), 170–189 s (private CSV); peak RAM ≤ 2.8 GB summed over the process tree. Proposed caps: Quick 6.5 min, Standard 10.5 min (3× median).
- A3: `local, pass`. Three idle Standard runs on the stand-in agree to every digit (ROI 2.1316 [1.0095, 3.2538], truth 1.87). With 4 cores busy: −3.1 % (≤ 4.1 % of interval width). Private-CSV spread ≤ 4.2 % of the interval width (values in `private/spike/runs/`). Proposed δ: 10 % of the interval width, for the ROI and both bounds. Saved hyperparameters reproduce a run exactly under load, but only through an override of the private `_run_global_hparam_search` (no public input in 0.2.3).
- A4: `live, pass`. `uv run python scripts/spike/llm_keys.py` at 21:40 exited 0: Gemini `gemini-3.8-flash` through the native `Gemini(client_kwargs={"api_key": …})` and Claude `claude-sonnet-5-5` through `LiteLlm(api_key=…)` both answered, wrong keys were rejected (`ClientError`, `AuthenticationError`), no provider environment variable was set, and the key appeared in no repr, log, error or console output. Two later runs (22:10 onwards) got Gemini `503` twice per run (provider capacity); Claude passed every run.
- A5: `local, pass`. Needed: lightgbm 4.7.0 and xgboost 3.4.1 fail to load without `libomp`. Fixes: `brew install libomp`, or `DYLD_FALLBACK_LIBRARY_PATH` set to scikit-learn's bundled `sklearn/.dylibs` before the interpreter starts (`uv run` drops it, so `_omp.py` re-executes once). Feeds G23.
- Verification: `uv run python scripts/spike/run_profiles.py` exit 0 (Quick, 123 s, ROI 2.1244 as in earlier runs); `make check` exit 0 (guard clean, ruff, 148 passed and 1 skipped, no client drift, pip-audit and npm audit clean).
- pass_to_pass G01/A2: `uv run pytest tests/test_guard.py` 43 passed, 1 skipped before any change; still passing inside `make check`.

Contracts:

- C2: `local`, G03/A1. The pipeline has no agent module; config enters only through the constructor.
- C7: `live`, G03/A4. The key is passed per call with no environment variable. Keychain storage, redaction and the secret scan remain G11's.
- C9: `local`, G03/A3. δ is measured and proposed. `env.json` remains G09's.

Companion skills: none. Skills: adk-engineer 2026.10.28 (primary), adk-model-and-output-contracts 2026.10.28 (LiteLlm per-call key; failover-and-providers reference).

Measurements:

- M1: Quick wall clock 125 s median (stand-in, n=3 incl. verification; private CSV 96 s, n=1); baseline: design assumption 2–6 min; window 2026-11-07; method `time.perf_counter` around `run_full_pipeline`; owner Ruslan; build doubleml-pipeline 0.2.3, lock of this change.
- M2: Standard wall clock 208 s median of 6 idle runs (stand-in 228–234 s, private 170–189 s); baseline: design assumption 10–30 min; same window, method, owner, build.
- M3: Peak RAM Standard ≤ 2.8 GB (summed RSS of the process tree, sampled every 0.25 s; overstates shared pages); no baseline; same window, owner, build.
- M4: Run-to-run deviation of total ROI and bounds ≤ 4.2 % of the interval width (stand-in idle 0, stand-in with 4 busy cores ≤ 4.1 %, private CSV ≤ 4.2 %); baseline: none (C9 left δ to G03); same window, owner, build.

Scope and changes outside `touches`:

- `pyproject.toml` and `uv.lock`: added `doubleml-pipeline==0.2.3`, `lightgbm`, `xgboost` (the pipeline does not declare them) and `litellm>=1.84,<1.106.3` (D7; cap as in ADK 2.13) to the runtime dependencies, and `psutil` to dev. Added the uv override `filelock>=4.2.1`: litellm 1.106.2 caps filelock below 4.0, which pulled in 3.32.7 and 13 pip-audit advisories. Review this override.
- `docs/architecture/truelift.md`: the Evidence cells of C7 and C9 only.

Rulings (for the designer's checkpoint):

- R1. D9 values: Quick = lgbm, 5 folds, `time_budget` 10, `top_n` 1, `n_reps` 3; Standard = lgbm and xgboost, folds 3 and 5, `time_budget` 30, `top_n` 3, `n_reps` 10, sensitivity on (total and geo). Standard is about 10× faster than the design assumed; a larger `n_reps` is affordable but unmeasured. Cost if wrong: a re-measure in G09.
- R2. Design §8 caps: 6.5 min (Quick), 10.5 min (Standard), measured on an M1 only. Cost if wrong: false timeouts on slow laptops; G09 records durations in `env.json`.
- R3. C9 δ = 10 % of the reference interval width for ROI and both bounds, without hyperparameter reuse (option 1 in the note). Cost if wrong: false "not reproducible" flags, or missed drift.
- R4. Money ROI is Σ incremental KPI ÷ Σ spend from `consolidated_1a_full_df.csv`, not `total_estimated_roi` from `consolidated_3b_summary.csv`, which divides by the summed rate for `percentage` treatments (F1, for D10 and G10). Cost if wrong: an ROI off by a factor of about 1,000 in the results.
- R5. G09 guards `plots.plot_prior_distributions` against `ValueError` on ATE-only runs (F2), until upstream fixes it. Without the guard, every run with no effect modifiers fails before sensitivity.
- R6. Gemini free-tier `503`s happen mid-session. G11 maps 5xx to `ai_unavailable`; D7's failover choice should note it.

Controls left out (spike depth): no Keychain module (`keyring`) or redaction filter (G11), no `env.json` (G09), no wall-clock cap enforcement (G09).

Human effort still owed: about 0.5–1 h. Review the note and rulings R1–R6, accept or reject the `filelock` override, and take R1–R4 into the design at the checkpoint. If you want a clean Gemini run on record, re-run `uv run python scripts/spike/llm_keys.py` once Gemini capacity is back.

actual: 1 h (Ruslan, review; owner accepted 2026-11-07)

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
