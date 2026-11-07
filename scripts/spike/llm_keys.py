"""G03/A4: Claude via ADK LiteLlm and Gemini via ADK's native model, key passed per call.

    uv run python scripts/spike/llm_keys.py

The keys are read from the macOS Keychain at call time (service ``truelift``, accounts
``gemini`` and ``anthropic``), handed to the model object only, and never printed,
logged, written or exported. The provider environment variables are removed first, so a
pass cannot come from an ambient key. Each provider gets one call with the real key and
one with a wrong key (which must fail with an auth error). The script then checks that
the key does not appear in the model and agent reprs, the captured logs or the error
text, and prints booleans only. Costs a few short calls (well under one US cent).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import time

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

# Pinned in D7; models.yaml (G11) will hold them.
GEMINI_MODEL = "gemini-3.8-flash"
CLAUDE_MODEL = "anthropic/claude-sonnet-5-5"
AMBIENT = [
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_CLOUD_PROJECT",
    "LITELLM_API_KEY",
]
WRONG_KEY = "truelift-spike-wrong-key-0000000000"


def keychain(account: str) -> str:
    out = subprocess.run(
        ["security", "find-generic-password", "-s", "truelift", "-a", account, "-w"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit(f"keychain item truelift/{account} not found")
    return out.stdout.strip()


def make_model(provider: str, key: str):
    if provider == "gemini":
        return Gemini(model=GEMINI_MODEL, client_kwargs={"api_key": key})
    return LiteLlm(model=CLAUDE_MODEL, api_key=key)


async def ask(model) -> tuple[str, str, str]:
    agent = LlmAgent(
        name="spike",
        model=model,
        instruction="Reply with the single word OK.",
        generate_content_config=types.GenerateContentConfig(max_output_tokens=512),
    )
    runner = InMemoryRunner(agent=agent, app_name="g03_spike")
    session = await runner.session_service.create_session(app_name="g03_spike", user_id="u")
    text = ""
    async for event in runner.run_async(
        user_id="u",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="Ping")]),
    ):
        if event.content and event.content.parts:
            text += "".join(p.text or "" for p in event.content.parts)
    return text, repr(model), repr(agent)


def check(provider: str, account: str, log: io.StringIO) -> dict:
    key = keychain(account)  # fetched at call time, held only in this frame and the model
    result: dict = {"provider": provider, "attempts": []}
    for _ in range(2):  # one retry on a provider-side 5xx; anything else is final
        try:
            reply, model_repr, agent_repr = asyncio.run(ask(make_model(provider, key)))
            result["attempts"].append("ok")
            result["call_ok"] = reply.strip().upper().startswith("OK")
            result["reply_chars"] = len(reply)
            result["key_in_model_repr"] = key in model_repr
            result["key_in_agent_repr"] = key in agent_repr
            break
        except Exception as exc:  # report class and status only; the text could carry request data
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            result["attempts"].append(f"{type(exc).__name__} {status}")
            result["call_ok"] = False
            result["key_in_error"] = result.get("key_in_error", False) or key in str(exc)
            if not (isinstance(status, int) and status >= 500):
                break
            time.sleep(20)
    try:
        asyncio.run(ask(make_model(provider, WRONG_KEY)))
        result["wrong_key_rejected"] = False
    except Exception as exc:
        text = str(exc)
        result["wrong_key_rejected"] = any(
            s in text
            for s in ("401", "403", "400", "API key", "api_key", "authentication", "PERMISSION_DENIED")
        )
        result["wrong_key_error_class"] = type(exc).__name__
        result["real_key_in_wrong_key_error"] = key in text
    result["key_in_logs"] = key in log.getvalue()
    result["ambient_env_still_absent"] = not any(v in os.environ for v in AMBIENT)
    return result


@contextlib.contextmanager
def captured_fds():
    """Send fds 1 and 2 to a private temp file, so library output never reaches the terminal."""
    sys.stdout.flush()
    sys.stderr.flush()
    fd, path = tempfile.mkstemp(prefix="g03_spike_")
    saved = os.dup(1), os.dup(2)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    try:
        yield path
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(fd)
        os.close(saved[0])
        os.close(saved[1])


def main() -> int:
    for var in AMBIENT:
        os.environ.pop(var, None)
    log = io.StringIO()
    handler = logging.StreamHandler(log)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    for name in ("LiteLLM", "litellm", "google_adk", "google_genai", "httpx"):
        logging.getLogger(name).setLevel(logging.DEBUG)

    with captured_fds() as path:
        results = [check("gemini", "gemini", log), check("claude", "anthropic", log)]
    try:
        with open(path, errors="replace") as fh:
            console = fh.read()
    finally:
        os.remove(path)
    for r, account in zip(results, ("gemini", "anthropic"), strict=True):
        r["key_in_console_output"] = keychain(account) in console
    print(json.dumps(results, indent=2))
    ok = all(
        r["call_ok"]
        and r["wrong_key_rejected"]
        and r["ambient_env_still_absent"]
        and not any(
            r.get(k)
            for k in (
                "key_in_model_repr",
                "key_in_agent_repr",
                "key_in_logs",
                "key_in_error",
                "real_key_in_wrong_key_error",
                "key_in_console_output",
            )
        )
        for r in results
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
