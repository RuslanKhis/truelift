# Implementation plan: truelift

Status: draft. Ready goals have been identified, and the cut line was confirmed by Ruslan on 2026-11-05. Independently reviewed on 2026-11-07; every finding is settled in *Changes after the independent review*.
Architecture: [docs/architecture/truelift.md](../architecture/truelift.md). Decisions (D), contracts (C) and requirements (R) are defined there and only referred to here.
Continuation source of truth: the tickets in `docs/tickets/truelift/` for status and evidence; this plan for the schedule and phases.

## Summary for the reader

- **Profile and phase 1.** MVP or pilot, self-hosted open source (design §3). Phase 1 is milestone **M1**: the full loop on `localhost`, run from source. That means interview → DAG edge cards → identification → compiled config → local pipeline run → grounded explanation. M1 passes the synthetic benchmark tier in CI and at the milestone, and the hackathon tier locally (C14). It ends with a demo and business and technical presentations to the hackathon organisers, whose feedback (W1) gates phase 2.
- **Effort and finish.** Phase 1 needs **101.5–165 human hours** across 23 goals and one wait (G01 at its actual 1 h): Ruslan 41–70 h, Thao 31–51 h, Chloe 29.5–44 h.
  - At about 2.75 h/week per person (0.55 h per working day, confirmed by Ruslan on 2026-11-07) with a 25% reserve, the schedule checker gives a finish of **128–220 working days**. At 2.5 h/week it would be 139–240 and would not fit.
  - The plan window is **235 working days**. Every load and the finish range fit, and the checker exits 0.
  - Two internal checkpoints show progress early:
    - **CP1**, the deterministic synthetic benchmark green (G10), at 65–130 days.
    - **CP2**, the agent-built benchmark green headless (G18), at 99–170 days.
  - At 3 h/week the finish would be 118–203 days.
- **Largest risks.**
  1. The critical path is a three-person chain (G05 and G10 Thao; G06, G31 and G09 Ruslan; G16, G17, G20 and G21 Chloe), with about 2 days of slack. Mitigation: protect those goals' hours, keep review handoffs short (recorded as waits on G06, G12 and G14), and apply the cut ladder at the first overrun.
  2. The hackathon ±25% target may be out of reach with any config: the expert estimate was −34% off, and the panel has only a few region clusters. Mitigation: C14 records a shortfall as a finding, and G19 diagnoses it.
  3. doubleml-pipeline is young: three releases in eight days. Mitigation: exact pin, plus a benchmark re-run on every upgrade (C9, G18).
- **Decisions needed from you.**
  - Confirm that Chloe owns the business presentation (G21), and who presents it.
- **Next prompt:** take a ready ticket (G02–G05) with "what can I grab?".

## Destination and constraints

**End result.** A CMO installs truelift and gets a correct, honestly uncertain answer about discount ROI from their own panel (design §2). Non-goals are listed in design §2. The stack is accepted (R7): React and TypeScript SPA, FastAPI, ADK in process, SQLite, uv. Authorization: this plan is design only. No goal publishes to PyPI, pushes outside the repo or uses the private files outside a core developer's machine (C13).

**Inspected repository.** At commit `ef65e18` the repo holds `README.md`, `LICENSE` (MIT) and `.gitignore`. `private/` and `data/*` are already ignored, with `!data/sample/` kept. There is no code yet. The layout below is **proposed**:

```text
pyproject.toml  uv.lock  Makefile  AGENTS.md  CLAUDE.md  CODEOWNERS  .pre-commit-config.yaml  .gitleaks.toml
scripts/guard_public.py
src/truelift/
  cli.py            # `truelift` launcher (D11, D12)
  api/              # FastAPI app, routes, auth middleware (D12)
  agents/           # interviewer.py, explainer.py, gateway.py (D2, D7)
  prompts/          # versioned instruction text
  causal/           # dag.py, identify.py, compile.py, forbidden.py (D3)
  intake/           # profile.py, validate.py (D20, C12)
  store/            # knowledge.py, versions.py, db.py (D1, D4, D21)
  worker/           # __main__.py, lifecycle.py (D8)
  explain/          # digest.py, verdicts.py, validate.py, template.py (D10)
  sample/           # synthetic generator (D14)
  bench/            # harness and scorer (D15)
  web/              # built SPA (generated in CI; not committed)
rules/  templates/  # Thao-owned YAML (D18)
data/sample/        # seed-1 synthetic panel, truth.yaml, persona_cmo.yaml
frontend/           # Vite + React + TS; src/client generated
tests/  tests/private/  (skips without private/benchmark.yaml)
```

**Pinned artefacts every goal inherits.**
- Model IDs: `gemini-3.8-flash` (default) and `claude-sonnet-5-5`, both in `src/truelift/models.yaml` (D7).
- `doubleml-pipeline==0.2.3`.
- `google-adk` 2.12.x, exact version in `uv.lock`.
- Python 3.12.
- Prompt versions in `src/truelift/prompts/`.

Changing any of these is a release-unit change (design §9).

## Delivery profile and capacity

| Phase | Delivers | Goals | Human hours, agent-assisted (range) | Capacity and reserve |
| --- | --- | --- | --- | --- |
| 1, M1 | The full loop from source, both benchmark tiers, demo and presentations to the organisers | G01–G22, W1 | 98.5–161 | 3 people × about 0.5 h per working day. 25% reserve. 235-day window. |
| 2, graduate for outside CMOs | Installer, comparison view, run re-adoption, interview evaluation, saturation and lags, governance note, security review, pilot | G23–G30 | 39–67 | When phase 1 is done and W1 has passed |

Estimates are person-hours of human effort with a coding agent: hands-on work plus review and verification. Ruslan knows ADK, so no multiplier applies to his goals. **Chloe's and Thao's goals that touch the agent (G12, G16) include ×1.5.** Presentation goals keep their own estimates.

| Person | Goals | Hours (phase 1) | Their capacity at 235 days × 0.5 h, 25% reserve |
| --- | --- | --- | --- |
| Ruslan (lead, agent, backend) | G01, G02, G03, G06, G08, G09, G11, G13, G14, G18 | 39–67.5 | 88 |
| Thao (econometrics) | G04, G05, G07, G10, G12, G19, G22 | 31–51 | 88 |
| Chloe (React) | G15, G16, G17, G20, G21 | 28.5–42.5 | 88 |

Owners are **suggestions** used for the schedule check, not assignments: anyone may self-assign a ticket whose blockers are done (GitHub issues #2–#24, board *truelift M1*). Load fits easily. The calendar is set by dependencies, by one person doing one goal at a time, and by W1.

### Capacity and cut line

Checker results for phase 1, run on 2026-11-05 with 0.5 h/day per person and 25% reserve. The independent review (2026-11-07) corrected four rows and added the missing work. After that the full M1 needs 0.55 h/day per person: **128–220 working days** (exit 0). The rows below are kept for the record; cuts and moves are now measured against that baseline.

| Scenario | Finish (working days) | Result |
| --- | --- | --- |
| **Full M1, as planned (confirmed)** | **134–231** | Fits a 235-day window (exit 0). Does not fit 115 days (exit 1). |
| CP1 only (G01, G03–G06, G08–G10) | 67–112 | Checkpoint, not a cut |
| CP2 only (adds G02, G07, G11–G14, G18) | 111–188 | Checkpoint, not a cut |
| Cut options 1–3 below applied | 130–225 | Gain of 4–6 days (corrected by the 2026-11-07 review) |
| Cut options plus Chloe takes G02 and Thao takes G03 | 135–233 | Worse than cuts alone: Chloe's UI chain starts later (re-modelled 2026-11-07) |
| Cut options plus a template-only explainer | 122–209 | About 10% gain for losing the LLM narrative. Rejected. |
| UI and presentations moved to phase 2 (headless M1) | 111–188 | 23–43 days gain for a much weaker CMO demo. Rejected. |
| Full M1 at 3 h/week each | 113–196 | The real lever, if hours can rise |

**Cut line (confirmed by Ruslan, 2026-11-05):** G01–G22 and W1 stay in M1, with a 235-day window and checkpoints CP1 and CP2. If work runs high, these items move to phase 2, in this order. Each step keeps a convincing end-to-end demo, but the checker shows they save hours more than days.

1. **G22 folds into G21.** A technical appendix replaces the second deck; Thao supplies a page of material through G19. This saves Thao 3–5 h.
2. **Claude support moves out of M1.** G11/A8 and G18/A4 become Gemini only, and the second provider moves to G26. This saves Ruslan about 1.5–3 h, but M1 then proves model-agnosticism only by design.
3. **Interview chat polish in G16** is limited to proposal cards with plain text, without streamed tool progress. This saves Chloe 2–3 h.
4. **Last resort: G19 hackathon tier with N = 3 repetitions instead of 5.** This lowers the bar and needs your explicit decision.

Never cut: the confidentiality guard (G01), identification and the run gate (G06, G09), the explanation validator (G14) and the synthetic benchmark (G10, G18). These are the floor and the core judgment.

The order below keeps each finished goal useful if time runs out early. By G10, the deterministic benchmark (a scripted DAG with no LLM) already proves the econometric core. By G13, a headless agent-built benchmark exists. The UI comes last.

### Schedule check

Command (Python 3.12, rerun 2026-11-07 after the independent review):

```bash
/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
  ~/.claude/skills/adk-system-designer/scripts/check_schedule.py \
  --plan docs/plans/truelift.md --tickets docs/tickets/truelift --design docs/architecture/truelift.md \
  --days 235 --reserve 0.25 --person "Ruslan=0.55" --person "Thao=0.55" --person "Chloe=0.55"
```

Result:
- 101.5–165 h of 290.81 h after reserve. Finish 127.58–220 working days. Exit 0.
- Longest chain, low and high: G01 → G05 → G06 → G31 → G16 → G17 → G20 → G21 → W1 (99.81 and 158.43 days). The finish is set by load, chiefly Ruslan's 41–70 h, not by the chain.
- At 0.5 h/day the same plan gives 139–240, which does not fit.
- Contracts: 16/16 cited.
- Coverage grid: every cell cites an acceptance item or gives an n/a reason.
- Security rules: 17/25 cited; 8 are n/a or deferred with reasons.

**Changes after the independent review (2026-11-07).** A reviewer in a fresh context checked prerequisites, settled mentions, claims and coverage, and returned 27 findings; Ruslan decided the four that needed a choice. Nothing was removed or weakened. Estimates rose by 3–4 h net: G31 is new at 2–4 h, and G08, G11 and G17 grew; G01 counts at its actual 1 h.

| Finding | Settlement |
| --- | --- |
| Hidden dependencies: G07 needs G05, G06 and G08; G08 needs G02; G09 needs G04; G11 needs G06 and G08; G12 needs G04 | Added to `blocked_by` in the plan and the tickets; handoff hours added to G07 and G09 |
| No goal built the DAG from confirmed facts, or the real DAG, identification and results routes | New goal **G31** (Ruslan, 2–4 h) after G06 and G08, feeding G13 and G16 |
| G15 could not check real G07 behaviour against stubs | G15/A2–A4 now test the stub contract; G20/A1 checks real payloads and rejection reasons (Ruslan's choice) |
| Cross-person reviews were not modelled | Waits of 1.33–2.67 days on G06 (Thao's review), G12 (Ruslan's phrasing check) and G14 (Thao's review) |
| G06 needs G04's truth-sidecar format | G05 fixes `rules/truth_sidecar.yaml` (A6); G04 and G06 follow it; no new dependency |
| With the missing work the plan no longer fitted at 2.5 h/week (237–241 days) | Capacity raised to about 2.75 h/week per person (Ruslan's choice): 128–220 days. The cut ladder stays as the fallback |
| G19 sends hackathon data to the LLM | Allowed by Ruslan: disclosed categories under C8, never truth columns (R10 revised). No approval wait |
| Private results in public notes (G03, G19, design §9) | G03's note uses the stand-in panel; G19 records counts and pass or shortfall; numbers stay in `private/` |
| Dataset-identifying wording in public history | Accepted exception (Ruslan). The guard now denies an encoded list of identifying terms in the tree, staged files and packages (D13) |
| "6 regions" and "6 clusters" left in the design and plan | Reworded to "a few regions" |
| Missing UI: ledger page, budget view, "AI unavailable" and "AI paused" banners | G17/A6 and G15/A6 |
| LLM grid: lost-response spend, other rejections and egress untested | G11/A9 (socket egress, LiteLLM cost map off), G11/A10 (400, safety block, context too long), G11/A11 (lost-response estimate) |
| SQLite, disk and upload grid cells with wrong citations or n/a reasons | Re-cited: G08/A9 (database errors, concurrent writers), G08/A5 (disk full), G07/A1 (atomic upload, size cap), G03/A2 (RAM caps), G13/A4 (stored text) |
| Action grid: partial apply and stale DAG confirmation cited the wrong items | G08/A8 (all-or-nothing batch) and G08/A7 (stale confirmation) |
| Code-owner review not enforced; Thao the sole owner of her own paths | Ruslan added as second owner of `rules/` and `templates/`; G05/A5 now requires the branch-protection setting |
| Checker command lacked `--tickets` | Fixed above |
| Claims: Risk 1, the cut rows, the headless gain, CP1 and CP2 dates, R13 | Corrected from the checker and the reviewer's re-runs |
| Documentation | G06–G22 ticket statuses set to `proposed`; G17 and G20–G22 "In:" filled; G06 touches `ci.yml`; G04/A7 tests the unobserved-confounder switch; G02/A7 keeps C15 (a double send would double model spend) |
| Prerequisites without a goal | Listed under *Prerequisites outside the goals* below |

**Prerequisites outside the goals** (owner in brackets):
- Thao and Chloe accept their GitHub invitations before **2026-11-12**, when the invitations expire (Ruslan re-invites if needed). Until then Thao's CODEOWNERS lines are ignored.
- Enable "Require review from Code Owners" on `main` once Thao has accepted (Ruslan; G05/A5).
- LLM keys and live-spend authorisation for G03/A4, G11/A8, G13 and G18/A4, within the $20/month budget (Ruslan).
- The private materials on the machine that runs G12/A3 and G19 (Ruslan, or Thao if she runs them).
- 3–10 h of unattended compute for the full benchmark tiers (G10/A5, G18/A2), run outside the people's hours.
- Booking the organisers' review session for W1 (Ruslan, once G21 and G22 are scheduled).

**Changes at checkpoint 1 (2026-11-07, after G01):** all eight G01 rulings were accepted by Ruslan. No contract changed, no estimate moved, and nothing was removed or weakened.

| Change | Why |
| --- | --- |
| D13 revised: the truth prefix is stored only base64-encoded, in the guard and in G06's `forbidden.py` (G01 R1) | The literal never enters the public repo, its history or packages; stricter than D13 as first written |
| D13 revised: case-insensitive stem match; only the top-level `private/` is denied; the guard's four modes are named (G01 R2–R4) | Recorded what G01 built so later goals rely on it |
| Python pinned `>=3.12,<3.13` (G01 R5) | Matches the release unit; G23 widens it |
| SB15: pip-audit fails on any known vulnerability, and exceptions are named in the `Makefile` (G01 R8) | pip-audit cannot filter by severity; stricter than "high" |
| Repo conventions: `make e2e` fails with "no tests ran" until G20; `scripts/tickets_to_github.py` stays outside ruff until a change of its own (G01 R6, R7) | Never report a pass that did not happen; keep G01 inside its touches |
| G06 scope line: `forbidden.py` holds the encoded prefix and tests it against the guard's | Follows from R1 |

**Changes after the first failing run:**

| Change | Why |
| --- | --- |
| [G07](../tickets/truelift/G07-data-intake-profiling-and-mapping-validation.md) now depends on G02 | Its routes replace G02 stubs |
| Handoff hours added to G04, G05, G07 (from G01) and G22 (from G20) | Cross-person dependencies |
| `mentions_only` settled for G02, G04, G15, G16, G17, G21, G22 | Prose references only |
| Window moved from 115 to 235 days | Confirmed cut line |
| Phase 1 goal entries moved into tickets; SB03 dropped from G02 (proved by G13/A7) | Tickets are the goal's home; the checker found no G02 item for SB03 |

No dependency, wait or review was removed.

```yaml
- goal: G01
  phase: 1
  hands_on: 0.75
  review: 0.25
  total: 1
  owner: Ruslan
  blocked_by: []
  calendar_waits: none
  wait_days: 0
  handoff: 0
  contracts: [C13]
  security: [SB15, SB16]
  mentions_only: []
  type: implementation
  status: done
- goal: G02
  phase: 1
  hands_on: 2-3
  review: 1-2
  total: 3-5
  owner: Ruslan
  blocked_by: [G01]
  calendar_waits: none
  wait_days: 0
  handoff: 0
  contracts: [C16, C15]
  security: [SB01, SB02, SB05, SB06, SB07, SB08, SB09, SB13]
  mentions_only: [G07]
  type: implementation
  status: done
- goal: G03
  phase: 1
  hands_on: 2-4
  review: 0.5-1
  total: 2.5-5
  owner: Ruslan
  blocked_by: [G01]
  calendar_waits: none
  wait_days: 0
  handoff: 0
  contracts: [C2, C9, C7]
  security: []
  mentions_only: []
  type: discovery
  status: done
- goal: G04
  phase: 1
  hands_on: 5-8
  review: 1-2
  total: 6-10
  owner: Thao
  blocked_by: [G01]
  calendar_waits: none
  wait_days: 0
  handoff: 0.25
  contracts: [C14, C4, C3]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G05
  phase: 1
  hands_on: 4-6
  review: 1-2
  total: 5-8
  owner: Thao
  blocked_by: [G01]
  calendar_waits: none
  wait_days: 0
  handoff: 0.25
  contracts: [C3, C2]
  security: []
  mentions_only: [G04]
  type: implementation
  status: planned
- goal: G06
  phase: 1
  hands_on: 4-6
  review: 1-2
  total: 5-8
  owner: Ruslan
  blocked_by: [G03, G05]
  calendar_waits: Thao's code-owner review (D18)
  wait_days: 1.33-2.67
  handoff: 0.5
  contracts: [C2, C3, C4]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G07
  phase: 1
  hands_on: 3-5
  review: 1-1.5
  total: 4-6.5
  owner: Thao
  blocked_by: [G01, G02, G05, G06, G08]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C12, C3, C4, C8, C11]
  security: [SB11]
  mentions_only: []
  type: implementation
  status: planned
- goal: G08
  phase: 1
  hands_on: 3.5-5.5
  review: 1-2
  total: 4.5-7.5
  owner: Ruslan
  blocked_by: [G01, G02]
  calendar_waits: none
  wait_days: 0
  handoff: 0
  contracts: [C11, C1]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G31
  phase: 1
  hands_on: 1.5-3
  review: 0.5-1
  total: 2-4
  owner: Ruslan
  blocked_by: [G06, G08]
  calendar_waits: none
  wait_days: 0
  handoff: 0
  contracts: [C1, C3]
  security: []
  mentions_only: [G14]
  type: implementation
  status: planned
- goal: G09
  phase: 1
  hands_on: 4-6
  review: 1-2
  total: 5-8
  owner: Ruslan
  blocked_by: [G04, G06, G08]
  calendar_waits: none
  wait_days: 0
  handoff: 0.25
  contracts: [C1, C9, C10, C14]
  security: [SB19]
  mentions_only: []
  type: implementation
  status: planned
- goal: G10
  phase: 1
  hands_on: 3-5
  review: 1-2
  total: 4-7
  owner: Thao
  blocked_by: [G04, G09]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C5, C6, C10, C14]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G11
  phase: 1
  hands_on: 3.5-6
  review: 1-2
  total: 4.5-8
  owner: Ruslan
  blocked_by: [G02, G03, G06, G08]
  calendar_waits: none
  wait_days: 0
  handoff: 0
  contracts: [C7, C8, C15]
  security: [SB14, SB19]
  mentions_only: []
  type: implementation
  status: planned
- goal: G12
  phase: 1
  hands_on: 4-6
  review: 1-2
  total: 5-8
  owner: Thao
  blocked_by: [G04, G05]
  calendar_waits: Ruslan reads the question phrasing (manual check)
  wait_days: 1.33-2.67
  handoff: 0
  contracts: [C3, C11, C14, C13]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G13
  phase: 1
  hands_on: 4-7
  review: 1.5-2.5
  total: 5.5-9.5
  owner: Ruslan
  blocked_by: [G06, G07, G08, G11, G12, G31]
  calendar_waits: none
  wait_days: 0
  handoff: 1
  contracts: [C1, C11, C15]
  security: [SB03, SB17]
  mentions_only: []
  type: implementation
  status: planned
- goal: G14
  phase: 1
  hands_on: 3-5
  review: 1-2
  total: 4-7
  owner: Ruslan
  blocked_by: [G10, G11]
  calendar_waits: Thao's review (G14/A5)
  wait_days: 1.33-2.67
  handoff: 0.5
  contracts: [C5, C6]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G15
  phase: 1
  hands_on: 5-7
  review: 1-2
  total: 6-9
  owner: Chloe
  blocked_by: [G02]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C7, C8, C12]
  security: [SB10]
  mentions_only: [G07]
  type: implementation
  status: planned
- goal: G16
  phase: 1
  hands_on: 7-10
  review: 2-3
  total: 9-13
  owner: Chloe
  blocked_by: [G15, G06, G08, G31]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C1, C3, C11]
  security: [SB10]
  mentions_only: [G13]
  type: implementation
  status: planned
- goal: G17
  phase: 1
  hands_on: 6-8.5
  review: 1-2
  total: 7-10.5
  owner: Chloe
  blocked_by: [G16, G09, G10]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C5, C6, C10]
  security: [SB10]
  mentions_only: [G14]
  type: implementation
  status: planned
- goal: G18
  phase: 1
  hands_on: 3-5
  review: 1-2
  total: 4-7
  owner: Ruslan
  blocked_by: [G13, G10]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C14, C2]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G19
  phase: 1
  hands_on: 3-5
  review: 1-1.5
  total: 4-6.5
  owner: Thao
  blocked_by: [G18]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C14, C13]
  security: []
  mentions_only: []
  type: implementation
  status: planned
- goal: G20
  phase: 1
  hands_on: 3-4
  review: 1-1.5
  total: 4-5.5
  owner: Chloe
  blocked_by: [G17, G18, G14, G13]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C1, C5, C6, C8, C10]
  security: []
  mentions_only: []
  type: journey
  status: planned
- goal: G21
  phase: 1
  hands_on: 3-5
  review: 0.5-1
  total: 3.5-6
  owner: Chloe
  blocked_by: [G19, G20]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C14]
  security: []
  mentions_only: [G22]
  type: presentation
  status: planned
- goal: G22
  phase: 1
  hands_on: 2.5-4
  review: 0.5-1
  total: 3-5
  owner: Thao
  blocked_by: [G19, G20]
  calendar_waits: none
  wait_days: 0
  handoff: 0.5
  contracts: [C14, C3]
  security: []
  mentions_only: [G21]
  type: presentation
  status: planned
- goal: W1
  phase: 1
  hands_on: 0
  review: 0
  total: 0
  blocked_by: [G21, G22]
  calendar_waits: organisers' review session and written feedback
  wait_days: 10-20
  contracts: []
  security: []
  mentions_only: []
  type: presentation
  status: planned
- goal: G23
  phase: 2
  total: 6-10
  owner: Ruslan
  blocked_by: [W1]
  contracts: []
  type: implementation
  status: planned
- goal: G24
  phase: 2
  total: 5-8
  owner: Chloe
  blocked_by: [W1]
  contracts: [C9]
  type: implementation
  status: planned
- goal: G25
  phase: 2
  total: 3-5
  owner: Ruslan
  blocked_by: [W1]
  contracts: [C10]
  type: implementation
  status: planned
- goal: G26
  phase: 2
  total: 6-10
  owner: Thao
  blocked_by: [W1]
  contracts: [C11, C8]
  type: implementation
  status: planned
- goal: G27
  phase: 2
  total: 5-8
  owner: Thao
  blocked_by: [G26]
  contracts: [C2, C3]
  type: implementation
  status: planned
- goal: G28
  phase: 2
  total: 3-5
  owner: Ruslan
  blocked_by: [W1]
  contracts: [C8]
  type: governance
  status: planned
- goal: G29
  phase: 2
  total: 3-6
  owner: Ruslan
  blocked_by: [G23]
  contracts: [C16, C7]
  security: [SB22]
  type: implementation
  status: planned
- goal: G30
  phase: 2
  total: 8-15
  owner: Chloe
  blocked_by: [G23, G26, G28, G29]
  contracts: [C14]
  type: journey
  status: planned
```

## Implementation map

| Contract / decision | Component and integration point | Hosting responsibility | Primary skill | Verification still needed |
| --- | --- | --- | --- | --- |
| C1, D2 | Run-gate function in `api/routes/runs.py`, rechecked in `worker/__main__.py` | none | `adk-workflow-design` | G09/A2 |
| C2, C3, C4, D3 | `causal/compile.py`, `identify.py`, `forbidden.py`; YAML in `rules/` and `templates/` | none | `adk-workflow-design` (ordinary code); Thao reviews | G06, G05 |
| C5, C6, D10 | `explain/digest.py`, `verdicts.py`, `validate.py`; Explainer `output_schema` | none | `adk-model-and-output-contracts` | G14/A2–A4 |
| C7, C8, C15, D7, D17 | `agents/gateway.py`: `before_model_callback`, keyring, ledger table | none (provider is external) | `adk-operational-guardrails` | G11 |
| C10, D8 | `worker/` process group, `state.db` runs table, startup reconcile | none | `adk-workflow-design` | G09/A3–A9 |
| C11, D1, D4 | `store/knowledge.py` (parser and writer), `proposals/`, `versions.py` | none | `adk-memory-architecture` | G08 |
| C12, D20 | `intake/profile.py`, `intake/validate.py` | none | `adk-fastapi-backend` | G07 |
| C13, D13 | `scripts/guard_public.py`, `.gitleaks.toml`, CI workflow | GitHub Actions | `adk-release-engineering` | G01 |
| C14, D14, D15 | `sample/`, `bench/`; CI smoke job | GitHub Actions (CPU minutes) | `adk-agent-evaluation` | G04, G10, G18, G19 |
| C16, D12 | `api/auth.py` middleware; `cli.py` launch URL | none | `adk-fastapi-backend` | G02 |

## Web stack and companion skills

This follows the designer's web defaults with three deviations:
- Identity is a launch token instead of IAP or Firebase (D12).
- Hosting is local, not Cloud Run (design §3).
- React Flow with ELK is added for the DAG graph (D6).

G02 wrote the companion table into [`AGENTS.md`](../../AGENTS.md#companion-skills) with resolved pins (2026-11-07). That table is the source; this section no longer repeats it.

## Goals and dependencies

| ID and goal | Phase | Type | Human hours | Depends on | Primary skill | State |
| --- | --- | --- | --- | --- | --- | --- |
| [G01](../tickets/truelift/G01-repo-foundation-and-confidentiality-guard.md) Repo foundation and confidentiality guard | 1 | implementation | 1 (actual; est. 2–4) | — | `adk-release-engineering` | done |
| [G02](../tickets/truelift/G02-api-skeleton-localhost-auth-stream-contract-and.md) API skeleton, localhost auth, stream contract, generated client | 1 | implementation | 3–5 (actual 0.5) | G01 | `adk-fastapi-backend` | done |
| [G03](../tickets/truelift/G03-pipeline-feasibility-spike.md) Pipeline feasibility spike | 1 | discovery | 2.5–5 | G01 | `adk-engineer` | done |
| [G04](../tickets/truelift/G04-synthetic-market-generator-and-truth.md) Synthetic market generator and truth | 1 | implementation | 6–10 | G01 | `adk-agent-evaluation` | ready |
| [G05](../tickets/truelift/G05-rules-dag-templates-and-golden-cases.md) Rules, DAG templates and golden cases | 1 | implementation | 5–8 | G01 | `adk-agent-evaluation` | ready |
| [G06](../tickets/truelift/G06-causal-core-dag-identification-and-config-compil.md) Causal core: DAG, identification, compiler | 1 | implementation | 5–8 | G03, G05 | `adk-workflow-design` | proposed |
| G07 Data intake, profiling and mapping validation | 1 | implementation | 4–6.5 | G02, G05, G06, G08 | `adk-fastapi-backend` | proposed |
| [G08](../tickets/truelift/G08-project-store-knowledge-markdown-versions-and-sq.md) Project store: knowledge Markdown, versions, SQLite | 1 | implementation | 4.5–7.5 | G02 | `adk-memory-architecture` | proposed |
| [G31](../tickets/truelift/G31-dag-builder-and-causal-routes.md) DAG builder and causal API routes (added by the 2026-11-07 review) | 1 | implementation | 2–4 | G06, G08 | `adk-workflow-design` | proposed |
| [G09](../tickets/truelift/G09-pipeline-worker-and-run-lifecycle.md) Pipeline worker and run lifecycle | 1 | implementation | 5–8 | G04, G06, G08 | `adk-workflow-design` | proposed |
| [G10](../tickets/truelift/G10-findings-digest-verdicts-scorer-and-deterministi.md) Findings digest, verdicts, scorer, deterministic synthetic tier | 1 | implementation | 4–7 | G04, G09 | `adk-agent-evaluation` | proposed |
| [G11](../tickets/truelift/G11-model-gateway-keys-consent-payload-limits-and-bu.md) Model gateway: keys, consent, payload, budget | 1 | implementation | 4.5–8 | G02, G03, G06, G08 | `adk-operational-guardrails` | proposed |
| [G12](../tickets/truelift/G12-question-bank-slot-catalogue-and-personas.md) Question bank, slot catalogue and personas | 1 | implementation | 5–8 | G04, G05 | `adk-agent-instructions` | proposed |
| [G13](../tickets/truelift/G13-interviewer-agent.md) Interviewer agent | 1 | implementation | 5.5–9.5 | G06, G07, G08, G11, G12, G31 | `adk-workflow-design` | proposed |
| [G14](../tickets/truelift/G14-explainer-agent-with-grounded-narrative.md) Explainer agent with grounded narrative | 1 | implementation | 4–7 | G10, G11 | `adk-model-and-output-contracts` | proposed |
| [G15](../tickets/truelift/G15-ui-shell-setup-and-consent-upload-and-mapping.md) UI: shell, setup and consent, upload and mapping | 1 | implementation | 6–9 | G02 | `adk-frontend-integration` | proposed |
| [G16](../tickets/truelift/G16-ui-interview-chat-edge-cards-and-dag-graph.md) UI: interview chat, edge cards, DAG graph | 1 | implementation | 9–13 | G15, G06, G08, G31 | `adk-frontend-integration` | proposed |
| [G17](../tickets/truelift/G17-ui-run-progress-and-results.md) UI: run progress and results | 1 | implementation | 7–10.5 | G16, G09, G10 | `adk-frontend-integration` | proposed |
| [G18](../tickets/truelift/G18-agent-driven-benchmark-and-ci-smoke.md) Agent-driven benchmark and CI smoke | 1 | implementation | 4–7 | G13, G10 | `adk-agent-evaluation` | proposed |
| [G19](../tickets/truelift/G19-hackathon-tier-and-answer-key-comparison-local-o.md) Hackathon tier and answer-key comparison (local) | 1 | implementation | 4–6.5 | G18 | `adk-agent-evaluation` | proposed |
| [G20](../tickets/truelift/G20-end-to-end-journey-and-demo-script.md) End-to-end journey and demo script | 1 | journey | 4–5.5 | G17, G18, G14, G13 | `adk-agent-evaluation` | proposed |
| [G21](../tickets/truelift/G21-presentation-to-organisers-business.md) Presentation to organisers: business | 1 | presentation | 3.5–6 | G19, G20 | `adk-presenter` | proposed |
| [G22](../tickets/truelift/G22-presentation-to-organisers-technical.md) Presentation to organisers: technical | 1 | presentation | 3–5 | G19, G20 | `adk-presenter` | proposed |
| W1 Organisers' review and feedback | 1 | wait | 0 (10–20 days) | G21, G22 | — | proposed |
| G23–G30 | 2 | see *Phase 2* | 39–67 | W1 | see *Phase 2* | proposed |

There is no teardown goal and no cost contract: nothing is provisioned that charges while idle. GitHub Actions minutes for a public repository are the only shared resource.

### Phase 1 goal entries

Each phase 1 goal lives in its ticket under `docs/tickets/truelift/`. The ticket holds the scope, route, acceptance, verification, status and evidence; this plan keeps only the table above and the schedule block. Tickets were generated from this plan's goal entries on 2026-11-05 and checked with `check_tickets.py` (0 errors, 0 warnings).

- [G01](../tickets/truelift/G01-repo-foundation-and-confidentiality-guard.md)
- [G02](../tickets/truelift/G02-api-skeleton-localhost-auth-stream-contract-and.md)
- [G03](../tickets/truelift/G03-pipeline-feasibility-spike.md)
- [G04](../tickets/truelift/G04-synthetic-market-generator-and-truth.md)
- [G05](../tickets/truelift/G05-rules-dag-templates-and-golden-cases.md)
- [G06](../tickets/truelift/G06-causal-core-dag-identification-and-config-compil.md)
- [G07](../tickets/truelift/G07-data-intake-profiling-and-mapping-validation.md)
- [G08](../tickets/truelift/G08-project-store-knowledge-markdown-versions-and-sq.md)
- [G09](../tickets/truelift/G09-pipeline-worker-and-run-lifecycle.md)
- [G10](../tickets/truelift/G10-findings-digest-verdicts-scorer-and-deterministi.md)
- [G11](../tickets/truelift/G11-model-gateway-keys-consent-payload-limits-and-bu.md)
- [G12](../tickets/truelift/G12-question-bank-slot-catalogue-and-personas.md)
- [G13](../tickets/truelift/G13-interviewer-agent.md)
- [G14](../tickets/truelift/G14-explainer-agent-with-grounded-narrative.md)
- [G15](../tickets/truelift/G15-ui-shell-setup-and-consent-upload-and-mapping.md)
- [G16](../tickets/truelift/G16-ui-interview-chat-edge-cards-and-dag-graph.md)
- [G17](../tickets/truelift/G17-ui-run-progress-and-results.md)
- [G18](../tickets/truelift/G18-agent-driven-benchmark-and-ci-smoke.md)
- [G19](../tickets/truelift/G19-hackathon-tier-and-answer-key-comparison-local-o.md)
- [G20](../tickets/truelift/G20-end-to-end-journey-and-demo-script.md)
- [G21](../tickets/truelift/G21-presentation-to-organisers-business.md)
- [G22](../tickets/truelift/G22-presentation-to-organisers-technical.md)

## Phase 2: graduate for outside CMOs (after W1)

Detail follows certainty: these goals will be refined after W1. The steps from feedback to phase 2 tickets and issues are in [truelift-after-demo.md](truelift-after-demo.md).

- **G23 Installer and packaging (Mac, Windows).** CI builds a wheel containing the SPA. `uv tool install truelift`. An install page written for pasting into an LLM assistant. Handles `libomp` on macOS and loky on Windows. *Skill:* `adk-release-engineering`. *Estimate:* 6–10 h. *Acceptance:* a clean Mac and a clean Windows VM go from the install page to the results page with no terminal steps beyond those the page lists.
- **G24 DAG and run comparison view.** Side-by-side DAG diff (edges and `x_cols`) and results, labelled with C9 versions. *Skill:* `adk-frontend-integration`. *Estimate:* 5–8 h. *Acceptance:* two runs with different DAG versions show the diff and both headline results, with a version-mismatch warning.
- **G25 Re-adopt live runs after a backend restart.** The worker is detached from the backend, which re-attaches through `status.json` and the process ID. *Skill:* `adk-workflow-design`. *Estimate:* 3–5 h. *Acceptance:* restart the backend mid-run, the run completes, and the results appear (C10).
- **G26 Interview quality evaluation.** A judge rubric for leading questions, the difficult personas, three markets and the OpenAI provider. *Skill:* `adk-agent-evaluation`. *Estimate:* 6–10 h. *Acceptance:* a rubric pass rate of at least the target Thao sets, on 3 personas × 3 markets × 2 providers.
- **G27 Saturation variant and pull-forward lags.** For spend treatments, plus a lag slot in the interview. *Skill:* `adk-workflow-design`. *Estimate:* 5–8 h. *Acceptance:* the golden cases cover saturation compile rules, and the benchmark stays green.
- **G28 Governance note.** User-facing privacy and data-flow note, third-party notices (Apache-2.0 attribution) and a review of the disclosure text. *Skill:* `adk-governance-pack`. *Estimate:* 3–5 h. *Acceptance:* the skill's checker passes on the drafts.
- **G29 Localhost security review.** ASVS Level 1 subset for a loopback app, plus adversarial prompt-injection cases. *Skill:* `adk-agent-security`. *Estimate:* 3–6 h. *Acceptance:* the review is recorded, with each gap fixed or turned into a goal (SB22).
- **G30 Pilot with 2–3 CMOs.** A journey run with real users on their own data, plus a pilot review presentation. *Skill:* `adk-presenter` (review) with `adk-agent-evaluation` (journey). *Estimate:* 8–15 h, plus recruiting time as a wait. *Acceptance:* the M records show the unaided completion rate and verdict comprehension.

## Later

| Item | Trigger that brings it forward | Risk accepted while it waits | Likely primary skill |
| --- | --- | --- | --- |
| Media channels as treatments | The v1 discount loop is validated by the pilot | Media confounding is handled only as controls | `adk-workflow-design` |
| Meridian prior export from the digest | A user or the organisers ask for it | None | `adk-workflow-design` |
| Data anonymisation add-on (gateway seam) | Paid support, or a user with sensitive panels | Summaries go to the provider as consented (accepted risk, design §3) | `protect-adk-sensitive-data` |
| Paid support bundle and opt-in telemetry | The first support contract | No usage insight | `adk-agent-observability` |
| Non-panel data shapes | Users with store-level or daily data | Those users cannot use v1 | `adk-fastapi-backend` |
| Desktop installer bundle | `uv` install support burden is too high (G23 feedback) | Some users fail to install | `adk-release-engineering` |
| Derived holiday columns from confirmed calendar facts | Users without holiday columns are blocked by C3 | Those users must add the columns by hand | `adk-workflow-design` |
| Shareable market packs (`market.md` templates per country) | Users in two or more markets | Each user re-answers the market module | `adk-memory-architecture` |
| Pipeline and ADK upgrade review | Each doubleml-pipeline or ADK release; model retirement dates (check `gemini-3.8-flash` quarterly) | Version drift | `adk-release-engineering` |

## What the reviewer reads

| Document | Establishes |
| --- | --- |
| [docs/architecture/truelift.md](../architecture/truelift.md) | Method, contracts and accepted decisions |
| `docs/research/pipeline-spike.md` (G03) and the bench reports under `bench-results/` (G10, G18) | Measured runtime, variability and benchmark results |
| This plan | Remaining limits, deferred controls and next goals |

## Open decisions for further planning

| Decision / question | Known facts and alternatives | Evidence or user decision needed | Blocks which goals? |
| --- | --- | --- | --- |
| Who presents G21 | Chloe prepares; Ruslan as project lead might present | Ruslan | G21 |
| Run-profile values and δ | Design §11 | G03 | G09 caps |
| ±25% hackathon tolerance achievable? | Expert reached −34% | G19 | M1 declaration |
| Identification thresholds | Design §11 | G05 (Thao) | G07/A6 |

## Resume here

- **Done:** G01 (PR #28, merged 2026-11-06; checkpoint 1 settled its rulings on 2026-11-07). Phase 1 base commit: `a10dfe5`.
- **Ready now:** G02, G03, G04 and G05, in parallel. G08 now waits for G02. Pick through the `pick-ticket` skill ("what can I grab?").
- **Read first:** [docs/architecture/truelift.md](../architecture/truelift.md) §3–5, `AGENTS.md`, the ticket.
- **Schedule check:** rerun 2026-11-07 at 0.55 h/day: 128–220 days, exit 0; results in *Schedule check*. G01 took 1 h against a 2–4 h estimate.
- **Independent review:** done 2026-11-07; findings settled in *Changes after the independent review*. Watch the invitation deadline (2026-11-12).
- **Continuation prompt:** take a ready ticket with "what can I grab?", then run the prompt in its *Run this ticket* section.

After that goal: `/adk-engineer Continue the next ready goal in docs/plans/truelift.md.`
