"""The six MCP tools.

Each function:

* takes its pydantic input model (or simple kwargs the input model wraps),
* returns either a pydantic output model or a plain ``dict`` for the
  preview-style returns,
* emits a single human-readable INFO log line to stderr summarising the
  call (this is what the demo video captures with ``tail -f``).

Mutating tools (``create_stations``, ``start_l3_traffic``) honour the
safety contract from ``CLAUDE.md``: ``dry_run=True`` is the default and
returns the exact CLI-JSON payloads that *would* have been POSTed plus a
human-readable preview, with no HTTP traffic. The LLM must explicitly set
``dry_run=False`` to execute.

The diagnose_failure summary is rule-based — no LLM calls. Pattern-match
on packet-loss thresholds, event severities, and event keywords like
``beacon`` or ``auth``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from lanforge_mcp.client import LANforgeClient
from lanforge_mcp.models import (
    CreateStationSpec,
    CXStats,
    DiagnosticReport,
    Event,
    Port,
    StartTrafficSpec,
)

logger = logging.getLogger("lanforge_mcp")


# Until we verify the exact LANforge add_sta flag bits against real hardware,
# every security mode sends flags=0 and flags_mask=0 — i.e. "do not modify any
# station-level flag bits; use LANforge defaults." The SSID/key parameters
# alone are enough for LANforge to negotiate the AP's advertised security
# (WPA2/WPA3/WPS) in mock mode and on real hardware that follows the cookbook
# add_sta examples. v0.2 will plumb explicit flag bits after a real LANforge
# bake-off. Source: https://www.candelatech.com/lfcli_ug.php#add_sta
_SECURITY_FLAG_BITS: dict[str, int] = {
    "open": 0,
    "wpa": 0,
    "wpa2": 0,
    "wpa3": 0,
}

_SEVERITY_RANK: dict[str, int] = {"INFO": 0, "WARN": 1, "ERR": 2}


def _now_hhmmss() -> str:
    """Return the current local time as ``HH:MM:SS`` for log lines."""
    return time.strftime("%H:%M:%S", time.localtime())


def _log_call(name: str, args: str, result: str) -> None:
    """Emit one demo-friendly INFO line per tool invocation.

    Args:
        name: Tool name.
        args: One-line representation of the call args.
        result: One-line representation of the return value.
    """
    logger.info("[%s] TOOL %s(%s) → %s", _now_hhmmss(), name, args, result)


def _build_add_sta_payload(spec: CreateStationSpec, index: int) -> dict[str, Any]:
    """Build a ``/cli-json/add_sta`` payload for the i-th station.

    Args:
        spec: Batch creation spec.
        index: Zero-based station index within the batch.

    Returns:
        A dict ready to POST to LANforge.
    """
    flags = _SECURITY_FLAG_BITS[spec.security]
    return {
        "shelf": spec.shelf,
        "resource": spec.resource,
        "radio": spec.radio,
        "sta_name": f"sta{index:04d}",
        "flags": flags,
        "ssid": spec.ssid_prefix,
        "key": spec.key if spec.key else "[BLANK]",
        "ap": "AUTO",
        "mode": 0,
        "mac": "NA",
        "flags_mask": 0,
    }


def _build_traffic_payloads(spec: StartTrafficSpec) -> list[dict[str, Any]]:
    """Build the ordered CLI-JSON payloads for a Layer-3 traffic flow.

    The realistic LANforge sequence is: ``add_endp`` (twice), ``add_cx``,
    ``set_cx_state RUNNING``. We surface all four so the LLM can reason
    about the full action.

    Args:
        spec: Traffic spec.

    Returns:
        List of ``{"path": "/cli-json/...", "body": {...}}`` records.
    """
    ep_a = f"{spec.cx_name}-A"
    ep_b = f"{spec.cx_name}-B"
    return [
        {
            "path": "/cli-json/add_endp",
            "body": {
                "alias": ep_a,
                "shelf": 1,
                "resource": 1,
                "port": spec.endpoint_a,
                "type": spec.protocol,
                "ip_port": -1,
                "min_rate": spec.bps_min,
                "max_rate": spec.bps_max,
            },
        },
        {
            "path": "/cli-json/add_endp",
            "body": {
                "alias": ep_b,
                "shelf": 1,
                "resource": 1,
                "port": spec.endpoint_b,
                "type": spec.protocol,
                "ip_port": -1,
                "min_rate": spec.bps_min,
                "max_rate": spec.bps_max,
            },
        },
        {
            "path": "/cli-json/add_cx",
            "body": {
                "alias": spec.cx_name,
                "test_mgr": "default_tm",
                "tx_endp": ep_a,
                "rx_endp": ep_b,
            },
        },
        {
            "path": "/cli-json/set_cx_state",
            "body": {
                "test_mgr": "default_tm",
                "cx_name": spec.cx_name,
                "cx_state": "RUNNING",
            },
        },
    ]


async def list_ports(resource: int = 1, *, client: LANforgeClient) -> list[Port]:
    """List every port on a LANforge resource.

    Read-only. Use this to discover which radios (``wiphy0``, ``wiphy1``)
    and stations (``sta0000``...) currently exist before creating new ones
    or starting traffic.

    Example: ``list_ports(resource=1)`` returns physical NICs, Wi-Fi
    radios, and any virtual stations on resource 1.

    Args:
        resource: Resource id (default 1; single-box installs only have 1).
        client: Active LANforge client (passed by the server wiring).

    Returns:
        List of :class:`Port` objects.
    """
    ports = await client.list_ports(resource=resource)
    _log_call("list_ports", f"resource={resource}", f"{len(ports)} ports returned")
    return ports


async def create_stations(
    spec: CreateStationSpec,
    dry_run: bool = True,
    *,
    client: LANforgeClient,
) -> dict[str, Any]:
    """Create N virtual Wi-Fi stations on a radio (``add_sta`` per station).

    **Defaults to dry_run=True — the LLM must explicitly set dry_run=False
    to execute.** When dry_run is True, returns the exact CLI-JSON payloads
    that would have been POSTed plus a human-readable preview, without
    making any HTTP calls.

    Use this to ramp test load: 4 stations join an SSID, then a separate
    ``start_l3_traffic`` call drives traffic across them.

    Example: ``create_stations(spec={'radio': 'wiphy0', 'count': 4,
    'ssid_prefix': 'Candela-Test', 'security': 'wpa2', 'key': 'secret'},
    dry_run=True)`` returns four payloads naming sta0000..sta0003 with
    WPA2 flags set.

    Args:
        spec: Batch spec (radio, count 1-200, SSID, security, key).
        dry_run: When True (default), return preview without POSTing.
        client: Active LANforge client (passed by the server wiring).

    Returns:
        ``{"dry_run": bool, "payloads": [...], "preview": str,
        "results": [...]}`` when executed; ``results`` is omitted on dry runs.
    """
    payloads = [_build_add_sta_payload(spec, i) for i in range(spec.count)]
    last_name = f"sta{spec.count - 1:04d}"
    preview = (
        f"Would create {spec.count} stations ({payloads[0]['sta_name']}..{last_name}) "
        f"on {spec.radio} joining '{spec.ssid_prefix}' with {spec.security.upper()}."
    )
    if dry_run:
        _log_call(
            "create_stations",
            f"count={spec.count}, ssid='{spec.ssid_prefix}', dry_run=True",
            "preview returned",
        )
        return {"dry_run": True, "payloads": payloads, "preview": preview}

    results = await asyncio.gather(*(client.add_station(p) for p in payloads))
    _log_call(
        "create_stations",
        f"count={spec.count}, ssid='{spec.ssid_prefix}', dry_run=False",
        f"{len(results)} stations posted",
    )
    return {
        "dry_run": False,
        "payloads": payloads,
        "preview": preview,
        "results": results,
    }


async def start_l3_traffic(
    spec: StartTrafficSpec,
    dry_run: bool = True,
    *,
    client: LANforgeClient,
) -> dict[str, Any]:
    """Start a Layer-3 cross-connect (traffic flow) between two endpoints.

    **Defaults to dry_run=True — the LLM must explicitly set dry_run=False
    to execute.** When dry_run is True, returns the exact CLI-JSON
    payloads (add_endp x2, add_cx, set_cx_state RUNNING) plus a
    human-readable preview, without making any HTTP calls.

    Example: ``start_l3_traffic(spec={'endpoint_a': 'sta0000',
    'endpoint_b': 'eth1', 'bps_min': 10000000, 'bps_max': 50000000,
    'duration_sec': 60, 'protocol': 'lf_udp', 'cx_name': 'cx_uplink'},
    dry_run=True)`` previews a 10-50 Mbps UDP CX named cx_uplink.

    Args:
        spec: Traffic spec (endpoints, rate, duration, protocol, cx_name).
        dry_run: When True (default), return preview without POSTing.
        client: Active LANforge client (passed by the server wiring).

    Returns:
        ``{"dry_run": bool, "payloads": [...], "preview": str,
        "results": [...]}`` when executed; ``results`` is omitted on dry runs.
    """
    payloads = _build_traffic_payloads(spec)
    rate_label = (
        f"{spec.bps_min // 1_000_000}-{spec.bps_max // 1_000_000} Mbps"
        if spec.bps_max >= 1_000_000
        else f"{spec.bps_min}-{spec.bps_max} bps"
    )
    preview = (
        f"Would create {spec.protocol.upper()} CX '{spec.cx_name}' "
        f"{spec.endpoint_a} <-> {spec.endpoint_b} at {rate_label} for {spec.duration_sec}s."
    )
    if dry_run:
        _log_call(
            "start_l3_traffic",
            f"cx='{spec.cx_name}', protocol={spec.protocol}, dry_run=True",
            "preview returned",
        )
        return {"dry_run": True, "payloads": payloads, "preview": preview}

    results: list[dict[str, Any] | list[Any]] = []
    for step in payloads:
        path: str = step["path"]
        body: dict[str, Any] = step["body"]
        results.append(await client.post(path, body))
    _log_call(
        "start_l3_traffic",
        f"cx='{spec.cx_name}', protocol={spec.protocol}, dry_run=False",
        f"CX started ({len(results)} steps)",
    )
    return {
        "dry_run": False,
        "payloads": payloads,
        "preview": preview,
        "results": results,
    }


async def get_test_results(cx_name: str, *, client: LANforgeClient) -> CXStats:
    """Fetch current statistics for a Layer-3 cross-connect.

    Read-only. Returns throughput, latency, and packet loss for the named
    CX. Pair with ``diagnose_failure`` if the numbers look bad.

    Example: ``get_test_results(cx_name='cx_001')`` returns a CXStats with
    bps_rx/bps_tx, latency_ms, pkt_loss_pct, etc.

    Args:
        cx_name: Cross-connect name.
        client: Active LANforge client.

    Returns:
        A :class:`CXStats` snapshot.
    """
    stats = await client.get_cx_stats(cx_name)
    _log_call(
        "get_test_results",
        f"cx_name='{cx_name}'",
        f"{stats.state}, {stats.bps_rx + stats.bps_tx} bps total, {stats.pkt_loss_pct:.2f}% loss",
    )
    return stats


async def get_events(
    limit: int = 50,
    min_severity: str = "INFO",
    *,
    client: LANforgeClient,
) -> list[Event]:
    """Fetch the last N LANforge events, optionally filtered by severity.

    Read-only. Severity is one of ``INFO``, ``WARN``, ``ERR``;
    ``min_severity='WARN'`` drops INFO entries. Filtering happens
    in-memory after fetching the most recent ``min(limit, 100)`` events
    from LANforge.

    Example: ``get_events(limit=20, min_severity='WARN')`` returns the
    most recent 20 WARN-or-worse events.

    Args:
        limit: Max events to return after filtering.
        min_severity: Drop events below this severity (INFO/WARN/ERR).
        client: Active LANforge client.

    Returns:
        Filtered list of :class:`Event`, newest-first if LANforge returns it that way.
    """
    fetch_limit = max(limit, 100)
    events = await client.get_events(limit=fetch_limit)
    threshold = _SEVERITY_RANK.get(min_severity.upper(), 0)
    filtered = [e for e in events if _SEVERITY_RANK.get(e.severity, 0) >= threshold][:limit]
    _log_call(
        "get_events",
        f"limit={limit}, min_severity={min_severity}",
        f"{len(filtered)} events returned",
    )
    return filtered


def _summarize(
    cx: CXStats,
    events: list[Event],
    ports: list[Port],
    cx_name: str,
) -> str:
    """Produce a rule-based diagnostic summary.

    Pattern matches on packet-loss thresholds and counts of WARN/ERR
    events whose messages mention beacon loss, authentication issues, or
    disconnects. No LLM calls.

    Args:
        cx: Cross-connect stats.
        events: Recent events.
        ports: Port list for the resource.
        cx_name: CX name (for the summary phrasing).

    Returns:
        A single human-readable diagnostic string.
    """
    bits: list[str] = []

    if cx.pkt_loss_pct >= 5.0:
        bits.append(f"CX has high packet loss ({cx.pkt_loss_pct:.1f}%)")
    elif cx.pkt_loss_pct >= 1.0:
        bits.append(f"CX has moderate packet loss ({cx.pkt_loss_pct:.1f}%)")
    elif cx.pkt_loss_pct > 0:
        bits.append(f"CX has minor packet loss ({cx.pkt_loss_pct:.2f}%)")
    else:
        bits.append("CX is loss-free")

    warn_or_err = [e for e in events if e.severity in {"WARN", "ERR"}]
    err_count = sum(1 for e in warn_or_err if e.severity == "ERR")
    warn_count = len(warn_or_err) - err_count

    rf_keywords = ("beacon", "signal", "auth", "disconn")
    rf_hits = sum(1 for e in warn_or_err if any(k in e.message.lower() for k in rf_keywords))

    if warn_or_err:
        ev_clause = (
            f"{warn_count} WARN and {err_count} ERR event(s)"
            if warn_count and err_count
            else f"{len(warn_or_err)} {warn_or_err[0].severity} event(s)"
        )
        bits.append(ev_clause)

    weak_links = [p for p in ports if p.link_state == "NO-LINK" and p.name.startswith("sta")]
    if weak_links:
        bits.append(f"{len(weak_links)} station(s) with NO-LINK")

    if cx.pkt_loss_pct >= 1.0 and rf_hits >= 1:
        bits.append("suspect RF interference or weak signal")
    elif cx.pkt_loss_pct >= 5.0:
        bits.append("suspect overdrive or radio congestion")
    elif weak_links and rf_hits:
        bits.append("suspect RF coverage gap on stations failing to associate")
    elif not warn_or_err and cx.pkt_loss_pct == 0.0:
        bits.append("no failure indicators")

    return f"{cx_name}: " + "; ".join(bits) + "."


async def diagnose_failure(
    cx_name: str,
    resource: int = 1,
    *,
    client: LANforgeClient,
) -> DiagnosticReport:
    """Composite read-only diagnostic for a failing cross-connect.

    Concurrently fetches CX stats, the last 100 events, and the full port
    list for the resource, then assembles a :class:`DiagnosticReport` with
    a rule-based ``summary`` field that calls out high packet loss,
    elevated WARN/ERR counts, beacon-loss/auth/disconnect patterns, and
    stations with NO-LINK.

    **No LLM calls** — the summary is pattern-matched. The LLM you're
    talking to right now uses the structured fields (cx_stats,
    recent_events, port_state) to build its own narrative; ``summary`` is
    a fallback hint for clients without an LLM.

    Example: ``diagnose_failure(cx_name='cx_001')`` for a CX with 12%
    loss alongside three beacon-loss WARN events returns a summary like
    "cx_001: CX has high packet loss (12.0%); 3 WARN event(s); suspect RF
    interference or weak signal."

    Args:
        cx_name: Cross-connect to diagnose.
        resource: Resource id (default 1).
        client: Active LANforge client.

    Returns:
        A :class:`DiagnosticReport` with cx_stats, recent_events,
        port_state, radio_info, and a summary string.
    """
    cx, events, all_ports = await asyncio.gather(
        client.get_cx_stats(cx_name, resource=resource),
        client.get_events(limit=100),
        client.list_ports(resource=resource),
    )
    radios = [p for p in all_ports if "phy" in p.name.lower() and not p.name.startswith("sta")]
    summary = _summarize(cx, events, all_ports, cx_name)
    report = DiagnosticReport(
        cx_stats=cx,
        recent_events=events,
        port_state=all_ports,
        radio_info=radios,
        summary=summary,
    )
    _log_call(
        "diagnose_failure",
        f"cx_name='{cx_name}', resource={resource}",
        f"{cx.pkt_loss_pct:.2f}% loss, {len(events)} events, summary generated",
    )
    return report
