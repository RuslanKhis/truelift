"""Launch settings for the local API (design D12, contract C16).

The launch token lives only in process memory. It is never read from or written to a file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

LOOPBACK_HOST = "127.0.0.1"
ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost"})

# Request-body caps (SB09). Uploads get their own, larger cap; G07 makes it configurable.
DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

MIN_TOKEN_LENGTH = 32

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


@dataclass(frozen=True)
class Settings:
    """Everything the app factory needs. Tests build one directly; the CLI builds one per launch."""

    port: int
    # None means "no token configured": every /api route then returns 401 (fail closed, SB01).
    launch_token: str | None = field(default=None, repr=False)
    # TRUELIFT_DEV=1 serves /docs and /openapi.json (SB07) and honours dev_origins.
    dev: bool = False
    # Extra browser origins allowed only in dev mode, e.g. the Vite dev server "http://localhost:5173".
    dev_origins: tuple[str, ...] = ()
    web_dir: Path = _WEB_DIR
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    # Seconds between replayed agent-stream events (fake stream only; tests use 0).
    fake_stream_delay_s: float = 0.04

    def __post_init__(self) -> None:
        if not 0 < self.port < 65536:
            raise ValueError("port out of range")
        if self.launch_token is not None and len(self.launch_token) < MIN_TOKEN_LENGTH:
            raise ValueError("launch token too short")

    @property
    def allowed_origins(self) -> frozenset[str]:
        origins = {f"http://{host}:{self.port}" for host in ALLOWED_HOSTNAMES}
        if self.dev:
            origins.update(o.rstrip("/") for o in self.dev_origins)
        return frozenset(origins)

    @classmethod
    def from_env(cls, *, port: int, launch_token: str | None) -> Settings:
        dev = _env_flag("TRUELIFT_DEV")
        raw = os.environ.get("TRUELIFT_DEV_ORIGINS", "")
        dev_origins = tuple(o.strip() for o in raw.split(",") if o.strip()) if dev else ()
        return cls(port=port, launch_token=launch_token, dev=dev, dev_origins=dev_origins)
