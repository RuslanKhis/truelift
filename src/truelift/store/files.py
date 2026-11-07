"""Atomic file writes and all-or-nothing multi-file changes for a project folder (C11, A5, A8).

``atomic_write`` writes a temp file in the same directory, fsyncs it and renames it over the
target, so a reader sees the old bytes or the new bytes, never a mix. ``Transaction`` writes
several files all-or-nothing: it copies the current bytes into a journal (``.txn/``) first, and
any failure, including a crash noticed at the next open (``recover``), restores them.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

import yaml

from truelift.store.errors import SaveFailed

log = logging.getLogger("truelift.store")

JOURNAL_DIR = ".txn"
_MANIFEST = "manifest.yaml"

# Seams for fault-injection tests (A5, A8). Production code always calls these names.
_replace = os.replace


def _fsync_dir(path: Path) -> None:
    # Directory fsync makes the rename durable on POSIX; Windows has no directory handles.
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` atomically. On any failure the previous file is untouched,
    the temp file is removed and ``SaveFailed`` is raised."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException as exc:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        if not isinstance(exc, OSError):
            raise
        log.error("atomic write failed file=%s", path.name, exc_info=exc)
        raise SaveFailed() from exc


class Transaction:
    """Write several files under ``root`` all-or-nothing.

    Commit order: (1) back up every target that exists into ``.txn/``; (2) write the journal
    manifest, which makes the journal valid; (3) replace each target atomically; (4) delete the
    manifest (the commit point), then the backups. A failure in (3) rolls back from the journal.
    A crash between (2) and (4) is rolled back by ``recover`` at the next open.
    """

    def __init__(self, root: Path):
        self.root = root
        self._writes: dict[str, bytes] = {}

    def write(self, rel_path: str, data: bytes) -> None:
        self._writes[rel_path] = data

    def commit(self) -> None:
        if not self._writes:
            return
        recover(self.root)
        journal = self.root / JOURNAL_DIR
        try:
            journal.mkdir()
        except OSError as exc:
            raise SaveFailed() from exc
        entries = []
        try:
            for index, rel in enumerate(self._writes):
                target = self.root / rel
                backup = None
                if target.exists():
                    backup = f"{index}.bak"
                    atomic_write(journal / backup, target.read_bytes())
                entries.append({"path": rel, "backup": backup})
            atomic_write(journal / _MANIFEST, yaml.safe_dump({"files": entries}).encode())
        except BaseException:
            # The manifest was never written, so no target has changed yet.
            shutil.rmtree(journal, ignore_errors=True)
            raise
        try:
            for rel, data in self._writes.items():
                atomic_write(self.root / rel, data)
        except BaseException:
            _rollback(self.root)
            raise
        (journal / _MANIFEST).unlink()
        shutil.rmtree(journal, ignore_errors=True)


def recover(root: Path) -> None:
    """Finish what a crash left: roll back a transaction whose journal is valid, discard one
    whose journal was never completed, and remove temp files of interrupted atomic writes."""
    for stray in (*root.glob(".*.tmp"), *root.glob("*/.*.tmp")):
        with contextlib.suppress(OSError):
            stray.unlink()
    journal = root / JOURNAL_DIR
    if not journal.exists():
        return
    if (journal / _MANIFEST).exists():
        log.warning("rolling back an unfinished change in a project folder")
        _rollback(root)
    else:
        shutil.rmtree(journal, ignore_errors=True)


def _rollback(root: Path) -> None:
    journal = root / JOURNAL_DIR
    manifest = yaml.safe_load((journal / _MANIFEST).read_text())
    for entry in manifest["files"]:
        target = root / entry["path"]
        if entry["backup"] is None:
            with contextlib.suppress(FileNotFoundError):
                target.unlink()
        else:
            # If this fails the journal stays, and the next open retries the rollback.
            atomic_write(target, (journal / entry["backup"]).read_bytes())
    (journal / _MANIFEST).unlink()
    shutil.rmtree(journal, ignore_errors=True)
