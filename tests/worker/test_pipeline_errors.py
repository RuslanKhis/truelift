"""G09/A4 with the real pipeline: doubleml-pipeline's own ``ValueError`` fails the run with a plain
reason and keeps the config (C10). The real worker (``python -m truelift.worker``) runs; the
pipeline refuses the data in its column check, before it fits anything. Local, about 10 s."""

from __future__ import annotations

import csv
import io

from truelift.store import VersionKind
from truelift.worker.gate import data_fingerprint
from truelift.worker.layout import RunFolder
from truelift.worker.manager import Limits, RunManager


def test_a_real_pipeline_value_error_fails_with_a_plain_reason(store, project) -> None:
    root = store.projects_dir / project
    rows = list(csv.DictReader(io.StringIO((root / "data" / "v1.csv").read_text())))
    out = io.StringIO()
    columns = [c for c in rows[0] if c != "media_grps"]  # the file no longer has a mapped column
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (root / "data" / "v2.csv").write_text(out.getvalue())
    fingerprint = data_fingerprint(root / "data" / "v2.csv")
    for kind in (VersionKind.mapping, VersionKind.dag):
        record = store.read_version(project, kind)
        store.write_version(project, kind, record.content, expected_current=1, data_fingerprint=fingerprint)
        store.confirm_version(project, kind, 2)

    manager = RunManager(store, limits=Limits(kill_grace_s=2.0))
    row = manager.start(project, 2, "quick")
    final = manager.wait(row.id, timeout=180)
    assert final is not None and final.status == "failed"
    assert final.reason is not None and final.reason.startswith("The analysis could not run on this data: ")
    assert "media_grps" in final.reason and "\n" not in final.reason
    folder = RunFolder(root / "runs" / row.id)
    assert folder.config.is_file() and folder.env.is_file() and not folder.manifest.exists()
    assert "ValueError" in folder.log.read_text()
