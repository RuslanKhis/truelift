"""Tests for scripts/guard_public.py (design D13, contract C13, security rule SB16).

Every forbidden fixture is built at run time, so this file contains no key
and no truth-prefix literal: the guard and gitleaks scan it like any other file.
Offline: the tests need git but no network.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = REPO_ROOT / "scripts" / "guard_public.py"

_spec = importlib.util.spec_from_file_location("guard_public", GUARD)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

PREFIX = guard.TRUTH_PREFIX

# Fake keys, assembled so that no literal in this file matches a key pattern.
FAKE_KEYS = {
    "key:google-api-key": "AI" + "za" + "Q" * 35,
    "key:google-aq-key": "AQ" + "." + "Ab3_" * 6,
    "key:anthropic-api-key": "sk" + "-ant-" + "api03-" + "x7" * 12,
    "key:openai-api-key": "sk" + "-proj-" + "Zq9" * 8,
}


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "guard-test@example.invalid")
    _git(tmp_path, "config", "user.name", "guard test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("# fixture repo\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _stage(repo: Path, rel: str, content: str | bytes) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)
    _git(repo, "add", "-f", rel)


# --- A2: each forbidden kind fails when staged ------------------------------

STAGED_CASES = [
    pytest.param("private/benchmark.yaml", "paths: []\n", "private-path", id="private-dir"),
    pytest.param("analysis/model.ipynb", '{"cells": []}\n', "notebook", id="ipynb"),
    pytest.param("docs/deck.pdf", b"%PDF-1.7\n\x00\x01", "pdf", id="pdf"),
    pytest.param("data/raw/panel.csv", "week,revenue\n1,10\n", "csv-outside-data-sample", id="csv"),
    pytest.param("notes/NOTEBOOK.IPYNB", "{}\n", "notebook", id="ipynb-upper-case"),
    pytest.param(
        "src/truelift/features.py", f"DROP = '{PREFIX}_Discount_Total'\n", "truth-prefix", id="truth-prefix"
    ),
    pytest.param(
        "docs/notes.md", f"column {PREFIX.lower()}_tv\n", "truth-prefix", id="truth-prefix-lower-case"
    ),
] + [
    pytest.param("config/settings.py", f"API_KEY = '{value}'\n", rule, id=rule)
    for rule, value in FAKE_KEYS.items()
]


@pytest.mark.parametrize(("rel", "content", "rule"), STAGED_CASES)
def test_staged_violation_fails(repo: Path, rel: str, content: str | bytes, rule: str) -> None:
    _stage(repo, rel, content)
    result = _run(repo, "--staged")
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{rel}" in result.stderr
    assert rule in result.stderr


@pytest.mark.parametrize("rule", list(FAKE_KEYS))
def test_key_value_is_never_printed(repo: Path, rule: str) -> None:
    _stage(repo, "leak.txt", FAKE_KEYS[rule] + "\n")
    result = _run(repo, "--staged")
    assert result.returncode == 1
    assert FAKE_KEYS[rule] not in result.stdout + result.stderr


def test_truth_prefix_is_never_printed(repo: Path) -> None:
    _stage(repo, "leak.py", f"x = '{PREFIX}_Base_Total'\n")
    result = _run(repo, "--staged")
    assert result.returncode == 1
    assert PREFIX.lower() not in (result.stdout + result.stderr).lower()


# --- A2: what stays allowed ---------------------------------------------------


def test_clean_staged_files_pass(repo: Path) -> None:
    _stage(repo, "src/truelift/app.py", "RISK = 'risk-adjusted-return-on-discount-spend'\n")
    _stage(repo, "docs/faq.md", "See FAQ.section_on_discounts_and_returns for details.\n")
    _stage(repo, "data/sample/panel.csv", "week,revenue\n1,10\n")
    result = _run(repo, "--staged")
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


@pytest.mark.parametrize("rel", sorted(guard.TRUTH_PREFIX_ALLOWLIST))
def test_truth_prefix_allowed_in_allowlisted_files(repo: Path, rel: str) -> None:
    _stage(repo, rel, f"FORBIDDEN_PREFIXES = ('{PREFIX}_',)\n")
    result = _run(repo, "--staged")
    assert result.returncode == 0, result.stderr


def test_keys_are_denied_even_in_allowlisted_files(repo: Path) -> None:
    _stage(repo, "src/truelift/causal/forbidden.py", f"K = '{FAKE_KEYS['key:google-api-key']}'\n")
    assert _run(repo, "--staged").returncode == 1


def test_nested_private_directory_is_not_top_level_private(repo: Path) -> None:
    # tests/private/ holds the skip-guarded private benchmark tests (plan layout).
    _stage(repo, "tests/private/test_bench.py", "def test_x():\n    pass\n")
    assert _run(repo, "--staged").returncode == 0


def test_clean_working_tree_passes() -> None:
    """The real repository, as checked out, is clean."""
    result = _run(REPO_ROOT, "--tree")
    assert result.returncode == 0, result.stderr


def test_tree_mode_sees_untracked_files(repo: Path) -> None:
    (repo / "export.csv").write_text("a,b\n")
    result = _run(repo, "--tree")
    assert result.returncode == 1
    assert "export.csv: csv-outside-data-sample" in result.stderr


# --- A3: the full-history scan finds files that were later deleted -----------


def test_history_finds_deleted_files(repo: Path) -> None:
    _stage(repo, "tmp/leak.env", f"TOKEN={FAKE_KEYS['key:anthropic-api-key']}\n")
    _stage(repo, "private/notes.md", "draft\n")
    _git(repo, "commit", "-q", "-m", "oops")
    _git(repo, "rm", "-q", "-r", "tmp", "private")
    _git(repo, "commit", "-q", "-m", "remove")
    assert _run(repo, "--tree").returncode == 0
    result = _run(repo, "--history")
    assert result.returncode == 1
    assert "key:anthropic-api-key" in result.stderr
    assert "private/notes.md: private-path" in result.stderr


def test_history_of_clean_repo_passes(repo: Path) -> None:
    assert _run(repo, "--history").returncode == 0


# --- A6: package content check ------------------------------------------------


def _wheel(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return path


def _sdist(path: Path, members: dict[str, str]) -> Path:
    src = path.parent / "sdist-src"
    for name, text in members.items():
        member = src / "truelift-0.0.1" / name
        member.parent.mkdir(parents=True, exist_ok=True)
        member.write_text(text)
    with tarfile.open(path, "w:gz") as tf:
        tf.add(src / "truelift-0.0.1", arcname="truelift-0.0.1")
    return path


@pytest.mark.parametrize(
    ("member", "rule"),
    [
        ("private/benchmark.yaml", "private-path"),
        ("truelift/data.csv", "csv-outside-data-sample"),
        ("truelift/example.ipynb", "notebook"),
        ("truelift/deck.pdf", "pdf"),
    ],
)
@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_dist_check_fails_on_forbidden_members(tmp_path: Path, kind: str, member: str, rule: str) -> None:
    members = {"truelift/__init__.py": "", member: "x\n"}
    if kind == "wheel":
        archive = _wheel(tmp_path / "truelift-0.0.1-py3-none-any.whl", members)
    else:
        archive = _sdist(tmp_path / "truelift-0.0.1.tar.gz", members)
    result = _run(tmp_path, "--dist", str(archive))
    assert result.returncode == 1, result.stderr
    assert rule in result.stderr


def test_dist_check_passes_clean_packages(tmp_path: Path) -> None:
    members = {"truelift/__init__.py": "", "truelift/data/sample/panel.csv": "a\n"}
    wheel = _wheel(tmp_path / "truelift-0.0.1-py3-none-any.whl", members)
    sdist = _sdist(tmp_path / "truelift-0.0.1.tar.gz", members)
    result = _run(tmp_path, "--dist", str(wheel), str(sdist))
    assert result.returncode == 0, result.stderr


# --- A4: private benchmark tests skip without the private materials -----------


@pytest.mark.private
def test_private_materials_stay_ignored() -> None:
    """Runs only where private/benchmark.yaml exists: git must keep ignoring it."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "private/benchmark.yaml"], cwd=REPO_ROOT, check=False
    )
    assert result.returncode == 0
