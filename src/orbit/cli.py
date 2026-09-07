"""CLI entry point for running ORBIT Desktop Assistant server."""

from __future__ import annotations

import argparse
import sys
import uvicorn

from orbit.config import RuntimeConfig
from orbit.contracts.capabilities import AdapterMode
from orbit.gateway.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="ORBIT Desktop Assistant Gateway Server")
    parser.add_argument("--host", default="127.0.0.1", help="Binding interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--log-level", default="info", help="Log level (default: info)")
    parser.add_argument("--mode", default=None, choices=["MOCK", "PRODUCTION"], help="Adapter execution mode (MOCK or PRODUCTION)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")
    args = parser.parse_args()

    # Enforce loopback safety check
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"WARNING: Binding to non-loopback host {args.host} is discouraged for security.")

    cfg = RuntimeConfig.from_env()
    if args.mode:
        cfg.adapter_mode = AdapterMode(args.mode)
    cfg.host = args.host
    cfg.port = args.port
    cfg.log_level = args.log_level

    if args.reload:
        uvicorn.run("orbit.gateway.app:create_app", host=args.host, port=args.port, log_level=args.log_level, factory=True, reload=True)
    else:
        app = create_app(config=cfg)
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
