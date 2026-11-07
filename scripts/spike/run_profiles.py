"""G03 spike: run doubleml-pipeline under the Quick and Standard profiles and measure them.

    uv run python scripts/spike/run_profiles.py                 # Quick once on the stand-in panel
    uv run python scripts/spike/run_profiles.py --full          # Quick once, Standard x3 (A2, A3)
    uv run python scripts/spike/run_profiles.py --data private  # the private CSV (core developers)

Each run records wall-clock time, peak resident memory of the whole process tree
(sampled every 0.25 s; shared pages are counted once per process, so it overstates),
CPU count, versions and the headline numbers, in ``<out>/<profile>_<n>/spike.json``.
Stand-in runs go to ``runs/spike/`` (git-ignored). Private runs read
``private/spike_config.json`` and write only under ``private/spike/``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _omp import ensure_openmp  # noqa: E402

OMP_SOURCE = ensure_openmp()

import pandas as pd  # noqa: E402
import psutil  # noqa: E402
from doubleml_pipeline.evaluation import hparam_search  # noqa: E402
from doubleml_pipeline.preprocessing.scalers import CausalDataScaler  # noqa: E402
from doubleml_pipeline.visualization import plots  # noqa: E402
from doubleml_pipeline.workflow import CausalWorkflowOrchestrator  # noqa: E402
from standin_panel import make_panel, standin_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# Candidate run profiles (D9). G03 measures them; G09 adopts them.
PROFILES: dict[str, dict] = {
    "quick": {
        "ml_models_y": ["lgbm"],
        "ml_models_t": ["lgbm"],
        "n_folds_list": [5],
        "time_budget": 10,
        "run_sensitivity": False,
        "run": {"top_n": 1, "n_reps": 3},
    },
    "standard": {
        "ml_models_y": ["lgbm", "xgboost"],
        "ml_models_t": ["lgbm", "xgboost"],
        "n_folds_list": [3, 5],
        "time_budget": 30,
        "run_sensitivity": True,
        "sensitivity_scope": ["total", "geo"],
        "run": {"top_n": 3, "n_reps": 10},
    },
}

PINNED = [
    "doubleml-pipeline",
    "doubleml",
    "flaml",
    "lightgbm",
    "xgboost",
    "scikit-learn",
    "numpy",
    "pandas",
    "scipy",
    "google-adk",
    "litellm",
]


class PeakRss:
    """Samples the summed RSS of this process and all its descendants."""

    def __init__(self, interval: float = 0.25) -> None:
        self.interval = interval
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        me = psutil.Process()
        while not self._stop.is_set():
            total = 0
            for p in [me, *me.children(recursive=True)]:
                with contextlib.suppress(psutil.Error):
                    total += p.memory_info().rss
            self.peak = max(self.peak, total)
            self._stop.wait(self.interval)

    def __enter__(self) -> PeakRss:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()


def load_data(which: str) -> tuple[pd.DataFrame, dict, dict, Path]:
    if which == "standin":
        df, truth = make_panel()
        return df, standin_config(), truth, ROOT / "runs" / "spike" / "standin"
    cfg_path = ROOT / "private" / "spike_config.json"
    if not cfg_path.exists():
        sys.exit("private materials absent: private/spike_config.json")
    cfg = {k: v for k, v in json.loads(cfg_path.read_text()).items() if not k.startswith("_")}
    df = pd.read_csv(ROOT / "private" / cfg.pop("csv"))
    if cfg.get("date_col"):
        df[cfg["date_col"]] = pd.to_datetime(df[cfg["date_col"]])
    keep = cfg.pop("keep_cols")
    return df[keep].reset_index(drop=True), cfg, {}, ROOT / "private" / "spike" / "runs"


PRIOR_PLOT_ERRORS: list[str] = []


def _tolerant_prior_plot(original):
    """doubleml-pipeline 0.2.3 crashes here on an ATE-only run (G03 finding F2).

    With no CATE covariates the per-date ROI ratio is constant, numpy refuses to build
    30 bins over a ~1e-12 range, and run_full_pipeline raises before sensitivity runs.
    """

    def wrapper(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except ValueError as exc:
            PRIOR_PLOT_ERRORS.append(str(exc))

    return wrapper


plots.plot_prior_distributions = _tolerant_prior_plot(plots.plot_prior_distributions)


def headline(out_dir: Path, cfg: dict) -> dict:
    """Total ROI as money over money, with its interval (G03 finding F1).

    For a ``percentage`` treatment, ``total_estimated_roi`` in consolidated_3b_summary.csv
    divides by the summed rate, not by spend. The money ROI is Σ incremental KPI ÷ Σ spend
    over consolidated_1a_full_df.csv, the same per-row ratio as ``roi_amount_based_<d>``.
    """
    full = out_dir / "step4_consolidated_results" / "consolidated_1a_full_df.csv"
    if not full.exists():
        return {"error": "consolidated_1a_full_df.csv missing"}
    d_col = cfg["d_cols"][0]
    df = pd.read_csv(full)
    spend = df[cfg["treatment_spend_cols"][d_col]].sum()
    kpi = f"estimated_incremental_KPI_{d_col}"
    return {
        "total_roi": float(df[kpi].sum() / spend),
        "roi_lo": float(df[f"{kpi}_2.5%"].sum() / spend),
        "roi_hi": float(df[f"{kpi}_97.5%"].sum() / spend),
    }


class ReusedHparams(CausalWorkflowOrchestrator):
    """Fits the hyperparameters a previous run saved instead of searching again (A3).

    0.2.3 has no public input for this: it overrides the private
    ``_run_global_hparam_search`` and reads the saved files with ``read_hparams_json``.
    """

    def __init__(self, *args, hparams_from: Path, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.hparams_from = hparams_from

    def _run_global_hparam_search(self, d_col, x_cols, df_norm, out_dir):
        found = {}
        for learner in {*self.ml_models_y, *self.ml_models_t}:
            name = hparam_search.hparams_json_name(d_col, learner)
            src = self.hparams_from / f"step1_exploration_{d_col}" / name
            shutil.copy(src, Path(out_dir) / name)
            for side, res in hparam_search.read_hparams_json(str(src)).items():
                found[(side, learner)] = res
        wanted = [(hparam_search.SIDE_Y, m) for m in self.ml_models_y]
        wanted += [(hparam_search.SIDE_T, m) for m in self.ml_models_t]
        return {key: found[key] for key in wanted}


@contextlib.contextmanager
def cpu_load(n: int):
    """Keep n cores busy, standing in for a user who keeps working during a run."""
    procs = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(n)]
    try:
        yield
    finally:
        for proc in procs:
            proc.kill()
            proc.wait()


def run_once(
    df: pd.DataFrame,
    cfg: dict,
    profile: str,
    out_dir: Path,
    hparams_from: Path | None = None,
    load: int = 0,
) -> dict:
    p = {k: v for k, v in PROFILES[profile].items() if k != "run"}
    cfg = dict(cfg)
    scaler = CausalDataScaler(**cfg.pop("scaler", {}))
    out_dir.mkdir(parents=True, exist_ok=True)
    kwargs = {"output_dir": str(out_dir), "n_jobs": -1, **cfg, **p}
    if hparams_from:
        orch = ReusedHparams(hparams_from=hparams_from, **kwargs)
    else:
        orch = CausalWorkflowOrchestrator(**kwargs)
    log = io.StringIO()
    t0 = time.perf_counter()
    with cpu_load(load), PeakRss() as rss, contextlib.redirect_stdout(log):
        orch.run_full_pipeline(df.copy(), scaler, **PROFILES[profile]["run"])
    elapsed = time.perf_counter() - t0
    (out_dir / "pipeline_stdout.log").write_text(log.getvalue())
    errors = list(PRIOR_PLOT_ERRORS)
    PRIOR_PLOT_ERRORS.clear()
    return {
        "profile": profile,
        "hparams_reused": bool(hparams_from),
        "cpu_load": load,
        "wall_clock_s": round(elapsed, 1),
        "peak_rss_mb": round(rss.peak / 2**20),
        "rows": len(df),
        "headline": headline(out_dir, cfg),
        "prior_plot_errors": errors,
        "outputs": sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()),
    }


def environment() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "openmp": OMP_SOURCE,
        "versions": {name: metadata.version(name) for name in PINNED},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", choices=["standin", "private"], default="standin")
    ap.add_argument("--full", action="store_true", help="Quick once, then Standard three times")
    ap.add_argument("--profile", choices=list(PROFILES), help="run one profile once")
    ap.add_argument("--load", type=int, default=0, help="keep N extra cores busy during the run")
    ap.add_argument(
        "--reuse-hparams", metavar="RUN", help="reuse the hyperparameters saved by run RUN (e.g. standard_1)"
    )
    args = ap.parse_args()

    plan = [("quick", "quick_1")]
    if args.full:
        plan = [("quick", "quick_1")] + [("standard", f"standard_{n}") for n in (1, 2, 3)]
    elif args.profile:
        label = args.profile
        if args.load:
            label += f"_load{args.load}"
        if args.reuse_hparams:
            label += f"_reuse-{args.reuse_hparams}"
        plan = [(args.profile, label)]

    df, cfg, truth, base = load_data(args.data)
    hparams_from = base / args.reuse_hparams if args.reuse_hparams else None
    env = environment()
    print(json.dumps(env, indent=2))
    results = []
    for profile, label in plan:
        out_dir = base / label
        res = run_once(df, cfg, profile, out_dir, hparams_from=hparams_from, load=args.load)
        (out_dir / "spike.json").write_text(json.dumps({**res, "env": env, "truth": truth}, indent=2))
        print(json.dumps(res))
        results.append(res)
    summary = {"env": env, "truth": truth, "runs": results}
    name = "spike_summary.json" if args.full else f"spike_summary_{plan[0][1]}.json"
    (base / name).write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
