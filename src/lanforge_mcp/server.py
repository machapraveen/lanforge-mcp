"""FastMCP wiring: tools, resources, and prompt templates.

This module is the LLM's entrypoint into lanforge-mcp. The decorator
docstrings below are what the LLM sees at tool-selection time — read
``CLAUDE.md`` before tweaking them.

A single :class:`LANforgeClient` is opened in the FastMCP lifespan and
shared across tool invocations. That keeps connection pooling sane in
real mode and avoids re-loading the fixture index on every call in mock
mode.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from lanforge_mcp import tools as tool_impls
from lanforge_mcp.client import LANforgeClient
from lanforge_mcp.config import Settings
from lanforge_mcp.models import (
    CreateStationSpec,
    CXStats,
    DiagnosticReport,
    Event,
    Port,
    StartTrafficSpec,
)

logger = logging.getLogger("lanforge_mcp")

_CLI_REFERENCE_PATH = Path(__file__).resolve().parent / "data" / "cli_reference.md"


@dataclass
class AppContext:
    """Lifespan-shared resources passed to every tool invocation.

    Attributes:
        client: Open async LANforge client.
        settings: Current runtime settings.
    """

    client: LANforgeClient
    settings: Settings


@asynccontextmanager
async def _lifespan(_: FastMCP[Any]) -> AsyncIterator[AppContext]:
    """Open one :class:`LANforgeClient` for the lifetime of the server.

    Args:
        _: The FastMCP app (unused — kept to satisfy the SDK signature).

    Yields:
        An :class:`AppContext` with the open client and active settings.
    """
    settings = Settings.from_env()
    logger.info(
        "lanforge-mcp starting (host=%s port=%d mock=%s timeout=%ds)",
        settings.host,
        settings.port,
        settings.mock,
        settings.timeout_sec,
    )
    async with LANforgeClient(settings) as client:
        yield AppContext(client=client, settings=settings)
    logger.info("lanforge-mcp shutting down")


app: FastMCP[AppContext] = FastMCP("lanforge-mcp", lifespan=_lifespan)


def _client() -> LANforgeClient:
    """Return the lifespan-managed client.

    Returns:
        The :class:`LANforgeClient` opened by ``_lifespan``.

    Raises:
        RuntimeError: If invoked outside of a request lifecycle.
    """
    ctx = app.get_context()
    return ctx.request_context.lifespan_context.client


# ---- Tools ----------------------------------------------------------------


@app.tool()
async def list_ports(resource: int = 1) -> list[Port]:
    """List every port on a LANforge resource.

    Read-only. Use this to discover which radios (``wiphy0``, ``wiphy1``)
    and stations (``sta0000``...) currently exist before creating new ones
    or starting traffic.

    Example: ``list_ports(resource=1)`` returns physical NICs, Wi-Fi
    radios, and any virtual stations on resource 1.

    Args:
        resource: Resource id (default 1; single-box installs only have 1).

    Returns:
        List of Port objects with name, mac, ip, radio, link_state, bps_rx, bps_tx.
    """
    return await tool_impls.list_ports(resource, client=_client())


@app.tool()
async def create_stations(spec: CreateStationSpec, dry_run: bool = True) -> dict[str, Any]:
    """Create N virtual Wi-Fi stations on a radio (``add_sta`` per station).

    Defaults to dry_run=True - LLM must explicitly set dry_run=False to execute.
    On dry runs returns the exact CLI-JSON payloads plus a human-readable preview;
    no HTTP traffic is generated.

    Example: ``create_stations(spec={'radio': 'wiphy0', 'count': 4,
    'ssid_prefix': 'Candela-Test', 'security': 'wpa2', 'key': 'secret'},
    dry_run=True)`` returns four payloads naming sta0000..sta0003.

    Args:
        spec: Batch spec — radio, count (1-200), ssid_prefix, security
            (open/wpa/wpa2/wpa3), key, optional resource and shelf.
        dry_run: Default True. False executes against the box.

    Returns:
        Dict with keys ``dry_run``, ``payloads``, ``preview``, and (when
        ``dry_run=False``) ``results`` containing one POST response per
        station.
    """
    return await tool_impls.create_stations(spec, dry_run=dry_run, client=_client())


@app.tool()
async def start_l3_traffic(spec: StartTrafficSpec, dry_run: bool = True) -> dict[str, Any]:
    """Start a Layer-3 cross-connect (traffic flow) between two endpoints.

    Defaults to dry_run=True - LLM must explicitly set dry_run=False to execute.
    On dry runs returns the exact CLI-JSON payloads (add_endp x2, add_cx,
    set_cx_state RUNNING) plus a human-readable preview; no HTTP traffic.

    Example: ``start_l3_traffic(spec={'endpoint_a': 'sta0000',
    'endpoint_b': 'eth1', 'bps_min': 10000000, 'bps_max': 50000000,
    'duration_sec': 60, 'protocol': 'lf_udp', 'cx_name': 'cx_uplink'},
    dry_run=True)`` previews a 10-50 Mbps UDP CX named cx_uplink.

    Args:
        spec: Traffic spec — endpoint_a, endpoint_b, bps_min, bps_max,
            duration_sec, protocol (udp/tcp/lf_udp/lf_tcp), cx_name.
        dry_run: Default True. False executes against the box.

    Returns:
        Dict with keys ``dry_run``, ``payloads``, ``preview``, and (when
        ``dry_run=False``) ``results`` containing one POST response per step.
    """
    return await tool_impls.start_l3_traffic(spec, dry_run=dry_run, client=_client())


@app.tool()
async def get_test_results(cx_name: str) -> CXStats:
    """Fetch current statistics for a Layer-3 cross-connect.

    Read-only. Returns throughput, latency, and packet loss for the named CX.
    Pair with ``diagnose_failure`` if the numbers look bad.

    Example: ``get_test_results(cx_name='cx_001')`` returns the CXStats with
    bps_rx/bps_tx, latency_ms, pkt_loss_pct, dropped, state.

    Args:
        cx_name: Cross-connect name.

    Returns:
        A CXStats snapshot.
    """
    return await tool_impls.get_test_results(cx_name, client=_client())


@app.tool()
async def get_events(limit: int = 50, min_severity: str = "INFO") -> list[Event]:
    """Fetch the last N LANforge events, optionally filtered by severity.

    Read-only. Severity is one of ``INFO``, ``WARN``, ``ERR``;
    ``min_severity='WARN'`` drops INFO entries.

    Example: ``get_events(limit=20, min_severity='WARN')`` returns the
    most recent 20 WARN-or-worse events.

    Args:
        limit: Max events to return after filtering (1-500).
        min_severity: Drop events below this severity (INFO/WARN/ERR).

    Returns:
        Filtered list of Event objects with timestamp, severity, message, port.
    """
    return await tool_impls.get_events(limit=limit, min_severity=min_severity, client=_client())


@app.tool()
async def diagnose_failure(cx_name: str, resource: int = 1) -> DiagnosticReport:
    """Composite read-only diagnostic for a failing cross-connect.

    Concurrently fetches CX stats, the last 100 events, and the full port
    list for the resource, then assembles a DiagnosticReport with a
    rule-based ``summary`` field that calls out high packet loss,
    elevated WARN/ERR counts, beacon-loss/auth/disconnect patterns, and
    stations with NO-LINK.

    No LLM calls — the summary is pattern-matched. The LLM you're
    talking to right now uses the structured fields (cx_stats,
    recent_events, port_state) to build its own narrative; ``summary`` is
    a fallback hint for clients without an LLM.

    Example: ``diagnose_failure(cx_name='cx_001')`` for a CX with 12% loss
    alongside three beacon-loss WARN events returns a summary like
    "cx_001: CX has high packet loss (12.0%); 3 WARN event(s); suspect RF
    interference or weak signal."

    Args:
        cx_name: Cross-connect to diagnose.
        resource: Resource id (default 1).

    Returns:
        A DiagnosticReport with cx_stats, recent_events, port_state,
        radio_info, and summary.
    """
    return await tool_impls.diagnose_failure(cx_name, resource=resource, client=_client())


# ---- Resources ------------------------------------------------------------


@app.resource("lanforge://docs/cli-reference", mime_type="text/markdown")
def cli_reference() -> str:
    """Curated markdown reference of the most-used LANforge CLI commands.

    Returns:
        The contents of ``data/cli_reference.md``.
    """
    return _CLI_REFERENCE_PATH.read_text(encoding="utf-8")


@app.resource(
    "lanforge://port/{resource}/{port}",
    mime_type="application/json",
)
async def port_detail(resource: str, port: str) -> str:
    """Live detail for a single LANforge port (mock-safe in dev).

    Args:
        resource: Resource id as a string (FastMCP treats URI segments as str).
        port: Port name (``wiphy0``, ``sta0000``, ``eth0``, ...).

    Returns:
        JSON-serialised :class:`Port`.
    """
    try:
        resource_int = int(resource)
    except ValueError:
        resource_int = 1
    obj = await _client().get_port(port, resource=resource_int)
    return obj.model_dump_json(indent=2)


# ---- Prompts --------------------------------------------------------------


@app.prompt()
def run_wifi_capacity_test(ssid: str, station_count: int = 10, duration_sec: int = 60) -> str:
    """Templated test plan for an end-to-end Wi-Fi capacity run.

    The LLM expands this into a concrete sequence of tool calls
    (``list_ports`` → ``create_stations`` → ``start_l3_traffic`` →
    ``get_test_results`` → ``diagnose_failure``).

    Args:
        ssid: SSID the stations should join.
        station_count: How many virtual stations to create.
        duration_sec: How long to run UDP traffic.

    Returns:
        A prompt template for the LLM to execute.
    """
    return (
        f"Run a Wi-Fi capacity test on the LANforge connected via lanforge-mcp:\n"
        f"\n"
        f"1. Call list_ports() to confirm wiphy0 (or whichever radio is on resource 1) is up.\n"
        f"2. Call create_stations(spec={{radio: 'wiphy0', count: {station_count}, "
        f"ssid_prefix: '{ssid}', security: 'wpa2', key: '<key>'}}, dry_run=False).\n"
        f"3. Call start_l3_traffic(spec={{endpoint_a: 'sta0000', endpoint_b: 'eth1', "
        f"bps_min: 10000000, bps_max: 100000000, duration_sec: {duration_sec}, "
        f"protocol: 'lf_udp', cx_name: 'cx_capacity'}}, dry_run=False).\n"
        f"4. After {duration_sec}s, call get_test_results(cx_name='cx_capacity').\n"
        f"5. Call diagnose_failure(cx_name='cx_capacity') for a rule-based "
        f"loss/event summary alongside the raw stats.\n"
        f"\n"
        f"Report aggregate Mbps, average RTT, packet loss percent, and any "
        f"WARN/ERR events. Suggest a TR-398 issue 4 pass/fail verdict at "
        f"{station_count} clients on '{ssid}'."
    )
