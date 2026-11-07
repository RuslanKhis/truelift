# AGENTS.md

Instructions for coding agents and people working on truelift. `CLAUDE.md` imports this file.

## What this is

truelift is a local app that interviews a marketing leader, builds a causal DAG and measures discount ROI with doubleml-pipeline. The model talks and code decides. Read these first:

- Design: [docs/architecture/truelift.md](docs/architecture/truelift.md) (decisions `D…`, contracts `C…`, security rules `SB…`)
- Plan: [docs/plans/truelift.md](docs/plans/truelift.md)
- Tickets: [docs/tickets/truelift/](docs/tickets/truelift/). The ticket file is the source of truth for scope, acceptance, status and evidence.

## Commands

You need [uv](https://docs.astral.sh/uv/). uv provisions Python 3.12 itself.

| Command | What it does |
| --- | --- |
| `make dev` | Install the locked environment and the pre-commit hooks |
| `make check` | Guard, ruff, pytest and pip-audit. CI runs the same. The audit needs network. |
| `make dist` | Build the sdist and wheel, then check their contents |
| `make e2e` | End-to-end tests. None exist until G20, so it fails with "no tests ran". |
| `uv run pytest tests/test_guard.py` | Guard tests (offline) |

`uv.lock` is committed. Change dependencies only with `uv add` or `uv remove` and commit the lock with them.

## Confidentiality (C13, D13): read before every commit

The repository is public. Its history and its packages must never contain:

- anything under `private/`. Hackathon materials live there, on core developers' machines only.
- `*.ipynb` or `*.pdf` files, or `*.csv` files outside `data/sample/`.
- the hackathon truth-column prefix. Only `src/truelift/causal/forbidden.py` and `scripts/guard_public.py` may name it. The guard stores it encoded, so do not spell it out anywhere else: not in code, tests, docs, commit messages or PR text.
- API keys: Google (`AIza…`, `AQ.…`), Anthropic (`sk-ant-…`) or OpenAI (`sk-…`).
- terms that identify the source dataset: the hackathon's event and file names, or the earlier example market. The guard holds an encoded list. Use the neutral example (a pet-food brand in Germany) or the synthetic market in docs.

Never quote, copy or paraphrase hackathon files, and never name them in public code. The brief allows only two numbers: true ROI ≈ 2.50 and the expert linear estimate of 1.64 [95% CI −1.64, 4.92].

These are enforced by:

- `scripts/guard_public.py` (`--staged` in pre-commit; `--tree` and `--history` in CI; `--dist` in `make dist`);
- gitleaks, with the custom rules in `.gitleaks.toml` (pre-commit and a CI full-history scan).

Keep the key patterns in the guard and in `.gitleaks.toml` in step. A guard failure names the file and the rule but never the matched text. Do not bypass it with `--no-verify`.

Tests that need private materials are marked `@pytest.mark.private`. They skip with "private materials absent" unless `private/benchmark.yaml` exists.

## Settled constraints

- **D2.** The stage machine lives in code. Agents only propose.
- **D12.** The server binds to 127.0.0.1 only and requires a per-launch token. Never start ADK's own server.
- **Pinned artefacts.** Python 3.12, `google-adk` 2.12.x (exact version in `uv.lock`), `doubleml-pipeline==0.2.3`, and the model IDs in `src/truelift/models.yaml`. Changing any of them is a release-unit change (design §9).
- **No secrets** in code, prompts, logs or project files (C7, C13).

## Ownership

`CODEOWNERS` is the source. Thao owns `rules/` and `templates/` and reviews `src/truelift/causal/**` (D18). Changes to the guard and its configs need a code-owner review.

## Companion skills

G02 writes the companion-skill table here with resolved pins. Until then, use the table in the plan's "Web stack and companion skills" section.

## Working on a ticket

Pick work in Claude Code with "what can I grab?" (`.claude/skills/pick-ticket`). Work on a branch `g<NN>-<slug>`. Fill the ticket's Evidence section and status. Leave commits to the person unless they ask.
