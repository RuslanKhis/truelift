"""``python -m truelift.worker <run_id> --run-dir <dir>``: one pipeline run (D8)."""

from __future__ import annotations

import sys

from truelift.worker.job import main

if __name__ == "__main__":
    sys.exit(main())
