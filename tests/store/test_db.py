"""G08 A9: state.db runs in WAL mode; two concurrent writers serialise without loss; a database
error or a locked state.db returns the generic 500 from G02 (C11, SB13)."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from truelift.store import ProjectStore
from truelift.store.db import ProjectRow, StateDb, projects


def test_wal_mode_and_busy_timeout(tmp_path: Path):
    db = StateDb(tmp_path / "state.db", busy_timeout_s=2.5)
    with db.transaction() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 2500
    db.dispose()


def test_building_the_app_creates_no_database(tmp_path: Path):
    from tests.api.support import make_settings
    from truelift.api.app import create_app

    create_app(make_settings(tmp_path)).openapi()
    assert not (tmp_path / "state").exists() and not (tmp_path / "projects").exists()


def test_two_concurrent_writers_lose_nothing(tmp_path: Path):
    path = tmp_path / "state.db"
    writers = [StateDb(path), StateDb(path)]  # two engines, as two processes would have
    now = datetime(2026, 11, 7, tzinfo=UTC)
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def write(n: int, db: StateDb) -> None:
        try:
            start.wait()
            for i in range(100):
                with db.transaction() as conn:
                    db.add_project(conn, ProjectRow(f"w{n}-{i}", "x", "setup", now, now))
                db.touch(f"w{n}-{i}", now)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(n, db)) for n, db in enumerate(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with writers[0].transaction() as conn:
        assert conn.execute(select(func.count()).select_from(projects)).scalar() == 200
    for db in writers:
        db.dispose()


def test_two_stores_creating_projects_at_once(tmp_path: Path):
    stores = [ProjectStore(tmp_path / "projects", StateDb(tmp_path / "state.db")) for _ in range(2)]
    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def create(n: int) -> None:
        try:
            start.wait()
            for i in range(10):
                stores[n].create(f"store {n} project {i}")
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=create, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(stores[0].list()) == 20
    assert len([p for p in (tmp_path / "projects").iterdir() if not p.name.startswith(".")]) == 20
    for s in stores:
        s.db.dispose()


def test_a_locked_state_db_returns_the_generic_500(client, api_store, tmp_path: Path):
    client.get("/api/projects")  # creates state.db
    holder = sqlite3.connect(api_store.db.path, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        r = client.post("/api/projects", json={"name": "Garden tools"})
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "internal_error" and body["request_id"] == r.headers["x-request-id"]
    assert set(body) == {"code", "message", "request_id"}
    assert "locked" not in r.text.lower() and "insert" not in r.text.lower()
    assert not (api_store.projects_dir / "garden-tools").exists()  # nothing half-made
    assert client.post("/api/projects", json={"name": "Garden tools"}).status_code == 201


def test_a_database_error_returns_the_generic_500(client, api_store, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError(
            "SELECT projects.id FROM projects", {}, sqlite3.OperationalError("disk I/O error")
        )

    monkeypatch.setattr(StateDb, "projects", broken)
    r = client.get("/api/projects")
    assert r.status_code == 500 and r.json()["code"] == "internal_error"
    assert "SELECT" not in r.text and "disk" not in r.text


@pytest.mark.parametrize("failure", ["add", "commit"])
def test_a_failed_create_leaves_no_folder(store: ProjectStore, monkeypatch, failure):
    def broken(*args, **kwargs):
        raise OperationalError("INSERT", {}, sqlite3.OperationalError("database is locked"))

    if failure == "add":
        monkeypatch.setattr(StateDb, "add_project", broken)
    else:
        real = StateDb.transaction

        @contextmanager
        def failing_commit(self):
            with real(self) as conn:
                yield conn
                broken()  # the COMMIT fails after the folder was laid out

        monkeypatch.setattr(StateDb, "transaction", failing_commit)
    with pytest.raises(OperationalError):
        store.create("Garden tools")
    monkeypatch.undo()
    assert not (store.projects_dir / "garden-tools").exists()
    assert store.list() == []
