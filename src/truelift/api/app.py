"""The FastAPI app factory (design D12, contract C16).

Middleware, outermost first: request ID, security headers, localhost guard (Host, Origin, no
token in the URL), body limit. The ``/api`` router requires the launch token on every route,
including its catch-all 404. ADK's own server (``get_fast_api_app``) is never mounted; the ADK
Runner arrives in process with G13. No CORS middleware is installed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from starlette.middleware import Middleware

from truelift import __version__
from truelift.api.auth import LocalhostGuardMiddleware, require_launch_token
from truelift.api.errors import ERROR_RESPONSES, ApiError, RequestIdMiddleware, install_error_handlers
from truelift.api.fakes import FakeStore
from truelift.api.middleware import BodyLimitMiddleware, SecurityHeadersMiddleware
from truelift.api.routes import agent, dag, intake, projects, results, runs, setup
from truelift.api.schemas import Health
from truelift.api.settings import Settings
from truelift.api.spa import router as spa_router
from truelift.api.stream import AGENT_EVENT


def _operation_id(route: APIRoute) -> str:
    # Stable, readable client names: "<tag>-<function>" (e.g. projects-list_projects).
    return f"{route.tags[0]}-{route.name}" if route.tags else route.name


def _api_router() -> APIRouter:
    api = APIRouter(prefix="/api", dependencies=[Depends(require_launch_token)], responses=ERROR_RESPONSES)
    for module in (projects, setup, intake, dag, runs, results, agent):
        api.include_router(module.router)

    @api.api_route(
        "/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    def api_not_found(path: str) -> None:
        # Behind the token like every /api route; never answered with the SPA shell.
        raise ApiError(404, "not_found", "Not found.")

    return api


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="truelift",
        version=__version__,
        summary="Local API of truelift. Every /api route needs the per-launch bearer token.",
        docs_url="/docs" if settings.dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.dev else None,
        swagger_ui_oauth2_redirect_url=None,
        generate_unique_id_function=_operation_id,
        middleware=[
            Middleware(RequestIdMiddleware),
            Middleware(SecurityHeadersMiddleware, settings=settings),
            Middleware(LocalhostGuardMiddleware, settings=settings),
            Middleware(BodyLimitMiddleware, settings=settings),
        ],
    )
    app.state.settings = settings
    app.state.fakes = FakeStore()
    app.state.agent_busy = set()
    install_error_handlers(app)

    @app.get("/health", tags=["health"])
    def health() -> Health:
        """Public liveness check: no token, no data."""
        return Health(status="ok")

    app.include_router(_api_router())
    app.include_router(spa_router)

    _add_stream_schemas(app)
    return app


def _add_stream_schemas(app: FastAPI) -> None:
    """Put the agent-stream event models into the OpenAPI components (not the paths), so the
    generated client exports their types while the stream route stays out of the client."""
    base_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = base_openapi()
        event_schema = AGENT_EVENT.json_schema(
            mode="serialization", ref_template="#/components/schemas/{model}"
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        defs = event_schema.pop("$defs", {})
        for name, definition in defs.items():
            if name in components and components[name] != definition:
                raise RuntimeError(f"stream schema {name!r} differs from the API schema of the same name")
            components[name] = definition
        components["AgentEvent"] = {**event_schema, "title": "AgentEvent"}
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
