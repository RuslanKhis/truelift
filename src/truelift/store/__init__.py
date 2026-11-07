"""The project store: the only writer of project files (design D1, D4, D21; contracts C11, C1).

- ``knowledge``: parser and writer of ``business.md``, ``market.md`` and ``data.md`` (D4).
- ``proposals``: agents propose, the user decides; contradictions and all-or-nothing batches.
- ``versions``: immutable ``dag/vN.yaml`` and ``mapping/vN.yaml`` with a pointer, confirmation
  records and staleness.
- ``files``: atomic writes and multi-file transactions.
- ``db``: ``state.db`` (SQLAlchemy, WAL).
- ``project``: ``ProjectStore``, the facade the API and the agents' tools call.

No ADK import here or below, so the store tests run without the SDK.
"""

from __future__ import annotations

from truelift.store.errors import (
    Conflict,
    InvalidProposal,
    NotFound,
    ParseFailed,
    ParseIssue,
    SaveFailed,
    StaleVersion,
    StoreError,
)
from truelift.store.knowledge import Fact, FactStatus, Source, SourceKind
from truelift.store.project import ProjectInfo, ProjectStore
from truelift.store.proposals import FactProposal, ProposalStatus, ProposalView
from truelift.store.versions import VersionKind, VersionStatus

__all__ = [
    "Conflict",
    "Fact",
    "FactProposal",
    "FactStatus",
    "InvalidProposal",
    "NotFound",
    "ParseFailed",
    "ParseIssue",
    "ProjectInfo",
    "ProjectStore",
    "ProposalStatus",
    "ProposalView",
    "SaveFailed",
    "Source",
    "SourceKind",
    "StaleVersion",
    "StoreError",
    "VersionKind",
    "VersionStatus",
]
