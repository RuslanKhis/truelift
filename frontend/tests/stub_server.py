"""Run the real truelift API (the G02 stub routes) for the frontend contract tests (G15).

Same app as ``uv run truelift``, but with a token the test chose instead of a random one, and on
loopback only. Project and state folders come from TRUELIFT_PROJECTS_DIR and TRUELIFT_STATE_DIR,
which the test points at a temporary directory, so no real project is touched. The server stops
when its stdin closes, so it never outlives the test run (also on Windows).
"""

from __future__ import annotations

import os
import sys
import threading

import uvicorn

from truelift.api.app import create_app
from truelift.api.settings import Settings


def main() -> None:
    port = int(sys.argv[1])
    token = os.environ["TRUELIFT_TEST_TOKEN"]
    settings = Settings.from_env(port=port, launch_token=token)
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )

    def stop_when_parent_closes_stdin() -> None:
        sys.stdin.read()
        server.should_exit = True

    threading.Thread(target=stop_when_parent_closes_stdin, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
