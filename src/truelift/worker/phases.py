"""Phase markers parsed from the pipeline's log (D8, C10/A7).

doubleml-pipeline 0.2.3 prints its progress to stdout and logs no per-phase timings (G03 note,
F3). The worker sends that output to ``log.txt`` and this parser maps the lines it knows to the
phases the progress bar shows. A line it does not know changes nothing, so a new pipeline
version can only make the bar coarser, never wrong.
"""

from __future__ import annotations

import re

from truelift.causal.compile import Profile

PREPARE = "prepare"
NUISANCE = "nuisance models"
ESTIMATION = "effect estimation"
CONSOLIDATE = "consolidate results"
SENSITIVITY = "sensitivity"
WRITE = "write outputs"

_ALL = (PREPARE, NUISANCE, ESTIMATION, CONSOLIDATE, SENSITIVITY, WRITE)

# The pipeline's own banners (0.2.3), as printed in the G03 runs.
_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"=== Phase 1: "), NUISANCE),
    (re.compile(r"=== Phase 2: "), NUISANCE),
    (re.compile(r"=== Phase 3: "), ESTIMATION),
    (re.compile(r"=== Phase 4: "), CONSOLIDATE),
    (re.compile(r"Running Sensitivity Analysis"), SENSITIVITY),
)


def phases_for(profile: Profile | str, run_sensitivity: bool | None = None) -> list[str]:
    """The phases a run of this profile goes through, in order."""
    sensitivity = Profile(profile) is Profile.standard if run_sensitivity is None else run_sensitivity
    return [p for p in _ALL if sensitivity or p != SENSITIVITY]


def phase_of(line: str) -> str | None:
    """The phase a log line starts, or None."""
    for pattern, phase in _MARKERS:
        if pattern.search(line):
            return phase
    return None


def advance(current: str, lines: list[str]) -> str:
    """The phase after reading ``lines``. Phases only move forward."""
    order = {p: i for i, p in enumerate(_ALL)}
    for line in lines:
        found = phase_of(line)
        if found is not None and order[found] > order.get(current, -1):
            current = found
    return current
