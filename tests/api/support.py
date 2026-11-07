"""Constants and helpers shared by the API tests."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from fastapi import FastAPI

from truelift.api.settings import Settings

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = BASE
TOKEN = secrets.token_urlsafe(32)

# Sample values for path parameters, so every /api route can be called.
PATH_VALUES = {
    "project_id": "petfood-de",
    "run_id": "run-demo01",
    "proposal_id": "P005",
    "edge_id": "e1",
}


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "port": PORT,
        "launch_token": TOKEN,
        "web_dir": tmp_path / "web",
        "fake_stream_delay_s": 0.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


# /api routes kept out of the OpenAPI document on purpose.
UNDOCUMENTED_API_CALLS = [
    ("POST", "/api/projects/petfood-de/agent/messages"),
    *((m, "/api/x") for m in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")),
]


def api_calls(app: FastAPI) -> list[tuple[str, str]]:
    """(method, concrete path) for every /api route: the documented ones from the app's own
    OpenAPI document (FastAPI 0.141 keeps included routers lazy, so app.routes is not flat),
    plus the undocumented ones listed above."""
    calls = []
    for path, item in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        concrete = re.sub(r"\{(\w+)\}", lambda m: PATH_VALUES.get(m.group(1), "x"), path)
        calls.extend((method.upper(), concrete) for method in item)
    return sorted(calls) + UNDOCUMENTED_API_CALLS


def no_cors_headers(response) -> bool:
    return not any(h.lower().startswith("access-control-") for h in response.headers)
