"""Domain routers. Each module is replaced route by route by the goal named in its docstring."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path, Request

from truelift.api.errors import ApiError
from truelift.api.fakes import DEMO_PROJECT, FakeStore
from truelift.api.schemas import ProjectId


def get_fakes(request: Request) -> FakeStore:
    return request.app.state.fakes


Fakes = Annotated[FakeStore, Depends(get_fakes)]


def demo_project(project_id: Annotated[ProjectId, Path()]) -> str:
    """The stubs hold data for the demo project only; any other ID is a 404."""
    if project_id != DEMO_PROJECT:
        raise ApiError(404, "project_not_found", "No project with this ID.")
    return project_id


DemoProject = Annotated[str, Depends(demo_project)]
