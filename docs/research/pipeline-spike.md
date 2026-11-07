# Pipeline feasibility spike (G03)

Date: 2026-11-07. Ticket: [G03](../tickets/truelift/G03-pipeline-feasibility-spike.md). Design: [truelift.md](../architecture/truelift.md) (D7, D9, D11, C2, C7, C9).

This note checks whether doubleml-pipeline's real interface, runtime and run-to-run variability match the design's assumptions. All figures below come from a quick stand-in synthetic panel (`scripts/spike/standin_panel.py`, 8 regions × 156 weeks = 1,248 rows, weekly discount rate plus discount spend, true total ROI 1.87). The stand-in is not the product's synthetic market (G04). The private CSV was run with the same profiles. Its config, results and logs stay in `private/`, and this note reports only its timings and whether its spread falls within the proposed δ.

Reference machine: Apple M1, 8 cores, 16 GB RAM, macOS 13.2.1 (arm64), Python 3.12.16 provisioned by uv.

Reproduce:

```sh
uv run python scripts/spike/run_profiles.py --full                                   # Quick once, Standard x3
uv run python scripts/spike/run_profiles.py --profile standard --load 4              # with 4 cores busy
uv run python scripts/spike/run_profiles.py --profile standard --load 4 --reuse-hparams standard_1
uv run python scripts/spike/llm_keys.py                                              # A4, needs the Keychain items
```

## A1. Interface

### Installed versions

| Package | Version | Note |
| --- | --- | --- |
| doubleml-pipeline | 0.2.3 | pinned |
| doubleml | 0.11.4 | |
| flaml | 2.8.0 | |
| lightgbm | 4.7.0 | not a dependency of the pipeline; added by G03 |
| xgboost | 3.4.1 | not a dependency of the pipeline; added by G03 |
| scikit-learn | 1.9.1 | |
| numpy | 2.5.4 | |
| pandas | 3.1.1 | |
| scipy | 1.18.1 | |
| google-adk | 2.12.0 | |
| google-genai | 2.34.0 | |
| litellm | 1.106.2 | capped `<1.106.3`, as ADK 2.13 caps it |
| filelock | 4.2.9 | uv override: litellm 1.106.2 caps it `<4.0`, and every 3.x release has open advisories (pip-audit). litellm imports it only in its proxy CLI. |

doubleml-pipeline 0.2.3 declares numpy, pandas, scikit-learn, doubleml, FLAML, scipy, patsy, matplotlib, cloudpickle and joblib. It does **not** declare lightgbm or xgboost, although FLAML needs them for the `lgbm` and `xgboost` learners that D9 uses. truelift therefore depends on both directly.

### C2: no agent module

`importlib.util.find_spec("doubleml_pipeline.agent")` returns `None`. The installed package contains only `evaluation`, `models`, `optimization`, `preprocessing`, `utils`, `visualization` and `workflow`. The pipeline has no LLM path of its own. Config enters only through the constructor below, which G06's compiler will own.

### Constructor, as used on the stand-in panel

`doubleml_pipeline.workflow.CausalWorkflowOrchestrator(...)`:

| Parameter | Value used | Source in the design (§ DAG and mapping) |
| --- | --- | --- |
| `y_col`, `sales_col` | `"revenue"` | Mapping: outcome |
| `d_cols` | `["discount_rate"]` | Mapping: treatment |
| `treatment_types` | `{"discount_rate": "percentage"}` | A rate in [0, 1] |
| `treatment_spend_cols` | `{"discount_rate": "discount_spend"}` | Mapping: treatment spend |
| `x_cols_list` | `[[population, distribution, media_grps, holiday, season, region_R1 … region_R8]]` | Adjustment set plus region dummies |
| `covariates_for_cate_list` | `[[]]` (ATE only) | No confirmed effect modifiers |
| `date_col`, `geo_col` | `"week"`, `"region"` | Mapping |
| `optimize`, `opt_threshold_roi` | `True`, `1.0` | Margin fact (default, assumed) |
| `ml_models_y`, `ml_models_t`, `n_folds_list`, `time_budget` | per profile, below | D9 |
| `run_sensitivity`, `sensitivity_scope` | per profile, below | D9 |
| `n_jobs` | `-1` (8 cores) | Design §8 |
| `output_dir` | the run directory | G09 |
| `hparam_policy` | default `"global"` | one FLAML search per (treatment, side, learner), seed 1 |
| `saturation_config`, `ground_truth_*` | not set | not used in v1 (C4) |

Scaler: `doubleml_pipeline.preprocessing.scalers.CausalDataScaler(median_normalize_cols=["media_grps"])`. The other lists stay empty.

`run_full_pipeline(df, scaler, top_n, n_reps, process_log="lightweight")`, with `df` carrying a unique index (the pipeline raises otherwise).

The constructor has **no seed parameter**. The FLAML search uses a fixed seed (`SEARCH_SEED = 1`), but it stops on `time_budget` seconds, so the number of trials depends on CPU speed and load (A3).

### Run profiles measured

| Profile | Learners (Y and T) | `n_folds_list` | `time_budget` | `top_n` | `n_reps` | Sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| Quick | `lgbm` | `[5]` | 10 s | 1 | 3 | off |
| Standard | `lgbm`, `xgboost` | `[3, 5]` | 30 s | 3 | 10 | on, scope `total` and `geo` |

### Output files the digest will read

Under `<output_dir>/`:

| File | Use |
| --- | --- |
| `step4_consolidated_results/consolidated_1a_full_df.csv` | Per-row incremental KPI with its 2.5 % and 97.5 % bounds, the spend column and `roi_amount_based_<d>`. **The money ROI comes from here** (finding F1). |
| `step4_consolidated_results/consolidated_3b_summary.csv` | Model group, x columns, error metrics, `total_estimated_incremental_KPI`. Its `total_estimated_roi` is per unit of treatment, not money over money (F1). |
| `step4_consolidated_results/consolidated_3b_summary_geo.csv` | The same per region |
| `step4_consolidated_results/consolidated_3a_detail.csv` | Per-repetition detail |
| `metadata.json` | Treatment and spend columns, spend totals, geos, date range, optimisation settings |
| `step1_exploration_<d>/hparams_<d>_<learner>.json` | Saved hyperparameters per side, with trial counts (A3) |
| `step4_consolidated_results/roi_output/<d>/007_optimization/optimization_metrics.csv` | Optimiser output (simple optimiser; forced for `percentage`) |
| `step4_consolidated_results/graph/006_sensitivity/sensitivity_metrics.csv` | Sensitivity metrics for scopes `total` and `geo` (Standard only; written after the prior plot, see F2) |

The run also writes PNG charts, an HTML report (`<d>_<y>.html`) and `step3_final_<d>/best_model/best_dml_object_<model>.pkl`. The digest must never unpickle that file (unpickling can run code). The orchestrator keeps the same object in memory as `best_model_data`.

### Findings for later goals

- **F1 (G10, D10).** For a `percentage` treatment, `total_estimated_roi` in `consolidated_3b_summary.csv` divides the incremental KPI by the summed **rate**, not by spend. On the stand-in it reads about 3,500 where the money ROI is about 2.1. The digest must compute total ROI as Σ `estimated_incremental_KPI_<d>` ÷ Σ spend over `consolidated_1a_full_df.csv`, and the interval from the 2.5 % and 97.5 % columns the same way. That matches `roi_amount_based_<d>` per row.
- **F2 (G09).** An ATE-only run (`covariates_for_cate_list=[[]]`, the design's case with no effect modifiers) crashes 0.2.3 in `plots.plot_prior_distributions`. The per-date ROI ratio is constant to about 1e-12, so `numpy.histogram` raises `ValueError: Too many bins for data range. Cannot create 30 finite-sized bins.` This happens after the consolidated CSVs are written, but **before sensitivity analysis**, so `run_full_pipeline` fails. The spike wraps that one function so a `ValueError` is recorded and the run continues. G09 needs the same guard until an upstream fix ships.
- **F3 (G09).** The pipeline prints its progress to stdout. The worker should capture it to the run log (as the spike does), not to the server's console.

## A2. Runtime and memory

Peak RAM is the summed resident memory of the process and all its worker processes, sampled every 0.25 s. Shared pages are counted once per process, so it overstates.

| Data | Profile | Runs | Wall clock (s) | Peak RAM (GB) |
| --- | --- | --- | --- | --- |
| Stand-in, 1,248 rows | Quick | 2 | 125, 126 | 0.95–0.99 |
| Stand-in | Standard | 3 | 234, 229, 228 | 2.3–2.8 |
| Stand-in, 4 cores busy | Standard | 1 | 209 | 2.4 |
| Stand-in, 4 cores busy, reused hyperparameters | Standard | 1 | 254 | 2.6 |
| Private CSV (fewer rows) | Quick | 1 | 96 | 1.1 |
| Private CSV | Standard | 3 | 170, 189, 187 | 2.4–2.5 |

The design assumed Quick ≈ 2–6 min and Standard ≈ 10–30 min on an 8-core laptop (§8). Measured on the reference Mac, Quick takes about 2 min and Standard about 3–4 min. The pipeline logs no per-phase timings. Standard runs 4 FLAML searches of 30 s each in parallel, 8 Phase 1 combinations and 27 Phase 3 repetitions (3 models × 9 new repetitions), all on 8 workers.

Proposed caps for G09 (3× the median of the unloaded runs, C9 and design §8):

| Profile | Median (s) | Cap |
| --- | --- | --- |
| Quick | 125 | 6.5 min |
| Standard | 208 | 10.5 min |

Memory: the measured peak stayed below 3 GB, an overstatement, so keeping 4 GB free for Standard is a safe floor. Machines with 8 GB of RAM should cope, but none was measured, and neither were slower or older laptops. G09 should record their durations in `env.json` and revisit the caps at the milestone run.

## A3. Run-to-run variability

Three Standard runs on the stand-in panel, on an otherwise idle machine:

| Run | Total ROI | 2.5 % bound | 97.5 % bound |
| --- | --- | --- | --- |
| 1 | 2.1316 | 1.0095 | 3.2538 |
| 2 | 2.1316 | 1.0095 | 3.2538 |
| 3 | 2.1316 | 1.0095 | 3.2538 |
| 4 cores busy | 2.0656 | 0.9705 | 3.1606 |
| 4 cores busy, hyperparameters reused from run 1 | 2.1316 | 1.0095 | 3.2538 |

True total ROI on the stand-in: 1.87, inside every interval.

- The spread of the three idle runs is zero to the last digit. The trial counts of the FLAML searches still differed (one search ran 14 trials instead of 15), but the selected model did not change.
- With four cores kept busy, the searches ran fewer trials (for example, 16 instead of 20 for xgboost on the Y side). The headline moved by −3.1 % and the bounds by −3.9 % and −2.9 %. That is 2.9 %, 1.7 % and 4.1 % of the interval width.
- A cold first run behaves the same way. The first Quick run of the session gave 2.28 against 2.12 for the next two.
- On the private CSV, the three Standard runs did not all agree, because the searches ran different trial counts. Each difference was within 5 % of the interval width, which is inside the δ proposed below.

**Proposed δ (C9).** A re-run reproduces the headline when the total ROI and both interval bounds each lie within **10 % of the reference run's interval width** (`|Δ| ≤ 0.1 × (hi − lo)`). The largest observed deviation was about 4 % of the width, so this leaves a margin of two. A relative tolerance on the ROI alone does not work: a bound near zero can move 18 % relative while moving 4 % of the width.

**Reusing saved hyperparameters.** Every run saves the searched hyperparameters to `step1_exploration_<d>/hparams_<d>_<learner>.json`, and `doubleml_pipeline.evaluation.hparam_search.read_hparams_json` reads them back. Reusing them removes the variance: with four cores busy, the run that reused run 1's hyperparameters reproduced run 1 exactly. But 0.2.3 has **no public input** for this. The spike overrides the private method `CausalWorkflowOrchestrator._run_global_hparam_search`. So reuse works today only through a private-API override that can break on any upgrade. The options for G09 are:

1. Re-run without reuse and judge it against δ (no private API). This is the recommendation for v1.
2. Reuse the saved file through the override, pinned to 0.2.3 with a test that fails when the method's signature changes.
3. Ask upstream for a public `hparams_from` input.

## A4. Model keys passed per call (C7)

Run live on 2026-11-07 with `scripts/spike/llm_keys.py`. Each key is read from the macOS Keychain (service `truelift`) at call time and passed only to the model object. The provider environment variables are removed first.

| Provider | Path | Call | Wrong key | Key seen in reprs, logs, errors or console |
| --- | --- | --- | --- | --- |
| Gemini `gemini-3.8-flash` | ADK native `Gemini(model=…, client_kwargs={"api_key": key})` | pass | rejected (`ClientError`) | no |
| Claude `claude-sonnet-5-5` | ADK `LiteLlm(model="anthropic/claude-sonnet-5-5", api_key=key)` | pass | rejected (`AuthenticationError`) | no |

Both calls succeeded with no `GOOGLE_API_KEY`, `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` in the environment. Logging ran at DEBUG for `LiteLLM`, `google_genai` and `httpx`, and the key did not appear in the captured logs or the model and agent reprs. With an API key in `client_kwargs`, ADK 2.12's `get_gcp_client_defaults` skips the Vertex defaults, so the Developer API backend is kept. The wrong-key calls prove that the key passed is the one used, not an ambient credential. G11 still owns the redaction filter and the secret-scan test.

Two later runs that day (after the filelock override, which `google-genai` does not use) got `503` from `gemini-3.8-flash` on both the first attempt and one retry 20 s later. The wrong-key call was still rejected with `ClientError`, and Claude passed each time. The free tier can run out of capacity mid-session. G11 should treat a 5xx as "AI unavailable, try again" (the `ai_unavailable` scenario in the API fakes), and D7's failover decision should account for it.

## A5. macOS OpenMP (`libomp`)

**Needed.** On a Mac without Homebrew's `libomp`, both `import lightgbm` (4.7.0) and `import xgboost` (3.4.1) fail with `Library not loaded: @rpath/libomp.dylib`. The wheels search only `/opt/homebrew/opt/libomp/lib` and `/opt/local/lib/libomp`.

Fixes, tested on the reference Mac:

- **Developers:** `brew install libomp`.
- **No Homebrew or admin rights:** scikit-learn's macOS wheel bundles `sklearn/.dylibs/libomp.dylib`. Setting `DYLD_FALLBACK_LIBRARY_PATH` to that directory before Python starts makes both learners load and fit. Loading it with `ctypes` after start does not work. `uv run` does not pass `DYLD_*` variables through, so the spike re-executes its interpreter once with the variable set (`scripts/spike/_omp.py`).

G23 decides what end users get. Options are the re-exec in the `truelift` launcher, or install instructions that include `brew install libomp`.

## What changes for the design

These are proposals; the designer takes them in at the checkpoint.

- D9: Quick and Standard as measured above, with `time_budget` 10 s and 30 s and `n_reps` 3 and 10. Standard is fast enough that a larger `n_reps` is affordable; that would need its own measurement.
- Design §8: caps of 6.5 min (Quick) and 10.5 min (Standard). Replace "Standard ≈ 10–30 min" with "Standard ≈ 3–4 min on an M1".
- C9: δ = 10 % of the interval width, applied to the total ROI and both bounds.
- D10 and G10: money ROI from `consolidated_1a_full_df.csv` (F1).
- G09: guard the prior plot (F2), capture stdout (F3), never unpickle the model file.
