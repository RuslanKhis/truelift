---
goal: G31
title: DAG builder and causal API routes
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-workflow-design
supporting_skills: [adk-fastapi-backend]
docs: []
blocked_by: [G06, G08]
touches: [src/truelift/causal/build.py, src/truelift/api/routes/dag.py, src/truelift/api/routes/results.py, tests/causal/test_build.py, tests/api/test_dag_routes.py]
parallel_safe: no
contracts: [C1, C3]
companion_skills: [fastapi]
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G06/A1, G08/A1]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 1.5-3
  review_and_verify: 0.5-1
  total: 2-4
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: verified_local
---

# G31 DAG builder and causal API routes

## Outcome

Confirmed facts plus a business-type template become a DAG version in code, and the real DAG, identification and results routes replace the G02 stubs (C1, C3; D3, D5). Added after the independent plan review, 2026-11-07.

## Scope

- In: `causal/build.py` applies confirmed facts from the G08 store to a G05 template as edge assertions and node mappings, marking unsupported edges `assumed` (design §5, "DAG construction"). Routes for DAG versions, identification results and the run digest replace the G02 stubs.
- Out: the interviewer (G13) and the narrative (G14).
- Route: `causal/build.py` called by the store's confirm route; `api/routes/dag.py` and `api/routes/results.py`.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [x] A1 Building from the same facts and template gives a byte-identical `dag/vN.yaml`; each edge cites its supporting fact ID or is marked `assumed` (C3).
- [x] A2 An edge cannot appear without a confirmed fact or a template default; a rejected proposal changes nothing in the built DAG (C1, C3).
- [x] A3 The DAG and identification routes return the current version and its block reasons in business words; the results route serves the digest, and each matches the generated client with no drift (C3).

Verification, automated: `uv run pytest tests/causal/test_build.py tests/api/test_dag_routes.py` exits 0 (offline).
Verification, manual: none.

## Evidence

Built on branch `g31-dag-builder` from `7450ef5`, 2026-11-27, Ruslan's machine (Apple M1, macOS 13.2.1, Python 3.12.16, FastAPI 0.141.1, networkx 3.7). Plain Python and FastAPI: no model and no ADK code, and no network in any test.

- `src/truelift/causal/build.py`: `build_dag(template, facts, mapping)` returns a `DagDraft`, which is the `content` of `dag/vN.yaml` (template ID, the G06 `Dag`, and per edge its fact IDs and sentence), plus the cited fact IDs. Two confirmed facts that disagree, an arrow in both directions, removing discount -> sales, a loop, or a column missing from the mapping each raise `BuildError` with a message in business words.
- `src/truelift/api/routes/dag.py`: real projects go through the store and the causal core. `GET` returns the version, `POST /build` builds or rebuilds, `PUT /edges/{id}/opinion` records an opinion, `POST /confirm` confirms, and `GET /identification` runs identification. The demo project still answers from the G02 fakes.
- `src/truelift/api/routes/results.py`: a real run's `runs/<id>/digest.json` is served only when `manifest.json` lists it with a matching sha256 (C10). Demo runs come from the fakes.
- Tests: `tests/causal/test_build.py` (17), `tests/api/test_dag_routes.py` (17).

Results (tier, outcome):

- pass_to_pass G06/A1 and G08/A1: `uv run pytest tests/causal/test_dag.py tests/store/test_knowledge.py` 72 passed on the base (run with the tracked changes stashed, **after** the change was written, not before) and 72 passed with the change.
- A1: `offline, pass`. The same facts in a shuffled order give the same YAML content and cites, and the stored form reads back. Two fresh stores with the same clock write byte-identical `dag/v1.yaml` files. Each edge carries its supporting fact IDs or is `assumed`, and its sentence comes from the template or is generated in words. Through the API, rebuilding from unchanged facts returns the same version and writes no new file.
- A2: `offline, pass`. Every built edge is either a template default or backed by a confirmed fact. Facts with status `assumed`, `unknown` or `contradicted` change nothing and are not cited. Through the API, a **rejected** proposal leaves the rebuilt DAG identical, and an accepted `no-edge` fact makes version 2 without that arrow. Confirming needs every edge answered (422 `edges_unreviewed`) and none Disagree (409 `edges_disputed`). A confirmed version turns `stale` when a cited fact changes (C1).
- A3: `offline, pass`. `GET /dag` returns the current version with each edge's basis, facts and opinion. `GET /dag/identification` returns blocks in business words: for example, "Ageing stock affects both when you discount and how much you sell…", with no node IDs. With facts that close every back door it returns `identified` and the adjustment set `[holiday_weeks, media]`. `GET /runs/{id}/results` serves a digest behind a matching manifest, and answers 409 with no manifest or a tampered hash, and 404 for an unknown run. `make client` regenerated `openapi.json` and `frontend/src/client`; `client-check: no drift`, and the client exports `dagBuild`. Frontend `typecheck` exit 0 and `npm test` 84 passed.
- Verification: `uv run pytest tests/causal/test_build.py tests/api/test_dag_routes.py` 34 passed, exit 0. `make check` exit 0: guard clean (256 files), ruff clean, 518 passed and 1 skipped, no client drift, pip-audit clean (2 named ignores), and npm audit below its high threshold (8 moderate, existing frontend tooling).

Contracts:

- C1: `offline`, G31/A1, G31/A2. A built version cites every fact it depends on and records the mapping's data fingerprint. Confirmation goes through the store's hash check. The run gate is G09.
- C3: `offline`, G31/A3. The identification route uses `truelift.causal.identify` and the rule-file messages.

Companion skills: `fastapi` at FastAPI 0.141.1 (bundled in the wheel; `Annotated` dependencies and return-type response models). Skills: adk-engineer 2026.10.28, adk-workflow-design 2026.10.28 (primary; ordinary Python), adk-fastapi-backend 2026.10.28 (supporting). Identity stays D12's launch token, not the skill's IdP pattern.

Scope and changes outside `touches`:

- `src/truelift/api/schemas.py`: `DagBuildIn` and an optional `DagVersion.template`. Both are additive; no existing field changed.
- `src/truelift/store/versions.py` and `src/truelift/store/project.py`: `read_version`, per-version opinions (`vN.opinions.yaml`, outside the hashed version) and `run_dir`. The store stays the only writer (C11).
- `openapi.json` and `frontend/src/client/`: regenerated with `make client`.
- `docs/architecture/truelift.md`: the Evidence cells of C1 and C3 only.

Rulings (for the designer's checkpoint):

- R1. How `supports` items are read (G08 left it to G31). Only `confirmed` facts are applied, in fact-ID order:
  - `edge(a -> b)` adds the arrow and drops a template-default arrow pointing the other way;
  - `no-edge(a -> b)` removes the arrow;
  - `node(a)` adds the factor;
  - `node(a)` together with exactly one `column(c)` in the same fact means a is measured by column c;
  - `column(c)` on its own does not change the diagram.

  Cost if wrong: G13's proposals must follow a different convention.
- R2. Building is an explicit `POST /dag/build`, which G13 or G16 calls after facts change. It is not automatic inside the store's accept route, as the ticket's Route line suggested. Accepting a fact then never fails on a diagram problem, and a build failure is shown on its own. Cost if wrong: one call moves into the accept route.
- R3. The mapping version's content is `{columns: [...], panel: {...}}`: `ColumnMapping` plus `PanelSummary` with `levels` (G06 R1). **G07 must write this shape.** Without `panel`, identification answers 409 `profile_needed`.
- R4. Opinions live beside the immutable version, so they never change its hash. Confirm needs every edge answered and none Disagree, because under D6 a disagreement goes through a proposal and a new version. The demo fakes keep their old behaviour.
- R5. Results: the run folder is found by scanning the projects' `runs/` folders. The manifest format is `{"files": {"digest.json": "<sha256>"}}`, and `digest.json` is in the `Results` shape. **G09 must write both**, adds the runs-table status check, and may replace the scan with an index lookup.
- R6. Effect modifiers, accepted risks and accepted proxies cannot be expressed in the `supports` grammar yet, so built DAGs have none. That means the average effect only, and an unobserved confounder can be fixed only by adding data or by a `no-edge` fact. This needs new `supports` kinds (a G08 parser change), decided with G12 (slot m6) and G16 (the remedies).
- R7. A factor the template lacks gets its role from where the facts put it (caused by the discount is a mediator; leads to both is a confounder; otherwise a predictor). Its label comes from any template's vocabulary, else its ID in words.
- R8. The identification route does not return warnings (`few_regions`, `left_out` and so on), because the API's `Identification` has no field for them. G16 or G17 adds the field when the UI shows them.

Specialist controls left out deliberately: R6 (modifiers, risks and proxies) waits for G12/G13/G16. There is no ADK, model or side effect here, so the workflow runtime cases do not apply. Ownership filtering does not apply either: this is a single local user behind the launch token (D12).

Human effort still owed: about 0.5–1 h. Ruslan reviews the PR himself; no other reviewer is requested (Ruslan, 2026-11-27, which covers D18 for `src/truelift/causal/build.py`). Review the routes and rulings R1–R8, and pass R3 to Chloe for G07 (#8) and the new client functions to her for G16 (#17).

actual: not reported.

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G31-dag-builder-and-causal-routes.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
