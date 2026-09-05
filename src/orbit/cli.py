"""CLI entry point for running ORBIT Desktop Assistant server."""

from __future__ import annotations

import argparse
import sys
import uvicorn

from orbit.gateway.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="ORBIT Desktop Assistant Gateway Server")
    parser.add_argument("--host", default="127.0.0.1", help="Binding interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--log-level", default="info", help="Log level (default: info)")
    args = parser.parse_args()

    # Enforce loopback safety check
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"WARNING: Binding to non-loopback host {args.host} is discouraged for security.")

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
