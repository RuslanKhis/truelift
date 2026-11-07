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
status: ready
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

- [ ] A1 Creating a project lays out `business.md`, `market.md`, `data.md`, `dag/`, `mapping/`, `proposals/` and `runs/`. Parse and write round-trip byte-identically (C11).
- [ ] A2 A proposal changes nothing until it is accepted through the API. Rejecting leaves the files byte-identical (C11).
- [ ] A3 A hand edit with a syntax error yields a parse error with the file and line, and no fact is dropped (C11).
- [ ] A4 A proposal that changes a confirmed fact is marked `contradiction` and needs an explicit choice per fact. A batch accept cannot apply it (C11).
- [ ] A5 Writes are atomic (temp file plus rename). An injected failure leaves the previous version intact and returns an error (C11).
- [ ] A6 DAG and mapping versions are written before the pointer moves. Changing a fact that a confirmed DAG cites marks that DAG `stale` (C11, C1).
- [ ] A7 A write carrying a stale version number returns 409 and overwrites nothing (C11). A DAG confirmation for a version that is no longer current is refused the same way (C1).
- [ ] A8 Accepting a batch of proposals applies all of them or none: an injected failure on the third fact leaves the first two unapplied (C11).
- [ ] A9 A database error or a locked `state.db` returns the generic 500 from G02; two concurrent writers to `state.db` serialise without loss (C11, SB13).

Verification, automated: `uv run pytest tests/store` exits 0 (offline).
Verification, manual: none.

## Evidence

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
