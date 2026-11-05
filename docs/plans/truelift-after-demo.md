# After the organisers' demo: from feedback to phase 2 tickets

This playbook covers the step from the end of milestone 1 (M1) to the start of phase 2. Phase 1 ends with the organisers' review (W1, GitHub issue #24). Phase 2 (G23–G30) is written in the [plan](truelift.md#phase-2-graduate-for-outside-cmos-after-w1), but only in outline. That outline is meant to change once the feedback is in, so this playbook makes sure the feedback reaches the design, plan and tickets before anyone builds phase 2.

Sources of truth do not change:
- The design ([docs/architecture/truelift.md](../architecture/truelift.md)) holds contracts and decisions.
- The plan ([truelift.md](truelift.md)) holds the schedule and phases.
- The tickets (`docs/tickets/truelift/`) hold acceptance, status and evidence.
- GitHub issues are pickup cards that link to tickets.

## Before the demo (optional, about 15 min)

Check that phase 1 really is complete before presenting it:

```text
/adk-system-designer Checkpoint docs/plans/truelift.md before the G21 and G22 presentations. Run plan_status.py with the phase gate, list any ticket whose evidence is missing or stale, and tell me whether M1 can be declared.
```

## Step 1: Record the feedback (same day, about 30–45 min)

Create `docs/feedback/truelift-organisers-<YYYY-MM-DD>.md` from the template below.

Write it within a day of the session, while the details are fresh. Record what was said, not what you plan to do about it; Step 2 is for that.

> **Confidentiality.** The organisers' material is proprietary (C13). If the feedback quotes the hackathon deck, notebook or data, or names anything under NDA, keep the full notes in `private/feedback/` and commit only a summary in your own words. The guard (G01) blocks `private/` paths, but it cannot recognise a paraphrased quote, so that judgement is yours.

```markdown
# Organisers' review: truelift M1

- Date / format: <YYYY-MM-DD, in person / call>
- Attendees: <names and roles>
- What was shown: <build commit SHA>, demo script G20, presentations G21 and G22
- Benchmark shown: synthetic tier <result>, hackathon tier <result> (numbers only)

## Feedback items

| ID | What they said (paraphrased) | Area | Severity | Affects (C/D/G IDs) | Suggested response |
| --- | --- | --- | --- | --- | --- |
| F1 | | econometrics / interview / explanation / UX / install / scope / trust | must / should / could | | |

## Questions we could not answer

- <question>, and who will find out.

## Asks and offers

- <introductions to CMOs, data, review of DGP, ...>

## Our read

- <the top 3 changes we believe the feedback implies>
```

If you only have rough notes or a call transcript, Claude can fill the template for you:

```text
Turn my notes in <path to notes> into docs/feedback/truelift-organisers-<YYYY-MM-DD>.md using the template in docs/plans/truelift-after-demo.md. Map each item to the contract, decision or goal IDs it affects in docs/architecture/truelift.md and docs/plans/truelift.md. Quote nothing from private/.
```

Then close issue #24 (W1) with a link to the feedback file.

## Step 2: Fold the feedback into the design and plan (about 1–2 h, with Thao)

Run a checkpoint with the designer. It treats each feedback item as one of four things:
- a contract delta (C), revised in place with a one-line note;
- a decision change (D);
- a change to a phase 2 goal (added, dropped, merged or re-estimated);
- "no action", with a reason.

It then reruns the schedule check and proposes the phase 2 cut line.

```text
/adk-system-designer Checkpoint docs/plans/truelift.md with the organisers' feedback in docs/feedback/truelift-organisers-<YYYY-MM-DD>.md. W1 is done. For every feedback item, record the contract delta, decision change, phase 2 goal change or "no action" with its reason. Revise the phase 2 goals (G23–G30; add or drop goals as needed) to full detail, rerun check_schedule.py for phase 2 with Ruslan, Thao and Chloe at 0.5 h/day, and propose the phase 2 cut line and milestone (M2) for me to confirm.
```

Answer its questions. They usually concern the cut line, the M2 window and any trade-off the feedback forces. When the answers are in, check two things:
- the plan's change table lists every goal, acceptance item or floor item that was removed or weakened, with its reason;
- the schedule check exits 0.

## Step 3: Write the phase 2 tickets (about 30 min)

```text
/adk-system-designer Turn the phase 2 goals in docs/plans/truelift.md into ticket files under docs/tickets/truelift/, with sibling dependencies in blocked_by and owners as suggestions. Then run check_tickets.py and check_schedule.py --tickets --design and fix every error.
```

Open a PR with the design, plan and ticket changes, and merge it. The issue links point to `main`, so they only work after the merge.

## Step 4: Export them to GitHub (about 5 min)

The script skips any goal that already has an issue, so it is safe to rerun.

```bash
gh auth status        # needs the 'project' scope: gh auth refresh -s project
python3 scripts/tickets_to_github.py --phase 2 --milestone M2            # dry run: read what it would create
python3 scripts/tickets_to_github.py --phase 2 --milestone M2 --apply    # create issues, labels, milestone
```

New issues get one of two labels:
- `ready to pick`, when all their blockers are closed;
- `blocked`, otherwise.

They also get a `suggested: …` label for the suggested owner. Add `--project <number>` only if you want them on a board as well.

## Step 5: Tell the team

Tell the team the M2 issues are up. They pick work the same way as in phase 1: in Claude Code, inside the repo, they ask "what can I grab?". The `pick-ticket` project skill lists the free issues, assigns the chosen one and prints its adk prompt. Remind people that phase 2 issues starting with G23 (installer) and G28 (privacy note) were outlines until Step 2, so they should read the ticket, not the old plan text.

## Keeping issues honest during phase 2

- Labels fix themselves: each time someone asks Claude what is free, `pick-ticket` swaps `blocked` for `ready to pick` on issues whose blockers have all closed.
- Once a week (about 10 min), get a status update and a list of tickets whose evidence is overdue:

```text
/adk-system-designer Weekly status for docs/plans/truelift.md.
```
