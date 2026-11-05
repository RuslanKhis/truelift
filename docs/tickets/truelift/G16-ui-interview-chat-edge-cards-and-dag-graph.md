---
goal: G16
title: UI: interview chat, edge cards and DAG graph
design: docs/architecture/truelift.md
plan: docs/plans/truelift.md
primary_skill: adk-frontend-integration
supporting_skills: []
docs: [adk-frontend-integration/references/agent-ui-states.md]
blocked_by: [G15, G06, G08]
touches: [frontend/src/routes/interview/, frontend/src/components/dag/]
parallel_safe: no
contracts: [C1, C3, C11]
companion_skills: [shadcn, vercel-react-best-practices]
security: [SB10]
design_system: docs/design/DESIGN.md
contract_deltas: []
pass_to_pass: [G02/A8, G15/A5]
phase: 1
type: implementation
profile: MVP or pilot
estimate:
  hands_on: 7-10
  review_and_verify: 2-3
  total: 9-13
  handoff: 0.5
  calendar_waits: none
owner: Chloe            # suggested owner; anyone may pick this ticket
status: ready
---

# G16 UI: interview chat, edge cards and DAG graph

## Outcome

The CMO talks to the agent, accepts or rejects proposals, and confirms the DAG as plain sentences (C1, C3, C11; D6).

## Scope

- In: SSE over `fetch` with zod-validated events. Proposal and contradiction cards. Edge cards. React Flow with ELK layout (exact version pinned). Identification panel.
- Out: the live Interviewer; this ticket builds against the G02 fake stream, and G20 connects the live agent.
- Route: SSE over `fetch` with zod-validated events. Proposal and contradiction cards. Edge cards. React Flow with ELK layout (exact version pinned). Identification panel.
- Depth: MVP depth per design §3; floor kept (no secrets, spend stop, pinned models).

## Constraints

Keep D12 (launch token, loopback only), D2 (stage machine in code; agents only propose) and C13 (nothing from `private/` in the repo). Pins live in AGENTS.md and the plan's *Destination and constraints*.

## Resources created

none

## Acceptance

- [ ] A1 Streamed agent text and tool progress appear. Proposals render as Accept / Reject cards. A contradiction card shows both answers with their turns (C11).
- [ ] A2 Edge cards offer Agree / Disagree / Not sure and send edits through the proposal endpoint. A stale-DAG banner appears when the store marks the DAG stale (C1, C11).
- [ ] A3 The read-only graph re-lays out on confirm, with roles (confounder, mediator, modifier) colour-coded and a legend (C1).
- [ ] A4 The identification panel shows blocks in business words, with options: add data, use an approved proxy, or accept the risk (C3).
- [ ] A5 Model output renders inert (SB10).

Verification, automated: `npm --prefix frontend run test` exits 0 against the G02 fake stream (local).
Verification, manual: none.

## Evidence

## Run this ticket

```text
/adk-engineer Carry out docs/tickets/truelift/G16-ui-interview-chat-edge-cards-and-dag-graph.md. Read its design and plan,
use its primary and supporting skills and its companion skills at the pins
in AGENTS.md, keep its constraints and security rules, run its
verification locally, fill in the Evidence section and set status
(verified_local when every acceptance case that can run offline has run here,
in_progress with the owed run named when the SDK is absent, verified_live after
the authorised run, done only when every acceptance item has fresh evidence and
the owner accepts). If Evidence starts with a Progress block, resume from it.
Leave changes uncommitted.
```
