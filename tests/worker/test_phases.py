"""G09/A7: phase markers parsed from the pipeline's log, and the log tail (D8). Offline."""

from __future__ import annotations

from pathlib import Path

from tests.worker.fake_worker import BANNERS
from truelift.causal.compile import Profile
from truelift.worker import phases
from truelift.worker.layout import RunFolder


def test_phases_per_profile() -> None:
    assert phases.phases_for(Profile.quick) == [
        "prepare",
        "nuisance models",
        "effect estimation",
        "consolidate results",
        "write outputs",
    ]
    assert phases.SENSITIVITY in phases.phases_for(Profile.standard)
    # A risk acceptance turns sensitivity on in Quick too (compiler, C3 b).
    assert phases.SENSITIVITY in phases.phases_for(Profile.quick, run_sensitivity=True)


def test_banners_move_the_phase_forward_only() -> None:
    assert phases.advance(phases.PREPARE, BANNERS[:1]) == phases.NUISANCE
    assert phases.advance(phases.PREPARE, BANNERS) == phases.CONSOLIDATE
    assert phases.advance(phases.ESTIMATION, [BANNERS[0]]) == phases.ESTIMATION
    sensitivity = "  ├─ Running Sensitivity Analysis Contours..."
    assert phases.advance(phases.CONSOLIDATE, [sensitivity]) == phases.SENSITIVITY


def test_unknown_lines_change_nothing() -> None:
    assert phases.advance(phases.NUISANCE, ["[Phase 1 Progress] 1/1 (100.0%) completed.", "", "x"]) == (
        phases.NUISANCE
    )


def test_log_tail_is_short_and_cut(tmp_path: Path) -> None:
    folder = RunFolder(tmp_path)
    assert folder.log_tail() == []
    folder.log.write_text("\n".join(f"line {i}" for i in range(100)) + "\n" + "y" * 1000 + "\n\n")
    tail = folder.log_tail()
    assert len(tail) == 20 and tail[-2] == "line 99" and len(tail[-1]) == 300
