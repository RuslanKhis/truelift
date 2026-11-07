"""Immutable DAG and mapping versions with a current pointer and confirmation records (C11, C1).

``dag/v4.yaml`` is written once and never overwritten. ``dag/current`` names the current
version. A write puts the new ``vN`` file down first and moves the pointer second (A6), so a
failure between the two leaves the previous version current. A write or confirmation that
carries a version other than the current one is refused with ``StaleVersion`` (A7).

Confirming records the content hash of ``vN`` and the fingerprint of every fact it cites in
``dag/v4.confirmed.yaml``. The status is worked out from those hashes each time it is read, so
any later change to a cited fact, by proposal or by hand, makes the version ``stale`` (A6, C1).

The ``content`` of a version is owned by its goal (G06/G31 for the DAG, G07 for the mapping);
the store keeps it inside an envelope with the cited fact IDs and the data fingerprint.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import yaml

from truelift.store.errors import Conflict, NotFound, ParseFailed, ParseIssue, StaleVersion
from truelift.store.files import atomic_write
from truelift.store.folder import ProjectFolder
from truelift.store.knowledge import Fact

_VERSION_FILE = re.compile(r"^v([0-9]{1,6})\.yaml$")
_POINTER = re.compile(r"^v([0-9]{1,6})\n?$")


class VersionKind(StrEnum):
    dag = "dag"
    mapping = "mapping"


class VersionStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    stale = "stale"


@dataclass(frozen=True)
class VersionRecord:
    version: int
    created_at: str
    cites: tuple[str, ...]
    data_fingerprint: str | None
    content: dict[str, Any]
    sha256: str


@dataclass(frozen=True)
class Confirmation:
    version: int
    content_sha256: str
    confirmed_at: str
    facts: dict[str, str]


class Versions:
    def __init__(self, folder: ProjectFolder, kind: VersionKind):
        self.kind = kind
        self.dir = folder.root / kind.value
        self.pointer = self.dir / "current"
        self._label = "DAG" if kind is VersionKind.dag else "mapping"

    def _rel(self, name: str) -> str:
        return f"{self.kind.value}/{name}"

    def current(self) -> int | None:
        try:
            text = self.pointer.read_text()
        except FileNotFoundError:
            return None
        m = _POINTER.match(text)
        if not m:
            raise ParseFailed([ParseIssue(self._rel("current"), 1, "Expected a version such as v3.")])
        version = int(m.group(1))
        if not (self.dir / f"v{version}.yaml").exists():
            raise ParseFailed([ParseIssue(self._rel("current"), 1, f"v{version} does not exist.")])
        return version

    def all(self) -> list[int]:
        return sorted(int(m.group(1)) for p in self.dir.glob("v*.yaml") if (m := _VERSION_FILE.match(p.name)))

    def read(self, version: int) -> VersionRecord:
        name = f"v{version}.yaml"
        try:
            raw = (self.dir / name).read_bytes()
        except FileNotFoundError:
            raise NotFound(f"No {self._label} version {version}.", code="version_not_found") from None
        try:
            data = yaml.safe_load(raw)
            return VersionRecord(
                version=int(data["version"]),
                created_at=str(data["created_at"]),
                cites=tuple(data.get("cites") or ()),
                data_fingerprint=data.get("data_fingerprint"),
                content=dict(data["content"]),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        except (yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
            raise ParseFailed([ParseIssue(self._rel(name), 1, "This version file is not valid.")]) from exc

    def write(
        self,
        content: dict[str, Any],
        *,
        expected_current: int | None,
        now: datetime,
        cites: list[str] | tuple[str, ...] = (),
        data_fingerprint: str | None = None,
    ) -> int:
        """Write a new immutable version, then move the pointer to it. ``expected_current`` is
        the version the caller edited (None when there is none yet)."""
        if self.current() != expected_current:
            raise StaleVersion(f"The {self._label} changed since you opened it. Reload and try again.")
        version = max(self.all(), default=0) + 1
        envelope = {
            "version": version,
            "created_at": now.isoformat(),
            "cites": sorted(set(cites)),
            "data_fingerprint": data_fingerprint,
            "content": content,
        }
        data = yaml.safe_dump(envelope, sort_keys=False, allow_unicode=True).encode()
        atomic_write(self.dir / f"v{version}.yaml", data)  # 1. the version
        atomic_write(self.pointer, f"v{version}\n".encode())  # 2. then the pointer
        return version

    def confirmation(self, version: int) -> Confirmation | None:
        name = f"v{version}.confirmed.yaml"
        try:
            data = yaml.safe_load((self.dir / name).read_bytes())
            return Confirmation(
                version=int(data["version"]),
                content_sha256=str(data["content_sha256"]),
                confirmed_at=str(data["confirmed_at"]),
                facts={str(k): str(v) for k, v in (data.get("facts") or {}).items()},
            )
        except FileNotFoundError:
            return None
        except (yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
            raise ParseFailed(
                [ParseIssue(self._rel(name), 1, "This confirmation file is not valid.")]
            ) from exc

    def confirm(self, version: int, *, facts: dict[str, Fact], now: datetime) -> Confirmation:
        """Confirm the current version. A version that is no longer current is refused (A7, C1)."""
        if version != self.current():
            raise StaleVersion(f"This {self._label} is no longer the current one. Review the latest version.")
        record = self.read(version)
        missing = [f for f in record.cites if f not in facts]
        if missing:
            raise Conflict(
                f"This {self._label} cites facts that are no longer there: {', '.join(missing)}.",
                code="facts_missing",
            )
        confirmation = Confirmation(
            version=version,
            content_sha256=record.sha256,
            confirmed_at=now.isoformat(),
            facts={f: facts[f].fingerprint() for f in record.cites},
        )
        data = {
            "version": confirmation.version,
            "content_sha256": confirmation.content_sha256,
            "confirmed_at": confirmation.confirmed_at,
            "facts": confirmation.facts,
        }
        atomic_write(self.dir / f"v{version}.confirmed.yaml", yaml.safe_dump(data, sort_keys=False).encode())
        return confirmation

    def status(self, version: int, facts: dict[str, Fact]) -> VersionStatus:
        """``confirmed`` only while the file and every cited fact still hash as they did when the
        user confirmed; ``stale`` after any change; ``draft`` when never confirmed."""
        record = self.read(version)
        confirmation = self.confirmation(version)
        if confirmation is None:
            return VersionStatus.draft
        if confirmation.content_sha256 != record.sha256:
            return VersionStatus.stale
        for fact_id, fingerprint in confirmation.facts.items():
            fact = facts.get(fact_id)
            if fact is None or fact.fingerprint() != fingerprint:
                return VersionStatus.stale
        return VersionStatus.confirmed

    def stale_facts(self, version: int, facts: dict[str, Fact]) -> list[str]:
        """The cited facts that changed since confirmation, for the "needs review" message."""
        confirmation = self.confirmation(version)
        if confirmation is None:
            return []
        return [
            f
            for f, fingerprint in confirmation.facts.items()
            if f not in facts or facts[f].fingerprint() != fingerprint
        ]
