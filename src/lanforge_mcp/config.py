"""Runtime configuration parsed from environment variables.

All defaults match the developer-friendly mock-mode workflow described in
``CLAUDE.md``: localhost LANforge, mock transport on, ten-second timeout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable.

    Truthy values: ``1``, ``true``, ``yes``, ``on`` (case-insensitive).
    Falsy values: ``0``, ``false``, ``no``, ``off``. Anything else falls back
    to ``default``.

    Args:
        name: Environment variable name.
        default: Value returned if the variable is unset or unparseable.

    Returns:
        The parsed boolean.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable, falling back on parse error.

    Args:
        name: Environment variable name.
        default: Value returned if the variable is unset or unparseable.

    Returns:
        The parsed integer.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Server configuration sourced from environment variables.

    Attributes:
        host: LANforge GUI host (default ``localhost``).
        port: LANforge HTTP port (default ``8080``).
        mock: When True, route all HTTP through the fixture loader. Default True.
        timeout_sec: Per-request HTTP timeout in seconds (default ``10``).
    """

    host: str = "localhost"
    port: int = 8080
    mock: bool = True
    timeout_sec: int = 10

    @classmethod
    def from_env(cls) -> Settings:
        """Construct Settings from ``LANFORGE_*`` environment variables.

        Returns:
            A populated, immutable :class:`Settings` instance.
        """
        return cls(
            host=os.environ.get("LANFORGE_HOST", "localhost"),
            port=_env_int("LANFORGE_PORT", 8080),
            mock=_env_bool("LANFORGE_MOCK", True),
            timeout_sec=_env_int("LANFORGE_TIMEOUT_SEC", 10),
        )

    @property
    def base_url(self) -> str:
        """The HTTP base URL for the configured LANforge instance."""
        return f"http://{self.host}:{self.port}"
