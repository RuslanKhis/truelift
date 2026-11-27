"""What may leave the machine: the disclosed payload categories and their limits (C8, D17; G11/A3).

Agents never put project data into a prompt directly. They build a ``Payload`` here, which keeps
only the disclosed categories, removes ground-truth columns (C4) and refuses more than 20 sample
rows, and send it as a user message (``Payload.as_text``) or a tool result
(``Payload.as_tool_result``). The gateway then checks the whole model request with
``inspect_request``: every part must be one of

* user text: the user's own words (category ``answers``), or a payload envelope, re-validated;
* a tool result carrying a payload envelope (``{"truelift_data": {...}}``), re-validated;
* the model's own earlier turns (text, thoughts and function calls), which add no category.

Anything else (a file or image part, a tool result without an envelope, an unknown category,
more than 20 rows, a forbidden column) is refused before the call. So is a request larger than
the byte cap. Refusal reasons are static codes; they never quote the payload.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from truelift.causal.forbidden import DEFAULT as DEFAULT_DENY
from truelift.causal.forbidden import DenyList

# The disclosed categories (C8), in disclosure order. Titles are shown on the disclosure screen.
CATEGORIES: dict[str, tuple[str, str]] = {
    "columns": ("Column names and types", "The names and kinds of your columns."),
    "summary": ("Summary statistics", "Per column: minimum, maximum, mean and share missing."),
    "sample_rows": ("Up to 20 sample rows", "Ground-truth columns removed. Never the whole file."),
    "answers": ("Your answers", "What you type in the interview."),
    "results": ("Result aggregates", "Headline and breakdown numbers of a run."),
}
MAX_SAMPLE_ROWS = 20
ENVELOPE_KEY = "truelift_data"
_OPEN = "<truelift-data>"
_CLOSE = "</truelift-data>"


class PayloadRefused(Exception):
    """A payload or request that may not leave the machine. ``code`` is static, never content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _check_no_forbidden(value: Any, deny: DenyList) -> None:
    """Refuse any mapping key, or column ``name``, that names a ground-truth column (C4)."""
    if isinstance(value, Mapping):
        for k, v in value.items():
            if isinstance(k, str) and deny.is_forbidden(k):
                raise PayloadRefused("forbidden_column")
            if k == "name" and isinstance(v, str) and deny.is_forbidden(v):
                raise PayloadRefused("forbidden_column")
            _check_no_forbidden(v, deny)
    elif isinstance(value, list | tuple):
        for v in value:
            _check_no_forbidden(v, deny)


@dataclass(frozen=True)
class Payload:
    """A validated, disclosed payload. Build it with ``build_payload``."""

    data: dict[str, Any]

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(c for c in CATEGORIES if c in self.data)

    def as_text(self) -> str:
        return _OPEN + json.dumps(self.data, separators=(",", ":"), ensure_ascii=False, default=str) + _CLOSE

    def as_tool_result(self, **status: Any) -> dict[str, Any]:
        """A tool's return value: ``status`` fields (small, model-facing) plus the envelope."""
        return {**status, ENVELOPE_KEY: self.data}


def build_payload(
    *,
    columns: Sequence[Mapping[str, Any]] | None = None,
    summary: Mapping[str, Mapping[str, Any]] | None = None,
    sample_rows: Sequence[Mapping[str, Any]] | None = None,
    results: Mapping[str, Any] | None = None,
    deny: DenyList = DEFAULT_DENY,
) -> Payload:
    """Keep only the disclosed categories; drop ground-truth columns; at most 20 sample rows."""
    data: dict[str, Any] = {}
    if columns is not None:
        data["columns"] = [
            {"name": str(c["name"]), "type": str(c.get("type", ""))}
            for c in columns
            if not deny.is_forbidden(str(c["name"]))
        ]
    if summary is not None:
        data["summary"] = {k: dict(v) for k, v in summary.items() if not deny.is_forbidden(k)}
    if sample_rows is not None:
        if len(sample_rows) > MAX_SAMPLE_ROWS:
            raise PayloadRefused("too_many_rows")
        data["sample_rows"] = [
            {k: v for k, v in row.items() if not deny.is_forbidden(k)} for row in sample_rows
        ]
    if results is not None:
        data["results"] = dict(results)
    _validate_envelope(data, deny)
    return Payload(data)


def _validate_envelope(data: Any, deny: DenyList) -> set[str]:
    if not isinstance(data, Mapping):
        raise PayloadRefused("unknown_payload")
    unknown = set(data) - set(CATEGORIES)
    if unknown:
        raise PayloadRefused("unknown_category")
    rows = data.get("sample_rows")
    if rows is not None and (not isinstance(rows, list) or len(rows) > MAX_SAMPLE_ROWS):
        raise PayloadRefused("too_many_rows")
    _check_no_forbidden(data, deny)
    return set(data)


def _envelopes_in_text(text: str) -> tuple[list[str], str]:
    """(envelope JSON bodies, the text outside them)."""
    bodies, rest, pos = [], [], 0
    while (start := text.find(_OPEN, pos)) != -1:
        end = text.find(_CLOSE, start)
        if end == -1:
            raise PayloadRefused("unknown_payload")
        rest.append(text[pos:start])
        bodies.append(text[start + len(_OPEN) : end])
        pos = end + len(_CLOSE)
    rest.append(text[pos:])
    return bodies, "".join(rest)


@dataclass(frozen=True)
class RequestShape:
    """What a model request carries: its categories and its size in bytes."""

    categories: tuple[str, ...]
    bytes: int


def inspect_request(
    contents: Iterable[Mapping[str, Any]],
    system_instruction: str = "",
    tools: Any = None,
    *,
    max_bytes: int,
    deny: DenyList = DEFAULT_DENY,
) -> RequestShape:
    """Check a model request (``contents`` as JSON dicts, genai ``Content`` shape). Raises
    ``PayloadRefused``; returns the categories and the byte size otherwise."""
    contents = list(contents)
    found: set[str] = set()
    for content in contents:
        role = content.get("role") or "user"
        for part in content.get("parts") or []:
            if role == "model":
                # The model's own earlier output (text, thoughts, function calls): no new data.
                if any(k in part for k in ("inline_data", "file_data")):
                    raise PayloadRefused("file_part")
                continue
            if any(
                k in part for k in ("inline_data", "file_data", "executable_code", "code_execution_result")
            ):
                raise PayloadRefused("file_part")
            if (response := part.get("function_response")) is not None:
                body = (response.get("response") or {}) if isinstance(response, Mapping) else {}
                if not isinstance(body, Mapping) or ENVELOPE_KEY not in body:
                    raise PayloadRefused("unknown_payload")
                extra = {k: v for k, v in body.items() if k != ENVELOPE_KEY}
                _check_no_forbidden(extra, deny)
                found |= _validate_envelope(body[ENVELOPE_KEY], deny)
                continue
            if "function_call" in part:
                continue
            text = part.get("text")
            if text is None:
                continue
            bodies, rest = _envelopes_in_text(text)
            for body in bodies:
                try:
                    data = json.loads(body)
                except ValueError:
                    raise PayloadRefused("unknown_payload") from None
                found |= _validate_envelope(data, deny)
            if rest.strip():
                found.add("answers")
    size = len(json.dumps(contents, separators=(",", ":"), ensure_ascii=False, default=str).encode())
    size += len(system_instruction.encode())
    if tools:
        size += len(json.dumps(tools, separators=(",", ":"), default=str).encode())
    if size > max_bytes:
        raise PayloadRefused("too_large")
    return RequestShape(tuple(c for c in CATEGORIES if c in found), size)
