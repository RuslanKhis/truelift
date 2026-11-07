"""Security headers (SB07) and request-body limits (SB09)."""

from __future__ import annotations

import re

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from truelift.api.errors import error_json, request_id_of
from truelift.api.settings import Settings

# No inline script, no framing, no third-party origins. G16 widens this only with a recorded reason.
CSP = (
    "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
    "form-action 'self'; img-src 'self' data:; connect-src 'self'"
)
# FastAPI's Swagger UI loads from a CDN; it is served only in dev mode (TRUELIFT_DEV=1).
DEV_DOCS_CSP = (
    "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com"
)

_BASE_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
)

# The upload route gets the larger cap (G07 owns the route; G02 owns the limit).
_UPLOAD_PATH = re.compile(r"^/api/projects/[^/]+/data/?$")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        csp = DEV_DOCS_CSP if self.settings.dev and path == "/docs" else CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [*_BASE_HEADERS, (b"content-security-policy", csp.encode())]
                if path.startswith("/api/") or path == "/api":
                    extra.append((b"cache-control", b"no-store"))
                headers.extend((k, v) for k, v in extra if k not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLarge(StarletteHTTPException):
    """Raised from ``receive`` mid-body. An HTTPException, so FastAPI's body parser re-raises it
    instead of turning it into a 400, and the app's handler renders the 413 ErrorBody."""

    def __init__(self) -> None:
        super().__init__(413, "The request is too large.")


class BodyLimitMiddleware:
    """Refuses a body over the cap with 413, whether or not Content-Length is declared."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    def _limit(self, scope: Scope) -> int:
        if scope["method"] == "POST" and _UPLOAD_PATH.match(scope["path"]):
            return self.settings.max_upload_bytes
        return self.settings.max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope)
        rid = request_id_of(scope)
        for key, value in scope.get("headers", []):
            if key.lower() == b"content-length":
                if not value.isdigit():
                    await error_json(400, rid)(scope, receive, send)
                    return
                if int(value) > limit:
                    await error_json(413, rid)(scope, receive, send)
                    return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if started:
                raise
            await error_json(413, rid)(scope, receive, send)
