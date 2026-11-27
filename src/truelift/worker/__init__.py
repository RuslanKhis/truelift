"""Pipeline runs: the run gate, the worker process and the run lifecycle (G09; C1, C9, C10; D8).

- ``gate``: the run gate (C1). The start-run route calls it, and the worker calls it again
  before it fits anything.
- ``layout``: the run folder ``runs/<run_id>/`` and its files, written in this order:
  ``config.json`` and ``run.json`` (the app), then ``env.json``, ``log.txt``, ``status.json``,
  ``work/`` and, last, ``manifest.json`` (the worker).
- ``phases``: the log parser that turns the pipeline's printed progress into phase markers.
- ``job``: what runs inside the worker process (``python -m truelift.worker <run_id>``).
- ``manager``: the app side: one run at a time, spawn, watch, wall-clock cap, cancel and the
  startup reconciliation.
- ``scripted``: a project on the synthetic market with a scripted DAG and mapping, for headless
  runs (``truelift run``, C14).

No ADK import here or below, and doubleml-pipeline is imported only inside the worker process.
"""
