"""G08 A5: writes are atomic (temp file plus rename); an injected failure leaves the previous
version intact and returns an error (C11)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.store.conftest import interview, snapshot
from truelift.store import SaveFailed
from truelift.store import files as files_mod
from truelift.store.files import Transaction, atomic_write


def _no_temp_files(directory: Path) -> bool:
    return not [p for p in directory.rglob("*.tmp")]


def test_atomic_write_replaces_through_a_temp_file_in_the_same_folder(tmp_path, monkeypatch):
    target = tmp_path / "business.md"
    target.write_bytes(b"old")
    seen = []
    real = files_mod._replace

    def spy(src, dst):
        seen.append((Path(src).parent, Path(src).name, Path(dst)))
        assert target.read_bytes() == b"old"  # readers still see the old bytes until the rename
        return real(src, dst)

    monkeypatch.setattr(files_mod, "_replace", spy)
    atomic_write(target, b"new")
    assert target.read_bytes() == b"new"
    [(folder, name, dst)] = seen
    assert folder == tmp_path and name.startswith(".business.md.") and name.endswith(".tmp") and dst == target
    assert _no_temp_files(tmp_path)


@pytest.mark.parametrize("where", ["rename", "write", "fsync"])
def test_injected_failure_keeps_the_previous_file(tmp_path, monkeypatch, where):
    target = tmp_path / "market.md"
    target.write_bytes(b"previous version")

    def fail(*args, **kwargs):
        raise OSError(28, "No space left on device")

    if where == "rename":
        monkeypatch.setattr(files_mod, "_replace", fail)
    elif where == "fsync":
        monkeypatch.setattr(files_mod.os, "fsync", fail)
    else:
        real_fdopen = os.fdopen

        class Full:
            def __init__(self, fd, mode):
                self.handle = real_fdopen(fd, mode)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.handle.close()

            def write(self, data):
                self.handle.write(data[: len(data) // 2])
                raise OSError(28, "No space left on device")

        monkeypatch.setattr(files_mod.os, "fdopen", Full)
    with pytest.raises(SaveFailed) as caught:
        atomic_write(target, b"new version that never lands")
    assert caught.value.code == "save_failed" and "Nothing was changed" in caught.value.message
    assert target.read_bytes() == b"previous version"
    assert _no_temp_files(tmp_path)


def test_new_file_is_absent_after_a_failed_first_write(tmp_path, monkeypatch):
    monkeypatch.setattr(files_mod, "_replace", lambda *a: (_ for _ in ()).throw(OSError(13, "denied")))
    with pytest.raises(SaveFailed):
        atomic_write(tmp_path / "dag" / "v1.yaml", b"x")
    assert not (tmp_path / "dag" / "v1.yaml").exists()


def test_transaction_failure_restores_every_file(tmp_path, monkeypatch):
    (tmp_path / "a").write_bytes(b"A0")
    (tmp_path / "b").write_bytes(b"B0")
    real = files_mod._replace
    count = {"targets": 0}

    def fail_second_target(src, dst):
        if ".txn" not in str(dst):
            count["targets"] += 1
            if count["targets"] == 3:
                raise OSError(28, "No space left on device")
        return real(src, dst)

    monkeypatch.setattr(files_mod, "_replace", fail_second_target)
    txn = Transaction(tmp_path)
    txn.write("a", b"A1")
    txn.write("b", b"B1")
    txn.write("c", b"C1")  # a new file
    with pytest.raises(SaveFailed):
        txn.commit()
    assert (tmp_path / "a").read_bytes() == b"A0" and (tmp_path / "b").read_bytes() == b"B0"
    assert not (tmp_path / "c").exists() and not (tmp_path / ".txn").exists()


def test_api_save_failure_is_an_error_and_changes_nothing(client, api_store, monkeypatch):
    project = client.post("/api/projects", json={"name": "Garden tools"}).json()["id"]
    root = api_store.projects_dir / project
    api_store.propose_fact(
        project,
        file="market.md",
        section="Calendar",
        text="Spring is the peak.",
        source=interview(3, "spring"),
        summary="Spring",
    )
    before = snapshot(root, skip=())

    def fail(*args):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(files_mod, "_replace", fail)
    r = client.post(
        f"/api/projects/{project}/proposals/P001/decision",
        json={"decision": "accept", "knowledge_version": 0},
    )
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "save_failed" and body["request_id"]
    assert "space" not in r.text and "Errno" not in r.text  # no OS error text in the body (SB13)
    monkeypatch.undo()
    assert snapshot(root, skip=()) == before
    assert client.get(f"/api/projects/{project}/proposals").json()[0]["status"] == "pending"
