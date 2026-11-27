"""``state.db``: the app's operational SQLite database (D1, D21).

SQLAlchemy Core on SQLite in WAL mode. Every transaction starts with ``BEGIN IMMEDIATE``, so
two writers (two threads, or two processes) queue on SQLite's write lock instead of failing
half-way or losing an update; a writer that waits longer than the busy timeout gets
``OperationalError("database is locked")``, which the API turns into its generic 500 (A9, SB13).

G08 owns the ``projects`` index and G09 the ``runs`` table. Later goals add their own tables
(consent, usage and the ledger: G11) to the same metadata. The engine is created on first use, so building the
app (for example to dump the OpenAPI document) never creates a database.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.types import TypeDecorator

metadata = MetaData()


class UtcDateTime(TypeDecorator[datetime]):
    """SQLite has no time zones: store naive UTC, return aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


projects = Table(
    "projects",
    metadata,
    Column("id", String(63), primary_key=True),
    Column("name", String(80), nullable=False),
    Column("stage", String(32), nullable=False),
    Column("created_at", UtcDateTime(), nullable=False),
    Column("updated_at", UtcDateTime(), nullable=False),
)


# One row per pipeline run (G09; C10, D8). ``status`` is the run's authority: results are served
# only for ``succeeded`` (with a manifest). ``pid`` is the worker, which leads its own process
# group; ``owner_pid`` is the truelift process that spawned and watches it.
runs = Table(
    "runs",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("project_id", String(63), nullable=False, index=True),
    Column("dag_version", Integer, nullable=False),
    Column("profile", String(16), nullable=False),
    Column("status", String(16), nullable=False, index=True),
    Column("reason", String(600)),
    Column("pid", Integer),
    Column("owner_pid", Integer),
    Column("cancel_requested", Boolean, nullable=False, default=False),
    Column("config_sha256", String(64), nullable=False),
    Column("created_at", UtcDateTime(), nullable=False),
    Column("started_at", UtcDateTime()),
    Column("finished_at", UtcDateTime()),
)

ACTIVE_RUN_STATUSES = ("queued", "running")


@dataclass(frozen=True)
class RunRow:
    id: str
    project_id: str
    dag_version: int
    profile: str
    status: str
    reason: str | None
    pid: int | None
    owner_pid: int | None
    cancel_requested: bool
    config_sha256: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class ProjectRow:
    id: str
    name: str
    stage: str
    created_at: datetime
    updated_at: datetime


def _ensure_wal(cursor: sqlite3.Cursor, busy_timeout_s: float) -> None:
    """WAL is stored in the database file, so only the first connection ever has to switch it.
    Switching needs a lock that SQLite's busy handler does not wait for, and asking again on
    every connection fails while another writer is active, so check first and retry briefly."""
    deadline = time.monotonic() + busy_timeout_s
    while True:
        try:
            if cursor.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
                return
            cursor.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def make_engine(path: Path, busy_timeout_s: float = 5.0) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"timeout": busy_timeout_s, "check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        # Let SQLAlchemy's "begin" event below issue BEGIN itself (pysqlite recipe).
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout_s * 1000)}")
        cursor.execute("PRAGMA foreign_keys=ON")
        _ensure_wal(cursor, busy_timeout_s)
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    metadata.create_all(engine)
    return engine


class StateDb:
    def __init__(self, path: Path, busy_timeout_s: float = 5.0):
        self.path = path
        self.busy_timeout_s = busy_timeout_s
        self._engine: Engine | None = None
        self._lock = threading.Lock()

    @property
    def engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self._engine = make_engine(self.path, self.busy_timeout_s)
            return self._engine

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.begin() as conn:
            yield conn

    def add_project(self, conn: Connection, row: ProjectRow) -> None:
        conn.execute(insert(projects).values(**row.__dict__))

    def projects(self) -> list[ProjectRow]:
        with self.transaction() as conn:
            rows = conn.execute(select(projects).order_by(projects.c.created_at, projects.c.id)).all()
        return [ProjectRow(**r._asdict()) for r in rows]

    def project(self, project_id: str) -> ProjectRow | None:
        with self.transaction() as conn:
            row = conn.execute(select(projects).where(projects.c.id == project_id)).first()
        return ProjectRow(**row._asdict()) if row else None

    def touch(self, project_id: str, at: datetime) -> None:
        with self.transaction() as conn:
            conn.execute(update(projects).where(projects.c.id == project_id).values(updated_at=at))

    # --- runs (G09) ---------------------------------------------------------------------------

    def insert_run_if_idle(self, row: RunRow) -> RunRow | None:
        """Insert ``row`` unless a run is queued or running on this machine; return that run then.

        ``BEGIN IMMEDIATE`` takes SQLite's write lock before the check, so two processes (the app
        and ``truelift run``) cannot both pass it (C10, SB19: one run at a time per machine)."""
        with self.transaction() as conn:
            active = conn.execute(select(runs).where(runs.c.status.in_(ACTIVE_RUN_STATUSES)).limit(1)).first()
            if active is not None:
                return RunRow(**active._asdict())
            conn.execute(insert(runs).values(**row.__dict__))
        return None

    def run(self, run_id: str) -> RunRow | None:
        with self.transaction() as conn:
            row = conn.execute(select(runs).where(runs.c.id == run_id)).first()
        return RunRow(**row._asdict()) if row else None

    def runs_for(self, project_id: str) -> list[RunRow]:
        with self.transaction() as conn:
            rows = conn.execute(
                select(runs).where(runs.c.project_id == project_id).order_by(runs.c.created_at.desc())
            ).all()
        return [RunRow(**r._asdict()) for r in rows]

    def active_runs(self) -> list[RunRow]:
        with self.transaction() as conn:
            rows = conn.execute(select(runs).where(runs.c.status.in_(ACTIVE_RUN_STATUSES))).all()
        return [RunRow(**r._asdict()) for r in rows]

    def update_run(self, run_id: str, *, only_if_active: bool = False, **values: object) -> bool:
        """Update one run. With ``only_if_active`` a run that already ended is left as it is, so
        a late writer never turns a finished run back (returns False then)."""
        with self.transaction() as conn:
            stmt = update(runs).where(runs.c.id == run_id)
            if only_if_active:
                stmt = stmt.where(runs.c.status.in_(ACTIVE_RUN_STATUSES))
            return conn.execute(stmt.values(**values)).rowcount == 1

    def dispose(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
