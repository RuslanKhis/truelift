"""What runs inside the worker process: ``python -m truelift.worker <run_id> --run-dir <dir>`` (D8).

The app has already written ``config.json`` and ``run.json``. The worker then writes, in order:

1. ``env.json`` (C9);
2. ``log.txt``, which takes the process's stdout and stderr, so the pipeline's progress and its
   loky workers' output land there and not on the server's console (G03 note, F3);
3. ``status.json``, refreshed every couple of seconds with the phase parsed from the log;
4. after the gate admits the same inputs again (C1), ``work/``, the pipeline's ``output_dir``;
5. last, ``manifest.json``, by atomic rename, and only when every expected output is there (C10).

On a refusal or an error the worker writes ``status.json`` with a plain reason and exits non-zero;
it never writes a manifest then. The config, run record and log stay for support.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import platform
import sys
import threading
import traceback
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any

from truelift import __version__
from truelift.causal.compile import PipelineConfig
from truelift.causal.forbidden import DEFAULT as DENY
from truelift.causal.rules import load_rules
from truelift.store.folder import ProjectFolder
from truelift.worker import phases
from truelift.worker.gate import GateRefused, RunInputs, recheck
from truelift.worker.layout import (
    MissingOutputs,
    RunFolder,
    expected_outputs,
    read_json,
    sha256_file,
    utcnow,
    write_json,
)

ENV_SCHEMA = "truelift.env/1"
STATUS_SCHEMA = "truelift.status/1"
HEARTBEAT_S = 2.0
N_JOBS = -1  # the pipeline uses every core; one run at a time per machine (D8)

# Exit codes the app reads together with status.json.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 3
EXIT_PIPELINE = 4
EXIT_OUTPUTS = 5

# Recorded in env.json (C9). Installed versions; under ``uv sync`` they are the lock's.
PINNED = (
    "doubleml-pipeline",
    "doubleml",
    "flaml",
    "lightgbm",
    "xgboost",
    "scikit-learn",
    "numpy",
    "pandas",
    "scipy",
)

_REASON_MAX = 400

Fit = Callable[[PipelineConfig, Path, Path], None]


def _version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _lock_sha256() -> str | None:
    # Present in a source checkout (phase 1, D11); an installed wheel has no lock beside it.
    lock = Path(__file__).resolve().parents[3] / "uv.lock"
    return sha256_file(lock) if lock.is_file() else None


def environment(config: PipelineConfig, inputs: RunInputs) -> dict[str, Any]:
    try:
        from doubleml_pipeline.evaluation.hparam_search import SEARCH_SEED
    except ImportError:  # pragma: no cover - the pipeline is a runtime dependency
        SEARCH_SEED = None
    return {
        "schema": ENV_SCHEMA,
        "truelift": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "n_jobs": N_JOBS,
        "versions": {name: _version(name) for name in PINNED},
        "lock_sha256": _lock_sha256(),
        # doubleml-pipeline 0.2.3 fixes its seeds: the FLAML search uses SEARCH_SEED, Phase 1 uses
        # random_state 1 and Phase 3 repetition r uses r + 1. It takes no seed argument.
        "seeds": {"hparam_search": SEARCH_SEED, "phase1_random_state": 1, "phase3_random_state": "rep + 1"},
        "config_sha256": inputs.config_sha256,
        "data_fingerprint": inputs.data_fingerprint,
        "compiler_version": config.compiler_version,
        "started_at": utcnow().isoformat(),
    }


class Status:
    """``status.json``: written at once, then refreshed by a heartbeat thread (C10/A7)."""

    def __init__(self, folder: RunFolder, run_id: str, run_phases: list[str]):
        self.folder = folder
        self.data: dict[str, Any] = {
            "schema": STATUS_SCHEMA,
            "run_id": run_id,
            "pid": os.getpid(),
            "state": "running",
            "phase": phases.PREPARE,
            "phases": run_phases,
            "started_at": utcnow().isoformat(),
            "heartbeat_at": utcnow().isoformat(),
            "reason": None,
        }
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._offset = 0
        self._thread = threading.Thread(target=self._beat, name="heartbeat", daemon=True)
        self._write()

    def start(self) -> None:
        self._thread.start()

    def _write(self) -> None:
        with self._lock:
            self.data["heartbeat_at"] = utcnow().isoformat()
            write_json(self.folder.status, self.data)

    def _read_log(self) -> list[str]:
        try:
            with self.folder.log.open("rb") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
        except OSError:
            return []
        cut = chunk.rfind(b"\n") + 1  # parse whole lines only
        self._offset += cut
        return chunk[:cut].decode("utf-8", errors="replace").splitlines()

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_S):
            self.refresh()

    def refresh(self) -> None:
        lines = self._read_log()
        with self._lock:
            self.data["phase"] = phases.advance(self.data["phase"], lines)
        with contextlib.suppress(Exception):  # a missed heartbeat must not end the run
            self._write()

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.data["phase"] = phase
        self._write()

    def end(self, state: str, reason: str | None = None) -> None:
        """Stop the heartbeat and write the last status."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=HEARTBEAT_S * 2)
        self.refresh()
        with self._lock:
            self.data["state"] = state
            self.data["reason"] = reason[:_REASON_MAX] if reason else None
        self._write()


def _redirect_output(log_path: Path) -> None:
    """Send fds 1 and 2 to the log, so child processes inherit it too."""
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    for stream, target in ((sys.stdout, 1), (sys.stderr, 2)):
        with contextlib.suppress(Exception):
            stream.flush()
        os.dup2(fd, target)
    os.close(fd)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(line_buffering=True)  # type: ignore[union-attr]


def _plain(exc: BaseException) -> str:
    """The exception's message on one line, cut to a readable length."""
    text = " ".join(line.strip() for line in str(exc).splitlines() if line.strip())
    return (text[:297] + "...") if len(text) > 300 else (text or type(exc).__name__)


# --- the fit ------------------------------------------------------------------------------


def load_panel(config: PipelineConfig, data_path: Path) -> Any:
    """Read the panel for the pipeline: ground-truth columns dropped (C4), the date parsed, the
    fixed-effect dummies the compiler named added, and a unique index (G03 note)."""
    import pandas as pd

    df = pd.read_csv(data_path)
    df = df.drop(columns=[c for c in df.columns if DENY.is_forbidden(str(c))])
    date_col = config.orchestrator.date_col
    df[date_col] = pd.to_datetime(df[date_col])
    for dummies in config.dummies:
        values = df[dummies.column].astype(str)
        for level, name in zip(dummies.levels, dummies.names, strict=True):
            df[name] = (values == level).astype(int)
    return df.reset_index(drop=True)


def _guard_prior_plot() -> None:
    """doubleml-pipeline 0.2.3 raises in ``plot_prior_distributions`` on an average-effect-only
    run before sensitivity runs (G03 finding F2, ruling R5). Skip that one chart instead."""
    from doubleml_pipeline.visualization import plots

    original = plots.plot_prior_distributions
    if getattr(original, "_truelift_guarded", False):
        return

    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return original(*args, **kwargs)
        except ValueError as exc:
            print(f"  ├─ truelift: prior distribution chart skipped ({_plain(exc)})", flush=True)
            return None

    guarded._truelift_guarded = True  # type: ignore[attr-defined]
    plots.plot_prior_distributions = guarded


def fit_pipeline(config: PipelineConfig, data_path: Path, work: Path) -> None:
    from doubleml_pipeline.preprocessing.scalers import CausalDataScaler
    from doubleml_pipeline.workflow import CausalWorkflowOrchestrator

    df = load_panel(config, data_path)
    _guard_prior_plot()
    orchestrator = CausalWorkflowOrchestrator(**config.orchestrator_kwargs(str(work), n_jobs=N_JOBS))
    scaler = CausalDataScaler(**config.scaler_kwargs())
    orchestrator.run_full_pipeline(df, scaler, top_n=config.run.top_n, n_reps=config.run.n_reps)


# --- the job ------------------------------------------------------------------------------


def run_job(run_id: str, folder: RunFolder, fit: Fit = fit_pipeline) -> int:
    config_bytes = folder.config.read_bytes()
    config = PipelineConfig.from_json(config_bytes)
    record = read_json(folder.run)
    if record is None or record.get("run_id") != run_id:
        return EXIT_ERROR
    inputs = RunInputs.from_dict(record["inputs"])
    write_json(folder.env, environment(config, inputs))  # 2. env.json
    _redirect_output(folder.log)  # 3. log.txt
    run_phases = phases.phases_for(config.profile, config.orchestrator.run_sensitivity)
    status = Status(folder, run_id, run_phases)  # 4. status.json
    status.start()
    try:
        project = ProjectFolder(folder.project_root)
        recheck(project, inputs, config_bytes, load_rules())  # C1: again, before fitting
        folder.work.mkdir(exist_ok=False)  # 5. work/
        fit(config, project.root / inputs.data_file, folder.work)
        status.set_phase(phases.WRITE)
        status.end("finishing")
        folder.write_manifest(run_id, expected_outputs(config.orchestrator.run_sensitivity))  # 6.
        print("truelift: manifest written", flush=True)
        return EXIT_OK
    except GateRefused as exc:
        status.end("failed", exc.message)
        return EXIT_REFUSED
    except MissingOutputs as exc:
        traceback.print_exc()
        status.end("failed", f"The analysis finished without all its results (missing {len(exc.missing)}).")
        return EXIT_OUTPUTS
    except ValueError as exc:
        traceback.print_exc()
        status.end("failed", f"The analysis could not run on this data: {_plain(exc)}")
        return EXIT_PIPELINE
    except Exception as exc:
        traceback.print_exc()
        status.end(
            "failed",
            f"The analysis stopped with an unexpected error ({type(exc).__name__}). "
            "The run log has the details.",
        )
        return EXIT_ERROR


def main(argv: list[str] | None = None, fit: Fit = fit_pipeline) -> int:
    parser = argparse.ArgumentParser(prog="python -m truelift.worker")
    parser.add_argument("run_id")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    folder = RunFolder(args.run_dir.resolve())
    if folder.root.name != args.run_id or not folder.config.is_file():
        print("truelift worker: no such run folder", file=sys.stderr)
        return EXIT_ERROR
    return run_job(args.run_id, folder, fit)
