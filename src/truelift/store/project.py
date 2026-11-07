"""``ProjectStore``: the only writer of project folders (C11) and of the project index in
``state.db`` (D1).

Every operation on a project holds that project's lock, finishes any interrupted transaction
first (``recover``) and checks the version the caller saw, so two requests cannot interleave
their writes. One truelift process serves a projects folder; two processes on the same folder
are not guarded in phase 1 (see the G08 Evidence).
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from truelift.store import proposals as proposals_mod
from truelift.store.db import ProjectRow, StateDb, projects
from truelift.store.errors import Conflict, NotFound, StoreError
from truelift.store.folder import PROJECT_FILE, ProjectFolder
from truelift.store.knowledge import Fact, FactStatus, Knowledge, Source
from truelift.store.proposals import FactProposal, ProposalStatus, ProposalView
from truelift.store.versions import Confirmation, VersionKind, Versions, VersionStatus

log = logging.getLogger("truelift.store")

PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower())[:63].strip("-") or "project"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ProjectInfo:
    id: str
    name: str
    stage: str
    created_at: datetime
    updated_at: datetime
    knowledge_version: int
    dag_version: int | None
    mapping_version: int | None


class ProjectStore:
    def __init__(
        self,
        projects_dir: Path,
        db: StateDb,
        *,
        reserved_ids: frozenset[str] = frozenset(),
        clock: Callable[[], datetime] = _utcnow,
    ):
        self.projects_dir = projects_dir
        self.db = db
        self.reserved_ids = reserved_ids
        self.clock = clock
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._create_lock = threading.Lock()

    # --- locking and lookup ------------------------------------------------------------------

    def _lock(self, project_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(project_id, threading.RLock())

    def _folder(self, project_id: str) -> ProjectFolder:
        root = self.projects_dir / project_id
        if not PROJECT_ID.match(project_id) or not (root / PROJECT_FILE).is_file():
            raise NotFound("No project with this ID.", code="project_not_found")
        return ProjectFolder(root)

    @contextmanager
    def open(self, project_id: str) -> Iterator[ProjectFolder]:
        """Hold the project's lock, with any interrupted change rolled back."""
        with self._lock(project_id):
            folder = self._folder(project_id)
            folder.recover()
            yield folder

    # --- projects ----------------------------------------------------------------------------

    def create(self, name: str) -> ProjectInfo:
        project_id = slugify(name)
        if project_id in self.reserved_ids:
            raise Conflict("A project with this name already exists.", code="project_exists")
        now = self.clock()
        row = ProjectRow(id=project_id, name=name, stage="setup", created_at=now, updated_at=now)
        with self._create_lock, self._lock(project_id):
            folder: ProjectFolder | None = None
            try:
                with self.db.transaction() as conn:
                    if conn.execute(select(projects.c.id).where(projects.c.id == project_id)).first():
                        raise Conflict("A project with this name already exists.", code="project_exists")
                    self.db.add_project(conn, row)
                    folder = ProjectFolder.create(self.projects_dir, project_id, name, now)
            except BaseException:
                # The row rolled back; a folder made before a failed commit goes with it.
                if folder is not None:
                    shutil.rmtree(folder.root, ignore_errors=True)
                raise
            return self._info(row, folder)

    def list(self) -> list[ProjectInfo]:
        out = []
        for row in self.db.projects():
            try:
                with self.open(row.id) as folder:
                    out.append(self._info(row, folder))
            except NotFound:
                continue  # folder removed by hand; the index is only a cache of the folders
            except StoreError as exc:
                log.warning("project %s has an unreadable file: %s", row.id, exc.code)
                out.append(
                    ProjectInfo(row.id, row.name, row.stage, row.created_at, row.updated_at, 0, None, None)
                )
        return out

    def get(self, project_id: str) -> ProjectInfo:
        if not PROJECT_ID.match(project_id):
            raise NotFound("No project with this ID.", code="project_not_found")
        row = self.db.project(project_id)
        if row is None:
            raise NotFound("No project with this ID.", code="project_not_found")
        with self.open(project_id) as folder:
            return self._info(row, folder)

    def _info(self, row: ProjectRow, folder: ProjectFolder) -> ProjectInfo:
        meta = folder.meta()
        return ProjectInfo(
            id=row.id,
            name=row.name,
            stage=row.stage,
            created_at=row.created_at,
            updated_at=row.updated_at,
            knowledge_version=meta.knowledge_version,
            dag_version=Versions(folder, VersionKind.dag).current(),
            mapping_version=Versions(folder, VersionKind.mapping).current(),
        )

    def _touch(self, project_id: str) -> None:
        # The index is a cache: a failure here must not report an applied change as failed.
        try:
            self.db.touch(project_id, self.clock())
        except SQLAlchemyError as exc:
            log.warning("could not update the project index for %s: %s", project_id, type(exc).__name__)

    # --- knowledge and proposals -------------------------------------------------------------

    def knowledge(self, project_id: str) -> Knowledge:
        with self.open(project_id) as folder:
            return folder.knowledge()

    def propose_fact(
        self,
        project_id: str,
        *,
        file: str,
        text: str,
        source: Source,
        summary: str,
        fact_status: FactStatus = FactStatus.confirmed,
        fact_id: str | None = None,
        section: str | None = None,
        supports: tuple[str, ...] | list[str] = (),
    ) -> FactProposal:
        """For agents' ``propose_*`` tools (G13). Changes no knowledge file."""
        with self.open(project_id) as folder:
            return proposals_mod.create_fact_proposal(
                folder,
                file=file,
                text=text,
                fact_status=fact_status,
                source=source,
                summary=summary,
                now=self.clock(),
                fact_id=fact_id,
                section=section,
                supports=supports,
            )

    def proposals(self, project_id: str, status: ProposalStatus | None = None) -> list[ProposalView]:
        with self.open(project_id) as folder:
            return proposals_mod.views(folder, status)

    def proposal(self, project_id: str, proposal_id: str) -> ProposalView:
        for view in self.proposals(project_id):
            if view.proposal.id == proposal_id:
                return view
        raise NotFound("No proposal with this ID.", code="proposal_not_found")

    def decide(
        self,
        project_id: str,
        proposal_id: str,
        *,
        accept: bool,
        knowledge_version: int,
        resolves_contradiction: bool = False,
    ) -> FactProposal:
        with self.open(project_id) as folder:
            result = proposals_mod.decide(
                folder,
                proposal_id,
                accept=accept,
                knowledge_version=knowledge_version,
                resolves_contradiction=resolves_contradiction,
                now=self.clock(),
            )
        self._touch(project_id)
        return result

    def accept_batch(
        self, project_id: str, proposal_ids: list[str], *, knowledge_version: int
    ) -> list[FactProposal]:
        with self.open(project_id) as folder:
            result = proposals_mod.accept_batch(
                folder, proposal_ids, knowledge_version=knowledge_version, now=self.clock()
            )
        self._touch(project_id)
        return result

    # --- DAG and mapping versions ------------------------------------------------------------

    def write_version(
        self,
        project_id: str,
        kind: VersionKind,
        content: dict[str, Any],
        *,
        expected_current: int | None,
        cites: list[str] | tuple[str, ...] = (),
        data_fingerprint: str | None = None,
    ) -> int:
        with self.open(project_id) as folder:
            version = Versions(folder, kind).write(
                content,
                expected_current=expected_current,
                now=self.clock(),
                cites=cites,
                data_fingerprint=data_fingerprint,
            )
        self._touch(project_id)
        return version

    def confirm_version(self, project_id: str, kind: VersionKind, version: int) -> Confirmation:
        with self.open(project_id) as folder:
            facts: dict[str, Fact] = folder.knowledge().facts
            confirmation = Versions(folder, kind).confirm(version, facts=facts, now=self.clock())
        self._touch(project_id)
        return confirmation

    def version_status(self, project_id: str, kind: VersionKind, version: int) -> VersionStatus:
        with self.open(project_id) as folder:
            return Versions(folder, kind).status(version, folder.knowledge().facts)
