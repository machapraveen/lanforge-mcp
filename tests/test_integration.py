"""End-to-end stdio integration test against ``python -m lanforge_mcp``.

Spawns the server as a subprocess, attaches an MCP SDK client over stdio,
and exercises tools/list and tools/call. This is the test that proves the
whole stack — config, client, tools, server, schema generation —
actually works as deployed.
"""

from __future__ import annotations

import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.fixture()
def server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "lanforge_mcp"],
        env={"LANFORGE_MOCK": "1"},
    )


async def test_stdio_lists_six_tools(server_params: StdioServerParameters) -> None:
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.list_tools()
        names = {t.name for t in result.tools}
        assert names == {
            "list_ports",
            "create_stations",
            "start_l3_traffic",
            "get_test_results",
            "get_events",
            "diagnose_failure",
        }


async def test_stdio_call_list_ports(server_params: StdioServerParameters) -> None:
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("list_ports", {"resource": 1})
        assert not result.isError
        # FastMCP emits one content block per list element AND a structuredContent
        # wrapper carrying the typed list. Verify both surfaces.
        assert len(result.content) == 6
        assert result.structuredContent is not None
        ports = result.structuredContent["result"]
        assert isinstance(ports, list)
        assert len(ports) == 6
        assert any(p["name"] == "eth0" for p in ports)


async def test_stdio_dry_run_create_stations(server_params: StdioServerParameters) -> None:
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "create_stations",
            {
                "spec": {
                    "radio": "wiphy0",
                    "count": 2,
                    "ssid_prefix": "Demo",
                    "security": "wpa2",
                    "key": "secret",
                },
                "dry_run": True,
            },
        )
        assert not result.isError
        data = (
            result.structuredContent["result"]
            if result.structuredContent and "result" in result.structuredContent
            else result.structuredContent
        )
        assert data is not None
        assert data["dry_run"] is True
        assert len(data["payloads"]) == 2
        assert data["payloads"][0]["sta_name"] == "sta0000"


async def test_stdio_diagnose_failure(server_params: StdioServerParameters) -> None:
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool("diagnose_failure", {"cx_name": "cx_001"})
        assert not result.isError
        assert result.structuredContent is not None
        data = result.structuredContent
        assert "summary" in data
        assert "packet loss" in data["summary"].lower()
