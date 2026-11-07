"""Errors raised by the project store (C11, C1).

Each carries a stable ``code`` and a plain message that is safe to show the user. The API maps
them to its ``ErrorBody`` shape; the store itself knows nothing about HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass


class StoreError(Exception):
    """Base class. ``status`` is the HTTP status the API should answer with."""

    status = 500
    code = "store_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class NotFound(StoreError):
    status = 404
    code = "not_found"


class Conflict(StoreError):
    """The request no longer matches the current state (409). Nothing was written."""

    status = 409
    code = "conflict"


class StaleVersion(Conflict):
    """A write or confirmation carried a version that is no longer current (C11, C1)."""

    code = "stale_version"


class InvalidProposal(StoreError):
    """A proposal that cannot be stored as given (bad file, empty text, malformed supports)."""

    status = 422
    code = "invalid_proposal"


class SaveFailed(StoreError):
    """A file write failed (disk full, permission, injected failure). The previous version stays."""

    status = 500
    code = "save_failed"

    def __init__(self, message: str = "Your change could not be saved. Nothing was changed."):
        super().__init__(message)


@dataclass(frozen=True)
class ParseIssue:
    """One syntax problem in a hand-edited file, with the file and the 1-based line."""

    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file} line {self.line}: {self.message}"


class ParseFailed(StoreError):
    """A project file does not parse. The app refuses to write until the user fixes it (C11)."""

    status = 422
    code = "parse_error"

    def __init__(self, issues: list[ParseIssue]):
        first = issues[0]
        more = f" ({len(issues) - 1} more)" if len(issues) > 1 else ""
        super().__init__(f"Fix {first}{more}, then try again. Nothing was changed.")
        self.issues = issues
