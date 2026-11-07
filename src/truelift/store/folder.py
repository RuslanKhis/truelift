"""One project folder on disk: its layout, its ``project.yaml`` and its knowledge files (D1, D4).

Layout (A1)::

    <projects_dir>/<project_id>/
      project.yaml   name, created_at, knowledge_version
      business.md  market.md  data.md
      dag/  mapping/  proposals/  runs/
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from truelift.store.errors import Conflict, ParseFailed, ParseIssue, SaveFailed
from truelift.store.files import atomic_write, recover
from truelift.store.knowledge import KNOWLEDGE_FILES, Knowledge, load_knowledge, new_file

LAYOUT_DIRS = ("dag", "mapping", "proposals", "runs")
PROJECT_FILE = "project.yaml"
PROJECT_SCHEMA = "truelift.project/1"


class ProjectMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: Literal["truelift.project/1"] = Field(default=PROJECT_SCHEMA, alias="schema")
    id: str
    name: str
    created_at: datetime
    knowledge_version: int = Field(default=0, ge=0)

    def to_bytes(self) -> bytes:
        data = self.model_dump(mode="json", by_alias=True)
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode()


class ProjectFolder:
    def __init__(self, root: Path):
        self.root = root
        self.id = root.name

    @classmethod
    def create(cls, parent: Path, project_id: str, name: str, now: datetime) -> ProjectFolder:
        """Lay out a new project in a temp folder, then rename it into place, so a failure never
        leaves a half-made project behind."""
        target = parent / project_id
        if target.exists():
            raise Conflict("A project with this name already exists.", code="project_exists")
        try:
            parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(tempfile.mkdtemp(dir=parent, prefix=f".{project_id}.creating-"))
        except OSError as exc:
            raise SaveFailed() from exc
        try:
            for name_ in LAYOUT_DIRS:
                (tmp / name_).mkdir()
            for file in KNOWLEDGE_FILES:
                atomic_write(tmp / file, new_file(file, project_id).encode())
            meta = ProjectMeta(id=project_id, name=name, created_at=now)
            atomic_write(tmp / PROJECT_FILE, meta.to_bytes())
            os.rename(tmp, target)
        except OSError as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            raise SaveFailed() from exc
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return cls(target)

    def recover(self) -> None:
        recover(self.root)

    def meta(self) -> ProjectMeta:
        path = self.root / PROJECT_FILE
        try:
            return ProjectMeta.model_validate(yaml.safe_load(path.read_bytes()))
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            issue = ParseIssue(PROJECT_FILE, 1, "This file is missing or not valid.")
            raise ParseFailed([issue]) from exc

    def knowledge(self) -> Knowledge:
        texts: dict[str, str] = {}
        issues: list[ParseIssue] = []
        for file in KNOWLEDGE_FILES:
            try:
                raw = (self.root / file).read_bytes()
            except FileNotFoundError:
                issues.append(ParseIssue(file, 1, "This file is missing."))
                continue
            try:
                texts[file] = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                line = raw[: exc.start].count(b"\n") + 1
                issues.append(ParseIssue(file, line, "This line is not valid UTF-8 text."))
        return load_knowledge(texts, issues)
