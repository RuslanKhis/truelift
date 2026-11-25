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
status: verified_local
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

- [x] A1 A DAG YAML round-trips byte-identically. A cycle is rejected with a message (C3).
- [x] A2 All golden cases from G05 pass, and every block reason is a business-language sentence naming the missing item (C3).
- [x] A3 The same inputs give a byte-identical config JSON in two processes and on two OSes (CI matrix). Changing a fact the DAG does not use leaves the config unchanged (C2). *(Accepted on macOS; the Linux leg was waived by Ruslan, 2026-11-25.)*
- [x] A4 A Hypothesis property test over random DAGs finds no descendant of the treatment, no outcome and no forbidden column in `x_cols` or the CATE covariates (C3, C4).
- [x] A5 A percentage treatment yields `treatment_types='percentage'` plus `sales_col` and the spend column. A margin of 0.4 gives `opt_threshold_roi=2.5` (C2).
- [x] A6 The compiled config constructs `CausalWorkflowOrchestrator` and `CausalDataScaler` without fitting, using the G03 parameter names (C2).

Verification, automated: `uv run pytest tests/causal tests/golden` exits 0 on macOS and Linux CI (offline).
Verification, manual: none.

## Evidence

Built on branch `g06-causal-core` from `970f8c0`, 2026-11-25, Ruslan's machine (Apple M1, macOS 13.2.1, Python 3.12.16, networkx 3.7, hypothesis 6.170.17, pydantic 2.14.3, doubleml-pipeline 0.2.3). Plain Python: no model, no ADK and no network in any test.

- `src/truelift/causal/dag.py`: the `Dag` model (one treatment, one outcome, nodes with role, label, column or accepted stand-in, edges, modifiers, accepted risks). It has a canonical YAML form (`to_yaml`, `from_yaml`, `to_content` for `dag/vN.yaml`) and a networkx graph, and it refuses a loop with a message that names it.
- `src/truelift/causal/mapping.py`: `ColumnMapping` and `PanelSummary` (the threshold quantities plus the levels of each region or category column).
- `src/truelift/causal/forbidden.py`: `DenyList`. It covers the `truth_` prefix, the hackathon prefix (base64 only, the same constant as the guard) and any column a truth sidecar lists. Matching ignores case.
- `src/truelift/causal/identify.py`: C3a–d with the `ancestral_v1` adjustment set, `networkx.is_d_separator` on the back-door graph, one block per unobserved node on an open path, and the panel thresholds. Every block and warning message is filled from `rules/identification.yaml` and `rules/cate.yaml`.
- `src/truelift/causal/compile.py`: `PipelineConfig` as canonical JSON (sorted keys, indent 2, UTF-8, trailing newline), the D9 profiles with G03's values, and `orchestrator_kwargs` / `scaler_kwargs` for the worker. Errors are `CompileError(code, message)`.
- `src/truelift/causal/rules.py`: a public `parse_yaml` split out of `read_yaml`, so DAG text uses the same duplicate-key-safe loader. No behaviour changed.
- Tests: `tests/causal/` (133), with the reference config `tests/causal/fixtures/g18_standard.config.json`.

Results (tier, outcome):

- pass_to_pass, before any change: `uv run pytest tests/test_guard.py tests/golden` 139 passed, 1 skipped (the private test). After: `tests/test_guard.py` 43 passed, 1 skipped; `tests/golden` 96 passed.
- A1: `offline, pass`. `test_dag.py`: every golden DAG and a DAG with labels and a stand-in give the same bytes after `to_yaml → from_yaml → to_yaml`. That includes awkward column names (`yes`, `Rabatt %: Anteil`). A loop is refused in data and in YAML text, with "The diagram has a loop: your sales -> holiday weeks -> …", and the same diagram without the extra arrow is accepted. Six other malformed diagrams and duplicate YAML keys are refused with their reason.
- A2: `offline, pass`. `test_golden_cases.py`: all 25 golden cases agree with `identify` (decision, blocks with remedies, adjustment set, `x_cols`, fixed effects, CATE covariates and degree, warnings) and with `compile_config`. Blocked cases raise `not_identified`, and g19 raises `missing_spend_column`. Every block and warning message ends with a full stop, starts with a capital or a number, contains no snake_case code word or leftover placeholder (the user's own column names are allowed, quoted exactly), and names the node's label or the panel number. The golden set triggers all nine block codes and both decisions.
- A3: `offline, pass` on macOS. The Linux leg was waived by Ruslan on 2026-11-25 ("we can skip linux test as long as it works on mac"); `make check` in CI still runs these tests on Linux. `test_compile.py` checks four things. The g18 config equals the committed reference bytes. Two child processes with `PYTHONHASHSEED` 1 and 2 give the in-process sha256. A changed label, an unconnected factor, something sales cause and an unused file column each leave the bytes unchanged. Five controls change them: margin, profile, fingerprint and an added confounder. CI: `make check` runs the same tests on ubuntu-24.04, and the new job `causal-macos` runs `tests/causal tests/golden` on macos-15. The CI result on Linux is informational for A3.
- A4: `offline, pass`. `test_properties.py` runs 400 derandomised random DAGs with up to 9 nodes. Their columns come from data, none, `truth_`, the private prefix in two cases, or a sidecar list. In 173 of them identification passed, and 134 of those had a ground-truth column. No discount descendant, outcome, treatment, spend or ground-truth column reached `x_cols`, the CATE covariates, `x_cols_list` or `covariates_for_cate_list`. Each identified adjustment set also passed the back-door d-separation check. Mutations, run by hand and then reverted, were each caught: dropping the private prefix, dropping `truth_`, and keeping the discount's descendants.
- A5: `offline, pass`. g18 compiles to `treatment_types={'discount_rate': 'percentage'}`, `sales_col='revenue'`, `treatment_spend_cols={'discount_rate': 'discount_spend'}` and `opt_threshold_roi=2.5`. g20 (a spend treatment) compiles to `sales_col=None`, spend equal to the treatment and 4.0. With no margin the threshold is 1.0, marked assumed. A margin of 0, −0.1 or 1.5 is refused.
- A6: `offline, pass`. `test_pipeline_construct.py` uses g18 (Standard), g20 (Quick) and g21 (CATE). Each config is written to JSON and read back in a child process, which builds `CausalWorkflowOrchestrator` and `CausalDataScaler` with warnings set to errors. Every compiled name is a 0.2.3 constructor parameter, the objects hold the compiled values, `simple_optimization` is True, and no output was written. On macOS the child gets `DYLD_FALLBACK_LIBRARY_PATH` set to scikit-learn's bundled libomp (G03/A5), because this Mac has no Homebrew libomp.
- Verification: `uv run pytest tests/causal tests/golden` 229 passed, exit 0. `make check` exit 0: guard clean (253 files), ruff clean, 484 passed and 1 skipped, no client drift, pip-audit clean (2 named ignores, unchanged), and npm audit below its high threshold (8 moderate, all in the existing frontend tooling). `make dist` exit 0: guard clean (169 package members).

Contracts:

- C2: `offline`, G06/A3 (macOS; Linux waived), G06/A5, G06/A6. The compiler is the only place that builds `PipelineConfig`. Agents get no config tool (G13 must keep it that way).
- C3: `offline`, G06/A1, G06/A2, G06/A4. Enforcement in the run gate is G09/G31.
- C4: `offline`, G06/A4. The deny-list and the compiler filter are in place. The gateway payload filter is G11, and the intake display is G07/A7.

Companion skills: none named. Skills: adk-engineer 2026.10.28, adk-workflow-design 2026.10.28 (primary; mode "ordinary Python", `references/validation.md`).

Scope and changes outside `touches`:

- `pyproject.toml` and `uv.lock`: `networkx>=3.3` (runtime; design §5 names it, resolved 3.7) and `hypothesis>=6.170.17` (dev, for A4). No other package changed.
- `src/truelift/causal/rules.py`: the `parse_yaml` split above.
- `docs/architecture/truelift.md`: the Evidence cells of C2, C3 and C4 only.

Rulings (for the designer's checkpoint):

- R1. Fixed effects are one 0/1 dummy per level, named `<column>_<level>` and sorted. No level is dropped, as in the G03 spike. Levels come from `PanelSummary.levels`, which G07's profile must fill; with no levels the result is the compile error `missing_levels`. Cost if wrong: dropping a reference level later changes every config, which means a compiler version bump.
- R2. The `max_predictors` cap (10) and the VIF > 10 drop are **not** applied here. Both need the data, and `rules/identification.yaml` has no warning code to tell the user a control was dropped. Proposal: G09 applies them where the data is loaded, after Thao adds a warning code. Cost if wrong: a run with more than 10 or collinear predictors gets noisier nuisance models. It is not biased, provided G09 drops a predictor only when the back-door check still passes without it (dropping one can open a path through a collider). No golden case exceeds the cap.
- R3. An accepted risk turns sensitivity analysis on in Quick as well, so the robustness value can lead the report (design §5, `run_sensitivity`).
- R4. A node whose column is mapped `ignore`, `date`, `outcome` or a treatment role counts as having no data. A column in the ground-truth deny-list never counts as data (G05 R9).
- R5. The config holds `data_fingerprint`, `profile` and `compiler_version`, not hashes of the DAG or the mapping. The run record keeps those (C1, G09). So a wording-only DAG change leaves the config bytes unchanged. `output_dir` and `n_jobs` belong to the run, and the worker adds them.
- R6. Compile errors other than `missing_spend_column` have their messages in `compile.py`, not in `rules/`, because they are data-shape problems rather than econometric rules. They are `ambiguous_spend_column`, `treatment_not_a_rate`, `missing_date_column`, `missing_region_column`, `missing_levels`, `dummy_name_clash`, `not_a_feature`, `forbidden_column` and `invalid_margin`. Thao may want them moved.
- R7. The population column is never a control. Only the scaler uses it, as `population_col`, which is what the golden cases pin. The G03 spike had it in `x_cols`.
- R8. Back-door paths are enumerated as simple paths, which is fine for diagrams of tens of nodes. G31 should cap diagram size (about 40 nodes) before G13 can grow one.

Specialist controls left out deliberately: R2 (cap and VIF), with G09 as the trigger. There is no orchestration, model or side effect here, so the workflow skill's runtime cases (sequential, parallel, loop, callbacks) do not apply.

Human effort still owed: about 1–2 h.

- Decide whether `causal-macos` becomes a required check on `main`.
- Get Thao's code-owner review of `src/truelift/causal/**` (D18). It is a calendar wait while Thao's invitation is pending, so admin bypass applies as in G05.
- Accept or reject rulings R1–R8.

actual: not reported.

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
