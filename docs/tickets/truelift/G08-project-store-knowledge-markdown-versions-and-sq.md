---
goal: G08
title: Project store: knowledge Markdown, versions and SQLite
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-memory-architecture
supporting_skills: []
docs: [adk-memory-architecture/references/sessions-state.md, adk-memory-architecture/references/failure-recovery.md]
blocked_by: [G01, G02]
touches: [src/truelift/store/, src/truelift/api/routes/projects.py, tests/store/]
parallel_safe: no
contracts: [C11, C1]
companion_skills: [fastapi]
security: []
design_system: none
contract_deltas: []
pass_to_pass: [G02/A1]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3.5-5.5
  review_and_verify: 1-2
  total: 4.5-7.5
  handoff: none
  calendar_waits: none
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: done
---

# G08 Project store: knowledge Markdown, versions and SQLite

## Outcome

Business knowledge, DAGs and mappings persist as files the user can read, with proposals, contradictions and staleness enforced in code (C11, C1; D1, D4, D21).

## Scope

- In: `store/knowledge.py` (parser and writer for the D4 format), `store/proposals.py`, `store/versions.py` (immutable `vN` files plus a pointer), `store/db.py` (SQLAlchemy, WAL). Routes for proposals and confirmation.
- Route: `store/knowledge.py` (parser and writer for the D4 format), `store/proposals.py`, `store/versions.py` (immutable `vN` files plus a pointer), `store/db.py` (SQLAlchemy, WAL). Routes for proposals and confirmation.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [x] A1 Creating a project lays out `business.md`, `market.md`, `data.md`, `dag/`, `mapping/`, `proposals/` and `runs/`. Parse and write round-trip byte-identically (C11).
- [x] A2 A proposal changes nothing until it is accepted through the API. Rejecting leaves the files byte-identical (C11).
- [x] A3 A hand edit with a syntax error yields a parse error with the file and line, and no fact is dropped (C11).
- [x] A4 A proposal that changes a confirmed fact is marked `contradiction` and needs an explicit choice per fact. A batch accept cannot apply it (C11).
- [x] A5 Writes are atomic (temp file plus rename). An injected failure leaves the previous version intact and returns an error (C11).
- [x] A6 DAG and mapping versions are written before the pointer moves. Changing a fact that a confirmed DAG cites marks that DAG `stale` (C11, C1).
- [x] A7 A write carrying a stale version number returns 409 and overwrites nothing (C11). A DAG confirmation for a version that is no longer current is refused the same way (C1).
- [x] A8 Accepting a batch of proposals applies all of them or none: an injected failure on the third fact leaves the first two unapplied (C11).
- [x] A9 A database error or a locked `state.db` returns the generic 500 from G02; two concurrent writers to `state.db` serialise without loss (C11, SB13).

Verification, automated: `uv run pytest tests/store` exits 0 (offline).
Verification, manual: none.

## Evidence

Built in `src/truelift/store/` (`knowledge.py`, `proposals.py`, `versions.py`, `db.py`, `files.py`, `folder.py`, `project.py`, `errors.py`) and wired into `src/truelift/api/routes/projects.py`. Tests: `tests/store/` (81 tests). All runs 2026-11-07, Ruslan's machine (Apple M1, macOS 13.2.1, Python 3.12, SQLAlchemy 2.1.8, PyYAML 6.0.3).

- pass_to_pass G02/A1: `uv run pytest tests/api/test_auth.py` 42 passed before any change and 42 passed after (the new batch route is covered by the every-route 401 test). The full suite was 148 passed, 1 skipped before.
- A1: `offline, pass`. `test_knowledge.py`: the D4 example from the design, a hand-edited file (prose, extra front-matter key, metadata in any order, a quote containing ` · `, Unicode, no final newline), CRLF variants and the new-file template all parse and render byte-identically. `test_create_lays_out_the_project_folder` checks `business.md`, `market.md`, `data.md`, `project.yaml`, `dag/`, `mapping/`, `proposals/`, `runs/` and that no temp folder is left. Changing one fact rewrites only that fact's lines.
- A2: `offline, pass`. `test_proposals.py`: creating and listing proposals changes no project file; rejecting leaves every file except the proposal record byte-identical, including a rejected contradiction; accepting writes the fact (`F001`, status, interview source, date) and bumps `knowledge_version`; the same through the API in `test_api_accept_and_reject`.
- A3: `offline, pass`. Nine broken hand edits (malformed ID, bullet without ID, unknown status, missing source, unknown source, unknown key, bad `supports`, stray indented line, duplicate ID), four front-matter errors, cross-file duplicate IDs and invalid UTF-8 each give the file and line; the good facts are still listed, the text is kept, and a write is refused. The API answers 422 `parse_error` with `fields: [{loc: [file, line], message}]`; the files stay byte-identical.
- A4: `offline, pass`. A proposal that changes a confirmed fact is listed with `contradiction: true` and the confirmed answer's turn quote. A plain accept is 409 `contradiction_choice_needed`; a batch containing it is 409 `contradiction_in_batch` and applies nothing; accepting with `resolves_contradiction: true` applies it and keeps the replaced fact in the proposal record. Changing an `assumed` fact is not a contradiction. A batch whose second proposal would overwrite the first's fact is refused.
- A5: `offline, pass`. `test_files.py`: writes go through a temp file in the same folder plus `os.replace`; failures injected at the write (disk full after half the bytes), the fsync and the rename all leave the previous bytes, no temp file, and raise `SaveFailed`. Through the API the accept returns 500 `save_failed` with a generic message (no OS error text), the files are unchanged and the proposal stays pending.
- A6: `offline, pass`. `test_versions.py`: `vN.yaml` is replaced before `current` (call order recorded); a failure writing the version leaves the folder unchanged; a failure moving the pointer keeps the previous version current and the orphan `vN` is never overwritten. A confirmed DAG turns `stale` when a cited fact changes by proposal or by hand, or when its own file is edited, and stays `confirmed` when an uncited fact changes. Mapping versions keep their data fingerprint.
- A7: `offline, pass`. Stale `knowledge_version` on accept, reject and batch raises `StaleVersion` (API 409 `stale_version`) and writes nothing; a decided proposal cannot be decided again (409 `already_decided`). A DAG or mapping write with a stale `expected_current` and a confirmation of a version that is no longer current are refused with `StaleVersion` (status 409) and change no file. The HTTP route for DAG confirmation is G31's; it gets the 409 from the shared `StoreError` handler.
- A8: `offline, pass`. A failure injected on the third fact of a three-proposal batch leaves every file byte-identical and all three pending. A disk-full failure while replacing the third file rolls back the two files already replaced. A simulated crash at that point (no rollback run) is rolled back from the `.txn/` journal at the next open.
- A9: `offline, pass`. `test_db.py`: `state.db` is in WAL mode with a busy timeout; two engines writing 100 rows each at once lose nothing (200 rows), and two stores creating 10 projects each at once give 20 projects and 20 folders. A `BEGIN EXCLUSIVE` held by another connection makes `POST /api/projects` return the generic 500 (`internal_error`, request ID, no SQL or "locked" text) and leaves no folder; a database error on list does the same. A failed insert or commit leaves no project folder.
- Verification: `uv run pytest tests/store` 81 passed, run five times in a row. `make check` exit 0: guard clean (121 files), ruff clean, 229 passed and 1 skipped, no client drift, pip-audit clean (1 named ignore, unchanged), npm audit 0.
- Fixed during the run: the first `make check` showed one failure in the concurrent-writer test, `database is locked` from `PRAGMA journal_mode=WAL` on a new connection while the other engine was writing (SQLite does not apply the busy handler to that switch). `db.py` now checks the mode first and retries within the busy timeout; 30 repetitions of the race and every later run passed.

Contracts:

- C11: `offline`, G08/A1–A9. The store is the only writer; proposals change nothing until accepted; contradictions are surfaced and need their own decision; a changed cited fact makes the DAG stale. G13/A3 (agents hold no write tools) is still owed.
- C1: `offline`, G08/A6, G08/A7. Confirmation records the content hash of `vN` and the fingerprint of each cited fact, and status is computed from them; a confirmation for a version that is not current is refused. The run gate itself is G09/A2.

Companion skills: `fastapi` at FastAPI 0.141.1 (bundled skill, version from `uv.lock`). Skills: adk-engineer 2026.10.28, adk-memory-architecture 2026.10.28 (primary; `sessions-state.md` and `failure-recovery.md` were listed but G08 has no ADK session or retrieval code, so no SDK test applies).

Scope and changes outside `touches`:

- `pyproject.toml` and `uv.lock`: `sqlalchemy>=2.1.8` and `pyyaml>=6.0.3` are now direct dependencies (both were already locked through google-adk; no other package changed).
- `src/truelift/api/settings.py`: `projects_dir` (default `~/truelift/projects`), `state_dir` (default `~/.truelift`), `db_busy_timeout_s`; `TRUELIFT_PROJECTS_DIR` and `TRUELIFT_STATE_DIR` override them. `tests/api/support.py` points both at `tmp_path`, so no test touches the home folder.
- `src/truelift/api/app.py`: builds the `ProjectStore` (the database is created on first use, so `make client` and `create_app` create nothing). `src/truelift/api/errors.py`: one handler maps every `StoreError` to `ErrorBody`.
- API contract (`schemas.py`, `openapi.json`, `frontend/src/client/`): new `POST /api/projects/{project_id}/proposals/accept` (`ProposalBatchIn`) and the field `resolves_contradiction` on `ProposalDecisionIn`. Regenerated with `make client`.
- `docs/architecture/truelift.md`: the Evidence cells of C11 and C1 only.

Rulings (for the designer's checkpoint):

- R1. Every bullet in a knowledge file must carry a fact ID; a plain `- ` bullet is a parse error. Why: otherwise a fact typed by hand without an ID would be silently ignored (A3, "no fact is dropped"). Cost if wrong: users writing notes as bullets see errors; relax to "warning" in G16.
- R2. The explicit choice for a contradiction is `resolves_contradiction: true` on the single decision route; rejecting keeps the confirmed fact. G16's contradiction card must send it.
- R3. A DAG or mapping version file is an envelope (`version`, `created_at`, `cites`, `data_fingerprint`, `content`); G06/G31 and G07 own `content`. Staleness is computed on read from hashes, not stored as a flag.
- R4. `knowledge_version` lives in `project.yaml` in the project folder (the authority, D1), not in `state.db`. `project.yaml` is an addition to the A1 layout.
- R5. `supports` items are `edge(a -> b)`, `no-edge(a -> b)`, `node(a)` or `column(a)`. G31 interprets them; a new kind needs a parser change.
- R6. The demo project (`petfood-de`) is still served from the fakes on the project routes, and its ID is reserved, until G07, G09–G11, G14 and G31 replace their stubs.

Left out on purpose (MVP depth), with the trigger that adds them:

- Two truelift processes on one projects folder: locks are per process only; the second process is not blocked. Trigger: G23 installer, or any report of two windows.
- A project folder whose `state.db` row is gone (database deleted) is invisible and its name gives 409. Trigger: G25 (recovery after restart) or the first report; the fix is a re-index from the folders.
- Proposal kinds `mapping` and `dag_edit`: the store applies `fact` proposals only. G07 and G13/G31 add their appliers.
- No API route reads the knowledge files or lists parse errors; errors reach the user when they decide a proposal. G16 (knowledge view) or G13 (`get_knowledge` tool).
- `Project.data_version` stays `None` until G07.
- Schemathesis over the store routes (deferred from G02): not added; G29 (localhost security review).

Effort: `actual:` 0.5 h hands-on (Ruslan, 2026-11-07). Accepted by the owner, Ruslan, 2026-11-07. Still open for the designer checkpoint: rulings R1–R6 (Chloe for R2, whoever builds G06/G31/G07 for R3).

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G08-project-store-knowledge-markdown-versions-and-sq.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
