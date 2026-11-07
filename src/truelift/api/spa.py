"""Serves the built SPA (public, no token: A1) with a client-side routing fallback.

The build lands in ``src/truelift/web/`` (G15 builds it; it is not committed). Until then a small
placeholder shell is served. Rules:

* a GET or HEAD for an existing file inside the build directory returns that file;
* a GET or HEAD for a path with a file extension that does not exist is 404 (so a missing
  ``/openapi.json`` is never answered with HTML);
* any other GET or HEAD returns the shell, which holds no data;
* any other method is 404. ``/api/...`` never reaches this router.

ADK's own paths (``/run``, ``/run_sse``, ``/apps/...``, ``/list-apps``, ``/dev-ui/``) are not
mounted, so they fall through to these rules and reach no agent (SB05).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from truelift.api.errors import error_json, request_id_of

PLACEHOLDER_SHELL = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>truelift</title></head>
<body><main><h1>truelift</h1>
<p>The API is running. The interface is not built yet.</p></main></body>
</html>
"""

router = APIRouter(include_in_schema=False)


def _shell(web_dir: Path) -> Response:
    index = web_dir / "index.html"
    if index.is_file():
        return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-cache"})
    return HTMLResponse(PLACEHOLDER_SHELL, headers={"Cache-Control": "no-cache"})


@router.api_route("/{path:path}", methods=["GET", "HEAD"])
def spa(path: str, request: Request) -> Response:
    web_dir: Path = request.app.state.settings.web_dir.resolve()
    if path:
        candidate = (web_dir / path).resolve()
        if candidate.is_relative_to(web_dir) and candidate.is_file():
            return FileResponse(candidate)
        if "." in path.rsplit("/", 1)[-1]:
            return error_json(404, request_id_of(request))
    return _shell(web_dir)


@router.api_route("/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def not_found(path: str, request: Request) -> Response:
    return error_json(404, request_id_of(request))
