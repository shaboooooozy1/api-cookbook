"""Command-line entry point.

Usage:
    semantic-scholar-mcp                      # stdio transport (default)
    semantic-scholar-mcp --transport http     # streamable HTTP on :8000
    semantic-scholar-mcp --transport http --port 9000
"""

from __future__ import annotations

import argparse
import sys

from . import client
from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="semantic-scholar-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="Transport to run. 'stdio' (default) for local use; 'http' for streamable HTTP.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port when --transport=http (default 8000).",
    )
    args = parser.parse_args()

    client.log_startup_mode()

    if args.transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
