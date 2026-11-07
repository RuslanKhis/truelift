"""``state.db``: the app's operational SQLite database (D1, D21).

SQLAlchemy Core on SQLite in WAL mode. Every transaction starts with ``BEGIN IMMEDIATE``, so
two writers (two threads, or two processes) queue on SQLite's write lock instead of failing
half-way or losing an update; a writer that waits longer than the busy timeout gets
``OperationalError("database is locked")``, which the API turns into its generic 500 (A9, SB13).

G08 owns the ``projects`` index. Later goals add their own tables (runs: G09; consent, usage
and the ledger: G11) to the same metadata. The engine is created on first use, so building the
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
    Column,
    Connection,
    DateTime,
    Engine,
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

    def dispose(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
