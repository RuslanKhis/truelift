---
goal: G01
title: Repo foundation and confidentiality guard
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-release-engineering
supporting_skills: [adk-tool-auth-and-secrets (secret patterns)]
docs: [adk-release-engineering/references/ci-eval-gates.md, adk-release-engineering/references/versioning.md]
blocked_by: []
touches: [pyproject.toml, uv.lock, Makefile, AGENTS.md, CLAUDE.md, CODEOWNERS, NOTICE, .pre-commit-config.yaml, .gitleaks.toml, scripts/guard_public.py, .github/workflows/ci.yml, tests/test_guard.py, tests/conftest.py, src/truelift/__init__.py]
parallel_safe: no
contracts: [C13]
companion_skills: []
security: [SB15, SB16]
design_system: none
contract_deltas: []
pass_to_pass: []
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 1.5-3
  review_and_verify: 0.5-1
  total: 2-4
  handoff: none
  calendar_waits: none
owner: Ruslan
status: ready
---

# G01 Repo foundation and confidentiality guard

## Outcome

A fresh clone builds and tests. Nothing private or secret can be committed or released (C13; D13).

## Scope

- In: `pyproject.toml` (uv, Python 3.12), package skeleton, `Makefile` (`dev`, `check`, `e2e`), the guard script, gitleaks config, pre-commit, CI workflow, CODEOWNERS (Thao on `rules/`, `templates/`, `src/truelift/causal/`), private-benchmark skip fixture, `AGENTS.md` with a one-line `CLAUDE.md`. Excluded: application code.
- Route: `scripts/guard_public.py` reads `git diff --cached --name-only` (pre-commit) or `git ls-files` (CI) and applies the deny rules from D13. gitleaks gets custom rules for `AIza[0-9A-Za-z_-]{35}`, `AQ\.[0-9A-Za-z_-]{20,}`, `sk-ant-[0-9A-Za-z_-]{20,}` and `sk-(proj-)?[0-9A-Za-z_-]{20,}`. A `pytest` marker `private` skips with the reason "private materials absent" when `private/benchmark.yaml` is missing.
- Depth: Floor items: secrets and confidentiality. Audit at Minimal depth (SB15).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 `make check` passes on a fresh clone, and `uv run python -c "import truelift"` succeeds (C13).
- [ ] A2 The guard exits non-zero on staged fixtures for each of these, and exits 0 on the clean tree: a file under `private/`; an `.ipynb`; a `.pdf`; a `.csv` outside `data/sample/`; the hackathon truth-column prefix in a non-allowlisted file; each of the four key patterns (C13, SB16).
- [ ] A3 CI runs the guard and gitleaks on every push and PR, with a full-history scan, and the current history is clean (C13).
- [ ] A4 `pytest -m private` is collected and skipped with that reason when `private/benchmark.yaml` is absent (C13).
- [ ] A5 `uv.lock` is committed, and `make check` runs `uv`/`pip-audit` failing on high findings (SB15).
- [ ] A6 `make dist` builds the sdist and wheel; a content check fails on any `.csv`, `.ipynb` or `.pdf` outside `data/sample/` and on any `private/` path (C13).

Verification, automated: `make check` exits 0; `uv run pytest tests/test_guard.py` exits 0 (offline).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G01-repo-foundation-and-confidentiality-guard.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
