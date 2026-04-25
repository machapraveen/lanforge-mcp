"""Entry point for ``python -m lanforge_mcp`` and the ``lanforge-mcp`` console script.

Configures stderr logging in the demo-friendly format described in
``CLAUDE.md`` (one human-readable line per tool invocation, no JSON), then
hands off to the FastMCP stdio server.
"""

from __future__ import annotations

import logging
import sys

from lanforge_mcp import __version__
from lanforge_mcp.server import app


def _configure_logging() -> None:
    """Configure root and lanforge_mcp loggers to write to stderr.

    Tool-call lines emitted by :func:`lanforge_mcp.tools._log_call` already
    include their own ``[HH:MM:SS]`` prefix, so the formatter only adds the
    log level for non-tool lines (server start, request errors, etc.).
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    logging.getLogger("lanforge_mcp").setLevel(logging.INFO)
    # Quiet httpx's per-request INFO logs — we already log tool calls explicitly.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> None:
    """Run the FastMCP server over stdio.

    Banner goes to stderr so it doesn't pollute the MCP stdio framing.
    """
    _configure_logging()
    logger = logging.getLogger("lanforge_mcp")
    logger.info("lanforge-mcp v%s — starting on stdio", __version__)
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
