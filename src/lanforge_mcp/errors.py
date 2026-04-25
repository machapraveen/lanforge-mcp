"""Domain-specific exceptions raised by the lanforge-mcp client and tools.

All exceptions inherit from :class:`LANforgeError` so callers can catch a
single base type when they don't care to distinguish failure modes.
"""

from __future__ import annotations


class LANforgeError(Exception):
    """Base class for every exception raised by lanforge-mcp."""


class LANforgeConnectionError(LANforgeError):
    """Raised when the underlying HTTP transport fails (DNS, refused, timeout)."""


class LANforgeAPIError(LANforgeError):
    """Raised when LANforge returns a non-2xx response.

    Attributes:
        status: HTTP status code returned by LANforge.
        body: Response body (as string), truncated by the caller if needed.
    """

    def __init__(self, status: int, body: str) -> None:
        """Initialise with status and body for downstream introspection.

        Args:
            status: HTTP status code.
            body: Response body for diagnostic context.
        """
        super().__init__(f"LANforge API returned HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


class LANforgeMockMissing(LANforgeError):  # noqa: N818  # Name fixed by CLAUDE.md spec.
    """Raised when a request hits a path with no mock fixture mapped.

    Attributes:
        path: Request path that had no fixture mapped.
        method: HTTP method (``GET``, ``POST``, ...).
    """

    def __init__(self, method: str, path: str) -> None:
        """Initialise with the unmapped method/path pair.

        Args:
            method: HTTP method.
            path: Request path.
        """
        super().__init__(
            f"No mock fixture mapped for {method} {path}. "
            "Add a fixture in tests/fixtures/ and register it in fixtures.FixtureStore."
        )
        self.method = method
        self.path = path
