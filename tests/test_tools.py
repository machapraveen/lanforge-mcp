"""Behaviour tests for the six MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from lanforge_mcp import tools
from lanforge_mcp.client import LANforgeClient
from lanforge_mcp.models import CreateStationSpec, StartTrafficSpec


async def test_list_ports_returns_six(client: LANforgeClient) -> None:
    ports = await tools.list_ports(client=client)
    assert len(ports) == 6


async def test_create_stations_dry_run_makes_no_http(client: LANforgeClient) -> None:
    spy_post = AsyncMock()
    client.add_station = spy_post  # type: ignore[method-assign]
    spec = CreateStationSpec(
        radio="wiphy0", count=4, ssid_prefix="Candela-Test", security="wpa2", key="secret"
    )
    out = await tools.create_stations(spec, dry_run=True, client=client)
    assert out["dry_run"] is True
    assert len(out["payloads"]) == 4
    assert out["payloads"][0]["sta_name"] == "sta0000"
    assert out["payloads"][3]["sta_name"] == "sta0003"
    assert "Candela-Test" in out["preview"]
    spy_post.assert_not_awaited()


async def test_create_stations_wet_posts_each_station(client: LANforgeClient) -> None:
    spy_post = AsyncMock(return_value={"status": "OK"})
    client.add_station = spy_post  # type: ignore[method-assign]
    spec = CreateStationSpec(radio="wiphy0", count=3, ssid_prefix="X", security="open")
    out = await tools.create_stations(spec, dry_run=False, client=client)
    assert out["dry_run"] is False
    assert len(out["results"]) == 3
    assert spy_post.await_count == 3


async def test_create_stations_payload_uses_safe_flag_defaults() -> None:
    """Until LANforge flag-bit values are verified, every payload sends flags=0
    and flags_mask=0 (do-not-modify-any-bits) so the demo preview stays clean."""
    spec_open = CreateStationSpec(radio="wiphy0", count=1, ssid_prefix="X", security="open")
    spec_wpa2 = CreateStationSpec(
        radio="wiphy0", count=1, ssid_prefix="X", security="wpa2", key="k"
    )
    p_open = tools._build_add_sta_payload(spec_open, 0)
    p_wpa2 = tools._build_add_sta_payload(spec_wpa2, 0)
    for payload in (p_open, p_wpa2):
        assert payload["flags"] == 0
        assert payload["flags_mask"] == 0
    assert p_open["key"] == "[BLANK]"
    assert p_wpa2["key"] == "k"


async def test_start_l3_traffic_dry_run(client: LANforgeClient) -> None:
    spy_post = AsyncMock()
    client.post = spy_post  # type: ignore[method-assign]
    spec = StartTrafficSpec(
        endpoint_a="sta0000",
        endpoint_b="eth1",
        bps_min=10_000_000,
        bps_max=50_000_000,
        duration_sec=60,
        protocol="lf_udp",
        cx_name="cx_test",
    )
    out = await tools.start_l3_traffic(spec, dry_run=True, client=client)
    assert out["dry_run"] is True
    paths = [p["path"] for p in out["payloads"]]
    assert paths == [
        "/cli-json/add_endp",
        "/cli-json/add_endp",
        "/cli-json/add_cx",
        "/cli-json/set_cx_state",
    ]
    assert "10-50 Mbps" in out["preview"]
    spy_post.assert_not_awaited()


async def test_start_l3_traffic_wet_runs_four_steps(client: LANforgeClient) -> None:
    spy_post = AsyncMock(return_value={"status": "OK"})
    client.post = spy_post  # type: ignore[method-assign]
    spec = StartTrafficSpec(
        endpoint_a="a",
        endpoint_b="b",
        bps_min=1000,
        bps_max=2000,
        duration_sec=1,
        protocol="udp",
        cx_name="cxw",
    )
    out = await tools.start_l3_traffic(spec, dry_run=False, client=client)
    assert out["dry_run"] is False
    assert spy_post.await_count == 4


async def test_get_test_results(client: LANforgeClient) -> None:
    cx = await tools.get_test_results("cx_001", client=client)
    assert cx.state == "Running"
    assert cx.pkt_loss_pct > 0


async def test_get_events_filtering(client: LANforgeClient) -> None:
    info = await tools.get_events(limit=50, min_severity="INFO", client=client)
    warn = await tools.get_events(limit=50, min_severity="WARN", client=client)
    err = await tools.get_events(limit=50, min_severity="ERR", client=client)
    assert len(info) >= len(warn) >= len(err)
    assert all(e.severity in {"WARN", "ERR"} for e in warn)
    assert all(e.severity == "ERR" for e in err)


async def test_get_events_unknown_severity_falls_back(client: LANforgeClient) -> None:
    out = await tools.get_events(limit=10, min_severity="bogus", client=client)
    assert len(out) > 0  # bogus -> threshold 0 -> all events kept


async def test_diagnose_failure_with_loss(client: LANforgeClient) -> None:
    report = await tools.diagnose_failure("cx_001", client=client)
    assert report.cx_stats.pkt_loss_pct > 1
    summary_l = report.summary.lower()
    assert "packet loss" in summary_l
    assert "warn" in summary_l or "err" in summary_l
    assert "rf interference" in summary_l or "weak signal" in summary_l


async def test_diagnose_failure_clean_loss_phrase(client: LANforgeClient) -> None:
    report = await tools.diagnose_failure("cx_clean", client=client)
    assert report.cx_stats.pkt_loss_pct == 0
    assert "loss-free" in report.summary.lower()


@pytest.mark.parametrize(
    ("loss_pct", "expected_phrase"),
    [
        (0.0, "loss-free"),
        (0.3, "minor packet loss"),
        (2.5, "moderate packet loss"),
        (12.0, "high packet loss"),
    ],
)
def test_summarize_loss_thresholds(loss_pct: float, expected_phrase: str) -> None:
    from lanforge_mcp.models import CXStats

    cx = CXStats(name="t", state="Running", pkt_loss_pct=loss_pct)
    summary = tools._summarize(cx, [], [], "t")
    assert expected_phrase in summary.lower()


def test_traffic_preview_uses_bps_when_below_mbps_threshold() -> None:
    spec = StartTrafficSpec(
        endpoint_a="a",
        endpoint_b="b",
        bps_min=500,
        bps_max=999,
        duration_sec=1,
        protocol="udp",
        cx_name="x",
    )
    payloads = tools._build_traffic_payloads(spec)
    assert payloads[0]["body"]["min_rate"] == 500
