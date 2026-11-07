"""G02 A8 (Python side): the committed OpenAPI dump matches the code, and its shape is stable.

``make client-check`` does the full regeneration of ``frontend/src/client`` and fails on drift.
"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path

from truelift.api.openapi_dump import render

REPO = Path(__file__).resolve().parents[2]


def test_committed_openapi_matches_code():
    committed = (REPO / "openapi.json").read_text(encoding="utf-8")
    assert committed == render(), "openapi.json is stale: run `make client` and commit the result"


def test_dump_needs_no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the OpenAPI dump tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    assert json.loads(render())["info"]["title"] == "truelift"


def test_operations_are_stable_and_documented():
    doc = json.loads(render())
    ids = []
    for path, item in doc["paths"].items():
        for method, op in item.items():
            ids.append(op["operationId"])
            assert re.fullmatch(r"[a-z]+-[a-z_]+", op["operationId"]), op["operationId"]
            if path.startswith("/api"):
                assert {"401", "403", "422", "500"} <= set(op["responses"]), (method, path)
                assert op["responses"]["401"]["content"]["application/json"]["schema"]["$ref"].endswith(
                    "/ErrorBody"
                )
    assert len(ids) == len(set(ids))
    assert "HTTPValidationError" not in doc["components"]["schemas"]


def test_stream_route_out_of_paths_but_events_in_components():
    doc = json.loads(render())
    assert not any("agent" in p for p in doc["paths"])
    schemas = doc["components"]["schemas"]
    assert "AgentEvent" in schemas
    members = {ref["$ref"].rsplit("/", 1)[-1] for ref in schemas["AgentEvent"]["oneOf"]}
    assert members == {
        "TurnStarted",
        "TextDelta",
        "TextDone",
        "ToolStarted",
        "ToolFinished",
        "ProposalCreated",
        "AiStatusChanged",
        "TurnFinished",
        "TurnFailed",
    }
    assert schemas["AgentEvent"]["discriminator"]["propertyName"] == "type"


def test_no_adk_or_docs_paths_in_contract():
    doc = json.loads(render())
    for path in doc["paths"]:
        assert not path.startswith(("/run", "/apps", "/list-apps", "/dev-ui", "/docs"))


def test_generated_client_is_committed():
    client = REPO / "frontend" / "src" / "client"
    assert (client / "types.gen.ts").is_file()
    types = (client / "types.gen.ts").read_text(encoding="utf-8")
    assert "export type AgentEvent" in types
    assert "ErrorBody" in types
