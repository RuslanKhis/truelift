"""Localhost authentication (design D12, contract C16; SB01, SB02, SB06, SB08).

Two layers, both failing closed:

* ``LocalhostGuardMiddleware`` runs on every request. It rejects a ``Host`` that is not
  127.0.0.1 or localhost on our port (DNS rebinding), a state-changing request whose ``Origin``
  is not ours (CSRF), and any request that carries a token in its query string.
* ``require_launch_token`` is a dependency on the whole ``/api`` router. It accepts the
  per-launch token only from ``Authorization: Bearer``. With no token configured it rejects
  everything.

No CORS middleware is installed, so no ``Access-Control-Allow-*`` header is ever sent.
"""

from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import Depends, Request
from starlette.types import ASGIApp, Receive, Scope, Send

from truelift.api.errors import ApiError, error_json, request_id_of
from truelift.api.settings import ALLOWED_HOSTNAMES, Settings

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Query parameter names that look like a credential. Any of them is refused (SB08).
_CREDENTIAL_PARAMS = frozenset({"token", "access_token", "auth", "authorization", "bearer", "key", "api_key"})

_BEARER_CHALLENGE = {"WWW-Authenticate": 'Bearer realm="truelift"'}
_SIGN_IN = "Open truelift from the link the truelift command printed."


def new_launch_token() -> str:
    """A fresh token for one launch: 256 bits from the OS CSPRNG."""
    return secrets.token_urlsafe(32)


def _header(scope: Scope, name: bytes) -> list[str]:
    return [v.decode("latin-1") for k, v in scope.get("headers", []) if k.lower() == name]


def host_allowed(host_header: str, settings: Settings) -> bool:
    host, sep, port = host_header.strip().rpartition(":")
    if not sep:
        host, port = host_header.strip(), "80"
    if not port.isdigit():
        return False
    host = host.lower()
    if host in ALLOWED_HOSTNAMES and int(port) == settings.port:
        return True
    if settings.dev:
        # In dev mode the Vite server proxies to us; its own host:port may appear here.
        return f"http://{host}:{port}" in settings.allowed_origins
    return False


def _query_carries_token(query_string: bytes, settings: Settings) -> bool:
    if not query_string:
        return False
    query = query_string.decode("latin-1")
    if settings.launch_token and settings.launch_token in query:
        return True
    return any(name.lower() in _CREDENTIAL_PARAMS for name, _ in parse_qsl(query, keep_blank_values=True))


class LocalhostGuardMiddleware:
    """Host allowlist, same-origin check for unsafe methods, and no tokens in URLs."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # No websockets in v1; refuse rather than pass through unchecked.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return

        rid = request_id_of(scope)
        hosts = _header(scope, b"host")
        if len(hosts) != 1 or not host_allowed(hosts[0], self.settings):
            await error_json(403, rid, code="host_not_allowed")(scope, receive, send)
            return

        if scope["method"] in UNSAFE_METHODS:
            origins = _header(scope, b"origin")
            if len(origins) != 1 or origins[0].rstrip("/") not in self.settings.allowed_origins:
                await error_json(403, rid, code="origin_not_allowed")(scope, receive, send)
                return

        if _query_carries_token(scope.get("query_string", b""), self.settings):
            await error_json(
                401,
                rid,
                code="token_in_query",
                message="Send the token in the Authorization header, never in the address.",
                headers=_BEARER_CHALLENGE,
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)


def require_launch_token(request: Request) -> None:
    """Dependency for every /api route: ``Authorization: Bearer <launch token>`` or 401."""
    settings: Settings = request.app.state.settings
    expected = settings.launch_token
    values = request.headers.getlist("authorization")
    if expected is None or len(values) != 1:
        raise ApiError(401, "unauthorized", _SIGN_IN, headers=_BEARER_CHALLENGE)
    scheme, _, presented = values[0].partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        presented.strip().encode(), expected.encode()
    ):
        raise ApiError(401, "unauthorized", _SIGN_IN, headers=_BEARER_CHALLENGE)


LaunchToken = Annotated[None, Depends(require_launch_token)]
