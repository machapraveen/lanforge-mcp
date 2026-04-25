"""Unit tests for ``LANforgeClient`` and the JSON-shape translation helpers."""

from __future__ import annotations

import httpx
import pytest

from lanforge_mcp.client import (
    LANforgeClient,
    _cx_from_raw,
    _event_from_raw,
    _normalize_severity,
    _port_from_raw,
)
from lanforge_mcp.config import Settings
from lanforge_mcp.errors import LANforgeAPIError, LANforgeConnectionError, LANforgeMockMissing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Info", "INFO"),
        ("Warning", "WARN"),
        ("ERROR", "ERR"),
        ("critical", "ERR"),
        ("notice", "INFO"),
        ("garbage", "INFO"),
        ("", "INFO"),
    ],
)
def test_normalize_severity(raw: str, expected: str) -> None:
    assert _normalize_severity(raw) == expected


def test_port_from_raw_uses_eid_when_no_name() -> None:
    p = _port_from_raw(
        "1.1.wiphy0",
        {"mac": "00:11:22:33:44:55", "ip": "10.0.0.1", "channel": 36, "link": "UP"},
    )
    assert p.name == "wiphy0"
    assert p.mac == "00:11:22:33:44:55"
    assert p.channel == 36
    assert p.link_state == "UP"


def test_port_from_raw_unknown_link_state() -> None:
    p = _port_from_raw("1.1.eth0", {"mac": "00:00:00:00:00:00", "link": "weird"})
    assert p.link_state == "UNKNOWN"


def test_event_from_raw_uses_event_when_description_missing() -> None:
    ev = _event_from_raw({"event": "Connect", "priority": "  Info", "name": "sta0000"})
    assert ev.message == "Connect"
    assert ev.severity == "INFO"
    assert ev.port == "sta0000"


def test_cx_from_raw_handles_missing_inner() -> None:
    cx = _cx_from_raw("nope", {"unrelated": {"name": "other"}})
    assert cx.name == "nope"
    assert cx.state == "Unknown"
    assert cx.bps_rx == 0


async def test_list_ports_returns_six_ports(client: LANforgeClient) -> None:
    ports = await client.list_ports()
    assert len(ports) == 6
    names = [p.name for p in ports]
    assert "eth0" in names
    assert "wiphy0" in names
    assert "sta0000" in names


async def test_get_port_detail(client: LANforgeClient) -> None:
    port = await client.get_port("wiphy0")
    assert port.name == "wiphy0"
    assert port.channel == 36
    assert port.link_state == "UP"


async def test_get_events_returns_eight(client: LANforgeClient) -> None:
    events = await client.get_events()
    assert len(events) == 8
    severities = {e.severity for e in events}
    assert severities == {"INFO", "WARN", "ERR"}


async def test_get_cx_stats_with_loss(client: LANforgeClient) -> None:
    cx = await client.get_cx_stats("cx_001")
    assert cx.state == "Running"
    assert cx.bps_rx > 0
    assert 0 < cx.pkt_loss_pct < 5


async def test_get_cx_stats_clean(client: LANforgeClient) -> None:
    cx = await client.get_cx_stats("cx_clean")
    assert cx.state == "Running"
    assert cx.pkt_loss_pct == 0


async def test_post_cli_returns_ok(client: LANforgeClient) -> None:
    body = await client.post("/cli-json/add_sta", {"shelf": 1, "resource": 1})
    assert isinstance(body, dict)
    assert body["status"] == "OK"


async def test_missing_fixture_raises_mock_missing(client: LANforgeClient) -> None:
    with pytest.raises(LANforgeMockMissing) as ei:
        await client.get("/does/not/exist")
    assert ei.value.method == "GET"
    assert ei.value.path == "/does/not/exist"


async def test_typed_helpers_post_paths(client: LANforgeClient) -> None:
    """Each typed POST helper should hit the corresponding cli-json endpoint."""
    for fn in (client.add_station, client.add_cx, client.set_cx_state):
        body = await fn({"shelf": 1, "resource": 1})
        assert isinstance(body, dict)
        assert body["status"] == "OK"


async def test_real_mode_transport_error_is_wrapped() -> None:
    """In real mode, a connection refused must surface as LANforgeConnectionError."""

    async def explode(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    settings = Settings(host="localhost", port=1, mock=False, timeout_sec=1)
    async with LANforgeClient(settings=settings) as c:
        c._http = httpx.AsyncClient(
            transport=httpx.MockTransport(explode), base_url="http://stub.local"
        )
        with pytest.raises(LANforgeConnectionError):
            await c.get("/anywhere")


async def test_real_mode_non_2xx_is_wrapped() -> None:
    """A 500 response must surface as LANforgeAPIError carrying status + body."""

    async def server_error(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    settings = Settings(host="localhost", port=8080, mock=False, timeout_sec=1)
    async with LANforgeClient(settings=settings) as c:
        c._http = httpx.AsyncClient(
            transport=httpx.MockTransport(server_error), base_url="http://stub.local"
        )
        with pytest.raises(LANforgeAPIError) as ei:
            await c.get("/explode")
        assert ei.value.status == 500
        assert "boom" in ei.value.body


async def test_client_outside_context_manager() -> None:
    c = LANforgeClient(settings=Settings(mock=True))
    with pytest.raises(RuntimeError):
        _ = c.http
