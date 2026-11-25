---
goal: G15
title: UI: shell, setup and consent, upload and mapping
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-frontend-integration
supporting_skills: []
docs: [adk-frontend-integration/references/frontend-quality.md]
blocked_by: [G02]
touches: [frontend/src/app/, frontend/src/routes/setup/, frontend/src/routes/data/, frontend/package.json, frontend/package-lock.json, docs/design/DESIGN.md]
parallel_safe: no
contracts: [C7, C8, C12]
companion_skills: [react-router, vercel-react-best-practices, shadcn]
security: [SB10]
design_system: docs/design/DESIGN.md
contract_deltas: []
pass_to_pass: [G02/A8]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 5-7
  review_and_verify: 1-2
  total: 6-9
  handoff: 0.5
  calendar_waits: none
owner: Chloe            # suggested owner; anyone may pick this ticket
status: verified_local
---

# G15 UI: shell, setup and consent, upload and mapping

## Outcome

A CMO can set up a key, see exactly what will be shared, upload data and confirm a valid mapping (C7, C8, C12; D17).

## Scope

- In: Vite, React and TS SPA in `frontend/`, with React Router in data mode and TanStack Query over the generated client. House `DESIGN.md` copied to `docs/design/DESIGN.md`. Launch-token handling (fragment → `sessionStorage` → header).
- Route: Vite, React and TS SPA in `frontend/`, with React Router in data mode and TanStack Query over the generated client. House `DESIGN.md` copied to `docs/design/DESIGN.md`. Launch-token handling (fragment → `sessionStorage` → header).
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [x] A1 The app shell renders with the house theme and no default shadcn tokens. All calls go through the generated client (C12).
- [x] A2 Setup: choose a provider; the key is sent once to the backend and never kept in browser storage; the disclosure screen renders the example payload the stub API returns for the uploaded file; consent is recorded (C8, C7). The real payload is checked in G20/A1.
- [x] A3 Upload shows progress, and every rejection reason in the stub API's error contract appears in plain language (C12). G20/A1 checks real G07 reasons.
- [x] A4 Mapping review shows each column's role and the stub's per-role validation errors inline; Confirm stays disabled until every role is valid (C12).
- [x] A6 The "AI unavailable" and "AI paused: budget reached" banners render from the stub stream's events, and the deterministic screens stay usable (C15).
- [x] A5 All server text renders as text (SB10).

Verification, automated: `npm --prefix frontend run test` and `npm --prefix frontend run build` exit 0 against the G02 stub API (local).
Verification, manual: none.

## Evidence

Built in `frontend/` (Vite, React, TypeScript): `src/app/` (shell, router, API setup, token, errors, upload transport, stream reader, AI status, theme, UI primitives), `src/routes/setup/` (provider and key, disclosure and consent) and `src/routes/data/` (upload and profile, mapping review). The house `DESIGN.md` was copied to `docs/design/DESIGN.md` and then adapted at Chloe's request into truelift's own theme (see R6). Tests: 67 screen and unit tests (jsdom) and 17 contract tests against the real G02 app, which `tests/stub-server.global.ts` starts on a test token with temporary data folders. All runs 2026-11-24 on Chloe's machine (Windows 10 Education 19045, Node 26.12.1, npm 10.8.2, Python 3.12 through uv).

Versions (a new project starts on the current line, adk-frontend-integration `compatibility.md`; exact pins in `frontend/package.json`): React 19.3.1, Vite 8.3.5, `@vitejs/plugin-react` 6.1.2, React Router 8.5.1 (data mode), TanStack Query 5.104.5, zod 4.6.7, Tailwind CSS 4.3.3, Vitest 5.1.1, jsdom 31.0.0, ESLint 10.14.0 with `eslint-plugin-react-hooks` 7.1.1, fonts `@fontsource-variable/schibsted-grotesk`, `@fontsource-variable/manrope` and `@fontsource-variable/jetbrains-mono`, all 5.3.0. Where neither the skill nor DESIGN.md recorded a version, the newest release at least two weeks old was chosen. Vitest is 5.1.1, not 5.1.0, because npm 10.8.2 crashes (`edgesOut`) on a peer set that resolves `vitest@*` to 5.1.1.

- pass_to_pass G02/A8: not run before the change (missed; the lifecycle asks for it). After the change, `uv run pytest` gives 324 passed and 2 skipped, including `test_committed_openapi_matches_code`, `test_dump_needs_no_network`, `test_recordings_are_valid` and `test_stream_replays_recording`. A mid-run attempt had one failure, `test_clean_working_tree_passes`, caused by this ticket's test key (see "Fixed during the run"). `make client-check` exits 2 on this Windows checkout. The cause is line endings only: `core.autocrlf=true` gives CRLF files and the generator writes LF. `diff -ru --strip-trailing-cr` against the regenerated copies shows no drift, and `openapi.json` and `frontend/src/client/` are unchanged. CI (Linux) is not affected.
- A1: `local, pass`. `shell.test.tsx`: the shell renders the sidebar, the page heading and the environment badge. A selected nav item keeps the 14 px size, turns semibold and gets the turquoise left marker. Every call in a mapping session goes to `/api/…` through the generated client with `Authorization: Bearer <token>`, never with the token in a URL. With no token the relaunch screen shows and nothing is called; a 401 switches to it. `token.test.ts`: `#token=` moves to `sessionStorage`, is stripped from the URL and is never written to `localStorage`. `theme.test.ts`: all 89 DESIGN.md colour tokens map one to one into `:root` and `.dark`, the heading and figure tokens use Schibsted Grotesk and the rest Manrope (code uses JetBrains Mono), cards have a resting shadow in light mode only, and the radius steps and self-hosted fonts are pinned. `uv run python -I frontend/scripts/check_theme.py --project frontend` exits 0 ("no shadcn 4.22.1 default tokens or fonts found"). Grepping `src/` for hex, `rgb(`, `oklch(` and palette classes finds nothing outside the theme file. The production CSP is unchanged: built and served by the real app, `index.html` loads only same-origin files (`/theme-init.js`, `/assets/…`), has no inline `<script>` or `style=`, and deep links return the shell.
- A2: `local, pass`. Against the stub (`stub-api.contract.test.ts`): the providers are listed, `PUT /api/setup/key` returns 204 with an empty body, a short key gets 422 without echoing it, the disclosure has categories and an example payload, consent is recorded for that version, and a stale version is 409 `disclosure_changed`. Screens (`setup.test.tsx`): the chosen provider's key goes in exactly one PUT. Afterwards the field is empty and the key appears in neither storage, the query or mutation cache nor the URL. A refused key is explained and the field cleared. The disclosure renders its categories, the example payload (as text in a `<pre>`) and the retention note. Allow sends `{provider, disclosure_version}` once and shows "Sharing allowed". Picking another provider loads its disclosure. A changed disclosure is reported and reloaded. The real payload is G20/A1.
- A3: `local, pass`. Against the stub: each of the six intake codes (`<code>.csv`, an empty file for `empty_file`) is 422 with that code, and the interface has a plain-language title and hint for every one. A non-CSV name gives `not_csv`, and a weekly CSV is accepted and versioned. Screens (`upload.test.tsx`, faked XHR): a progress bar shows during the upload, and the request carries the bearer token to `/api/projects/{id}/data`. After an accepted upload the profile appears, with "ground truth: excluded". Each rejection code, 413 and an unknown code (server message and request ID) are explained.
- A4: `local, pass`. Against the stub: setting the outcome column to a discount rate gives `ok: false` with a reason, confirm is 422 `mapping_invalid`, and after fixing the role confirm returns `confirmed`. A stale version is 409 `stale_version`. Screens (`mapping.test.tsx`): an invalid role shows `aria-invalid`, and its reason inline as the select's accessible description. Confirm is disabled while any role is invalid. A change is sent with `expected_version` and enables Confirm once every role is valid, and a change that breaks a role disables it again. A stale version is reported and reloaded.
- A6: `local, pass`. Against the stub: `/scenario ai_unavailable` and `/scenario budget_paused` move the AI state to `unavailable` and `budget_paused` through the zod-validated reader. The recorded interview validates event by event. Screens (`banners-and-text.test.tsx`): replaying the repository's recordings shows "AI unavailable" and "AI paused: budget reached" with the event's message. Mapping can still be confirmed and upload still works while a banner shows, and the usage endpoint alone can raise the budget banner. `stream.test.ts`: all four recordings parse even when split into 7-byte chunks, and an invalid event, an out-of-order event and a stream cut before its terminal event are each refused.
- A5: `local, pass`. Hostile strings (`<img onerror>`, `<b>`) from the project name, disclosure, error message, mapping column and reason, profile observation and stream message render as literal text, with no `img` or `b` element and no script effect. ESLint forbids `dangerouslySetInnerHTML`, `innerHTML` and `outerHTML`.
- Verification: `npm --prefix frontend run test` exit 0 (12 files, 84 tests; stable over repeated runs). `npm --prefix frontend run build` exit 0 (`tsc -b` over the app, tests and configs, then `vite build`; every route is a lazy chunk, the largest is 408 kB, no chunk-size warning). `npm --prefix frontend run lint` exit 0. `guard_public.py --tree` clean (229 files). `ruff check .` and `ruff format --check .` clean. `npm audit --audit-level=high` exit 0, with 8 moderate findings in `minimatch` through the lint tooling.
- Fixed during the run: (1) the guard flagged the test key `sk-test-…` as an OpenAI key pattern; it is now `test-key-not-real-…`. (2) Confirming the mapping invalidated `['project', id]` as a prefix, which refetched and overwrote the confirmed mapping; it now invalidates with `exact: true`. (3) The visually hidden "Not valid:" lost its space at a JSX line break, so assistive technology read "Not valid:A discount…". (4) `theme.test.ts` first parsed zero tokens because of CRLF line endings, so the one-to-one check checked nothing; it now normalises line endings and asserts more than 80 tokens. (5) A flaky A6 test exposed a race: a usage response arriving after an `ai_status` stream event cleared the banner the stream had raised, and a later usage refetch would do the same in the app. `ai-status.ts` now records who set the state, and usage never clears a state the stream set (`ai-status.test.ts`). (6) The sidebar's project link pointed at the Data step, so the project lost its selected mark on the other steps; it now points at the project.

Contracts:

- C7: evidenced, local; G15/A2. The interface sends the key once and keeps it in no browser storage, cache or URL. Keychain storage is G11/A1.
- C8: evidenced, local; G15/A2. The disclosure screen shows the categories and the example payload before consent, and consent is recorded per provider and version. The gateway refusal and the real payload are G11/A2 and G20/A1.
- C12: evidenced, local; G15/A3, G15/A4. Every stub rejection reason and per-column check is shown, and Confirm is gated on every role being valid. The real validator is G07.
- C15: evidenced, local; G15/A6 (cited by A6). The banners come from stream events, and the deterministic screens stay usable.

Security rules:

- SB10: evidenced, local; G15/A5 (and an ESLint rule). SB08 kept: the token is read from the fragment and sent only in the bearer header, both by the generated client and by the stream reader, which uses `fetch`, not `EventSource`.

Companion skills: `react-router`, `vercel-react-best-practices` and `shadcn` were not installed in this session, so their guidance is not claimed (install lines in AGENTS.md). The shadcn components (button, input, native select, card, badge, notice, progress) were written by hand in the base-nova shape with the DESIGN.md corrections, because running the shadcn CLI needs `npx`, which was not permitted. `components.json` is in place for later `shadcn add`. Skills: adk-engineer 2026.10.28, adk-frontend-integration 2026.10.28 (primary; `frontend-quality.md`).

Scope and changes outside `touches`:

- New scaffold files in `frontend/` that the ticket needs but does not list: `index.html`, `public/theme-init.js`, `vite.config.ts`, `tsconfig*.json`, `eslint.config.js`, `components.json`, `src/main.tsx`, `tests/` (test setup, the stub launcher `stub_server.py`, its global setup and the contract tests), and `scripts/check_theme.py` with `scripts/LICENSE-check_theme.txt` (vendored unchanged from adk-frontend-integration, MIT).
- `.gitignore`: `src/truelift/web/`, the build output that `spa.py` serves and says is never committed. It was not ignored before.
- `pyproject.toml`: ruff `extend-exclude` adds `frontend/scripts/check_theme.py`, so the vendored file stays byte-identical to upstream.
- `docs/architecture/truelift.md`: the Evidence cells of C7, C8, C12 and C15 only.

Rulings (for the designer's checkpoint):

- R1. `IntakeErrorCode` is not in `openapi.json`, because no response model references it, so the interface lists the six codes in `src/app/errors.ts`. The contract test uploads each one to the stub and fails on a missing or renamed code. Cost if wrong: a code G07 adds shows the server's message, not a written hint. Better fix: G07 exposes the enum in the schema.
- R2. Upload progress needs XHR (fetch cannot report upload progress). The generated `intakeUploadData` call is given an XHR transport through its `fetch` option, so A1 ("all calls through the generated client") still holds.
- R3. The theme is set before first paint by a same-origin `/theme-init.js`, not the inline script DESIGN.md asks for, because the production CSP has no `'unsafe-inline'`. The effect is the same and the CSP is unchanged.
- R4. The API has no route to set the active provider. The setup screen's choice decides which key is entered, and the consent screen picks its own provider (defaulting to `active_provider`). G11 should add a setting if the active provider must persist.
- R6. Design (Chloe, 2026-11-24, fourteen passes and a final review): the house look (warm paper greys, ink blue, Source Serif headings) read as too close to Claude's own interface, and a first slate-and-emerald pass read as too plain. `docs/design/DESIGN.md` is now truelift's adaptation:
  - cool slate neutrals with clear surface steps (canvas #F4F6F8 below white cards);
  - a dark slate sidebar in both modes, with a new `sidebar-muted-foreground` token and a turquoise selected marker;
  - one turquoise accent (hue 198–200, `primary` #007176). `success` stays green (148) and `info` blue (258), so status never looks like the accent;
  - Schibsted Grotesk for headings and figures (new `metric` token, stat tiles), Manrope for the interface, no serif;
  - one resting card shadow in light mode only, icon chips on card headers, a numbered stepper for the project steps;
  - a selected nav item keeps its size and turns semibold;
  - pass 3 overhaul, after review in the browser and with coder.com, flick.social and jasper.ai as style references (their downloaded CSS; lovable.dev was also asked for but served a bot challenge, so it was not used):
    - a larger fluid type scale with body text at Manrope 450;
    - 36 px controls and 8/12/16 px radii;
    - a softer, wider light-mode card shadow;
    - a calmer dark primary (`#50B0B3`, label 7.5:1);
    - pointer cursors on every enabled control;
    - a landing page: hero on a faint grid, an example result labelled "illustrative", How it works, What you get, projects;
    - page headers on every screen, and the AI provider screen explaining why an AI model is needed and what it never does;
    - stepper status captions with checks, sticky action bars for Allow sharing and Confirm roles, a two-column consent screen that fits a 1280×800 window, and centred content columns (the per-screen width caps had pushed content to one side).
  - pass 4, brighter and more refined, using lovable.dev's computed CSS (pasted from DevTools) as the brightness reference:
    - near-neutral canvas `#F6F7F8`, white cards, a **light sidebar** (replacing the dark one from pass 2);
    - accent turquoise moved to hue 212 (`#0C7686` light, `#3AB7CD` dark). sRGB caps this hue at about chroma 0.09 where white text still reaches 4.5:1, so brightness comes from the surfaces and a brighter wash (`#D5F5FC`);
    - the AI provider explainer moved below the key card, in rows of three, because the two-column layout felt cramped; it is a secondary section (header on the canvas, three small cards at 60% white);
    - a calmer dark accent (`#4BA0B0`); a new pastel `selected` fill (`#E9F9FD` light, `#132124` dark) for the chosen provider and the selected sidebar item, so a selection no longer looks like an icon chip;
    - the sidebar becomes a 72 px icon rail from 768 to 1023 px, so tablets keep room for the work area.
    - a Home link in the sidebar; the hero grid at half strength, fading out over its bottom 40%; the example card as wide as the sections below; a hairline above Your projects; the AI provider explainer cut to a Notion-style callout (info icon, inline bold title, one line, three chips), since the landing page explains the product.
  - pass 5, monotone + gold (Chloe: "money colours", gold and green only):
    - bright monotone surfaces, neutral `accent` and `selected` fills;
    - gold `#E7B643` used only as a fill with a near-black label (9.6:1) on buttons, the active step and a hero highlighter mark, since gold is unreadable as text on white (1.7:1);
    - a deep gold `primary-ink` (`#845A0F`, 5.7:1) for links, eyebrows, checks, the sidebar marker and focus;
    - near-black icon chips with gold icons, and a coin brand mark and favicon;
    - `warning` in deep gold, `info` neutral, charts in gold, green and grey; red kept for errors only;
    - the hero grid fades out below its top 40%, and the AI provider callout lists the model's three jobs as check lines.
  - pass 6: a deep green main colour (`#0C5C3C`, white label 7.9:1; `#59B387` in dark) with gold as the small accent (gold icons in deep green chips, the coin mark, charts). The hero highlighter and the near-black chips from pass 5 were dropped at Chloe's request; the hero's key words are deep green text, and selection fills are a faint mint (`#E9F8EF`).
  - pass 7: monotone chrome again (grey hover and selection fills, a grey theme switch); light grey icon chips with deep green icons; gold kept only for the coin mark (on a fixed `brand` green, 7.1:1 in both modes) and charts; the hero grid now fades from the middle of the headline (fixed 160 → 440 px, so it lands on the headline at every width).
  - pass 8: the grey chips blended into the grey canvas, so icon chips became bold (her reference: a pale square chip, a two-tone icon, an outlined card): a square pale gold `chip` with a deep green stroke over a gold `chip-fill` (one `IconChip` component; icons with open axis or zigzag paths swapped for closed-shape ones), and feature and project cards outlined in a new `card-edge`. The hero grid no longer vanishes: full to mid-headline, a faint 12% from the end of the headline to 80% of the hero, then fully blended at the bottom. The project page saying "Uploaded" after a refresh is correct: the G02 fake demo project is seeded with data version 1; a new project shows "To do".
  - pass 9 (Chloe's own edits): the brand mark became a gold rising arrow (`TrendingUp`) on a near-black `brand` (11.6:1), also as the favicon; her hero grid mask: full to 140 px, 25% at 220 px, 8% at 300 px, blended by 75% of the hero.
  - pass 10: the label on a primary fill is weight 700 in dark mode (`type-label-primary`; dark text on light green read thinner); a brighter light-mode sidebar marker (#087C46, the deep green read as black); the hero grid fades slowly over the whole hero (50% at half, 30% at 70%, 15% at 88%) and blends out at its bottom edge; feature cards lift 4 px on hover (reduced motion: none); the selected provider uses a new green-tinted `choice` fill so it differs from the grey callout; single-series bars lead with green (`chart-1`), gold stays on the brand mark and icon fills.
  - pass 11: below 768 px the nav links (Home, AI provider, projects) stay pinned at the top on scroll; the brand row and theme switch scroll away.
  - pass 12: below 768 px the project steps are a vertical accordion instead of a sideways-scrolling stepper: the current step opens with its screen under its header, opening another closes it, and the open header folds the screen away.
  - final review: a new page opens at the top (`ScrollRestoration`; step links keep their place), and on a phone the newly opened step's header scrolls into view; DESIGN.md's Do's and Don'ts and Elevation brought in line with the adaptation (radius steps, the card resting and hover shadows, the eyebrow as the one all-caps label, the theme script as a file under the CSP). npm audit: no high findings; 8 moderate in dev-only lint tooling (eslint, typescript-eslint via minimatch).
  - pass 13 (instead of a background gradient, which the house rules forbid): a cause-and-effect map illustration as the first part of the landing example (static SVG from tokens); How it works on a full-bleed `section` band one step darker than the canvas; a dark closing call-to-action `band` (near-black light, deep green-black dark) with a gold button (`button` variant `gold`) and a gold focus ring, replacing the hairline above the projects. New tokens `section`, `band`, `band-foreground`, `band-muted`, `gold-hover`, all through the contrast gate (99 pairs per mode).
  - pass 14: the cause-and-effect map illustration was removed (Chloe did not like it); the dark call-to-action band moved to the very bottom, after the projects, with the hairline above the projects back and a one-line caption footer under the band (© 2026 the truelift authors · MIT licence); the How it works band lightened to a barely darker step of the canvas (#F1F3F5 light, #090B0D dark).
    The house rules on glow and animation stay (Chloe's decision, after reading their source in Ruslan's `house-design-system-2026-10-23.md`); a landing-page motion and glow proposal is parked until the team agrees to change them.
  Structure, layout, motion and the accessibility floor are unchanged. The colours came from a contrast script: 76 pairs per mode clear 4.5:1 (text) or 3:1 (edges and focus), all in the sRGB gamut, and the smallest margin is `input` on `accent` (3.18 dark). Manifold CF, Forma DJR and Helvetica were asked for but are commercial and cannot ship in this public repository; Schibsted Grotesk is the OFL stand-in. Newsreader is the recorded choice if G16 answers need a serif. Cost if wrong: G16 and G17 follow this file, so a later change of direction touches only tokens and a few shell classes.
- R7. The What is shared step reports "Allowed" only for consent recorded in the current session (kept in the query cache), because the API has no read route for consent. After a reload it says "To review" even if consent exists. Cost if wrong: a person may consent twice, which is harmless. G11 should add `GET /projects/{id}/consent` and the stepper will read it.
- R5. Only the demo project's setup, data and mapping routes exist in the stub, so the screens are exercised on `petfood-de`. A project created through the store gets 404s on them until G07 and G11 land.

Left out on purpose (MVP depth), with the trigger that adds them:

- The shadcn `Sidebar` with an icon rail and a `Sheet` below 768 px: the shell uses a plain sidebar that becomes a top bar. Trigger: G16 (conversation layout).
- The axe scan with `target-size`, screenshots at 375, 768 and 1280 px in light and dark, the browser journey, a keyboard-only run, Lighthouse vitals, and reviewing the first dark frame and a reduced-motion run. Trigger: G20 (Playwright, `playwright-cli` companion).
- The ledger page and budget control: G17/A6. Real keychain storage: G11/A1. Real rejection reasons and payloads: G20/A1.

Estimate: the design passes asked for in review (fourteen, R6) were extra work beyond the acceptance scope, which is unchanged; the whole ticket still came in at about 5 h (see `actual`).

Human effort still owed (about 1–2 h review and verify):

- ~~Run the DESIGN.md lint~~ done 2026-11-24 (`@google/design.md` 0.4.0, run from the local npx cache): `summary` errors 0, warnings 0 (one info). The first run had 10 warnings, fixed: `chart-1` and `chart-2` darkened a step to clear 4.5:1 on `muted` (#0E794C, #93640C), and component entries added for the tokens no component referenced (`choice`, `card-edge`, `chip-fill`, `dark-gold-hover`, `dark-brand`).
- ~~Look at the app once in a browser~~ done by Chloe, 2026-11-24 (light and dark, 375 px, tablet and desktop).
- Optionally install the three companion skills and check the hand-written components against the `shadcn` skill.
- Review the diff and commit (nothing is committed).

actual: about 5 h (Chloe's report, 2026-11-24; agent-assisted, including the fourteen design passes; within the 6–9 h estimate even with the extra design work)

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G15-ui-shell-setup-and-consent-upload-and-mapping.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
