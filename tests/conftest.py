"""Shared pytest configuration.

Tests marked ``private`` need the private benchmark materials, which live only
on a core developer's machine and never in the repository (contract C13).
They are collected everywhere and skipped when ``private/benchmark.yaml`` is
absent, so CI and outside contributors see them as skipped, not passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_BENCHMARK = REPO_ROOT / "private" / "benchmark.yaml"
PRIVATE_SKIP_REASON = "private materials absent"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if PRIVATE_BENCHMARK.is_file():
        return
    skip_private = pytest.mark.skip(reason=PRIVATE_SKIP_REASON)
    for item in items:
        if "private" in item.keywords:
            item.add_marker(skip_private)
