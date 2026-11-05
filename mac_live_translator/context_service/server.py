"""Localhost-only HTTP server runner for the FastAPI Context Service."""

from __future__ import annotations

import sys
import uvicorn
from mac_live_translator.context_service.api import create_app
from mac_live_translator.context_service.engine import ContextEngine

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, engine: ContextEngine | None = None) -> None:
    """Run uvicorn server binding strictly to 127.0.0.1."""
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Context Service is strictly restricted to 127.0.0.1 for privacy.")
    app = create_app(engine)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    run_server(port=port)
