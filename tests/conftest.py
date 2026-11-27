"""Shared pytest configuration.

Tests marked ``private`` need the private benchmark materials, which live only
on a core developer's machine and never in the repository (contract C13).
They are collected everywhere and skipped when ``private/benchmark.yaml`` is
absent, so CI and outside contributors see them as skipped, not passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_BENCHMARK = REPO_ROOT / "private" / "benchmark.yaml"
PRIVATE_SKIP_REASON = "private materials absent"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if PRIVATE_BENCHMARK.is_file():
        return
    skip_private = pytest.mark.skip(reason=PRIVATE_SKIP_REASON)
    for item in items:
        if "private" in item.keywords:
            item.add_marker(skip_private)


class MemoryKeyring:
    """An in-memory keyring backend: no test reads or writes the developer's real keychain (G11)."""

    priority = 1

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.items.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.items[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        import keyring.errors

        if self.items.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch: pytest.MonkeyPatch) -> MemoryKeyring:
    import keyring

    backend = MemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    for var in ("TRUELIFT_GEMINI_API_KEY", "TRUELIFT_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return backend
