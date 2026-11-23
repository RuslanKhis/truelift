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
status: verified_local
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
- [ ] A6 Region × week heterogeneity is documented: holiday weeks have higher ROI and the low season has negative ROI (C14).
- [ ] A7 The unobserved-confounder switch works: with it on, the generator omits the confounder column and `truth.yaml` records it as hidden (C14, C3).

Verification, automated: `uv run pytest tests/sample` exits 0 (offline).
Verification, manual: none.

## Evidence

Taken by Thao, the suggested owner, on 2026-11-23. Built: the generator `src/truelift/sample/` (`generator.py` for the data-generating process and writers, `diagnostics.py` for the three OLS reference estimates, `__main__.py` for the command line); the committed seed-1 sample `data/sample/panel.csv` (134 KB), `data/sample/truth.yaml` and `data/sample/README.md`; tests `tests/sample/test_sample.py` (26). All runs 2026-11-23 on Thao's machine (Windows 11 10.0.26200, Intel x86-64, Python 3.12.10, NumPy 2.5.4, PyYAML 6.0.3, jsonschema 4.26.0).

Design choices made here, for Thao's (owner's) review:

- Baseline sales per head are **additive** in the drivers (week level, distribution, media, competitor promotions), not multiplicative. A first multiplicative version left even the correctly adjusted OLS at about 2× the truth, so adding the mediator moved the estimate *towards* the truth and hid the trap. With the additive baseline, the adjusted reference lands within about 10% of the truth on every seed tried (1–8).
- The ROI levels (holiday 2.6, other weeks 1.5, low season −0.6, region shifts up to ±0.3) put seed 1's true ROI at 2.01. A first draft gave 2.49, too close to the hackathon's 2.50; D14 wants the synthetic market to differ on purpose.
- 40% of the effect travels through `store_traffic` (the mediator trap). `competitor_promo` is the confounder the switch hides.
- Every column is written with fixed decimals, LF line ends and no negative zero, so the bytes stay stable across platforms. Rows run region by region, then week by week.

Acceptance:

- pass_to_pass G01/A2, G01/A6: `uv run pytest tests/test_guard.py` gave 43 passed, 1 skipped (the private test), after the change. `guard_public.py --tree` is clean (177 files) and `--dist` is clean (150 package members). This change touches no guard file.
- A1: `offline, pass`. `test_cli_same_seed_same_sha256` runs `python -m truelift.sample generate` twice for seed 7: same sha256, same truth.yaml bytes, and a different hash for seed 8. truth.yaml's `panel.sha256` equals the file's hash. `test_committed_sample_is_seed_1` regenerates seed 1 and compares it byte for byte with `data/sample/` (sha256 `17acb6d6…c703552`). `test_schema_committed_sample_truth` from G05 now runs and passes; it was skipped before.
- A2: `offline, pass`. Σ `truth_incremental_revenue` ÷ Σ `discount_spend` read back from the committed CSV equals the generator's analytic value (2.0085068824088306) within 1e-6. Seeds 2, 11 and 20 also pass. Per row, incremental = `truth_roi` × spend and revenue = baseline + incremental, both within 1e-3.
- A3: `offline, pass`. Seed 1: naive OLS 8.08 (+302%); confounders, fixed effects and segment slopes 2.13 (+6%); the same plus `store_traffic` 1.25 (−38%). The README records these four rows. `test_readme_records_the_numbers` regenerates them, so the README cannot go stale silently. `test_traps_hold_across_seeds` checks that seeds 2–6 also show naive bias over 30% and a mediator drop over 20% of the truth.
- A4: `offline, pass`. For the default, hidden-confounder and no-heterogeneity variants, every `truth_` column in the header is listed in `truth_columns`, the list has nothing else, and the document passes `validate_truth()`. Treatment, spend, outcome, confounder and mediator columns all exist and none of them is a truth column.
- A5: `offline, pass`. `generate-bundle --seeds 1..20` wrote 20 folders with 20 distinct hashes in 0.4 s (the test allows 120 s); its seed 1 equals the committed panel. `data/sample/` holds one CSV, seed 1, and 136 KB in total (limit 5 MB).
- A6: `offline, pass`. Seed 1's true ROI by segment: holiday weeks 2.67 > other weeks 1.60 > 0 > low season −0.53, total 2.01. The README explains why in prose and lists the four values; `test_heterogeneity_documented` checks both. With `--no-heterogeneity`, every row has ROI 1.8.
- A7: `offline, pass`. With `--hidden-confounder`, the panel has no `competitor_promo` column and is otherwise identical to the default. truth.yaml sets the switch, names the column under `hidden_confounders` and leaves it out of `confounders`. On seed 1 the adjusted OLS then reads 1.78 (−11%); the README records this.
- Verification: `uv run pytest tests/sample` gave 26 passed, exit 0 (offline). The full suite gave 351 passed and 1 skipped (private). `ruff check` and `ruff format --check` are clean. The client drift check found no drift and npm audit found 0 vulnerabilities. `make` itself is not installed on this machine, so each `make check` step was run directly from the Makefile's recipes.
- **pip-audit is not clean, and not because of this change.** It reports CVE-2026-126360 in `opentelemetry-api` 1.42.1 (fixed in 1.45.2), which comes in through google-adk 2.12's cap. This branch changes no dependency; the finding is new since G05's run. Fixing it means a google-adk upgrade, which is a release-unit decision, or a new named exception in the Makefile (SB15). Both are for the maintainers, so neither is done here.

Contracts:

- C14: `offline`, generator side. A public panel with known truth, deterministic by seed, 20 seeds for coverage, `truth.yaml` in the G05 sidecar shape. The coverage scorer itself is G10/A5.
- C4: `offline`, G04/A4. Every truth column carries the `truth_` prefix and is listed in truth.yaml. The deny-list that keeps them out of features is G06/A4.
- C3: `offline`, G04/A3 and A7. The mediator trap and the hidden confounder are built in and measured. The run gate that blocks them is G06.

Companion skills: none named by the ticket. Skills: adk-engineer, adk-agent-evaluation (primary). There is no ADK or model code, so no SDK test applies.

Changes outside `touches`:

- `.gitattributes` (new). It marks `data/sample/*.csv` and `*.yaml` as `-text`. With `core.autocrlf=true` (as on this machine), git would otherwise rewrite the panel's line endings on checkout and break the sha256 that truth.yaml records (A1).
- `docs/tickets/truelift/G04-…md`: this Evidence section and the status.

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
