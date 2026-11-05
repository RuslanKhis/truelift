---
goal: G07
title: Data intake, profiling and mapping validation
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-fastapi-backend
supporting_skills: []
docs: [adk-fastapi-backend/references/validation.md]
blocked_by: [G01, G02]
touches: [src/truelift/intake/, src/truelift/api/routes/intake.py, tests/intake/]
parallel_safe: no
contracts: [C12, C3, C4, C8, C11]
companion_skills: [fastapi]
security: [SB11]
design_system: none
contract_deltas: []
pass_to_pass: [G02/A1, G02/A6]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 3-5
  review_and_verify: 1-1.5
  total: 4-6.5
  handoff: 0.25
  calendar_waits: none
owner: Thao            # suggested owner; anyone may pick this ticket
status: ready
---

# G07 Data intake, profiling and mapping validation

## Outcome

An uploaded panel is checked, profiled and mapped to roles that the user can confirm only when they are valid (C12, C3, C4, C8, C11; D20).

## Scope

- In: `intake/profile.py` and `intake/validate.py` (pandas); upload and mapping routes replace the G02 stubs.
- Route: `intake/profile.py` and `intake/validate.py` (pandas); upload and mapping routes replace the G02 stubs.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 Only `.csv` files up to 50 MB (configurable) are accepted; other types and oversize files are rejected with a message. Files are stored in the project, never served inline (SB11, C12).
- [ ] A2 Panel detection: weekly dates, region and category keys, duplicate keys, gaps and malformed rows produce plain-language errors (C12).
- [ ] A3 A role fails validation when it breaks its rule: rate in [0, 1], spend ≥ 0, outcome numeric, population > 0. A failing role cannot be confirmed (C12).
- [ ] A4 A new upload with a different fingerprint marks the mapping and DAG as needing review. An unchanged schema carries the mapping proposal over (C12).
- [ ] A5 Profile observations (zero-discount share by region and season, missing values) become `data.md` proposals (C11).
- [ ] A6 The variation thresholds from `rules/identification.yaml` produce block reasons that `identify` uses (C3).
- [ ] A7 Columns matching the forbidden patterns are flagged "ground truth: excluded" and dropped from the profile sample that the gateway may send (C4, C8).

Verification, automated: `uv run pytest tests/intake` exits 0 (offline).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G07-data-intake-profiling-and-mapping-validation.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
