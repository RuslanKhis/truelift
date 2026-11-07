"""Fixtures for the project-store tests (G08). Everything runs offline in ``tmp_path``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.support import BASE, ORIGIN, TOKEN, make_settings
from truelift.api.app import create_app
from truelift.store import ProjectStore, Source, SourceKind
from truelift.store.db import StateDb

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def interview(turn: int, quote: str) -> Source:
    return Source(SourceKind.interview, turn, quote)


def snapshot(root: Path, *, skip: tuple[str, ...] = ("proposals",)) -> dict[str, bytes]:
    """Every file in a project folder, by relative path, except the directories in ``skip``."""
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.relative_to(root).parts[0] not in skip
    }


@pytest.fixture
def store(tmp_path: Path) -> Iterator[ProjectStore]:
    s = ProjectStore(
        tmp_path / "projects",
        StateDb(tmp_path / "state" / "state.db"),
        reserved_ids=frozenset({"petfood-de"}),
        clock=lambda: NOW,
    )
    yield s
    s.db.dispose()


@pytest.fixture
def project(store: ProjectStore) -> str:
    return store.create("Pet food DE").id


@pytest.fixture
def root(store: ProjectStore, project: str) -> Path:
    return store.projects_dir / project


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(make_settings(tmp_path, db_busy_timeout_s=0.2))


@pytest.fixture
def api_store(app: FastAPI) -> Iterator[ProjectStore]:
    yield app.state.store
    app.state.store.db.dispose()


@pytest.fixture
def client(app: FastAPI, api_store: ProjectStore) -> Iterator[TestClient]:
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
    with TestClient(app, base_url=BASE, headers=headers, raise_server_exceptions=False) as c:
        yield c
