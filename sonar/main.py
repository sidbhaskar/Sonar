"""Sonar -- Terminal-native distributed trace visualizer.

Entry point for the application. Runs the FastAPI ingestion server
(HTTP + gRPC) in background threads and the Textual TUI on the main thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading


def _run_http_server_thread() -> None:
    """Run the uvicorn HTTP server in a dedicated thread with its own event loop.

    Textual owns the main thread's event loop (it needs direct terminal
    control), so the FastAPI ingestion server runs in a daemon thread.
    Using a daemon thread ensures the server dies when the main process
    exits — no orphaned listeners.
    """
    import uvicorn
    from sonar.ingestion.server import app

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=4318,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Create a fresh event loop for this thread.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())


def _run_grpc_server_thread() -> None:
    """Run the gRPC OTLP server in a dedicated daemon thread.

    Listens on port 4317 (the standard OTLP gRPC port).
    """
    try:
        from sonar.ingestion.grpc_server import serve_grpc
        serve_grpc(port=4317)
    except Exception:
        logging.getLogger(__name__).warning(
            "gRPC server failed to start (grpcio may not be installed). "
            "OTLP/gRPC ingestion on port 4317 is unavailable.",
            exc_info=True,
        )


def main() -> None:
    """Launch Sonar: ingestion servers (background) + TUI (foreground).

    The server threads are daemons so they auto-terminate when the TUI
    exits and the main process shuts down.
    """
    # Configure logging (only visible in log files, not the TUI).
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Share the same trace store between servers and UI.
    from sonar.ingestion.server import trace_store

    # Start the HTTP ingestion server in a daemon thread.
    http_thread = threading.Thread(
        target=_run_http_server_thread,
        name="sonar-http-ingestion",
        daemon=True,
    )
    http_thread.start()

    # Start the gRPC ingestion server in a daemon thread.
    grpc_thread = threading.Thread(
        target=_run_grpc_server_thread,
        name="sonar-grpc-ingestion",
        daemon=True,
    )
    grpc_thread.start()

    # Run the Textual TUI on the main thread (it needs terminal control).
    from sonar.ui.app import SonarApp

    app = SonarApp(trace_store=trace_store)
    app.run()


if __name__ == "__main__":
    main()
