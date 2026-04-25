"""Shared pytest fixtures for the lanforge-mcp test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from lanforge_mcp.client import LANforgeClient
from lanforge_mcp.config import Settings
from lanforge_mcp.fixtures import FixtureStore

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def settings() -> Settings:
    """Mock-mode settings with the in-repo fixture dir."""
    return Settings(host="localhost", port=8080, mock=True, timeout_sec=5)


@pytest.fixture()
def store() -> FixtureStore:
    """Fresh FixtureStore pointing at tests/fixtures."""
    return FixtureStore(fixture_dir=FIXTURE_DIR)


@pytest_asyncio.fixture()
async def client(settings: Settings, store: FixtureStore) -> AsyncIterator[LANforgeClient]:
    """Open async LANforge client in mock mode for the duration of a test."""
    async with LANforgeClient(settings=settings, store=store) as c:
        yield c
