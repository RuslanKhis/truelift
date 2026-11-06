#!/usr/bin/env python3
"""Confidentiality guard for the public truelift repository.

Design decision D13, contract C13. The repository, its history and the built
packages must contain:

* no file under ``private/``;
* no ``*.ipynb`` or ``*.pdf`` file;
* no ``*.csv`` file outside ``data/sample/``;
* no hackathon truth-column prefix outside the allowlisted files;
* no API key matching the Google (``AIza…``, ``AQ.…``), Anthropic
  (``sk-ant-…``) or OpenAI (``sk-…``) patterns. gitleaks enforces the same
  key patterns through ``.gitleaks.toml``.

Modes (exactly one):

``--staged``   files staged for commit, read from the index (pre-commit).
``--tree``     tracked plus untracked, non-ignored files in the working tree
               (``make check`` and CI).
``--history``  every path and blob reachable from any ref (CI full-history scan).
``--dist F…``  members of built sdists (``.tar.gz``) and wheels (``.whl``).

Exit codes: 0 clean, 1 violations found, 2 usage or git error. A violation is
reported as ``<path>[:<line>]: <rule>``. The guard never prints the matched
text, so a leaked key is not copied into logs.

Standard library only; runs on Python 3.8 or later.
"""

from __future__ import annotations

import argparse
import base64
import re
import subprocess
import sys
import tarfile
import zipfile
from typing import Iterable, Iterator, List, NamedTuple, Optional, Tuple

# The hackathon truth-column prefix (named in the hackathon brief). It is kept
# base64-encoded so the literal never appears in the public repository, not
# even in this file. Matching ignores case, so variants are caught too.
TRUTH_PREFIX = base64.b64decode("VHJ1ZUNvbnRyaWI=").decode("ascii")
TRUTH_PREFIX_RE = re.compile(re.escape(TRUTH_PREFIX), re.IGNORECASE)

# Files allowed to name the truth prefix (D13). CODEOWNERS covers both.
TRUTH_PREFIX_ALLOWLIST = frozenset(
    {
        "src/truelift/causal/forbidden.py",
        "scripts/guard_public.py",
    }
)

# Key patterns from D13. The look-behind stops matches in the middle of an
# identifier (for example "task-…" or "FAQ.…").
_EDGE = r"(?<![0-9A-Za-z_.-])"
KEY_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("key:google-api-key", re.compile(_EDGE + r"AIza[0-9A-Za-z_-]{35}")),
    ("key:google-aq-key", re.compile(_EDGE + r"AQ\.[0-9A-Za-z_-]{20,}")),
    ("key:anthropic-api-key", re.compile(_EDGE + r"sk-ant-[0-9A-Za-z_-]{20,}")),
    ("key:openai-api-key", re.compile(_EDGE + r"sk-(?!ant-)(?:proj-)?[0-9A-Za-z_-]{20,}")),
)

SAMPLE_DIR = "data/sample/"
BINARY_SNIFF_BYTES = 8192


class Violation(NamedTuple):
    path: str
    line: Optional[int]
    rule: str

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{where}: {self.rule}"


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


def path_violations(path: str, *, sample_anywhere: bool = False) -> List[Violation]:
    """Path rules. ``sample_anywhere`` accepts ``data/sample/`` at any depth
    (package members, where the sample may sit inside the package)."""
    found: List[Violation] = []
    lower = path.lower()
    if path == "private" or path.startswith("private/"):
        found.append(Violation(path, None, "private-path"))
    if lower.endswith(".ipynb"):
        found.append(Violation(path, None, "notebook"))
    if lower.endswith(".pdf"):
        found.append(Violation(path, None, "pdf"))
    if lower.endswith(".csv"):
        in_sample = ("/" + SAMPLE_DIR) in ("/" + path) if sample_anywhere else path.startswith(SAMPLE_DIR)
        if not in_sample:
            found.append(Violation(path, None, "csv-outside-data-sample"))
    return found


def content_violations(path: str, data: bytes) -> List[Violation]:
    """Content rules: the truth prefix and the key patterns. Binary blobs are
    skipped; the path rules still apply to them."""
    if b"\x00" in data[:BINARY_SNIFF_BYTES]:
        return []
    text = data.decode("utf-8", errors="replace")
    check_prefix = path not in TRUTH_PREFIX_ALLOWLIST
    found: List[Violation] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if check_prefix and TRUTH_PREFIX_RE.search(line):
            found.append(Violation(path, number, "truth-prefix"))
        for rule, pattern in KEY_PATTERNS:
            if pattern.search(line):
                found.append(Violation(path, number, rule))
    return found


def check(path: str, data: Optional[bytes], *, sample_anywhere: bool = False) -> List[Violation]:
    found = path_violations(path, sample_anywhere=sample_anywhere)
    if data is not None:
        found.extend(content_violations(path, data))
    return found


# --------------------------------------------------------------------------
# Git helpers
# --------------------------------------------------------------------------


class GitError(RuntimeError):
    pass


def _git(*args: str) -> bytes:
    proc = subprocess.run(["git", *args], capture_output=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def _split_z(raw: bytes) -> List[str]:
    return [p.decode("utf-8", errors="surrogateescape") for p in raw.split(b"\x00") if p]


def _read_objects(specs: List[str]) -> Iterator[Tuple[str, Optional[bytes]]]:
    """Read many objects through one ``git cat-file --batch`` process."""
    if not specs:
        return
    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for spec in specs:
            proc.stdin.write(spec.encode("utf-8", errors="surrogateescape") + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().rstrip(b"\n").split(b" ")
            if len(header) < 3 or header[1] == b"missing":
                yield spec, None
                continue
            size = int(header[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)  # trailing newline
            yield spec, data if header[1] == b"blob" else None
    finally:
        proc.stdin.close()
        proc.wait()


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------


def scan_staged() -> Tuple[int, List[Violation]]:
    paths = _split_z(_git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"))
    found: List[Violation] = []
    for spec, data in _read_objects([":" + p for p in paths]):
        found.extend(check(spec[1:], data))
    return len(paths), found


def scan_tree() -> Tuple[int, List[Violation]]:
    root = _git("rev-parse", "--show-toplevel").decode().strip()
    paths = _split_z(_git("-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    found: List[Violation] = []
    for path in paths:
        try:
            with open(f"{root}/{path}", "rb") as handle:
                data: Optional[bytes] = handle.read()
        except (FileNotFoundError, IsADirectoryError):
            data = None  # deleted in the working tree but not yet staged
        found.extend(check(path, data))
    return len(paths), found


def scan_history() -> Tuple[int, List[Violation]]:
    """Every (blob, path) pair reachable from any ref, including deleted files."""
    listing = _git("rev-list", "--objects", "--all").decode("utf-8", errors="surrogateescape")
    pairs: List[Tuple[str, str]] = []
    for line in listing.splitlines():
        sha, _, path = line.partition(" ")
        if path:
            pairs.append((sha, path))
    found: List[Violation] = []
    seen_paths = set()
    blobs = {}
    for sha, path in pairs:
        if path not in seen_paths:
            seen_paths.add(path)
            found.extend(path_violations(path))
        blobs.setdefault(sha, set()).add(path)
    for sha, data in _read_objects(sorted(blobs)):
        if data is None:  # tree or commit object
            continue
        for path in sorted(blobs[sha]):
            for violation in content_violations(path, data):
                found.append(violation._replace(path=f"{path} @ {sha[:12]}"))
    return len(blobs), found


def _strip_root(member: str, archive: str) -> str:
    if archive.endswith((".tar.gz", ".tgz")):
        # sdist members sit under "<name>-<version>/"
        return member.split("/", 1)[1] if "/" in member else member
    return member


def _archive_members(archive: str) -> Iterable[Tuple[str, Optional[bytes]]]:
    if archive.endswith(".whl") or archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    yield info.filename, zf.read(info)
    elif archive.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                if member.isfile():
                    handle = tf.extractfile(member)
                    yield member.name, handle.read() if handle else None
    else:
        raise ValueError(f"unsupported archive type: {archive}")


def scan_dist(archives: List[str]) -> Tuple[int, List[Violation]]:
    count = 0
    found: List[Violation] = []
    for archive in archives:
        for member, data in _archive_members(archive):
            count += 1
            path = _strip_root(member, archive)
            for violation in check(path, data, sample_anywhere=True):
                found.append(violation._replace(path=f"{archive}!{violation.path}"))
    return count, found


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="scan files staged for commit")
    mode.add_argument("--tree", action="store_true", help="scan tracked and untracked files")
    mode.add_argument("--history", action="store_true", help="scan every blob in every ref")
    mode.add_argument("--dist", nargs="+", metavar="ARCHIVE", help="scan sdist/wheel members")
    args = parser.parse_args(argv)

    try:
        if args.staged:
            label, (count, found) = "staged files", scan_staged()
        elif args.tree:
            label, (count, found) = "files", scan_tree()
        elif args.history:
            label, (count, found) = "blobs in history", scan_history()
        else:
            label, (count, found) = "package members", scan_dist(args.dist)
    except (GitError, ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"guard_public: error: {exc}", file=sys.stderr)
        return 2

    if found:
        for violation in found:
            print(violation, file=sys.stderr)
        print(
            f"guard_public: {len(found)} violation(s) in {count} {label}. "
            "See AGENTS.md, 'Confidentiality' (design D13, contract C13).",
            file=sys.stderr,
        )
        return 1
    print(f"guard_public: clean ({count} {label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
