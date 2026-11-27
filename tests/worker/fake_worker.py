"""A real worker process with a scripted fit, for the lifecycle tests (G09).

    python tests/worker/fake_worker.py <mode> <run_id> --run-dir <dir>

Everything is the production worker (``truelift.worker.job.main``): env.json, the log redirect,
status.json and its heartbeat, the gate's re-check and the manifest. Only the pipeline fit is
replaced, so a run takes seconds instead of minutes. The modes:

* ``ok``: prints the pipeline's phase banners, writes the expected outputs and records which run
  files existed when the fit started (``work/seen.json``);
* ``sleep``: prints the Phase 1 banner, starts a child in its process group (standing in for
  the pipeline's loky workers) and sleeps, for the kill, cancel, cap and status tests;
* ``valueerror``: raises ``ValueError`` as the pipeline does on unusable data;
* ``missing``: returns without writing any output;
* ``crash``: the process kills itself with SIGKILL.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from truelift.worker import layout  # noqa: E402
from truelift.worker.job import main  # noqa: E402

# The pipeline's own banners (doubleml-pipeline 0.2.3), as the G03 runs printed them.
BANNERS = [
    "=== Phase 1: Grid Search Exploration (1 total combinations of models) ===",
    "=== Phase 2: Shortlisting Top 1 Performing Models ===",
    "=== Phase 3: Robust Ensemble Estimation (3 repetitions per model) ===",
    "=== Phase 4: Consolidating Results & Visualizing Impact ===",
]


def fit_ok(config, data_path: Path, work: Path) -> None:
    root = work.parent
    seen = {
        name: (root / name).exists()
        for name in ("config.json", "run.json", "env.json", "log.txt", "status.json", "work", "manifest.json")
    }
    for line in BANNERS:
        print(line, flush=True)
    for rel in layout.expected_outputs(config.orchestrator.run_sensitivity):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
    (work / "seen.json").write_text(json.dumps({"seen": seen, "data": data_path.name}))


def fit_sleep(config, data_path: Path, work: Path) -> None:
    print(BANNERS[0], flush=True)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    (work / "child.pid").write_text(str(child.pid))
    time.sleep(120)


def fit_valueerror(config, data_path: Path, work: Path) -> None:
    raise ValueError("Column 'media_grps' is not in the data.\nMore detail on a second line.")


def fit_missing(config, data_path: Path, work: Path) -> None:
    print(BANNERS[0], flush=True)


def fit_crash(config, data_path: Path, work: Path) -> None:
    print(BANNERS[0], flush=True)
    os.kill(os.getpid(), signal.SIGKILL)


MODES = {
    "ok": fit_ok,
    "sleep": fit_sleep,
    "valueerror": fit_valueerror,
    "missing": fit_missing,
    "crash": fit_crash,
}

if __name__ == "__main__":
    mode = sys.argv[1]
    sys.exit(main(sys.argv[2:], fit=MODES[mode]))
