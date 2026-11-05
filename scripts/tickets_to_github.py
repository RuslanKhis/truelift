#!/usr/bin/env python3
"""Export ticket files to GitHub issues, a milestone and labels (optionally a project board).

Idempotent: a ticket whose issue already exists (title starts with its goal ID) is skipped.
The ticket file stays the source of truth for acceptance, status and evidence; the issue
is a pickup card that links to it.

Usage, from the repository root (needs `gh auth login -s project`):

    python3 scripts/tickets_to_github.py --phase 2 --milestone M2            # dry run
    python3 scripts/tickets_to_github.py --phase 2 --milestone M2 --apply    # create
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

SUGGESTED = {
    "ruslan": "suggested: Ruslan · agent & backend",
    "chloe": "suggested: Chloe · frontend",
    "thao": "suggested: Thao · econometrics",
}
LABELS = {
    "ready to pick": ("0e8a16", "All blockers done: self-assign and start."),
    "blocked": ("b60205", "Waits on the issues listed under 'Blocked by'. Remove when they close."),
}

ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="RuslanKhis/truelift")
ap.add_argument("--tickets", default="docs/tickets/truelift")
ap.add_argument("--phase", default="1")
ap.add_argument("--milestone", default="M1")
ap.add_argument("--project", type=int, default=0, help="also add issues to this user project board (0 = no board)")
ap.add_argument("--branch", default="main")
ap.add_argument("--apply", action="store_true")
args = ap.parse_args()
OWNER = args.repo.split("/")[0]


def gh(*a, write=False):
    if write and not args.apply:
        print("DRY:", "gh", " ".join(x if len(x) < 70 else x[:67] + "..." for x in a))
        return ""
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"gh {' '.join(a[:3])} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def graphql(query):
    return json.loads(gh("api", "graphql", "-f", f"query={query}", write=query.lstrip().startswith("mutation")) or "{}")


def front(text):
    d, cur = {}, None
    for line in text.split("\n---", 1)[0].splitlines()[1:]:
        m = re.match(r"^(\s*)(\w+):\s*(.*?)\s*(?:#.*)?$", line)
        if not m:
            continue
        if m.group(1):
            d.setdefault(cur, {})[m.group(2)] = m.group(3)
        else:
            cur = m.group(2)
            d[cur] = m.group(3) or {}
    return d


def lst(v):
    return [x.strip() for x in str(v).strip("[]").split(",") if x.strip()]


def section(text, name):
    m = re.search(r"^## %s\n\n(.*?)(?=^## |\Z)" % name, text, re.S | re.M)
    return m.group(1).strip() if m else ""


# Existing issues by goal ID, open or closed.
issues = json.loads(gh("issue", "list", "--repo", args.repo, "--state", "all", "--limit", "500",
                       "--json", "number,title,state"))
by_goal = {}
for i in issues:
    m = re.match(r"^([A-Z]+\d+)\s", i["title"])
    if m:
        by_goal[m.group(1)] = i

for name, (color, desc) in {**LABELS, f"phase-{args.phase}": ("0e8a16", f"Phase {args.phase} goal"),
                            f"milestone:{args.milestone}": ("5319e7", f"Milestone {args.milestone}")}.items():
    gh("label", "create", name, "--repo", args.repo, "--color", color, "--description", desc, "--force", write=True)
for t in ("implementation", "discovery", "journey", "presentation", "governance", "teardown"):
    gh("label", "create", f"type:{t}", "--repo", args.repo, "--color", "c5def5", "--force", write=True)

if not gh("api", f"repos/{args.repo}/milestones?state=all", "--jq",
          f'.[] | select(.title=="{args.milestone}") | .number'):
    gh("api", f"repos/{args.repo}/milestones", "-f", f"title={args.milestone}",
       "-f", "description=See docs/plans/truelift.md", write=True)

created = []
for path in sorted(pathlib.Path(args.tickets).glob("*.md")):
    text = path.read_text()
    f = front(text)
    if str(f.get("phase")) != args.phase or "goal" not in f:
        continue
    gid = f["goal"]
    if gid in by_goal:
        print(f"{gid}: issue #{by_goal[gid]['number']} exists, skipped")
        continue
    blockers = lst(f.get("blocked_by", "[]"))
    open_blockers = [b for b in blockers if b not in by_goal or by_goal[b]["state"] != "CLOSED"]
    blocked_line = ", ".join(f"#{by_goal[b]['number']} ({b})" if b in by_goal else b for b in blockers) or "nothing"
    est = f.get("estimate", {}) if isinstance(f.get("estimate"), dict) else {}
    url = f"https://github.com/{args.repo}/blob/{args.branch}/{args.tickets}/{path.name}"
    run = re.search(r"```text\n(.*?)```", section(text, "Run this ticket"), re.S)
    body = f"""**Ticket (source of truth for acceptance, status and evidence):** [{path.name}]({url})

{section(text, "Outcome")}

| | |
|---|---|
| Suggested owner (anyone may pick) | {f.get('owner', '—')} |
| Estimate (human h, agent-assisted) | {est.get('total')} (hands-on {est.get('hands_on')}, review {est.get('review_and_verify')}) |
| Blocked by | {blocked_line} |
| Contracts | {f.get('contracts')} |
| Security rules | {f.get('security', '[]')} |
| Primary skill | `{f.get('primary_skill')}` |
| Type | {f.get('type')} |

**To pick this up (anyone):** in Claude Code, in the repo, ask *"what can I grab?"* (project skill `pick-ticket`). It checks the blockers, assigns the issue to you and makes a branch. Then run:

```text
{run.group(1).strip() if run else ''}
```

Acceptance lives only in the ticket file; evidence goes in its Evidence section, not here.
"""
    labels = [f"phase-{args.phase}", f"milestone:{args.milestone}", f"type:{f.get('type')}",
              "blocked" if open_blockers else "ready to pick"]
    owner = str(f.get("owner", "")).lower()
    if owner in SUGGESTED:
        labels.append(SUGGESTED[owner])
    out = gh("issue", "create", "--repo", args.repo, "--title", f"{gid} {f['title']}", "--body", body,
             "--milestone", args.milestone, *sum((["--label", l] for l in labels), []), write=True)
    number = out.rsplit("/", 1)[-1] if out else f"<{gid}>"
    by_goal[gid] = {"number": number, "state": "OPEN"}
    created.append(number)
    print(f"{gid}: {'created #' + number if out else 'would create'}")

# Optionally add new issues to a project board, in the Todo column.
if created and args.apply and args.project:
    proj = graphql(f'query{{user(login:"{OWNER}"){{projectV2(number:{args.project}){{id '
                   f'field(name:"Status"){{... on ProjectV2SingleSelectField{{id options{{id name}}}}}}}}}}}}')
    p = proj["data"]["user"]["projectV2"]
    todo = next(o["id"] for o in p["field"]["options"] if o["name"] == "Todo")
    for n in created:
        node = gh("api", f"repos/{args.repo}/issues/{n}", "--jq", ".node_id")
        item = graphql(f'mutation{{addProjectV2ItemById(input:{{projectId:"{p["id"]}",contentId:"{node}"}})'
                       f'{{item{{id}}}}}}')["data"]["addProjectV2ItemById"]["item"]["id"]
        graphql(f'mutation{{updateProjectV2ItemFieldValue(input:{{projectId:"{p["id"]}",itemId:"{item}",'
                f'fieldId:"{p["field"]["id"]}",value:{{singleSelectOptionId:"{todo}"}}}}){{projectV2Item{{id}}}}}}')
    print(f"added {len(created)} issues to project {args.project}")
