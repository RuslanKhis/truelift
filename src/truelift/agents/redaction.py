"""Log redaction: no key reaches a log record (C7, SB14; G11/A1).

``install()`` wraps the logging record factory, so every record from every logger (ours, ADK,
google-genai, LiteLLM, httpx, uvicorn) is scrubbed when it is created, before any handler or
filter sees it. The message is formatted, keys are replaced with ``[redacted]``, and exception and
stack text is formatted and scrubbed the same way; the live exception object is dropped from the
record, so a later formatter cannot print the original text.

Two kinds of key are removed: every key the key store has handed out in this process (exact
match), and anything shaped like a Google, Anthropic or OpenAI key (the guard's patterns, C13).
"""

from __future__ import annotations

import logging
import re
import threading
import traceback
from typing import Any

REDACTED = "[redacted]"
_EDGE = r"(?<![0-9A-Za-z_.-])"
# Same shapes as scripts/guard_public.py and .gitleaks.toml. Keep the three in step.
KEY_PATTERNS = (
    re.compile(_EDGE + r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(_EDGE + r"AQ\.[0-9A-Za-z_-]{20,}"),
    re.compile(_EDGE + r"sk-ant-[0-9A-Za-z_-]{20,}"),
    re.compile(_EDGE + r"sk-(?:proj-)?[0-9A-Za-z_-]{20,}"),
)
# Keys shorter than this are never registered: replacing short strings would mangle logs.
_MIN_SECRET = 8


class Redactor:
    def __init__(self) -> None:
        self._secrets: set[str] = set()
        self._lock = threading.Lock()

    def register(self, secret: str) -> None:
        if len(secret) >= _MIN_SECRET:
            with self._lock:
                self._secrets.add(secret)

    def redact(self, text: str) -> str:
        with self._lock:
            secrets = sorted(self._secrets, key=len, reverse=True)
        for secret in secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        for pattern in KEY_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text


REDACTOR = Redactor()


def scrub_record(record: logging.LogRecord, redactor: Redactor = REDACTOR) -> logging.LogRecord:
    try:
        message = record.getMessage()
    except Exception:  # a bad format string must not lose the record or leak its args
        message = str(record.msg)
    record.msg = redactor.redact(message)
    record.args = None
    if record.exc_info:
        text = "".join(traceback.format_exception(*record.exc_info))
        record.exc_text = redactor.redact(text.rstrip("\n"))
        record.exc_info = None
    elif record.exc_text:
        record.exc_text = redactor.redact(record.exc_text)
    if record.stack_info:
        record.stack_info = redactor.redact(record.stack_info)
    return record


_installed = False
_install_lock = threading.Lock()


def install() -> None:
    """Scrub every log record of this process from now on. Idempotent."""
    global _installed
    with _install_lock:
        if _installed:
            return
        previous = logging.getLogRecordFactory()

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            return scrub_record(previous(*args, **kwargs))

        logging.setLogRecordFactory(factory)
        _installed = True
