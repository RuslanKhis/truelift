"""Proposals: the only way a fact enters or changes the knowledge files (C11, D2, D4).

Agents create proposals through code (``create_fact_proposal``); nothing in the knowledge files
changes until the user accepts one through the API. Accepting applies the change, rejecting
records the decision and leaves the knowledge files byte-identical. A proposal that changes a
confirmed fact is a *contradiction*: it is applied only by a single decision that says so
explicitly, never by a batch. A batch is all-or-nothing.

Each proposal is one file, ``proposals/P001.yaml``, kept after the decision as the audit trail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from truelift.store.errors import (
    Conflict,
    InvalidProposal,
    NotFound,
    ParseFailed,
    ParseIssue,
    StaleVersion,
)
from truelift.store.files import Transaction, atomic_write
from truelift.store.folder import PROJECT_FILE, ProjectFolder, ProjectMeta
from truelift.store.knowledge import (
    FACT_ID_PATTERN,
    KNOWLEDGE_FILES,
    MAX_QUOTE,
    MAX_TEXT,
    Fact,
    FactStatus,
    Knowledge,
    Source,
    SourceKind,
    valid_support,
)

PROPOSAL_ID = re.compile(r"^P[0-9]{3,6}$")
KnowledgeFile = Literal["business.md", "market.md", "data.md"]
MAX_BATCH = 100


class ProposalStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SourceKind
    turn: int | None = None
    quote: str | None = None

    def to_source(self) -> Source:
        return Source(self.kind, self.turn, self.quote)

    @classmethod
    def of(cls, source: Source) -> SourceRecord:
        return cls(kind=source.kind, turn=source.turn, quote=source.quote)


class FactSnapshot(BaseModel):
    """The fact as it was before an accepted proposal replaced it (audit trail)."""

    model_config = ConfigDict(extra="forbid")

    text: str
    status: FactStatus
    source: SourceRecord
    supports: list[str]


class FactProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=PROPOSAL_ID.pattern)
    kind: Literal["fact"] = "fact"
    status: ProposalStatus = ProposalStatus.pending
    file: KnowledgeFile
    section: str | None = None
    fact_id: str | None = Field(default=None, pattern=rf"^{FACT_ID_PATTERN}$")
    text: str
    fact_status: FactStatus
    source: SourceRecord
    supports: list[str] = []
    summary: str
    created_at: datetime
    decided_at: datetime | None = None
    contradiction: bool = False
    replaced: FactSnapshot | None = None

    def to_bytes(self) -> bytes:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True).encode()


@dataclass(frozen=True)
class ProposalView:
    """A proposal with its contradiction state worked out against the current knowledge."""

    proposal: FactProposal
    contradiction: bool
    contradicts: Source | None


def _one_line(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


def is_contradiction(target: Fact | None, proposal: FactProposal) -> bool:
    """True when the proposal would change a confirmed fact."""
    if target is None or target.status is not FactStatus.confirmed:
        return False
    return (target.text, target.status, target.supports) != (
        proposal.text,
        proposal.fact_status,
        tuple(proposal.supports),
    )


def _path(folder: ProjectFolder, proposal_id: str) -> str:
    return f"proposals/{proposal_id}.yaml"


def load(folder: ProjectFolder, proposal_id: str) -> FactProposal:
    if not PROPOSAL_ID.match(proposal_id):
        raise NotFound("No proposal with this ID.", code="proposal_not_found")
    path = folder.root / _path(folder, proposal_id)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise NotFound("No proposal with this ID.", code="proposal_not_found") from None
    try:
        return FactProposal.model_validate(yaml.safe_load(raw))
    except (yaml.YAMLError, ValidationError) as exc:
        raise ParseFailed(
            [ParseIssue(_path(folder, proposal_id), 1, "This proposal file is not valid.")]
        ) from exc


def load_all(folder: ProjectFolder) -> list[FactProposal]:
    ids = sorted(
        (p.stem for p in (folder.root / "proposals").glob("P*.yaml") if PROPOSAL_ID.match(p.stem)),
        key=lambda i: int(i[1:]),
    )
    return [load(folder, i) for i in ids]


def views(folder: ProjectFolder, status: ProposalStatus | None = None) -> list[ProposalView]:
    knowledge = folder.knowledge()
    out = []
    for proposal in load_all(folder):
        if status is not None and proposal.status is not status:
            continue
        if proposal.status is ProposalStatus.pending:
            target = knowledge.fact(proposal.fact_id) if proposal.fact_id else None
            contradiction = is_contradiction(target, proposal)
            contradicts = target.source if contradiction and target else None
        else:
            contradiction = proposal.contradiction
            replaced = proposal.replaced
            contradicts = replaced.source.to_source() if contradiction and replaced else None
        out.append(ProposalView(proposal, contradiction, contradicts))
    return out


def create_fact_proposal(
    folder: ProjectFolder,
    *,
    file: str,
    text: str,
    fact_status: FactStatus,
    source: Source,
    summary: str,
    now: datetime,
    fact_id: str | None = None,
    section: str | None = None,
    supports: tuple[str, ...] | list[str] = (),
) -> FactProposal:
    """Store a pending proposal. The knowledge files are not touched (A2)."""
    if file not in KNOWLEDGE_FILES:
        raise InvalidProposal("Facts go into business.md, market.md or data.md.")
    clean_text = _one_line(text, MAX_TEXT)
    if not clean_text:
        raise InvalidProposal("A fact needs some text.")
    bad = [s for s in supports if not valid_support(s)]
    if bad:
        raise InvalidProposal(
            "Each 'supports' item must look like edge(a -> b), no-edge(a -> b), node(a) or column(a)."
        )
    if source.kind is SourceKind.interview:
        # Quotes live inside double quotes on one line of the Markdown file.
        source = Source(source.kind, source.turn, _one_line(source.quote or "", MAX_QUOTE).replace('"', "'"))
    if fact_id is not None:
        target = folder.knowledge().fact(fact_id)
        if target is None:
            raise NotFound("No fact with this ID.", code="fact_not_found")
        if target.file != file:
            raise InvalidProposal(f"Fact {fact_id} is in {target.file}, not {file}.")
    existing = [
        int(p.stem[1:]) for p in (folder.root / "proposals").glob("P*.yaml") if PROPOSAL_ID.match(p.stem)
    ]
    proposal_id = f"P{max(existing, default=0) + 1:03d}"
    proposal = FactProposal(
        id=proposal_id,
        file=file,  # type: ignore[arg-type]
        section=_one_line(section, 80) if section else None,
        fact_id=fact_id,
        text=clean_text,
        fact_status=fact_status,
        source=SourceRecord.of(source),
        supports=list(supports),
        summary=_one_line(summary, 200) or clean_text[:200],
        created_at=now,
    )
    atomic_write(folder.root / _path(folder, proposal_id), proposal.to_bytes())
    return proposal


def _check_version(meta: ProjectMeta, knowledge_version: int) -> None:
    if knowledge_version != meta.knowledge_version:
        raise StaleVersion("Your knowledge files changed. Reload and decide again.")


def _pending(folder: ProjectFolder, proposal_id: str) -> FactProposal:
    proposal = load(folder, proposal_id)
    if proposal.status is not ProposalStatus.pending:
        raise Conflict("This proposal was already decided.", code="already_decided")
    return proposal


def decide(
    folder: ProjectFolder,
    proposal_id: str,
    *,
    accept: bool,
    knowledge_version: int,
    now: datetime,
    resolves_contradiction: bool = False,
) -> FactProposal:
    """Accept or reject one proposal. Accepting a contradiction needs ``resolves_contradiction``:
    the user chose the new answer over the confirmed one for this fact (A4)."""
    meta = folder.meta()
    _check_version(meta, knowledge_version)
    proposal = _pending(folder, proposal_id)
    if not accept:
        target = folder.knowledge().fact(proposal.fact_id) if proposal.fact_id else None
        rejected = proposal.model_copy(
            update={
                "status": ProposalStatus.rejected,
                "decided_at": now,
                "contradiction": is_contradiction(target, proposal),
            }
        )
        atomic_write(folder.root / _path(folder, proposal_id), rejected.to_bytes())
        return rejected
    return _apply(folder, meta, [proposal], allow_contradiction=resolves_contradiction, now=now)[0]


def accept_batch(
    folder: ProjectFolder, proposal_ids: list[str], *, knowledge_version: int, now: datetime
) -> list[FactProposal]:
    """Accept several proposals, all or none (A8). A contradiction refuses the whole batch (A4)."""
    if not proposal_ids or len(proposal_ids) > MAX_BATCH or len(set(proposal_ids)) != len(proposal_ids):
        raise InvalidProposal(f"Send between 1 and {MAX_BATCH} different proposal IDs.")
    meta = folder.meta()
    _check_version(meta, knowledge_version)
    proposals = [_pending(folder, i) for i in proposal_ids]
    knowledge = folder.knowledge()
    clashing = [p.id for p in proposals if p.fact_id and is_contradiction(knowledge.fact(p.fact_id), p)]
    if clashing:
        raise Conflict(
            f"{', '.join(clashing)} conflict with confirmed facts. Decide each of them on its own.",
            code="contradiction_in_batch",
        )
    return _apply(folder, meta, proposals, allow_contradiction=False, now=now)


def _snapshot(fact: Fact | None) -> FactSnapshot | None:
    if fact is None:
        return None
    return FactSnapshot(
        text=fact.text, status=fact.status, source=SourceRecord.of(fact.source), supports=list(fact.supports)
    )


def _apply(
    folder: ProjectFolder,
    meta: ProjectMeta,
    proposals: list[FactProposal],
    *,
    allow_contradiction: bool,
    now: datetime,
) -> list[FactProposal]:
    """Work out every change in memory, then write all files in one transaction."""
    knowledge: Knowledge = folder.knowledge()
    knowledge.require_valid()
    original = {name: doc.render() for name, doc in knowledge.docs.items()}
    decided: list[FactProposal] = []
    for proposal in proposals:
        target = knowledge.fact(proposal.fact_id) if proposal.fact_id else None
        if proposal.fact_id and target is None:
            raise Conflict(
                f"Fact {proposal.fact_id} is no longer in the knowledge files. Reload and decide again.",
                code="fact_missing",
            )
        contradiction = is_contradiction(target, proposal)
        if contradiction and not allow_contradiction:
            raise Conflict(
                f"{proposal.id} conflicts with confirmed fact {proposal.fact_id}. "
                "Choose which answer to keep.",
                code="contradiction_choice_needed",
            )
        fact = Fact(
            id=proposal.fact_id or knowledge.next_fact_id(),
            text=proposal.text,
            status=proposal.fact_status,
            source=proposal.source.to_source(),
            date=now.date().isoformat(),
            supports=tuple(proposal.supports),
            section=target.section if target else proposal.section,
            file=target.file if target else proposal.file,
        )
        knowledge = knowledge.with_doc(knowledge.docs[fact.file].upsert(fact))
        decided.append(
            proposal.model_copy(
                update={
                    "status": ProposalStatus.accepted,
                    "decided_at": now,
                    "fact_id": fact.id,
                    "contradiction": contradiction,
                    "replaced": _snapshot(target),
                }
            )
        )
    txn = Transaction(folder.root)
    for name, doc in knowledge.docs.items():
        text = doc.render()
        if text != original[name]:
            txn.write(name, text.encode("utf-8"))
    for proposal in decided:
        txn.write(_path(folder, proposal.id), proposal.to_bytes())
    bumped = meta.model_copy(update={"knowledge_version": meta.knowledge_version + 1})
    txn.write(PROJECT_FILE, bumped.to_bytes())
    txn.commit()
    return decided
