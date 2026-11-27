"""The run folder ``<project>/runs/<run_id>/`` and its files (C9, C10; D8).

Files, in the order they are written:

1. ``config.json``: the compiled pipeline config as canonical JSON (C2). Written by the app.
   ``run.json`` beside it records what the gate admitted: the DAG and mapping versions and
   their hashes, the data fingerprint and the config hash (C1).
2. ``env.json``: versions of the pinned packages, platform, CPU count, ``n_jobs`` and seeds (C9).
3. ``log.txt``: everything the pipeline prints.
4. ``status.json``: the worker's heartbeat, phase and, on failure, the plain reason.
5. ``work/``: the pipeline's ``output_dir``.
6. ``manifest.json``: every output with its sha256, written last by atomic rename (C10). A run
   folder without a manifest has no results, whatever else is in it.

All JSON here is written with ``atomic_write``, so a reader sees an old or a new file, never half.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from truelift.store.files import atomic_write

CONFIG = "config.json"
RUN = "run.json"
ENV = "env.json"
LOG = "log.txt"
STATUS = "status.json"
WORK = "work"
MANIFEST = "manifest.json"
MANIFEST_SCHEMA = "truelift.manifest/1"

# Outputs every finished run must have (G03 note, "Output files the digest will read"). The
# sensitivity metrics exist only when sensitivity ran.
EXPECTED_OUTPUTS = (
    "work/metadata.json",
    "work/step4_consolidated_results/consolidated_1a_full_df.csv",
    "work/step4_consolidated_results/consolidated_3b_summary.csv",
)
SENSITIVITY_OUTPUT = "work/step4_consolidated_results/graph/006_sensitivity/sensitivity_metrics.csv"

# Files that change while the run is watched; never listed in the manifest.
_NOT_OUTPUTS = frozenset({LOG, STATUS, MANIFEST})

LOG_TAIL_LINES = 20
_LOG_LINE_MAX = 300
_HASH_CHUNK = 1 << 20


def utcnow() -> datetime:
    return datetime.now(UTC)


def dump_json(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_json(path: Path, data: Any) -> None:
    atomic_write(path, dump_json(data))


def read_json(path: Path) -> dict[str, Any] | None:
    """The file's JSON object, or None when it is missing or not a valid object."""
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RunFolder:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / CONFIG

    @property
    def run(self) -> Path:
        return self.root / RUN

    @property
    def env(self) -> Path:
        return self.root / ENV

    @property
    def log(self) -> Path:
        return self.root / LOG

    @property
    def status(self) -> Path:
        return self.root / STATUS

    @property
    def work(self) -> Path:
        return self.root / WORK

    @property
    def manifest(self) -> Path:
        return self.root / MANIFEST

    @property
    def project_root(self) -> Path:
        return self.root.parent.parent

    def read_status(self) -> dict[str, Any]:
        return read_json(self.status) or {}

    def log_tail(self, lines: int = LOG_TAIL_LINES) -> list[str]:
        """The last lines of the log, each cut to a readable length. Reads at most 64 KB."""
        try:
            with self.log.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - 65536))
                text = handle.read().decode("utf-8", errors="replace")
        except OSError:
            return []
        out = [line.rstrip()[:_LOG_LINE_MAX] for line in text.splitlines() if line.strip()]
        return out[-lines:]

    # --- the manifest (C10) -------------------------------------------------------------------

    def write_manifest(self, run_id: str, expected: tuple[str, ...]) -> dict[str, str]:
        """Hash every file of the run except the log and the status, and write ``manifest.json``
        last. Raises ``MissingOutputs`` when an
        expected output is absent, so a run that produced too little never gets a manifest."""
        missing = [rel for rel in expected if not (self.root / rel).is_file()]
        if missing:
            raise MissingOutputs(missing)
        files: dict[str, str] = {}
        for path in sorted(p for p in self.root.rglob("*") if p.is_file()):
            rel = path.relative_to(self.root).as_posix()
            if rel in _NOT_OUTPUTS or (path.name.startswith(".") and path.name.endswith(".tmp")):
                continue
            files[rel] = sha256_file(path)
        write_json(self.manifest, {"schema": MANIFEST_SCHEMA, "run_id": run_id, "files": files})
        return files

    def verify_manifest(self, run_id: str, expected: tuple[str, ...]) -> bool:
        """True only when the manifest names this run, lists every expected output, and every
        listed file is on disk with the hash the manifest records."""
        manifest = read_json(self.manifest)
        if not manifest or manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("run_id") != run_id:
            return False
        files = manifest.get("files")
        if not isinstance(files, dict) or any(rel not in files for rel in (CONFIG, RUN, ENV, *expected)):
            return False
        for rel, digest in files.items():
            path = self.root / rel
            if not isinstance(digest, str) or ".." in Path(rel).parts or not path.is_file():
                return False
            if sha256_file(path) != digest:
                return False
        return True


class MissingOutputs(Exception):
    def __init__(self, missing: list[str]):
        super().__init__(", ".join(missing))
        self.missing = missing


def expected_outputs(run_sensitivity: bool) -> tuple[str, ...]:
    return (*EXPECTED_OUTPUTS, SENSITIVITY_OUTPUT) if run_sensitivity else EXPECTED_OUTPUTS
