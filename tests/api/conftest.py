"""Fixtures for the API tests (G02). The real app, middleware and routes run; nothing is mocked
except where a test says so."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.support import BASE, ORIGIN, TOKEN, make_settings
from truelift.api.app import create_app
from truelift.api.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


def _client(app: FastAPI, headers: dict[str, str]) -> TestClient:
    return TestClient(app, base_url=BASE, headers=headers, raise_server_exceptions=False)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with _client(app, {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}) as c:
        yield c


@pytest.fixture
def anon(app: FastAPI) -> Iterator[TestClient]:
    """Same origin, no token."""
    with _client(app, {"Origin": ORIGIN}) as c:
        yield c
