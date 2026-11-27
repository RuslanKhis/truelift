"""The ``truelift`` command: start the local server and open the browser (design D11, D12).

It binds 127.0.0.1 only, on a free port chosen by the OS unless ``--port`` is given, makes a new
token for this launch, and opens ``http://127.0.0.1:<port>/#token=<token>``. The token travels
only in the URL fragment, which browsers never send to the server; the SPA moves it to
``sessionStorage`` and sends it as ``Authorization: Bearer``. ADK's own server is never started.

Two headless commands use the same project folders and ``state.db`` without a server (G09):

* ``truelift sample-project --name demo --seed 1`` writes a project on the synthetic market with
  a scripted, confirmed DAG and mapping;
* ``truelift run --project demo --dag v1 --profile quick`` runs the pipeline through the same run
  gate and worker as the app, prints the phases and exits 0 only when the run succeeded (C14).
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


def _version_number(text: str) -> int:
    value = text.removeprefix("v")
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError("expected a version such as v1")
    return int(value)


def build_run_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="truelift run", description="Run the analysis without the browser.")
    parser.add_argument("--project", required=True, help="project ID, for example demo")
    parser.add_argument("--dag", type=_version_number, required=True, help="confirmed DAG version, e.g. v1")
    parser.add_argument("--profile", choices=["quick", "standard"], default="quick")
    return parser


def build_sample_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="truelift sample-project",
        description="Create a project on the synthetic market with a scripted DAG and mapping.",
    )
    parser.add_argument("--name", default="demo")
    parser.add_argument("--seed", type=int, default=1)
    return parser


def _headless_store():  # type: ignore[no-untyped-def]
    from truelift.store import ProjectStore
    from truelift.store.db import StateDb

    settings = Settings.from_env(port=1, launch_token=None)
    return ProjectStore(
        settings.projects_dir,
        StateDb(settings.state_dir / "state.db", busy_timeout_s=settings.db_busy_timeout_s),
    )


def sample_project_main(argv: list[str]) -> int:
    from truelift.store import StoreError
    from truelift.worker.scripted import create_scripted_project

    args = build_sample_parser().parse_args(argv)
    store = _headless_store()
    try:
        project_id, true_roi = create_scripted_project(store, args.name, args.seed)
    except StoreError as exc:
        print(f"Could not create the project: {exc}")
        return 1
    print(f"Created project {project_id} (synthetic seed {args.seed}, true ROI {true_roi:.2f}).")
    print(f"Run it with: truelift run --project {project_id} --dag v1 --profile quick")
    return 0


def run_main(argv: list[str]) -> int:
    import time

    from truelift.store import StoreError
    from truelift.worker.gate import GateRefused
    from truelift.worker.manager import RunActive, RunManager

    args = build_run_parser().parse_args(argv)
    manager = RunManager(_headless_store())
    manager.reconcile()
    try:
        row = manager.start(args.project, args.dag, args.profile)
    except (GateRefused, RunActive, StoreError) as exc:
        print(f"The run did not start: {exc}")
        return 1
    print(f"Run {row.id} started ({args.profile}). Press Ctrl+C to cancel.", flush=True)
    seen: str | None = None
    try:
        while (current := manager.get(row.id)) is not None and current.status in ("queued", "running"):
            view = manager.view(current)
            if view.phase and view.phase != seen:
                seen = view.phase
                print(f"  {view.elapsed_s:6.0f} s  {view.phase}", flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        manager.cancel(row.id)
    final = manager.wait(row.id)
    assert final is not None
    view = manager.view(final)
    print(f"Run {final.id}: {final.status} after {view.elapsed_s:.0f} s.")
    if final.reason:
        print(final.reason)
    print(f"Run folder: {manager.folder(final).root}")
    return 0 if final.status == "succeeded" and manager.succeeded(final) else 1


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        return run_main(argv[1:])
    if argv[:1] == ["sample-project"]:
        return sample_project_main(argv[1:])
    return serve_main(argv)


def serve_main(argv: list[str]) -> int:
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
