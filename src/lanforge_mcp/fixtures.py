"""Mock fixture store backing ``LANFORGE_MOCK=1``.

The store maps an HTTP request (method + path) to a recorded JSON fixture
on disk. Fixtures live alongside the test suite at ``tests/fixtures/`` and
ship inside the wheel via ``hatch.build.targets.wheel.force-include`` so
mock mode works whether the package is installed editable or via wheel.

A small synthetic latency (``MOCK_LATENCY_SEC``) is awaited on every
``get`` so async behaviour is observable in unit tests — and so the demo
log shows real timings instead of impossibly-fast responses.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from lanforge_mcp.errors import LANforgeMockMissing

MOCK_LATENCY_SEC: float = 0.01

_DEFAULT_FIXTURE_DIRS: tuple[Path, ...] = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures",
    Path(__file__).resolve().parent / "data" / "fixtures",
)


def _resolve_fixture_dir() -> Path:
    """Return the first existing fixture directory.

    We check the dev-tree path (``tests/fixtures``) first so editable
    installs work; otherwise fall back to ``data/fixtures`` packaged in the
    wheel (currently unused but reserved for future read-only shipping).

    Returns:
        The resolved fixture directory path.

    Raises:
        FileNotFoundError: If no fixture directory exists in any candidate.
    """
    for candidate in _DEFAULT_FIXTURE_DIRS:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"No fixture directory found. Looked in: {[str(p) for p in _DEFAULT_FIXTURE_DIRS]}"
    )


_CX_PATH_RE = re.compile(r"^/cx/\d+/\d+/(?P<cx_name>[\w-]+)/?$")


class FixtureStore:
    """Maps LANforge HTTP request paths to JSON fixture files.

    Read-only. Construct with a path to the fixture directory, or default
    to the in-repo fixtures shipped under ``tests/fixtures``.

    Attributes:
        fixture_dir: Directory containing the JSON fixture files.
    """

    def __init__(self, fixture_dir: Path | None = None) -> None:
        """Initialise the store.

        Args:
            fixture_dir: Directory of fixture JSON files. Defaults to the
                in-repo ``tests/fixtures`` directory.

        Raises:
            FileNotFoundError: If ``fixture_dir`` is None and no default
                directory exists.
        """
        self.fixture_dir: Path = fixture_dir if fixture_dir is not None else _resolve_fixture_dir()

    async def get(self, path: str, method: str = "GET") -> dict[str, Any] | list[Any]:
        """Resolve a request to its fixture body.

        Args:
            path: Request path, e.g. ``/ports/1/1/list``. Leading slash optional.
            method: HTTP method, defaults to ``GET``.

        Returns:
            The decoded JSON body for the fixture (dict or list).

        Raises:
            LANforgeMockMissing: If no fixture is mapped for this path/method pair.
        """
        await asyncio.sleep(MOCK_LATENCY_SEC)
        fixture_name = self._route(path, method)
        if fixture_name is None:
            raise LANforgeMockMissing(method, path)
        return self._load(fixture_name)

    def _route(self, path: str, method: str) -> str | None:
        """Map a path/method pair to a fixture filename.

        Returns:
            Fixture filename (without ``.json``) or ``None`` if unmapped.
        """
        normalized = "/" + path.lstrip("/").rstrip("/")

        if method == "POST" and normalized.startswith("/cli-json/"):
            return "cli_post_ok"

        static_get_routes: dict[str, str] = {
            "/": "server_info",
            "/resource/1/1": "resource_1_1",
            "/ports/1/1/list": "ports_list",
            "/port/1/1/wiphy0": "port_detail",
            "/events/last/100": "events",
            "/help/add_sta": "help_add_sta",
        }
        if method == "GET" and normalized in static_get_routes:
            return static_get_routes[normalized]

        if method == "GET":
            cx_match = _CX_PATH_RE.match(normalized)
            if cx_match is not None:
                cx_name = cx_match.group("cx_name")
                if cx_name == "cx_clean":
                    return "cx_clean"
                return "cx_stats"

        return None

    def _load(self, fixture_name: str) -> dict[str, Any] | list[Any]:
        """Load and decode a fixture by name.

        Args:
            fixture_name: Filename without ``.json`` suffix.

        Returns:
            Decoded JSON.

        Raises:
            FileNotFoundError: If the fixture file is missing on disk.
        """
        fixture_path = self.fixture_dir / f"{fixture_name}.json"
        with fixture_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] | list[Any] = json.load(f)
        return data
