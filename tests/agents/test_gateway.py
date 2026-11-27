"""G11 acceptance: the model gateway (C7, C8, C15; SB14, SB19). Offline, recorded replies.

Every test drives a real ADK Runner (or the real API app) with the gated model; only the
provider's network hop is replaced (``tests.agents.support``). Test names carry the acceptance
item they evidence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import textwrap
import time
import traceback
from pathlib import Path

import keyring.backends.fail
import keyring.errors
import pytest
from fastapi.testclient import TestClient

from tests.agents.support import (
    PROVIDERS,
    Recorder,
    fake_key,
    final_text,
    make_gateway,
    record_note,
    run_session,
)
from tests.api.support import BASE, ORIGIN, TOKEN, make_settings
from truelift.agents import gateway as gateway_mod
from truelift.agents import redaction
from truelift.agents.gateway import (
    Gateway,
    GatewayError,
    default_model_factory,
    gateway_error_for,
    load_catalog,
)
from truelift.agents.keys import KeychainUnavailable, KeySource, KeyStore
from truelift.agents.payload import MAX_SAMPLE_ROWS, PayloadRefused, build_payload, inspect_request
from truelift.api.app import create_app
from truelift.causal.forbidden import SYNTHETIC_PREFIX
from truelift.store.db import StateDb
from truelift.worker.scripted import create_scripted_project

PROJECT = "demo-1"
CATALOG = load_catalog()


def run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def data_message(rows: int = MAX_SAMPLE_ROWS) -> str:
    payload = build_payload(
        columns=[{"name": "week", "type": "date"}, {"name": "revenue", "type": "number"}],
        summary={"revenue": {"min": 18400, "max": 96100, "missing_share": 0}},
        sample_rows=[{"week": f"2025-01-{i % 28 + 1:02d}", "revenue": 40000 + i} for i in range(rows)],
    )
    return "Here is my data. " + payload.as_text()


def ledger(gw: Gateway, project: str = PROJECT) -> list:
    return list(reversed(gw.ledger(project)))


# --- A8: both providers pass the same recorded-reply suite; IDs from models.yaml ------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a8_recorded_text_reply(tmp_path, provider):
    rec = Recorder(provider, ["text"])
    gw = make_gateway(tmp_path, rec)
    events = run(run_session(gw, data_message()))
    assert "Holiday weeks" in final_text(events)
    assert rec.calls == 1 and rec.requests[0]["key_matches"]
    spec = CATALOG.spec(provider)
    if provider == "gemini":
        assert f"/models/{spec.model_id}:generateContent" in rec.requests[0]["url"]
    else:
        assert rec.requests[0]["model"] == spec.litellm_model
        assert rec.requests[0]["num_retries"] == 0
    [row] = ledger(gw)
    assert (row.provider, row.model_id, row.status) == (provider, spec.model_id, "settled")
    assert (row.input_tokens, row.output_tokens) == (812, 14)
    assert json.loads(row.categories) == ["columns", "summary", "sample_rows", "answers"]
    assert row.bytes_sent > 0


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a8_recorded_tool_call_then_text(tmp_path, provider):
    rec = Recorder(provider, ["tool_call", "text"])
    gw = make_gateway(tmp_path, rec)
    events = run(run_session(gw, "We discount in holiday weeks.", tools=[record_note]))
    assert "Holiday weeks" in final_text(events)
    assert rec.calls == 2
    assert [r.status for r in ledger(gw)] == ["settled", "settled"]


def test_a8_model_ids_come_from_models_yaml():
    assert CATALOG.spec("gemini").model_id == "gemini-3.8-flash"
    assert CATALOG.spec("claude").model_id == "claude-sonnet-5-5"
    assert CATALOG.spec("claude").litellm_model == "anthropic/claude-sonnet-5-5"


def test_a8_default_factory_passes_key_per_call_and_no_sdk_retries(monkeypatch):
    for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    gemini = default_model_factory(CATALOG.spec("gemini"), fake_key("factory"))
    assert gemini.model == "gemini-3.8-flash"
    assert gemini.client_kwargs == {"api_key": fake_key("factory")}
    assert gemini.retry_options is None  # google-genai then makes exactly one attempt
    claude = default_model_factory(CATALOG.spec("claude"), fake_key("factory"))
    assert claude.model == "anthropic/claude-sonnet-5-5"
    assert claude._additional_args["num_retries"] == 0
    assert claude._additional_args["api_key"] == fake_key("factory")
    assert fake_key("factory") not in repr(gemini) + repr(claude)


# --- A1: the key only in the keychain; never in logs, db, files, requests or errors ---------


def test_a1_key_never_leaves_the_keychain(tmp_path, caplog, capfd, memory_keyring):
    redaction.install()
    key = "tl-canary-" + os.urandom(12).hex()
    caplog.set_level(logging.DEBUG)
    for name in ("LiteLLM", "litellm", "google_adk", "google_genai", "httpx", "truelift"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / PROJECT).mkdir()
    for provider in PROVIDERS:
        # A reply, then a provider error whose text quotes the key, then a rejected key.
        rec = Recorder(provider, ["text", ("status", 400, f"bad request near {key}"), 401])
        gw = make_gateway(tmp_path / provider, rec, key=key)
        run(run_session(gw, data_message()))
        for _ in range(2):
            with pytest.raises(GatewayError) as err:
                run(run_session(gw, "Another answer."))
            # The whole printed chain (what a traceback in a log would show) never has the key.
            chain = "".join(traceback.format_exception(err.value))
            assert key not in chain and "near" not in chain
        logging.getLogger("truelift.test").exception("provider said %s", key, exc_info=RuntimeError(key))
        for request in rec.requests:
            assert key not in request["body"] and key not in request.get("url", "")
        assert rec.requests[0]["key_matches"]
        gw.db.dispose()
    assert ("truelift", "gemini") in memory_keyring.items  # stored in the keychain only
    out, err_text = capfd.readouterr()
    logs = "\n".join(logging.Formatter("%(message)s").format(r) + (r.exc_text or "") for r in caplog.records)
    assert "provider said [redacted]" in logs
    for text in (logs, out, err_text):
        assert key not in text
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes(), path.name


def test_a1_redaction_filter_scrubs_patterns_and_exceptions():
    redaction.install()
    google_shaped = "AI" + "za" + "B" * 35
    record = logging.getLogger("x").makeRecord(
        "x",
        logging.ERROR,
        __file__,
        1,
        "key %s",
        (google_shaped,),
        (ValueError, ValueError(google_shaped), None),
    )
    text = logging.Formatter("%(message)s").format(record)
    assert google_shaped not in text and "[redacted]" in text


def test_a1_api_key_route_stores_only_in_keychain_and_never_echoes(tmp_path, memory_keyring):
    key = "tl-canary-" + os.urandom(12).hex()
    app = create_app(make_settings(tmp_path))
    with TestClient(app, base_url=BASE, headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}) as c:
        r = c.put("/api/setup/key", json={"provider": "gemini", "api_key": key})
        assert r.status_code == 204 and key not in r.text
        setup = c.get("/api/setup").json()
        assert key not in json.dumps(setup)
        assert setup["active_provider"] == "gemini"
        assert {p["provider"]: p["key_configured"] for p in setup["providers"]} == {
            "gemini": True,
            "claude": False,
        }
    assert memory_keyring.items[("truelift", "gemini")] == key
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes()


# --- A2: no call before consent for the current version and provider -----------------------


def test_a2_no_call_without_consent(tmp_path):
    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec, consent=False)
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    assert err.value.code == "consent_needed" and err.value.ai_state == "consent_needed"
    assert rec.calls == 0 and ledger(gw) == []
    gw.accept(PROJECT, "gemini", gateway_mod.DISCLOSURE_VERSION)
    run(run_session(gw, "Hello"))
    assert rec.calls == 1


def test_a2_consent_is_per_provider(tmp_path):
    rec = Recorder("claude", ["text"])
    gw = make_gateway(tmp_path, rec, consent=False)
    gw.accept(PROJECT, "gemini", gateway_mod.DISCLOSURE_VERSION)
    with pytest.raises(GatewayError, match="Review what will be shared"):
        run(run_session(gw, "Hello", provider="claude"))
    assert rec.calls == 0


def test_a2_version_bump_forces_reconsent(tmp_path, monkeypatch):
    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec)
    run(run_session(gw, "Hello"))
    monkeypatch.setattr(gateway_mod, "DISCLOSURE_VERSION", "2099-01-1")
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello again"))
    assert err.value.code == "consent_needed" and rec.calls == 1
    with pytest.raises(ValueError):
        gw.accept(PROJECT, "gemini", "2026-11-1")
    gw.accept(PROJECT, "gemini", "2099-01-1")
    run(run_session(gw, "Hello again"))
    assert rec.calls == 2


# --- A3: allowed categories only, <= 20 rows, no forbidden column, byte cap, ledger -------


def test_a3_build_payload_removes_forbidden_columns_and_caps_rows():
    truth = SYNTHETIC_PREFIX + "roi"
    p = build_payload(
        columns=[{"name": "revenue", "type": "number"}, {"name": truth, "type": "number"}],
        summary={"revenue": {"min": 1}, truth: {"min": 2}},
        sample_rows=[{"revenue": 1, truth: 2.5}],
    )
    assert truth not in p.as_text()
    assert p.categories == ("columns", "summary", "sample_rows")
    with pytest.raises(PayloadRefused, match="too_many_rows"):
        build_payload(sample_rows=[{"a": i} for i in range(MAX_SAMPLE_ROWS + 1)])


@pytest.mark.parametrize(
    ("part", "code"),
    [
        ({"inline_data": {"mime_type": "text/csv", "data": "d2Vlaw=="}}, "file_part"),
        ({"function_response": {"name": "t", "response": {"rows": [1, 2]}}}, "unknown_payload"),
        ({"text": '<truelift-data>{"raw_file": "..."}</truelift-data>'}, "unknown_category"),
        (
            {"text": '<truelift-data>{"sample_rows": [' + ",".join(["{}"] * 21) + "]}</truelift-data>"},
            "too_many_rows",
        ),
        (
            {"text": '<truelift-data>{"columns": [{"name": "' + SYNTHETIC_PREFIX + 'x"}]}</truelift-data>'},
            "forbidden_column",
        ),
        ({"text": "<truelift-data>{not json</truelift-data>"}, "unknown_payload"),
    ],
)
def test_a3_inspect_request_refuses(part, code):
    with pytest.raises(PayloadRefused) as err:
        inspect_request([{"role": "user", "parts": [part]}], max_bytes=10**6)
    assert err.value.code == code


def test_a3_forbidden_payload_refused_before_any_call(tmp_path):
    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec)
    bad = '<truelift-data>{"sample_rows": [{"' + SYNTHETIC_PREFIX + 'roi": 2.5}]}</truelift-data>'
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, bad))
    assert err.value.code == "payload_refused" and rec.calls == 0 and ledger(gw) == []


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a3_oversized_payload_refused(tmp_path, provider):
    rec = Recorder(provider, ["text"])
    gw = make_gateway(tmp_path, rec, limits={"max_request_bytes": 4096})
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "x" * 5000))
    assert err.value.code == "payload_too_large" and rec.calls == 0 and ledger(gw) == []


def test_a3_ledger_row_has_sizes_and_no_content(tmp_path):
    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec)
    run(run_session(gw, data_message()))
    [row] = ledger(gw)
    stored = json.dumps(row.__dict__, default=str)
    assert "2025-01-" not in stored and "40000" not in stored and "Holiday" not in stored
    assert row.bytes_sent >= len(data_message())
    db_bytes = b"".join(p.read_bytes() for p in (tmp_path / "state").glob("state.db*"))
    assert b"40019" not in db_bytes and b"Holiday weeks" not in db_bytes


# --- A4: an invalid or revoked key: "key rejected" and setup asks again ---------------------


@pytest.mark.parametrize(
    ("provider", "step"),
    [
        ("gemini", ("status", 400, "API key not valid. Please pass a valid API key.")),
        ("gemini", 403),
        ("claude", 401),
        ("claude", 403),
    ],
)
def test_a4_rejected_key_prompts_for_a_new_one(tmp_path, provider, step):
    rec = Recorder(provider, [step, "text"])
    gw = make_gateway(tmp_path, rec)
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    assert err.value.code == "key_rejected" and err.value.ai_state == "no_key"
    assert "rejected your API key" in err.value.message
    assert rec.calls == 1  # no retry
    state = {p.provider: p for p in gw.providers()}[provider]
    assert state.key_rejected and not state.key_configured
    assert gw.usage(PROJECT, provider).ai_state == "no_key"
    with pytest.raises(GatewayError, match="rejected"):
        run(run_session(gw, "Hello"))
    assert rec.calls == 1  # refused locally until a new key is saved
    gw.save_key(provider, fake_key("new"))
    rec.expected_key = fake_key("new")
    run(run_session(gw, "Hello"))
    assert rec.calls == 2 and rec.requests[-1]["key_matches"]


# --- A5: max_llm_calls, the project budget, and 429 retries ---------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a5_max_llm_calls_stops_a_looping_agent(tmp_path, provider):
    rec = Recorder(provider, ["tool_call"])  # the model asks for the tool forever
    gw = make_gateway(tmp_path, rec, limits={"max_llm_calls": 4})
    with pytest.raises(Exception) as err:
        run(run_session(gw, "Loop", tools=[record_note]))
    mapped = gateway_error_for(err.value)
    assert mapped is not None and mapped.code == "call_limit"
    assert rec.calls == 4


def test_a5_pinned_call_limit_is_positive():
    assert CATALOG.limits.max_llm_calls > 0
    gw = Gateway(StateDb(Path("/nonexistent/never-created.db")), catalog=CATALOG)
    assert gw.run_config().max_llm_calls == CATALOG.limits.max_llm_calls


def test_a5_budget_exhausted_pauses_ai(tmp_path):
    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec)
    gw.set_budget(PROJECT, 10_000)
    run(run_session(gw, "Hello"))  # 826 tokens settled
    assert gw.usage(PROJECT).tokens_used == 826
    gw.set_budget(PROJECT, 826)
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    assert err.value.code == "budget_paused" and err.value.ai_state == "budget_paused"
    assert "AI paused: budget reached" in err.value.message
    assert rec.calls == 1 and gw.usage(PROJECT).ai_state == "budget_paused"


def test_a5_estimate_must_fit_the_budget(tmp_path):
    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec)
    gw.set_budget(PROJECT, CATALOG.limits.max_output_tokens)  # cannot fit input estimate + reply cap
    with pytest.raises(GatewayError, match="budget"):
        run(run_session(gw, "Hello"))
    assert rec.calls == 0


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a5_429_retried_twice_then_paused(tmp_path, provider):
    rec = Recorder(provider, [429, 429, 429, "text"])
    gw = make_gateway(tmp_path, rec)
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    assert err.value.code == "rate_limited" and err.value.ai_state == "unavailable"
    assert rec.calls == 3  # first attempt + 2 retries
    assert [r.status for r in ledger(gw)] == ["rejected"] * 3
    assert all(r.input_tokens == 0 for r in ledger(gw))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a5_429_then_success(tmp_path, provider):
    rec = Recorder(provider, [429, "text"])
    gw = make_gateway(tmp_path, rec)
    assert "Holiday" in final_text(run(run_session(gw, "Hello")))
    assert rec.calls == 2


def test_a5_deterministic_flows_work_while_ai_is_paused(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    project, _ = create_scripted_project(app.state.store, "paused", 1)
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}
    with TestClient(app, base_url=BASE, headers=headers) as c:
        c.put("/api/setup/key", json={"provider": "gemini", "api_key": fake_key("test")})
        version = c.get(f"/api/projects/{project}/disclosure", params={"provider": "gemini"}).json()[
            "version"
        ]
        assert (
            c.post(
                f"/api/projects/{project}/consent", json={"provider": "gemini", "disclosure_version": version}
            ).status_code
            == 200
        )
        assert c.get(f"/api/projects/{project}/usage").json()["ai_state"] == "available"
        gw: Gateway = app.state.gateway
        gw.db.reserve_call(
            gateway_mod.LedgerRow(
                0, project, gw.clock(), "gemini", "gemini-3.8-flash", "[]", 10, 10_000, 0, "settled"
            ),
            10**9,
        )
        r = c.put(f"/api/projects/{project}/budget", json={"token_budget": 10_000})
        assert r.json() == {"tokens_used": 10_000, "token_budget": 10_000, "ai_state": "budget_paused"}
        for path in (
            f"/api/projects/{project}",
            f"/api/projects/{project}/dag",
            f"/api/projects/{project}/dag/identification",
            f"/api/projects/{project}/runs",
            f"/api/projects/{project}/ledger",
        ):
            assert c.get(path).status_code == 200, path


# --- A6: provider timeout or unavailable: wait up to 60 s, then "AI unavailable" -----------


def test_a6_deadline_is_sixty_seconds():
    assert CATALOG.limits.call_deadline_s == 60.0


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a6_timeout_shows_ai_unavailable(tmp_path, provider):
    rec = Recorder(provider, ["hang"])
    gw = make_gateway(tmp_path, rec, limits={"call_deadline_s": 0.5})
    start = time.monotonic()
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    elapsed = time.monotonic() - start
    assert err.value.code == "unavailable" and err.value.ai_state == "unavailable"
    assert err.value.message.startswith("AI unavailable")
    assert 0.5 <= elapsed < 5
    assert rec.calls == 1  # the deadline covers the whole call, retries included


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a6_unavailable_provider_retried_then_banner(tmp_path, provider):
    rec = Recorder(provider, [503, 503, 503, "text"])
    gw = make_gateway(tmp_path, rec)
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    assert err.value.code == "unavailable" and rec.calls == 3


# --- A7: keychain unavailable or locked: env var only, never a file; read-back ------------


class _LockedKeyring:
    priority = 1

    def get_password(self, service, username):
        raise keyring.errors.KeyringLocked("locked")

    def set_password(self, service, username, password):
        raise keyring.errors.KeyringLocked("locked")


class _DroppingKeyring:
    """Accepts a write and keeps nothing: the read-back catches it."""

    priority = 1

    def get_password(self, service, username):
        return None

    def set_password(self, service, username, password):
        return None


class _PlaintextKeyring:
    priority = 1

    def __init__(self):
        self.items = {}

    def get_password(self, service, username):
        return self.items.get((service, username))

    def set_password(self, service, username, password):
        self.items[(service, username)] = password


_PlaintextKeyring.__module__ = "keyrings.alt.file"


@pytest.mark.parametrize("backend", [keyring.backends.fail.Keyring(), _LockedKeyring(), _PlaintextKeyring()])
def test_a7_no_keychain_falls_back_to_env_var_only(backend):
    store = KeyStore(
        CATALOG.key_slots(), backend=backend, environ={"TRUELIFT_GEMINI_API_KEY": fake_key("env")}
    )
    with pytest.raises(KeychainUnavailable) as err:
        store.save("gemini", fake_key("typed"))
    assert "TRUELIFT_GEMINI_API_KEY" in str(err.value) and "tl-typed-key" not in str(err.value)
    assert store.get("gemini") == (fake_key("env"), KeySource.env)
    assert store.get("claude") is None
    if isinstance(backend, _PlaintextKeyring):
        assert backend.items == {}  # never written to a file-backed store


def test_a7_saved_key_is_read_back():
    store = KeyStore(CATALOG.key_slots(), backend=_DroppingKeyring(), environ={})
    with pytest.raises(KeychainUnavailable):
        store.save("claude", fake_key("typed"))
    assert store.status("claude").configured is False


def test_a7_keychain_wins_over_env(memory_keyring):
    store = KeyStore(CATALOG.key_slots(), environ={"TRUELIFT_ANTHROPIC_API_KEY": fake_key("env")})
    assert store.get("claude") == (fake_key("env"), KeySource.env)
    store.save("claude", fake_key("chain"))
    assert store.get("claude") == (fake_key("chain"), KeySource.keychain)
    assert memory_keyring.items == {("truelift", "anthropic"): fake_key("chain")}


def test_a7_api_reports_locked_keychain_without_echo(tmp_path, monkeypatch):
    import keyring as keyring_mod

    monkeypatch.setattr(keyring_mod, "get_keyring", lambda: _LockedKeyring())
    key = "tl-canary-" + os.urandom(12).hex()
    app = create_app(make_settings(tmp_path))
    with TestClient(app, base_url=BASE, headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}) as c:
        r = c.put("/api/setup/key", json={"provider": "gemini", "api_key": key})
    assert r.status_code == 503 and r.json()["code"] == "keychain_unavailable"
    assert "TRUELIFT_GEMINI_API_KEY" in r.json()["message"] and key not in r.text
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert key.encode() not in path.read_bytes()


def test_a7_env_key_drives_a_session(tmp_path, monkeypatch):
    import keyring as keyring_mod

    monkeypatch.setattr(keyring_mod, "get_keyring", lambda: keyring.backends.fail.Keyring())
    monkeypatch.setenv("TRUELIFT_GEMINI_API_KEY", fake_key("env"))
    rec = Recorder("gemini", ["text"], expected_key=fake_key("env"))
    gw = make_gateway(tmp_path, rec, key=None)
    assert gw.active_provider() == "gemini"
    run(run_session(gw, "Hello"))
    assert rec.requests[0]["key_matches"]


# --- A9: the provider is the only network destination ----------------------------------------

_SOCKET_PROBE = textwrap.dedent(
    """
    import asyncio, json, socket, sys
    hosts = []
    real_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host, *args, **kwargs):
        hosts.append(str(host))
        raise socket.gaierror(socket.EAI_NONAME, "blocked by the G11 egress test")

    def guarded_connect(self, address):
        hosts.append(repr(address))
        raise ConnectionRefusedError("blocked by the G11 egress test")

    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.connect = guarded_connect

    from pathlib import Path
    import truelift  # the app's entry point imports truelift first, which disables the fetch
    import litellm  # imported under the guard: a cost-map fetch would show up in hosts
    from litellm.litellm_core_utils.get_model_cost_map import get_model_cost_map_source_info
    from truelift.agents.gateway import Gateway, load_catalog
    from truelift.store.db import StateDb
    from tests.agents.support import catalog, fake_key, run_session

    import keyring
    from tests.conftest import MemoryKeyring
    backend = MemoryKeyring()
    keyring.get_keyring = lambda: backend

    async def no_sleep(_):
        return None

    info = get_model_cost_map_source_info()
    out = {"cost_map": [info["source"], info["is_env_forced"]], "import_hosts": sorted(set(hosts))}
    for provider in ("gemini", "claude"):
        hosts.clear()
        gw = Gateway(StateDb(Path(sys.argv[1]) / provider / "state.db"), catalog=catalog(), sleep=no_sleep)
        gw.save_key(provider, fake_key("egress"))
        gw.accept("demo-1", provider, __import__("truelift.agents.gateway").agents.gateway.DISCLOSURE_VERSION)
        try:
            asyncio.run(run_session(gw, "Hello", provider=provider))
            out[provider] = {"error": None}
        except Exception as exc:
            out[provider] = {"error": getattr(exc, "code", type(exc).__name__)}
        out[provider]["hosts"] = sorted(set(hosts))
    print("RESULT " + json.dumps(out))
    """
)


def test_a9_provider_is_the_only_network_destination(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GOOGLE_", "GEMINI_", "ANTHROPIC_"))}
    env.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)  # truelift must set it itself
    env.update({"OTEL_SDK_DISABLED": "true", "PYTHONPATH": str(Path(__file__).resolve().parents[2])})
    proc = subprocess.run(
        [sys.executable, "-c", _SOCKET_PROBE, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=Path(__file__).resolve().parents[2],
    )
    line = next((x for x in proc.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line is not None, proc.stderr[-3000:]
    result = json.loads(line.removeprefix("RESULT "))
    assert result["cost_map"] == ["local", True] and result["import_hosts"] == []
    for provider in PROVIDERS:
        assert result[provider]["error"] == "unavailable"
        assert result[provider]["hosts"] == [CATALOG.spec(provider).host], result


# --- A10: 400, safety block, context too long: plain message, no retry ----------------------


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(
    ("step", "code", "message"),
    [
        (("status", 400, "Request contains an invalid argument."), "invalid_request", "could not process"),
        ("safety", "safety_blocked", "declined to answer"),
        (
            (
                "status",
                400,
                "The input token count (1200000) exceeds the maximum number of tokens allowed. context",
            ),
            "context_too_long",
            "too long",
        ),
    ],
)
def test_a10_plain_message_and_no_retry(tmp_path, provider, step, code, message):
    rec = Recorder(provider, [step, "text"])
    gw = make_gateway(tmp_path, rec)
    with pytest.raises(GatewayError) as err:
        run(run_session(gw, "Hello"))
    assert err.value.code == code and message in err.value.message
    assert rec.calls == 1
    assert "invalid argument" not in err.value.message and "1200000" not in err.value.message


# --- A11: a lost response still charges an estimate -----------------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a11_lost_response_charges_estimate(tmp_path, provider):
    rec = Recorder(provider, ["hang"])
    gw = make_gateway(tmp_path, rec, limits={"call_deadline_s": 0.3})
    with pytest.raises(GatewayError):
        run(run_session(gw, data_message()))
    [row] = ledger(gw)
    assert row.status == "lost"
    assert row.input_tokens > 0 and row.output_tokens == CATALOG.limits.max_output_tokens
    assert gw.usage(PROJECT).tokens_used == row.input_tokens + row.output_tokens


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a11_reply_without_usage_keeps_estimate(tmp_path, provider):
    rec = Recorder(provider, ["no_usage"])
    gw = make_gateway(tmp_path, rec)
    assert "Understood" in final_text(run(run_session(gw, "Hello")))
    [row] = ledger(gw)
    assert row.status == "estimated" and row.input_tokens > 0
    assert gw.usage(PROJECT).tokens_used == row.input_tokens + row.output_tokens


def test_a11_unsent_request_charges_nothing(tmp_path):
    import httpx

    rec = Recorder("gemini", ["text"])
    gw = make_gateway(tmp_path, rec, limits={"max_retries": 0})

    def refuse(spec, key):  # type: ignore[no-untyped-def]
        model = rec.model_factory(spec, key)

        async def boom(request):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("refused", request=request)

        model.client_kwargs["http_options"].httpx_async_client = httpx.AsyncClient(
            transport=httpx.MockTransport(boom)
        )
        return model

    gw.model_factory = refuse
    with pytest.raises(GatewayError, match="AI unavailable"):
        run(run_session(gw, "Hello"))
    [row] = ledger(gw)
    assert (row.status, row.bytes_sent, row.input_tokens, row.output_tokens) == ("not_sent", 0, 0, 0)


# --- the setup routes on a real project -----------------------------------------------------


def test_setup_routes_on_a_real_project(tmp_path):
    app = create_app(make_settings(tmp_path))
    project, _ = create_scripted_project(app.state.store, "setup", 1)
    with TestClient(app, base_url=BASE, headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGIN}) as c:
        assert c.get(f"/api/projects/{project}/usage").json()["ai_state"] == "no_key"
        c.put("/api/setup/key", json={"provider": "claude", "api_key": fake_key("test")})
        assert c.get("/api/setup").json()["active_provider"] == "claude"
        d = c.get(f"/api/projects/{project}/disclosure", params={"provider": "claude"}).json()
        assert d["version"] == gateway_mod.DISCLOSURE_VERSION
        assert [x["id"] for x in d["categories"]] == [
            "columns",
            "summary",
            "sample_rows",
            "answers",
            "results",
        ]
        assert d["example_payload"]["columns"] and all(
            not x["name"].startswith(SYNTHETIC_PREFIX) for x in d["example_payload"]["columns"]
        )
        assert c.get(f"/api/projects/{project}/usage").json()["ai_state"] == "consent_needed"
        old = c.post(
            f"/api/projects/{project}/consent", json={"provider": "claude", "disclosure_version": "old"}
        )
        assert old.status_code == 409 and old.json()["code"] == "disclosure_changed"
        ok = c.post(
            f"/api/projects/{project}/consent",
            json={"provider": "claude", "disclosure_version": d["version"]},
        )
        assert ok.status_code == 200
        usage = c.get(f"/api/projects/{project}/usage").json()
        assert usage == {
            "tokens_used": 0,
            "token_budget": CATALOG.limits.default_token_budget,
            "ai_state": "available",
        }
        assert c.get(f"/api/projects/{project}/ledger").json() == []
        assert c.get("/api/projects/nope-1/usage").status_code == 404
