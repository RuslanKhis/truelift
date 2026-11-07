"""Write the OpenAPI document offline: no token, no network, no server.

    uv run python -m truelift.api.openapi_dump openapi.json

``make client`` regenerates ``frontend/src/client`` from it; ``make check`` fails on drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from truelift.api.app import create_app
from truelift.api.settings import Settings


def render() -> str:
    app = create_app(Settings(port=8000, launch_token=None))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    text = render()
    if not args or args[0] == "-":
        sys.stdout.write(text)
    else:
        Path(args[0]).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
