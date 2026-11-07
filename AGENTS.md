# AGENTS.md

Instructions for coding agents and people working on truelift. `CLAUDE.md` imports this file.

## What this is

truelift is a local app that interviews a marketing leader, builds a causal DAG and measures discount ROI with doubleml-pipeline. The model talks and code decides. Read these first:

- Design: [docs/architecture/truelift.md](docs/architecture/truelift.md) (decisions `D…`, contracts `C…`, security rules `SB…`)
- Plan: [docs/plans/truelift.md](docs/plans/truelift.md)
- Tickets: [docs/tickets/truelift/](docs/tickets/truelift/). The ticket file is the source of truth for scope, acceptance, status and evidence.

## Commands

You need [uv](https://docs.astral.sh/uv/) and Node ≥ 22.18 (for the generated API client). uv provisions Python 3.12 itself.

| Command | What it does |
| --- | --- |
| `make dev` | Install the locked environment, the frontend tooling (`npm ci`) and the pre-commit hooks |
| `make check` | Guard, ruff, pytest, client drift check, pip-audit and npm audit. CI runs the same. The audits need network. |
| `make client` | Dump `openapi.json` offline and regenerate `frontend/src/client`. Commit both after any API change. |
| `uv run truelift` | Start the local app on 127.0.0.1 with a fresh token and open the browser (`--no-browser` prints the link) |
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

## API contract (G02)

- The server binds 127.0.0.1 only. Every `/api` route needs `Authorization: Bearer <launch token>`; `/health` and the SPA shell are public. Host must be 127.0.0.1 or localhost on the launch port; POST, PUT, PATCH and DELETE need a same-origin `Origin`. No CORS.
- Errors always have the `ErrorBody` shape (`code`, `message`, `request_id`, optional `fields`), never a stack trace or the submitted input.
- `openapi.json` and `frontend/src/client/` are generated and committed. Change a route or model, then run `make client`; `make check` fails on drift.
- The agent stream (`POST /api/projects/{id}/agent/messages`, SSE) is out of the OpenAPI paths, but its `AgentEvent` types are in the generated client. See `src/truelift/api/stream.py` for the event order. One message at a time per project (409 `agent_busy`).
- Until G07–G14 and G31 land, the routes serve fakes from `src/truelift/api/fakes.py`. Fake triggers: an upload named `<IntakeErrorCode>.csv` is rejected with that code; an agent message `/scenario ai_unavailable` (or `budget_paused`, `turn_failed`) replays that recording.
- Vite dev server: run `TRUELIFT_DEV=1 TRUELIFT_DEV_ORIGINS=http://localhost:5173 uv run truelift --port 8000 --no-browser`, proxy `/api` to it, and open the printed `dev:` link. Dev mode also serves `/docs` and `/openapi.json`.

## Companion skills

Pins resolved on 2026-11-07 (G02). Load a companion at its pin when a ticket names it; a pin change is a recorded decision.

| Companion | Source and install | Pin | Load when | Scope notes |
| --- | --- | --- | --- | --- |
| `fastapi` | Bundled in the FastAPI wheel: `.venv/lib/python3.12/site-packages/fastapi/.agents/skills/fastapi/` after `uv sync` (or `uvx library-skills --claude`) | FastAPI 0.141.1 (from `uv.lock`; google-adk 2.12.0 caps it below 0.142) | backend routes | Identity follows D12, not the skill's IdP examples. Features from 0.142 on (native OpenTelemetry) are unavailable. |
| `react-router` | `npx skills add https://github.com/remix-run/react-router --skill react-router` | `remix-run/react-router@8f364c820ef698952e4bed876d6c93c895357692` | SPA routes | Data mode |
| `vercel-react-best-practices` | `npx skills add vercel-labs/agent-skills --skill vercel-react-best-practices` | `vercel-labs/agent-skills@063bee94c3f4df8453406c830b0a7df0f2860278` | UI goals | SPA: skip the server rules; TanStack Query, not SWR |
| `shadcn` | `npx skills add shadcn/ui` | `shadcn-ui/ui@4233ed1caded8c38f4bc14b14afe1f93ebcaf966` | UI goals | Tokens from `docs/design/DESIGN.md` (house design system); no default theme |
| `playwright-cli` | `npm i -g @playwright/cli@0.1.22 && playwright-cli install --skills` | 0.1.22 | G20 | Role locators; never wait for network idle on the stream |

Frontend tooling pins (exact, in `frontend/package.json`): `@hey-api/openapi-ts` 0.99.0, `typescript` 5.9.3, and an override `js-yaml` 4.3.2 (fixes three high advisories in openapi-ts's parser dependency; remove once openapi-ts ships it). CI uses Node 22.23.3.

## Working on a ticket

Pick work in Claude Code with "what can I grab?" (`.claude/skills/pick-ticket`). Work on a branch `g<NN>-<slug>`. Fill the ticket's Evidence section and status. Leave commits to the person unless they ask.
