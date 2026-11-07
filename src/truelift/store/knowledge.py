"""The knowledge file format (design D4, contract C11): parser and writer.

A knowledge file is Markdown with YAML front matter. Each fact is one bullet with an ID, then
indented metadata lines::

    ---
    project: petfood-de
    schema: truelift.knowledge/1
    ---
    # How discounts are decided
    - [F012] We discount mostly in holiday weeks and when stock is ageing.
      status: confirmed · source: interview t14 "mostly around Black Friday" · 2026-11-05
      supports: edge(holiday_weeks -> discount), edge(inventory_age -> discount)

The parser keeps every line it read, so ``render(parse(text)) == text`` byte for byte, and a
change to one fact rewrites only that fact's lines. Hand edits are tolerated, but a line that
looks like a fact and does not parse is an error with the file and line, never skipped: every
bullet must carry a fact ID, and a fact needs a status and a source.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum

import yaml

from truelift.store.errors import ParseFailed, ParseIssue

SCHEMA = "truelift.knowledge/1"

# File name -> its sections, in order (D4).
KNOWLEDGE_FILES: dict[str, tuple[str, ...]] = {
    "business.md": ("Business model", "Channels", "How discounts are decided", "Margin"),
    "market.md": ("Country and regions", "Calendar", "Seasons", "Competition", "Macro factors"),
    "data.md": ("Column meanings", "Data-profile observations"),
}

FACT_ID_PATTERN = r"F[0-9]{3,6}"
MAX_TEXT = 500
MAX_QUOTE = 300

_LINES = re.compile(r"[^\n]*\n|[^\n]+\Z")
_HEADER = re.compile(rf"^- \[({FACT_ID_PATTERN})\] (\S.*)$")
_HEADING = re.compile(r"^#{1,6} +(\S.*?)\s*$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_INTERVIEW = re.compile(r'^interview t([0-9]{1,6}) "([^"]*)"$')
_SUPPORT = re.compile(
    r"^(?:(?:edge|no-edge)\(\s*[A-Za-z0-9_]+\s*->\s*[A-Za-z0-9_]+\s*\)"
    r"|(?:node|column)\(\s*[A-Za-z0-9_]+\s*\))$"
)
_KEYS = ("status", "source", "supports")


class FactStatus(StrEnum):
    confirmed = "confirmed"
    assumed = "assumed"
    unknown = "unknown"
    contradicted = "contradicted"


class SourceKind(StrEnum):
    interview = "interview"
    data_profile = "data profile"
    agent_suggestion = "agent suggestion"
    template_default = "template default"


@dataclass(frozen=True)
class Source:
    """Where a fact came from (C11): an answer turn with its verbatim quote, the data profile,
    an agent suggestion or a template default."""

    kind: SourceKind
    turn: int | None = None
    quote: str | None = None

    def __post_init__(self) -> None:
        if (self.kind is SourceKind.interview) != (self.turn is not None and self.quote is not None):
            raise ValueError("an interview source needs a turn and a quote, and only it has them")

    def render(self) -> str:
        if self.kind is SourceKind.interview:
            return f'interview t{self.turn} "{self.quote}"'
        return self.kind.value

    @classmethod
    def parse(cls, text: str) -> Source | None:
        if m := _INTERVIEW.match(text):
            return cls(SourceKind.interview, int(m.group(1)), m.group(2))
        try:
            kind = SourceKind(text)
        except ValueError:
            return None
        return None if kind is SourceKind.interview else cls(kind)


@dataclass(frozen=True)
class Fact:
    id: str
    text: str
    status: FactStatus
    source: Source
    date: str | None = None
    supports: tuple[str, ...] = ()
    section: str | None = None
    file: str = ""
    line: int = 0

    def fingerprint(self) -> str:
        """Content hash of what a DAG can depend on: text, status, source and supports. The date,
        file and position are excluded, so moving a fact or re-dating it is not a change."""
        payload = [self.id, self.text, self.status.value, self.source.render(), list(self.supports)]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()

    def same_content(self, other: Fact) -> bool:
        return (self.text, self.status, self.supports) == (other.text, other.status, other.supports)


@dataclass(frozen=True)
class _Raw:
    line: str


@dataclass(frozen=True)
class _FactBlock:
    lines: tuple[str, ...]
    fact: Fact | None  # None when the fact has an error (reported in Document.issues)
    fact_id: str | None


@dataclass(frozen=True)
class Document:
    """One parsed knowledge file. Immutable: ``upsert`` returns a new document."""

    file: str
    blocks: tuple[_Raw | _FactBlock, ...]
    issues: tuple[ParseIssue, ...]
    newline: str = "\n"
    front: dict = field(default_factory=dict)

    @property
    def facts(self) -> list[Fact]:
        return [b.fact for b in self.blocks if isinstance(b, _FactBlock) and b.fact is not None]

    @property
    def fact_ids(self) -> list[str]:
        """Every fact ID in the file, including facts that have an error."""
        return [b.fact_id for b in self.blocks if isinstance(b, _FactBlock) and b.fact_id]

    def get(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def render(self) -> str:
        return _join(self.blocks)

    def upsert(self, fact: Fact) -> Document:
        """Replace the fact with this ID, or insert it at the end of its section (a new section
        is appended when there is none). Only that fact's lines change."""
        if self.issues:
            raise ParseFailed(list(self.issues))
        new = _FactBlock(fact_lines(fact, self.newline), None, fact.id)
        blocks = list(self.blocks)
        for i, block in enumerate(blocks):
            if isinstance(block, _FactBlock) and block.fact_id == fact.id:
                blocks[i] = new
                return self._reparse(blocks, fact.id)
        target = (fact.section or "").casefold()
        insert_at = None
        section: str | None = None
        for i, block in enumerate(blocks):
            if isinstance(block, _Raw):
                if m := _HEADING.match(block.line.rstrip("\r\n")):
                    section = m.group(1)
                    if section.casefold() == target:
                        insert_at = i + 1
            elif section is not None and section.casefold() == target:
                insert_at = i + 1
        if insert_at is None:
            nl = self.newline
            text = _join(blocks)
            if text and not text.endswith("\n"):
                blocks.append(_Raw(nl))
            if text and not text.endswith(nl + nl) and text.strip():
                blocks.append(_Raw(nl))
            blocks.append(_Raw(f"# {fact.section or 'Facts'}{nl}"))
            blocks.append(new)
        else:
            blocks.insert(insert_at, new)
        return self._reparse(blocks, fact.id)

    def _reparse(self, blocks: list[_Raw | _FactBlock], fact_id: str) -> Document:
        doc = parse(_join(blocks), self.file)
        if doc.issues or doc.get(fact_id) is None:  # pragma: no cover - a writer bug, not user input
            raise ValueError(f"writer produced an unparseable {self.file}")
        return doc


def _join(blocks: list[_Raw | _FactBlock] | tuple[_Raw | _FactBlock, ...]) -> str:
    out: list[str] = []
    for block in blocks:
        chunk = block.line if isinstance(block, _Raw) else "".join(block.lines)
        # A block inserted after a last line that had no newline must not run into it.
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(chunk)
    return "".join(out)


def fact_lines(fact: Fact, newline: str = "\n") -> tuple[str, ...]:
    meta = f"  status: {fact.status.value} · source: {fact.source.render()}"
    if fact.date:
        meta += f" · {fact.date}"
    lines = [f"- [{fact.id}] {fact.text}{newline}", meta + newline]
    if fact.supports:
        lines.append(f"  supports: {', '.join(fact.supports)}{newline}")
    return tuple(lines)


def new_file(file: str, project_id: str) -> str:
    """The initial content of a knowledge file: front matter and its empty sections."""
    sections = "".join(f"# {s}\n\n" for s in KNOWLEDGE_FILES[file])
    return f"---\nproject: {project_id}\nschema: {SCHEMA}\n---\n{sections}"


def valid_support(item: str) -> bool:
    return bool(_SUPPORT.match(item))


# --- parsing ---------------------------------------------------------------------------------


def parse(text: str, file: str) -> Document:
    lines = _LINES.findall(text)
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    issues: list[ParseIssue] = []
    blocks: list[_Raw | _FactBlock] = []
    body_start, front = _front_matter(lines, file, issues)
    blocks.extend(_Raw(line) for line in lines[:body_start])

    section: str | None = None
    pending: list[tuple[int, str]] | None = None
    for index in range(body_start, len(lines)):
        line = lines[index]
        stripped = line.rstrip("\r\n")
        number = index + 1
        if pending is not None:
            if stripped.startswith("  ") and stripped.strip():
                pending.append((number, line))
                continue
            blocks.append(_parse_fact(pending, section, file, issues))
            pending = None
        if stripped.startswith("- ["):
            pending = [(number, line)]
            continue
        if stripped.startswith("- ") or stripped.rstrip() == "-":
            issues.append(ParseIssue(file, number, "This bullet has no fact ID. Start it like '- [F001] …'."))
        elif stripped.startswith("  ") and stripped.strip():
            issues.append(ParseIssue(file, number, "This indented line does not belong to a fact."))
        elif m := _HEADING.match(stripped):
            section = m.group(1)
        blocks.append(_Raw(line))
    if pending is not None:
        blocks.append(_parse_fact(pending, section, file, issues))

    seen: dict[str, int] = {}
    for block in blocks:
        if isinstance(block, _FactBlock) and block.fact_id and block.fact is not None:
            if block.fact_id in seen:
                issues.append(
                    ParseIssue(file, block.fact.line, f"Fact ID {block.fact_id} is used twice in this file.")
                )
            seen[block.fact_id] = block.fact.line
    issues.sort(key=lambda i: i.line)
    return Document(file, tuple(blocks), tuple(issues), newline, front)


def _front_matter(lines: list[str], file: str, issues: list[ParseIssue]) -> tuple[int, dict]:
    if not lines or lines[0].rstrip("\r\n") != "---":
        issues.append(ParseIssue(file, 1, "The file must start with front matter between '---' lines."))
        return 0, {}
    end = next((j for j in range(1, len(lines)) if lines[j].rstrip("\r\n") == "---"), None)
    if end is None:
        issues.append(ParseIssue(file, 1, "The front matter has no closing '---' line."))
        return 1, {}
    try:
        front = yaml.safe_load("".join(lines[1:end]))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = 2 + (mark.line if mark is not None else 0)
        issues.append(ParseIssue(file, line, "The front matter is not valid YAML."))
        return end + 1, {}
    if not isinstance(front, dict) or front.get("schema") != SCHEMA:
        issues.append(ParseIssue(file, 1, f"The front matter needs 'schema: {SCHEMA}'."))
        return end + 1, front if isinstance(front, dict) else {}
    return end + 1, front


def _segments(body: str) -> list[str]:
    """Split a metadata line on ' · ', ignoring separators inside a double-quoted quote."""
    out: list[str] = []
    buf: list[str] = []
    quoted = False
    i = 0
    while i < len(body):
        if body[i] == '"':
            quoted = not quoted
        elif not quoted and body.startswith(" · ", i):
            out.append("".join(buf))
            buf = []
            i += 3
            continue
        buf.append(body[i])
        i += 1
    out.append("".join(buf))
    return out


def _split_supports(value: str) -> list[str]:
    return [s.strip() for s in re.split(r",(?![^()]*\))", value) if s.strip()]


def _parse_fact(
    entries: list[tuple[int, str]], section: str | None, file: str, issues: list[ParseIssue]
) -> _FactBlock:
    first_line, header = entries[0]
    lines = tuple(line for _, line in entries)
    m = _HEADER.match(header.rstrip("\r\n"))
    if not m:
        issues.append(ParseIssue(file, first_line, "A fact must look like '- [F001] text'."))
        return _FactBlock(lines, None, None)
    fact_id, text = m.group(1), m.group(2).rstrip()
    local: list[ParseIssue] = []
    meta: dict[str, tuple[str, int]] = {}
    date: str | None = None
    for number, line in entries[1:]:
        for segment in _segments(line.strip()):
            segment = segment.strip()
            if _DATE.match(segment):
                if date is not None:
                    local.append(ParseIssue(file, number, f"Fact {fact_id} has two dates."))
                date = segment
                continue
            key, sep, value = segment.partition(":")
            key = key.strip()
            if not sep or key not in _KEYS:
                local.append(
                    ParseIssue(
                        file,
                        number,
                        "Expected 'status: …', 'source: …', 'supports: …' or a date (YYYY-MM-DD).",
                    )
                )
            elif key in meta:
                local.append(ParseIssue(file, number, f"Fact {fact_id} has '{key}' twice."))
            else:
                meta[key] = (value.strip(), number)

    status: FactStatus | None = None
    if "status" not in meta:
        local.append(ParseIssue(file, first_line, f"Fact {fact_id} has no status."))
    else:
        value, number = meta["status"]
        try:
            status = FactStatus(value)
        except ValueError:
            local.append(
                ParseIssue(file, number, "Unknown status. Use confirmed, assumed, unknown or contradicted.")
            )
    source: Source | None = None
    if "source" not in meta:
        local.append(ParseIssue(file, first_line, f"Fact {fact_id} has no source."))
    else:
        value, number = meta["source"]
        source = Source.parse(value)
        if source is None:
            local.append(
                ParseIssue(
                    file,
                    number,
                    'Unknown source. Use interview tN "quote", data profile, agent suggestion or '
                    "template default.",
                )
            )
    supports: tuple[str, ...] = ()
    if "supports" in meta:
        value, number = meta["supports"]
        items = _split_supports(value)
        bad = [s for s in items if not valid_support(s)]
        if bad or not items:
            local.append(
                ParseIssue(
                    file,
                    number,
                    "Each 'supports' item must look like edge(a -> b), no-edge(a -> b), "
                    "node(a) or column(a).",
                )
            )
        supports = tuple(items)

    if local or status is None or source is None:
        issues.extend(local)
        return _FactBlock(lines, None, fact_id)
    fact = Fact(fact_id, text, status, source, date, supports, section, file, first_line)
    return _FactBlock(lines, fact, fact_id)


# --- the three files together ----------------------------------------------------------------


@dataclass(frozen=True)
class Knowledge:
    """A project's knowledge files, parsed. ``issues`` covers all files, including IDs that two
    files share."""

    docs: dict[str, Document]
    issues: tuple[ParseIssue, ...]

    @property
    def facts(self) -> dict[str, Fact]:
        return {f.id: f for doc in self.docs.values() for f in doc.facts}

    def fact(self, fact_id: str) -> Fact | None:
        return self.facts.get(fact_id)

    def require_valid(self) -> None:
        if self.issues:
            raise ParseFailed(list(self.issues))

    def next_fact_id(self, taken: frozenset[str] | set[str] = frozenset()) -> str:
        ids = {i for doc in self.docs.values() for i in doc.fact_ids} | set(taken)
        top = max((int(i[1:]) for i in ids), default=0)
        return f"F{top + 1:03d}"

    def with_doc(self, doc: Document) -> Knowledge:
        return replace(self, docs={**self.docs, doc.file: doc})


def load_knowledge(texts: dict[str, str], extra_issues: list[ParseIssue] | None = None) -> Knowledge:
    docs = {name: parse(text, name) for name, text in texts.items()}
    issues = [i for doc in docs.values() for i in doc.issues] + list(extra_issues or [])
    owner: dict[str, str] = {}
    for name, doc in docs.items():
        for fact in doc.facts:
            if fact.id in owner and owner[fact.id] != name:
                issues.append(
                    ParseIssue(name, fact.line, f"Fact ID {fact.id} is also used in {owner[fact.id]}.")
                )
            owner.setdefault(fact.id, name)
    return Knowledge(docs, tuple(issues))
