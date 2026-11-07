"""The ``truelift`` command: start the local server and open the browser (design D11, D12).

It binds 127.0.0.1 only, on a free port chosen by the OS unless ``--port`` is given, makes a new
token for this launch, and opens ``http://127.0.0.1:<port>/#token=<token>``. The token travels
only in the URL fragment, which browsers never send to the server; the SPA moves it to
``sessionStorage`` and sends it as ``Authorization: Bearer``. ADK's own server is never started.
"""

from __future__ import annotations

import argparse
import socket
import webbrowser

from truelift import __version__
from truelift.api.auth import new_launch_token
from truelift.api.settings import LOOPBACK_HOST, Settings


def launch_url(port: int, token: str, host: str = LOOPBACK_HOST) -> str:
    return f"http://{host}:{port}/#token={token}"


def bind_loopback(port: int) -> socket.socket:
    """Bind before the server starts, so the chosen port cannot be taken in between."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LOOPBACK_HOST, port))
    sock.listen(128)
    return sock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="truelift", description="Measure discount ROI on your own machine.")
    parser.add_argument("--version", action="version", version=f"truelift {__version__}")
    parser.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: a free one)")
    parser.add_argument("--no-browser", action="store_true", help="print the link instead of opening it")
    return parser


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    from truelift.api.app import create_app

    args = build_parser().parse_args(argv)
    sock = bind_loopback(args.port)
    port = sock.getsockname()[1]
    token = new_launch_token()
    settings = Settings.from_env(port=port, launch_token=token)
    app = create_app(settings)

    url = launch_url(port, token)
    print(f"truelift is running. Open this link in your browser:\n\n  {url}\n")
    for origin in settings.dev_origins:
        print(f"  dev: {origin}/#token={token}")
    print("Keep this window open. Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)

    config = uvicorn.Config(
        app,
        log_level="info",
        proxy_headers=False,
        server_header=False,
        date_header=False,
        ws="none",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
