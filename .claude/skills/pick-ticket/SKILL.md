---
name: pick-ticket
description: Show which truelift GitHub issues are open and free to grab, assign the one the user chooses to them, create a branch and hand over the right adk skill prompt. Use when someone asks what they can work on, what is open, what is ready, or wants to take or start an issue or ticket (G01, #5, ...). Also use when someone says they finished a ticket and wants to open the PR.
---

# Pick a truelift ticket

The tickets live in `docs/tickets/truelift/`. Each GitHub issue on `RuslanKhis/truelift` is a pickup card for one ticket and links to its file. The ticket file is the source of truth for scope, acceptance, status and evidence. `suggested: <name>` labels are hints only: anyone may take any free issue.

Use `gh api` (REST) for writes. `gh issue edit` fails on older gh versions because it queries the retired classic Projects.

## 1. Show what is free

1. Run `gh api user --jq .login` to learn who the user is. If `gh` is not logged in, ask them to run `! gh auth login` and stop.
2. List the open issues that have no assignee:
   `gh issue list --repo RuslanKhis/truelift --state open --search "no:assignee" --limit 100 --json number,title,labels,body`
3. Decide whether each issue is free. Read the "Blocked by" row in its body (`#n (Gxx)` entries).
   - It is free when every listed issue is closed. Check with `gh api repos/RuslanKhis/truelift/issues/<n> --jq .state`.
   - If a label is out of date, fix it: remove `blocked` (`gh api -X DELETE "repos/RuslanKhis/truelift/issues/<n>/labels/blocked"`) and add `ready to pick` (`gh api -X POST repos/RuslanKhis/truelift/issues/<n>/labels -f "labels[]=ready to pick"`). Tell the user which labels you fixed.
4. Show the free issues as a short table: issue number, goal ID and title, suggested person, estimate (from the body), and primary skill. List issues waiting on others separately, one line each, with what they wait for. Also mention any issue already assigned to the user.

## 2. Assign the chosen issue

When the user picks one:

1. Check that it is still unassigned (someone may have taken it a minute ago): `gh api repos/RuslanKhis/truelift/issues/<n> --jq '.assignees|length'`.
2. Assign it: `gh api -X POST repos/RuslanKhis/truelift/issues/<n>/assignees -f "assignees[]=<login>"`.
3. Remove the `ready to pick` label from it.
4. Comment on the issue: `gh api -X POST repos/RuslanKhis/truelift/issues/<n>/comments -f body="Taken by @<login> via Claude Code."`.

## 3. Get ready to work

1. Start from fresh main: `git checkout main && git pull`, then `git checkout -b g<NN>-<short-slug>`. If there are uncommitted changes, ask before switching.
2. Open the ticket file linked in the issue. Tell the user the outcome, the acceptance items (A1…), the estimate, and the "Run this ticket" prompt from the ticket:
   - most tickets use `/adk-engineer Carry out docs/tickets/truelift/<file>.md …`, which loads the ticket's primary skill;
   - presentation tickets use `/adk-presenter`.
3. Ask whether to start now. Do not start implementing on your own.

## 4. When the user says the ticket is done

1. Check the ticket's Evidence section is filled and its `status` is `verified_local` or later. If not, say what is missing.
2. Show `git status` and the diff summary. The user reviews and commits. Do not commit for them unless they ask.
3. Push the branch and open the PR: `gh api -X POST repos/RuslanKhis/truelift/pulls -f title="G<NN> <title>" -f head=<branch> -f base=main -f body="Closes #<n>"`.
4. Once it is merged, run step 1 again. Issues that were waiting on this one may now be free, and their labels get fixed there.

Never commit or quote anything from `private/`.
