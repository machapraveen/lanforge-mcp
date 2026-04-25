"""Pydantic v2 schemas for LANforge entities and MCP tool inputs.

Output schemas (``Port``, ``Event``, ``CXStats``, ``DiagnosticReport``) are
trimmed projections of the LANforge JSON API: only the fields the LLM
actually needs at tool-selection time. We deliberately do not surface every
column LANforge ships in ``/ports/.../list`` — fewer fields keep the LLM's
context lean.

Input schemas (``ListPortsInput``, ``CreateStationsInput``, ...) are the
JSON shapes MCP exposes to the LLM. Their docstrings become tool
descriptions; their field descriptions become parameter descriptions. Write
them for the LLM, not for humans.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["INFO", "WARN", "ERR"]
Security = Literal["open", "wpa", "wpa2", "wpa3"]
Protocol = Literal["udp", "tcp", "lf_udp", "lf_tcp"]


class Port(BaseModel):
    """A LANforge port: physical NIC, radio, or virtual station.

    Field meanings track the public LANforge JSON cookbook. Source:
    https://www.candelatech.com/cookbook.php?vol=cli&book=JSON__Querying_the_LANforge_Client_for_JSON_Data
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(description="Port name, e.g. 'wiphy0' or 'sta0000'.")
    mac: str = Field(description="MAC address, e.g. '00:0e:8e:aa:bb:01'.")
    ip: str = Field(default="0.0.0.0", description="IPv4 address; '0.0.0.0' if unassigned.")
    alias: str = Field(default="", description="User-supplied alias, often empty.")
    radio: str = Field(default="", description="Parent radio (e.g. 'wiphy0') for stations.")
    channel: int = Field(default=0, description="Wi-Fi channel; 0 if not applicable.")
    bps_rx: int = Field(default=0, description="Current RX bits/sec.")
    bps_tx: int = Field(default=0, description="Current TX bits/sec.")
    link_state: str = Field(default="UNKNOWN", description="UP, DOWN, or NO-LINK.")


class Event(BaseModel):
    """A LANforge event log entry."""

    model_config = ConfigDict(extra="ignore")

    timestamp: str = Field(description="ISO-8601 or LANforge native timestamp string.")
    severity: Severity = Field(description="One of INFO, WARN, ERR.")
    message: str = Field(description="Human-readable event message.")
    resource: int = Field(default=1, description="Resource id; 1 on a single-box install.")
    port: str = Field(default="", description="Port name if event is port-scoped, else empty.")


class CXStats(BaseModel):
    """Current statistics for a Layer-3 cross-connect (traffic flow)."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Cross-connect name.")
    state: str = Field(description="Run state: 'Running', 'Stopped', 'Quiesce', etc.")
    bps_rx: int = Field(default=0, description="Current RX bits/sec across both endpoints.")
    bps_tx: int = Field(default=0, description="Current TX bits/sec across both endpoints.")
    latency_ms: float = Field(default=0.0, description="Latest reported one-way latency (ms).")
    pkt_loss_pct: float = Field(default=0.0, description="Packet-loss percentage, 0-100.")
    dropped: int = Field(default=0, description="Cumulative dropped-packet count.")


class CreateStationSpec(BaseModel):
    """Spec for batch-creating virtual stations on a single radio."""

    model_config = ConfigDict(extra="forbid")

    radio: str = Field(description="Parent radio, e.g. 'wiphy0'.")
    count: int = Field(ge=1, le=200, description="Number of stations to create (1-200).")
    ssid_prefix: str = Field(description="SSID the stations will join.")
    security: Security = Field(default="wpa2", description="Security mode: open/wpa/wpa2/wpa3.")
    key: str = Field(default="", description="Pre-shared key. Empty if security is 'open'.")
    resource: int = Field(default=1, description="Resource id; 1 on a single-box install.")
    shelf: int = Field(default=1, description="Shelf id; almost always 1.")


class StartTrafficSpec(BaseModel):
    """Spec for starting a Layer-3 cross-connect between two endpoints."""

    model_config = ConfigDict(extra="forbid")

    endpoint_a: str = Field(description="First endpoint port (e.g. 'sta0000').")
    endpoint_b: str = Field(description="Second endpoint port (e.g. 'eth1').")
    bps_min: int = Field(ge=0, description="Min throughput per endpoint, bits/sec.")
    bps_max: int = Field(ge=0, description="Max throughput per endpoint, bits/sec.")
    duration_sec: int = Field(ge=1, description="How long to run, seconds.")
    protocol: Protocol = Field(default="lf_udp", description="LANforge endpoint protocol.")
    cx_name: str = Field(default="cx_auto", description="Name to assign the cross-connect.")


class DiagnosticReport(BaseModel):
    """Composite diagnostic snapshot returned by ``diagnose_failure``."""

    model_config = ConfigDict(extra="forbid")

    cx_stats: CXStats
    recent_events: list[Event]
    port_state: list[Port]
    radio_info: list[Port]
    summary: str = Field(
        description="Rule-based human-readable summary. No LLM calls — pattern matched."
    )


class ListPortsInput(BaseModel):
    """Input schema for ``list_ports``."""

    model_config = ConfigDict(extra="forbid")

    resource: int = Field(default=1, description="Resource id (default 1).")


class CreateStationsInput(BaseModel):
    """Input schema for ``create_stations``."""

    model_config = ConfigDict(extra="forbid")

    spec: CreateStationSpec
    dry_run: bool = Field(
        default=True,
        description="If True (default), return CLI-JSON payload preview without executing.",
    )


class StartL3TrafficInput(BaseModel):
    """Input schema for ``start_l3_traffic``."""

    model_config = ConfigDict(extra="forbid")

    spec: StartTrafficSpec
    dry_run: bool = Field(
        default=True,
        description="If True (default), return CLI-JSON payload preview without executing.",
    )


class GetTestResultsInput(BaseModel):
    """Input schema for ``get_test_results``."""

    model_config = ConfigDict(extra="forbid")

    cx_name: str = Field(description="Cross-connect name (e.g. 'cx_001').")


class GetEventsInput(BaseModel):
    """Input schema for ``get_events``."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=500, description="Maximum events to return.")
    min_severity: Severity = Field(default="INFO", description="Drop events below this severity.")


class DiagnoseFailureInput(BaseModel):
    """Input schema for ``diagnose_failure``."""

    model_config = ConfigDict(extra="forbid")

    cx_name: str = Field(description="Cross-connect to diagnose.")
    resource: int = Field(default=1, description="Resource id (default 1).")
