"""One error contract for every response the API sends (SB09, SB13).

Bodies are generic: no stack trace, no SQL, no provider text and no echo of the request input,
so a pasted API key in a rejected body never comes back. Each body carries the request ID that
is also sent as the ``X-Request-ID`` header.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from truelift.store.errors import ParseFailed, StoreError

log = logging.getLogger("truelift.api")

REQUEST_ID_HEADER = "X-Request-ID"

_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "unavailable",
}

_MESSAGES = {
    400: "The request could not be read.",
    401: "Open truelift from the link the truelift command printed.",
    403: "This request is not allowed.",
    404: "Not found.",
    405: "This method is not allowed here.",
    409: "This conflicts with the current state. Reload and try again.",
    413: "The request is too large.",
    415: "This content type is not supported.",
    422: "Some fields are not valid.",
    500: "Something went wrong. Quote the request ID if you report it.",
    503: "Temporarily unavailable. Try again shortly.",
}


class FieldError(BaseModel):
    """One invalid field. ``loc`` is the path to it; the submitted value is never echoed."""

    loc: list[str | int]
    message: str


class ErrorBody(BaseModel):
    """The body of every 4xx and 5xx response."""

    code: str = Field(description="Stable machine-readable code, e.g. `unauthorized` or `agent_busy`.")
    message: str = Field(description="Plain-language message, safe to show to the user as text.")
    request_id: str
    fields: list[FieldError] | None = None


class ApiError(Exception):
    """An expected, user-facing failure with its own code (e.g. ``agent_busy``, ``not_csv``)."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        fields: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields
        self.headers = headers


# Every /api route documents these, so the generated client knows the error shape.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorBody, "description": _MESSAGES[status]} for status in (401, 403, 422, 500)
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorBody, "description": _MESSAGES[status]} for status in statuses}


def request_id_of(scope_or_request: Scope | Request) -> str:
    scope = scope_or_request.scope if isinstance(scope_or_request, Request) else scope_or_request
    state = scope.get("state") or {}
    return state.get("request_id") or "unknown"


def error_json(
    status: int,
    request_id: str,
    *,
    code: str | None = None,
    message: str | None = None,
    fields: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorBody(
        code=code or _CODES.get(status, "error"),
        message=message or _MESSAGES.get(status, "The request failed."),
        request_id=request_id,
        fields=fields,
    )
    all_headers = {REQUEST_ID_HEADER: request_id, "Cache-Control": "no-store"}
    all_headers.update(headers or {})
    return JSONResponse(body.model_dump(exclude_none=True), status_code=status, headers=all_headers)


class RequestIdMiddleware:
    """Gives every request a server-generated ID (a client-sent one is ignored)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)


async def _api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_json(
        exc.status,
        request_id_of(request),
        code=exc.code,
        message=exc.message,
        fields=exc.fields,
        headers=exc.headers,
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    # Our own HTTPExceptions carry a safe message as detail; framework ones ("Not Found") are replaced.
    message = exc.detail if isinstance(exc.detail, str) and exc.detail not in _framework_details else None
    return error_json(status, request_id_of(request), message=message, headers=dict(exc.headers or {}))


_framework_details = frozenset(
    {"Not Found", "Method Not Allowed", "Bad Request", "Unauthorized", "Forbidden"}
)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        FieldError(
            loc=[p for p in err.get("loc", ()) if isinstance(p, str | int)], message=str(err.get("msg"))
        )
        for err in exc.errors()
    ]
    # A body that is not valid JSON is a 422 here too: the field list names the body.
    return error_json(422, request_id_of(request), fields=fields)


async def _store_error(request: Request, exc: Exception) -> JSONResponse:
    """Project-store failures (G08). A parse error names each file and line in ``fields``; a
    failed save is a 500 with its own code and a plain message, never the OS error."""
    assert isinstance(exc, StoreError)
    if exc.status >= 500:
        log.error("store error request_id=%s code=%s", request_id_of(request), exc.code, exc_info=exc)
    fields = None
    if isinstance(exc, ParseFailed):
        fields = [FieldError(loc=[i.file, i.line], message=i.message) for i in exc.issues]
    return error_json(exc.status, request_id_of(request), code=exc.code, message=exc.message, fields=fields)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # The full traceback stays in the local log only; the body is generic (SB13).
    log.error("unhandled error request_id=%s path=%s", request_id_of(request), request.url.path, exc_info=exc)
    response = error_json(500, request_id_of(request))
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StoreError, _store_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unexpected_error)
