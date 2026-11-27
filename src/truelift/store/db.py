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
    delete,
    event,
    func,
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


# --- Model gateway (G11; C7, C8, C15, D17) --------------------------------------------------
# No table holds a key, a prompt or a reply: consent, the budget and per-call sizes only.

# One row per project and provider: the disclosure version the user accepted (C8).
consents = Table(
    "consents",
    metadata,
    Column("project_id", String(63), primary_key=True),
    Column("provider", String(16), primary_key=True),
    Column("disclosure_version", String(32), nullable=False),
    Column("accepted_at", UtcDateTime(), nullable=False),
)

# The token budget the user set for a project (C15). No row means the default budget.
ai_budgets = Table(
    "ai_budgets",
    metadata,
    Column("project_id", String(63), primary_key=True),
    Column("token_budget", Integer, nullable=False),
)

# The egress ledger (C8, D17): one row per provider attempt, written before the request leaves,
# with categories, sizes and tokens, never content. ``status``: ``sent`` (reserved, in flight),
# ``settled`` (provider usage), ``estimated`` (reply without usage), ``lost`` (no reply; the
# estimate stays charged, C15), ``rejected`` (refused by the provider, not billed),
# ``not_sent`` (the connection never opened).
ledger = Table(
    "egress_ledger",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", String(63), nullable=False, index=True),
    Column("at", UtcDateTime(), nullable=False),
    Column("provider", String(16), nullable=False),
    Column("model_id", String(80), nullable=False),
    Column("categories", String(200), nullable=False),
    Column("bytes_sent", Integer, nullable=False),
    Column("input_tokens", Integer, nullable=False),
    Column("output_tokens", Integer, nullable=False),
    Column("status", String(16), nullable=False),
)

# Small app-wide settings, for example the active provider. Never a secret.
app_settings = Table(
    "app_settings",
    metadata,
    Column("key", String(40), primary_key=True),
    Column("value", String(200), nullable=False),
)


@dataclass(frozen=True)
class ConsentRow:
    project_id: str
    provider: str
    disclosure_version: str
    accepted_at: datetime


@dataclass(frozen=True)
class LedgerRow:
    id: int
    project_id: str
    at: datetime
    provider: str
    model_id: str
    categories: str
    bytes_sent: int
    input_tokens: int
    output_tokens: int
    status: str


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

    # --- model gateway (G11) ----------------------------------------------------------------

    def consent(self, project_id: str, provider: str) -> ConsentRow | None:
        with self.transaction() as conn:
            row = conn.execute(
                select(consents).where(consents.c.project_id == project_id, consents.c.provider == provider)
            ).first()
        return ConsentRow(**row._asdict()) if row else None

    def set_consent(self, row: ConsentRow) -> None:
        with self.transaction() as conn:
            conn.execute(
                delete(consents).where(
                    consents.c.project_id == row.project_id, consents.c.provider == row.provider
                )
            )
            conn.execute(insert(consents).values(**row.__dict__))

    def token_budget(self, project_id: str) -> int | None:
        with self.transaction() as conn:
            return conn.execute(
                select(ai_budgets.c.token_budget).where(ai_budgets.c.project_id == project_id)
            ).scalar()

    def set_token_budget(self, project_id: str, token_budget: int) -> None:
        with self.transaction() as conn:
            conn.execute(delete(ai_budgets).where(ai_budgets.c.project_id == project_id))
            conn.execute(insert(ai_budgets).values(project_id=project_id, token_budget=token_budget))

    @staticmethod
    def _tokens_used(conn: Connection, project_id: str) -> int:
        total = conn.execute(
            select(func.coalesce(func.sum(ledger.c.input_tokens + ledger.c.output_tokens), 0)).where(
                ledger.c.project_id == project_id
            )
        ).scalar()
        return int(total or 0)

    def tokens_used(self, project_id: str) -> int:
        with self.transaction() as conn:
            return self._tokens_used(conn, project_id)

    def reserve_call(self, row: LedgerRow, token_budget: int) -> int | None:
        """Write the ledger row of an attempt and charge its estimate, unless the estimate would
        take the project past ``token_budget``; return the row ID, or None when refused.

        ``BEGIN IMMEDIATE`` makes the check and the insert one step, so two writers cannot both
        pass the same remaining budget (C15)."""
        with self.transaction() as conn:
            used = self._tokens_used(conn, row.project_id)
            if used >= token_budget or used + row.input_tokens + row.output_tokens > token_budget:
                return None
            values = {k: v for k, v in row.__dict__.items() if k != "id"}
            return int(conn.execute(insert(ledger).values(**values)).inserted_primary_key[0])

    def settle_call(self, ledger_id: int, **values: object) -> None:
        with self.transaction() as conn:
            conn.execute(update(ledger).where(ledger.c.id == ledger_id).values(**values))

    def ledger_rows(self, project_id: str, limit: int = 500) -> list[LedgerRow]:
        with self.transaction() as conn:
            rows = conn.execute(
                select(ledger)
                .where(ledger.c.project_id == project_id)
                .order_by(ledger.c.id.desc())
                .limit(limit)
            ).all()
        return [LedgerRow(**r._asdict()) for r in rows]

    def setting(self, key: str) -> str | None:
        with self.transaction() as conn:
            return conn.execute(select(app_settings.c.value).where(app_settings.c.key == key)).scalar()

    def set_setting(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(delete(app_settings).where(app_settings.c.key == key))
            conn.execute(insert(app_settings).values(key=key, value=value))

    def dispose(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
