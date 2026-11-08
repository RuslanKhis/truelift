---
goal: G05
title: Rules, DAG templates and golden cases
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-agent-evaluation
supporting_skills: []
docs: [adk-agent-evaluation/references/deterministic-tests.md]
blocked_by: [G01]
touches: [rules/, templates/, tests/golden/]
parallel_safe: no
contracts: [C3, C2]
companion_skills: []
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G01/A2]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 4-6
  review_and_verify: 1-2
  total: 5-8
  handoff: 0.25
  calendar_waits: none
owner: Thao            # suggested owner; anyone may pick this ticket
status: done
---

# G05 Rules, DAG templates and golden cases

## Outcome

Econometric knowledge is written as data that code enforces and Thao verifies (C3, C2; D3, D18).

## Scope

- In: - `rules/identification.yaml`: minimum weeks, regions and rows; treatment-variation thresholds. - `rules/proxies.yaml`. - `rules/normalisation.yaml`: semantic type → scaler list. - `rules/cate.yaml`: maximum covariates and degree rule. - `rules/truth_sidecar.yaml`: the schema of a benchmark's `truth.yaml` (truth columns, hidden confounders, true ROI), which G04 writes and G06 reads (C4). - `templates/*.yaml`: one per business type, in Thao's own words, with nodes, roles, default edges and the slots that confirm each edge. - `tests/golden/*.yaml`: at least 15 cases, each giving a DAG plus mapping and the expected decision, adjustment set and `x_cols`/CATE.
- Route: YAML schemas as in design §5. A small loader with pydantic validation.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [x] A1 Each threshold in `rules/identification.yaml` has a value and a one-line source or rationale (C3).
- [x] A2 The templates cover the five business types and validate against the schema (C3).
- [x] A3 Each proxy rule has a caveat text the UI can show (C3).
- [x] A4 At least 15 golden cases, including a mediator trap, an unobserved confounder with no proxy, a proxy accepted, a descendant of the treatment, a collider, low variation and a percentage treatment with spend. Each states its expected outcome (C3, C2).
- [x] A5 CODEOWNERS names Thao, with Ruslan as second owner, for `rules/`, `templates/` and `src/truelift/causal/`, and `main` requires a code-owner review (C3).
- [x] A6 `rules/truth_sidecar.yaml` validates G04's seed-1 `truth.yaml` shape in a schema test (C4).

Verification, automated: `uv run pytest tests/golden -k schema` exits 0 (offline).
Verification, manual: none.

## Evidence

Taken by Ruslan instead of the suggested owner (Thao) on 2026-11-08. D18 makes Thao the owner and reviewer of `rules/` and `templates/`. Ruslan and Thao both cover the econometrics, so Ruslan reviewed and accepted the wording, thresholds and golden expectations on 2026-11-08 (Ruslan's decision, recorded here).

Built: `rules/identification.yaml`, `rules/proxies.yaml`, `rules/normalisation.yaml`, `rules/cate.yaml`, `rules/truth_sidecar.yaml` (a JSON Schema in YAML); five templates in `templates/`; the loader `src/truelift/causal/rules.py` (pydantic, duplicate-key-safe YAML); 25 golden cases `tests/golden/g01…g25_*.yaml` with their format `tests/golden/cases.py`; an independent reference `tests/golden/oracle.py` (plain-Python d-separation, no networkx); tests `tests/golden/test_*.py` (96). All runs 2026-11-08, Ruslan's machine (Apple M1, macOS 13.2.1, Python 3.12.16, pydantic 2.14.3, jsonschema 4.26.0).

- pass_to_pass G01/A2: `uv run pytest tests/test_guard.py` gave 43 passed, 1 skipped (the private test), but only **after** the change. It was not run before. The base commit `90ea157` passed both required CI checks, and this change touches no guard file.
- A1: `offline, pass`. All seven thresholds (`min_weeks` 52, `min_regions` 2, `min_rows` 200, `min_treated_share` 0.10, `min_untreated_share` 0.05, `min_treatment_levels` 3, `max_gap_share` 0.05) have a value, a unit and a one-line rationale. `test_schema_every_threshold_has_value_and_one_line_rationale` checks there is one line of 20–250 characters per threshold, and the loader refuses a threshold without a rationale. The `few_regions` warning (below 30, the pipeline's own warning) and the CATE degree rule (the pipeline's warning below 1,000 rows) cite doubleml-pipeline 0.2.3. That source was read in `.venv`: `evaluation/runner.py` (the n < 1000 warning, `auto_additive` with `df` 3 and `degree` 2) and `preprocessing/scalers.py` (scaler list names).
- A2: `offline, pass`. `brand_via_retailers`, `store_chain`, `online_shop`, `food_service` and `subscription_service` all load. Each has a unique treatment `discount` and outcome `sales`, an acyclic graph, nothing caused by sales, and roles that match the default edges (a confounder really reaches both; a mediator lies between the discount and sales). Each also has at least one confounder, one mediator, one candidate modifier and one edge that is only asked about. A node ID means the same kind of thing in every template. `test_templates_schema.py` covers this, and 12 broken-file cases in `test_schema_loader_rejects_invalid_files` each give the file and field.
- A3: `offline, pass`. All six proxy rules have a one-line caveat of at least 80 characters, known conditions, and `stands_for` nodes that exist in the templates. The three proxies for things a discount could move must be lagged or measured at the start of the week.
- A4: `offline, pass`. There are 25 cases. They cover the mediator trap (g03, g04, g23), an unobserved confounder with no proxy (g06, g07, g11), an accepted proxy (g08), descendants of the treatment (g04, g05, g23), colliders (g10, g11), low variation (g12–g15, g17) and a percentage treatment with spend (g18, g19). They also cover the back-door, risk acceptance, panel shape, CATE, normalisation, a ground-truth column and a spend treatment. Every block code and every template appears. Each case states its decision; identified cases also give the adjustment set, `x_cols`, fixed effects, CATE covariates and degree, and warnings, and seven give compile settings. `test_golden_oracle.py` recomputes every expectation independently and agrees on all 25. For each unobserved-confounder block it also checks by brute force that no set of the available columns would have worked. Changing four expectations on purpose (g03 `x_cols`, g11 one block, g18 threshold, g22 CATE) made four tests fail; the files were then restored.
- A5: `live, pass`. CODEOWNERS already names `@thithachthaotran @RuslanKhis` for `/rules/`, `/templates/` and `/src/truelift/causal/` (from G01; no change needed). On 2026-11-08, at Ruslan's request, `main` branch protection was set to require one approving review from a code owner (`require_code_owner_reviews: true`, `required_approving_review_count: 1`). The two required status checks were kept, and `enforce_admins` stays off. Read back with `gh api repos/RuslanKhis/truelift/branches/main/protection`. Thao's collaborator invitation (sent 2026-11-05, expires 2026-11-12) is still pending, so GitHub ignores Thao's CODEOWNERS lines until it is accepted. Until then `@RuslanKhis` is the only effective code owner, so Ruslan's own PRs merge by admin bypass after CI passes; this PR did.
- A6: `offline, pass` on the expected shape; the real file is owed by G04. `rules/truth_sidecar.yaml` passes `Draft202012Validator.check_schema`. The seed-1 shape in `tests/golden/fixtures/truth_seed1.yaml` validates (placeholder numbers). Eight broken variants are each rejected with their path: a truth column without the `truth_` prefix, no `true_roi`, ROI over the rate, an unknown treatment kind, an extra field, the hidden-confounder switch without names, heterogeneity without segments, and a bad hash. `test_schema_committed_sample_truth` is **skipped (not run)** until G04 commits `data/sample/truth.yaml`; G04/A1 must make it pass.
- Verification: `uv run pytest tests/golden -k schema` gave 68 passed and 1 skipped (that A6 sample test), exit 0. `uv run pytest tests/golden` gave 95 passed and 1 skipped. `make check` exit 0: guard clean (167 files), ruff clean, 324 passed and 2 skipped, no client drift, pip-audit clean (1 named ignore, unchanged), npm audit 0. `make dist` exit 0: guard clean (140 package members).

Contracts:

- C3: `offline`, G05/A1–A4. The thresholds, block messages in business words, proxy caveats and 25 oracle-checked golden cases are in place. Enforcement in `identify` is G06/A2 and G07/A6.
- C2: `offline`, G05/A4 (expectations only). Seven cases pin the treatment kind, sales and spend columns, `opt_threshold_roi` and scaler lists, and `missing_spend_column`. The compiler that must reproduce them is G06 (A3, A5, A6).
- C4 (via A6): `offline`, schema only. The sidecar requires the `truth_` prefix on every truth column; g24 pins that a ground-truth column is never a control.

Companion skills: none named by the ticket. Skills: adk-engineer 2026.10.28, adk-agent-evaluation (primary; `references/deterministic-tests.md`). There is no ADK or model code, so no SDK test applies.

Scope and changes outside `touches`:

- `src/truelift/causal/__init__.py` and `src/truelift/causal/rules.py` (new). The ticket's route asks for "a small loader with pydantic validation", and G06 and G07 need it at runtime, so it lives in the causal core rather than in the tests. It repeats the API's `NodeRole`, `SemanticType`, `Role` and `Remedy` values, so the core does not import the web layer; `test_schema_vocabularies_match_the_api` keeps them equal.
- `pyproject.toml` and `uv.lock`: `jsonschema>=4.26` is now a direct dependency. It was already locked at 4.26.0 through other packages, and no other package changed.
- `docs/architecture/truelift.md`: only the Evidence cell of C3.

Rulings (for the designer's checkpoint):

- R1. The five business types are a brand selling through retailers, a chain of own shops, an online shop, food service, and a subscription service. Why: the design says "five business types" but does not name them. Cost if wrong: one template swapped, and G12's `m1.business_type` choices follow.
- R2. Threshold values as listed in A1 (design §11 open decision "Identification thresholds", owner Thao). Why: the values are reasoned, not measured. Cost if wrong: users are blocked too often or too rarely. G07/A6 re-checks the values on the synthetic panel.
- R3. Adjustment rule `ancestral_v1`: every node with data that is an ancestor of the discount or of sales, minus anything the discount causes (van der Zander, Liśkiewicz and Textor 2019). Outcome predictors are therefore part of the adjustment set, not a separate "selected predictors" list. The `max_predictors` cap (10) and the VIF drop (> 10) apply at compile time with data (G06). Cost if wrong: G06 must change how the set is chosen, and the golden `x_cols` change with it.
- R4. C3a semantics. A node the discount causes blocks the run only when the DAG labels it a confounder, predictor or modifier, or names it as an effect modifier (a contradiction the user must resolve). A node correctly labelled `mediator` is left out silently. Cost if wrong: either mislabelled mediators slip through, or correct ones nag.
- R5. An unobserved confounder gives one block per node. `use_proxy` is offered only when `rules/proxies.yaml` has a rule for that node; `delivery_platform_promos` and `retailer_promo_calendar` have none today.
- R6. Scaling applies only to controls and CATE covariates. The outcome, treatment and spend are never scaled, because ROI is money ÷ money. Unit prices must be typed `index` at mapping time (G07), because `money` is treated as a regional total.
- R7. CATE: at most 3 covariates, keeping the first by column name; degree 2 everywhere (the pipeline default), `df` 3, no intercept.
- R8. A percentage treatment without a spend column is a compile error (`missing_spend_column`, C2), not an identification block.
- R9. A ground-truth column counts as "no data" for identification (C4), so a confounder known only through a truth column blocks the run.
- R10. The slot IDs the templates use (18, listed in `test_templates_schema.py`) are G12's to define in `templates/slots.yaml`. The template loader skips any file in `templates/` whose `schema` is not `truelift.template/1`.
- R11. Packaging: the wheel does not ship `rules/` or `templates/` yet. The loader reads them from the repository root, which is enough while phase 1 runs from source. G23 must ship them, and `DEFAULT_ROOT` must then point at the packaged copy.

Specialist controls left out deliberately: none. G05 is data plus deterministic tests, with no agent, model or effects.

actual: not reported.

Rulings R1–R11 and the review of `rules/`, `templates/` and the golden expectations: accepted by Ruslan, 2026-11-08.

Human effort still owed: none for G05. Two items now belong to other goals: Thao accepting the GitHub invitation before 2026-11-12 (a plan prerequisite), and G04 making `data/sample/truth.yaml` pass `test_schema_committed_sample_truth` (G04/A1).

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G05-rules-dag-templates-and-golden-cases.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
