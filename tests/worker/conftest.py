"""Fixtures for the worker tests (G09): a store in ``tmp_path`` with the scripted synthetic project
(seed 1, confirmed DAG and mapping). The tests spawn real worker processes. Local."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from truelift.store import ProjectStore
from truelift.store.db import StateDb
from truelift.worker.scripted import create_scripted_project


@pytest.fixture
def store(tmp_path: Path) -> Iterator[ProjectStore]:
    s = ProjectStore(tmp_path / "projects", StateDb(tmp_path / "state" / "state.db"))
    yield s
    s.db.dispose()


@pytest.fixture
def project(store: ProjectStore) -> str:
    project_id, _ = create_scripted_project(store, "demo", 1)
    return project_id
