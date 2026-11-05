# truelift

Find out if your discounts actually pay. truelift is a local AI econometrician: it interviews you about your business, builds the causal DAG and runs Double ML.

> **Status: design stage.** The architecture and plan are written and the first tickets are open. There is no runnable code yet. Milestone 1 is a full end-to-end demo that recovers a known discount ROI on synthetic data.

## What it will do

Most marketing teams know their business well, but they have no econometrician to tell them whether a discount made money or just gave margin away. truelift fills that gap, on your own machine:

1. **Interview.** It asks plain business questions: how you decide when and how deep to discount, what else drives sales, and what changes when a promotion runs. Your answers are saved as readable Markdown files you can reuse and edit.
2. **DAG.** It turns your answers into a causal diagram and shows each link as a sentence you can agree or disagree with.
3. **Check.** Deterministic code verifies that the discount effect can be identified. If something is missing, it blocks the run and tells you what (for example "we need competitor promo data, or a proxy for it").
4. **Run.** It compiles the confirmed diagram into a configuration for Google's [doubleml-pipeline](https://github.com/google/doubleml-pipeline) and runs it locally.
5. **Explain.** It reports incremental revenue and ROI against your break-even margin, and where and when discounts work. Every statement is labelled fact, inference or hypothesis, and cites the output it comes from.

You bring your own LLM key: Gemini by default, with Claude and OpenAI also supported. Before the first call, truelift shows you exactly what it will send to the model provider (column names, summary statistics and a few sample rows). It never sends your raw file.

## How it is built

- **Agent:** Google ADK, with two narrow agents, an interviewer and an explainer. The model talks; code decides identification, configuration and verdicts.
- **Backend:** FastAPI. Runs only on `127.0.0.1`.
- **Frontend:** React with TypeScript.
- **Storage:** your project folder (Markdown and YAML) and SQLite.
- **Engine:** doubleml-pipeline, run in a separate local worker process.

Correctness is checked against data where the right answer is known. truelift ships its own synthetic dataset with a true ROI, built-in confounders and a mediator trap, and CI checks that the agent-built analysis recovers it.

## Docs

| Document | What it covers |
| --- | --- |
| [Architecture](docs/architecture/truelift.md) | Requirements, contracts (C1–C16), decisions (D1–D22), diagrams, failure handling |
| [Plan](docs/plans/truelift.md) | Phases, estimates, schedule, cut line |
| [Tickets](docs/tickets/truelift/) | One file per goal: scope, acceptance criteria, evidence |
| [After the demo](docs/plans/truelift-after-demo.md) | From the organisers' feedback to phase 2 tickets |

## Working on it

Open issues on GitHub correspond one-to-one with the ticket files. To pick one up:

1. Open [Claude Code](https://claude.com/claude-code) in this repo and ask **"what can I grab?"**. The project skill `pick-ticket` lists the issues that are free, assigns the one you choose to you, makes a branch and gives you the prompt to start, usually `/adk-engineer Carry out docs/tickets/truelift/<ticket>.md`.
2. The ADK skills come from [agentic-engineering-skills](https://github.com/RuslanKhis/agentic-engineering-skills):

   ```bash
   npx skills@latest add RuslanKhis/agentic-engineering-skills --skill '*' -a claude-code
   ```

3. Claude assigns issues through the GitHub CLI, so log in once with `gh auth login`.

The ticket file, not the issue, holds the acceptance criteria and the evidence. "Suggested" labels on issues are only hints: anyone can take any free issue.

**Confidential material.** Some core developers keep private benchmark files in `private/`. That folder is gitignored and must never be committed, quoted or attached anywhere. CI will refuse it.

## License

[MIT](LICENSE)
