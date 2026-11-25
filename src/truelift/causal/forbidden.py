"""The ground-truth deny-list (contract C4, decisions D3 and D13).

A ground-truth column is never a pipeline feature, never a CATE covariate and never part of an
LLM payload. Three things make a column ground truth, each matched without regard to case:

* the ``truth_`` prefix our own synthetic market uses (D14, ``rules/truth_sidecar.yaml``);
* the hackathon's truth-column prefix. It is stored here only base64-encoded, like the guard
  (``scripts/guard_public.py``), so the literal never enters the repository, its history or its
  packages. This file and the guard are the only two allowed to name it (D13); a test keeps the
  two encoded constants equal;
* any column a benchmark's truth sidecar lists under ``truth_columns``.

The compiler filters with this module (G06); the gateway's payload builder will too (C8, G11).
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from typing import Any

# The hackathon truth-column prefix, base64-encoded (D13, revised 2026-11-07). Must equal the
# guard's encoded value; tests/causal/test_forbidden.py checks it.
_TRUTH_PREFIX_B64 = "VHJ1ZUNvbnRyaWI="
_PRIVATE_PREFIX = base64.b64decode(_TRUTH_PREFIX_B64).decode("ascii").lower()

SYNTHETIC_PREFIX = "truth_"
FORBIDDEN_PREFIXES: tuple[str, ...] = (SYNTHETIC_PREFIX, _PRIVATE_PREFIX)


class DenyList:
    """Decides whether a column holds ground truth. Immutable; build one per data file."""

    def __init__(self, truth_columns: Iterable[str] = ()):
        self._extra = frozenset(c.lower() for c in truth_columns)

    def is_forbidden(self, column: str) -> bool:
        name = column.lower()
        return name.startswith(FORBIDDEN_PREFIXES) or name in self._extra

    def filter(self, columns: Iterable[str]) -> list[str]:
        """``columns`` without any ground-truth column, in the same order."""
        return [c for c in columns if not self.is_forbidden(c)]

    @classmethod
    def from_sidecar(cls, truth: Mapping[str, Any] | None) -> DenyList:
        """A deny-list that also covers the columns a truth sidecar (``truth.yaml``) lists."""
        columns = (truth or {}).get("truth_columns") or []
        if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
            raise ValueError("truth sidecar: truth_columns must be a list of column names")
        return cls(columns)


DEFAULT = DenyList()


def is_forbidden(column: str) -> bool:
    """True for a column with a ground-truth prefix (no sidecar)."""
    return DEFAULT.is_forbidden(column)
