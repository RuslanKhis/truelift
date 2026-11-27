"""API key storage: the OS keychain, or the user's own environment variable (C7, SB14; G11/A1, A7).

The key is written to the keychain only (service ``truelift``, one account per provider) and read
back once to prove the write. It is never written to a file, ``state.db``, a project folder or a
log. When the keychain is unavailable or locked, the key comes only from the provider's
environment variable (``TRUELIFT_GEMINI_API_KEY``, ``TRUELIFT_ANTHROPIC_API_KEY``), never from a
file: keyring backends that store secrets in files (``keyrings.alt``) or that store nothing
(``fail``, ``null``) count as "no keychain".

Every key this module sees is registered with the log redactor before it is returned.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import keyring
import keyring.errors

from truelift.agents.redaction import REDACTOR

SERVICE = "truelift"

# Backends that are not an OS keychain: they keep nothing, or keep secrets in a file.
_NOT_A_KEYCHAIN_MODULES = ("keyring.backends.fail", "keyring.backends.null", "keyrings.alt")


class KeySource(StrEnum):
    keychain = "keychain"
    env = "env"


@dataclass(frozen=True)
class KeySlot:
    """Where one provider's key lives: its keychain account and its environment variable."""

    provider: str
    account: str
    env_var: str


@dataclass(frozen=True)
class KeyStatus:
    configured: bool
    source: KeySource | None
    keychain_available: bool


class KeychainUnavailable(Exception):
    """The keychain could not store or read the key. The message is static and names the
    environment variable to use instead; it never contains the key."""

    def __init__(self, slot: KeySlot):
        super().__init__(
            "The system keychain is locked or unavailable, so the key was not saved. Unlock the "
            f"keychain and try again, or set {slot.env_var} before starting truelift."
        )
        self.env_var = slot.env_var


def _is_keychain(backend: Any) -> bool:
    module = type(backend).__module__
    if module.startswith(_NOT_A_KEYCHAIN_MODULES):
        return False
    # A chainer with no usable backend behind it stores nothing.
    backends = getattr(backend, "backends", None)
    if backends is not None and not any(_is_keychain(b) for b in backends):
        return False
    return True


class KeyStore:
    """Reads and writes provider keys. ``backend`` defaults to keyring's current backend, looked
    up on each call, so ``keyring.set_keyring`` (tests) takes effect."""

    def __init__(
        self, slots: Mapping[str, KeySlot], *, backend: Any = None, environ: Mapping[str, str] | None = None
    ):
        self._slots = dict(slots)
        self._backend = backend
        self._environ = environ if environ is not None else os.environ

    def slot(self, provider: str) -> KeySlot:
        return self._slots[provider]

    def _keychain(self) -> Any | None:
        backend = self._backend if self._backend is not None else keyring.get_keyring()
        return backend if _is_keychain(backend) else None

    def _read_keychain(self, slot: KeySlot) -> tuple[str | None, bool]:
        """(key or None, keychain available)."""
        backend = self._keychain()
        if backend is None:
            return None, False
        try:
            value = backend.get_password(SERVICE, slot.account)
        except Exception:  # locked, denied or broken: treat as unavailable, never as "no key"
            return None, False
        return (value or None), True

    def get(self, provider: str) -> tuple[str, KeySource] | None:
        """The key and where it came from, or None. Fetched on each call (D7)."""
        slot = self._slots[provider]
        value, _ = self._read_keychain(slot)
        source = KeySource.keychain
        if value is None:
            value = (self._environ.get(slot.env_var) or "").strip() or None
            source = KeySource.env
        if value is None:
            return None
        REDACTOR.register(value)
        return value, source

    def status(self, provider: str) -> KeyStatus:
        slot = self._slots[provider]
        value, available = self._read_keychain(slot)
        if value is not None:
            return KeyStatus(True, KeySource.keychain, available)
        if (self._environ.get(slot.env_var) or "").strip():
            return KeyStatus(True, KeySource.env, available)
        return KeyStatus(False, None, available)

    def save(self, provider: str, key: str) -> None:
        """Store ``key`` in the keychain and read it back. Raises ``KeychainUnavailable``."""
        slot = self._slots[provider]
        REDACTOR.register(key)
        backend = self._keychain()
        if backend is None:
            raise KeychainUnavailable(slot)
        try:
            backend.set_password(SERVICE, slot.account, key)
            ok = backend.get_password(SERVICE, slot.account) == key
        except Exception:
            ok = False
        if not ok:
            raise KeychainUnavailable(slot) from None

    def delete(self, provider: str) -> None:
        slot = self._slots[provider]
        backend = self._keychain()
        if backend is None:
            return
        try:
            backend.delete_password(SERVICE, slot.account)
        except keyring.errors.PasswordDeleteError:
            pass
