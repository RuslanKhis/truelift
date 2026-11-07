"""The launcher binds loopback only, makes a fresh token per launch, and never starts ADK's server
(D12, C16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from truelift.api.auth import new_launch_token
from truelift.api.settings import Settings
from truelift.cli import bind_loopback, build_parser

SRC = Path(__file__).resolve().parents[2] / "src" / "truelift"


def test_bind_loopback_only():
    sock = bind_loopback(0)
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1" and port > 0
    finally:
        sock.close()


def test_launch_tokens_are_fresh_and_long():
    a, b = new_launch_token(), new_launch_token()
    assert a != b and len(a) >= 43


def test_settings_reject_short_token_and_bad_port():
    with pytest.raises(ValueError):
        Settings(port=8000, launch_token="short")
    with pytest.raises(ValueError):
        Settings(port=0, launch_token=None)


def test_cli_has_no_host_option():
    options = {opt for action in build_parser()._actions for opt in action.option_strings}
    assert "--host" not in options and "--bind" not in options


def test_source_never_binds_wide_or_mounts_adk_server():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "0.0.0.0" not in text, path
        assert "get_fast_api_app" not in text or path.name == "app.py", path
        assert "allow_origins" not in text, path
    app_text = (SRC / "api" / "app.py").read_text(encoding="utf-8")
    assert "get_fast_api_app` is never mounted" in app_text or "never mounted" in app_text
    assert "import get_fast_api_app" not in app_text
