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
owner: Ruslan            # suggested owner; anyone may pick this ticket
status: verified_local
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

Execution scope: local repository plus GitHub Actions on the existing remote. No publishing to PyPI.

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

Session 2026-11-06, branch `g01-repo-foundation`, changes uncommitted. Toolchain: uv 0.13.7, CPython 3.12.16 (provisioned by uv), gitleaks 8.30.1, pytest 9.2.0, ruff 0.17.4, pip-audit 2.10.1, pre-commit 4.7.0. "Fresh clone" means this: the uncommitted G01 files were committed in a scratch copy of the repository, pushed to a scratch bare remote, and cloned again from it.

Acceptance:
- A1: `local, pass`. Fresh clone: `make check` exit 0; `uv run python -c "import truelift"` printed `0.0.1`.
- A2: `offline, pass`. `uv run pytest tests/test_guard.py`: 34 passed, 1 skipped (the private test, A4).
  - The guard exits 1 on staged fixtures for each case: `private/`, `.ipynb` (also in upper case), `.pdf`, a `.csv` outside `data/sample/`, and the truth prefix in a file not on the allowlist (also in lower case). It also exits 1 on each of the four key patterns.
  - It exits 0 for a clean stage, for `data/sample/*.csv`, for the two allowlisted files and for `tests/private/`.
  - Near misses pass: `risk-adjusted-…` and `FAQ.…`.
  - Output never contains the key or the prefix (tested).
  - On the real tree, `--tree` exits 0.
  - In a scratch clone, `pre-commit` blocked a commit of `private/a.txt`: guard hook exit 1, commit refused. That is `local, pass`.
- A3: `local, pass` for the content; `live, not run` for the CI run.
  - `.github/workflows/ci.yml` runs on every push and pull request. The `confidentiality` job uses `fetch-depth: 0` and runs `guard --tree`, `guard --history`, then gitleaks 8.30.1 (pinned, sha256-verified) `git --log-opts=--all`.
  - Current history is clean: `guard --history` reported "clean (82 blobs)". `gitleaks git --log-opts=--all` found no leaks across 11 commits. The fresh clone with G01 committed was also clean: 102 blobs, gitleaks no leaks.
  - The custom gitleaks rules caught all four fake keys. The near-miss file passed. The pre-commit gitleaks hook applied the custom `truelift-google-aq-key` rule.
  - Owed: the first GitHub Actions run after push.
- A4: `offline, pass`. `uv run pytest -m private -rs`: 1 collected, 1 skipped, "private materials absent"; `private/benchmark.yaml` is absent here.
- A5: `local, pass`.
  - `uv.lock` is created; it is committed with this change.
  - `make check` runs `uv export --locked` → `pip-audit --disable-pip --require-hashes` with the result "No known vulnerabilities found". It needs network.
  - pip-audit has no severity filter. It fails on every known vulnerability, which covers "high".
- A6: `local, pass`.
  - `make dist` built the sdist and wheel. `guard --dist` reported "clean (16 package members)". The sdist allowlist is `src/truelift`, `tests` and `scripts/guard_public.py`, plus the hatch defaults (README, LICENSE, NOTICE, pyproject, .gitignore).
  - The content check exits 1 for wheel and sdist fixtures holding `private/…`, a `.csv` outside `data/sample/`, an `.ipynb` or a `.pdf` (`offline, pass`).

Contracts and security rules:
- C13: evidenced, local; G01/A1–A6. The CI run (A3) is owed after push.
- SB15: evidenced, local; A5 (supply chain, Minimal). The lockfile is committed, `--locked` is on every `uv run`, and the audit runs in `make check`. CI actions are pinned to commit SHAs and the gitleaks binary is checksum-verified.
- SB16: evidenced, local; A2 (offline) and A3 (local) (secrets, Build). The guard checks the four key patterns, and gitleaks runs its default rules plus the four custom ones.

Companion skills: none (`companion_skills: []`).
Specialists: `adk-release-engineering` 2026.10.28 is primary, and `adk-tool-auth-and-secrets` 2026.10.28 supports. The two versions match.

Rulings:
- R1. The guard stores the truth prefix base64-encoded, so the literal is nowhere in the repository, not even in the guard. D13 allowed the literal in the guard; this is stricter. G06's `forbidden.py` may import `TRUTH_PREFIX` from the guard or keep its own literal, since it is allowlisted. Cost if wrong: none to the contract.
- R2. The prefix matches case-insensitively on its stem, without the trailing separator. This is stricter, and a false positive is possible but unlikely.
- R3. `--tree` scans tracked files plus untracked files that are not ignored, so `make check` catches a new file before it is staged. `--history` scans every blob reachable from any ref.
- R4. Only the top-level `private/` is denied. `tests/private/` (plan layout) is allowed.
- R5. `requires-python = ">=3.12,<3.13"` matches the pinned release unit. G23 widens it if needed.
- R6. `make e2e` runs `pytest -m e2e`. It exits 5 ("no tests ran") until G20 adds tests, so it never reports a pass that did not happen.
- R7. `scripts/tickets_to_github.py` already existed and is excluded from ruff (`extend-exclude`). Lint it in its own change.
- R8. pip-audit is stricter than "high" (see A5). Any ignore must be a named `--ignore-vuln` with a reason.

Controls left out at this profile: severity-based audit thresholds, SBOM generation, signed releases and wheel-content checks on PyPI upload. No goal publishes to PyPI. The release ticket adds these if publishing is ever authorised.

Resources that charge: none.

Human effort still owed (about 0.5–1 h):
- Review the diff. Look especially at the `scripts/guard_public.py` rules and the `.gitleaks.toml` regexes.
- Commit, push, and confirm both CI jobs pass on GitHub (A3 live).
- In GitHub branch protection for `main`, mark `ci / confidentiality guard and gitleaks (full history)` and `ci / make check and package content check` as required checks. C13 calls the CI job "required", which is a repository setting only an admin can change.
- Give `CODEOWNERS` Thao's GitHub handle: replace `@RuslanKhis` on the `/rules/`, `/templates/` and `/src/truelift/causal/` lines (D18). The only collaborator today is `RuslanKhis`.
- Each developer runs `make dev` once to install the hooks. The first gitleaks hook run downloads a Go toolchain, which takes a few minutes.

actual: not reported

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
