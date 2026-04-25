"""Async HTTP client for LANforge's JSON API.

Two modes, picked by ``Settings.mock``:

* **Mock** — httpx ``AsyncClient`` backed by ``MockTransport`` that
  delegates to :class:`lanforge_mcp.fixtures.FixtureStore`. Fast, offline,
  CI-safe.
* **Real** — vanilla ``AsyncClient`` pointed at ``http://host:port``.

Either way, callers see the same async surface: ``get``, ``post``, plus
typed helpers that translate LANforge's "key-with-spaces" JSON into the
pydantic models from :mod:`lanforge_mcp.models`.

The translation layer is the single tolerated boundary for ``Any`` per
``CLAUDE.md`` — once we leave this module, every value has a concrete type.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from lanforge_mcp.config import Settings
from lanforge_mcp.errors import LANforgeAPIError, LANforgeConnectionError, LANforgeMockMissing
from lanforge_mcp.fixtures import FixtureStore
from lanforge_mcp.models import CXStats, Event, Port

logger = logging.getLogger("lanforge_mcp")


_PRIORITY_TO_SEVERITY: dict[str, str] = {
    "info": "INFO",
    "notice": "INFO",
    "warning": "WARN",
    "warn": "WARN",
    "error": "ERR",
    "err": "ERR",
    "critical": "ERR",
    "fatal": "ERR",
}


def _normalize_severity(priority_field: str) -> str:
    """Translate a LANforge ``priority`` string ('  Warning') to ``WARN``.

    LANforge pads priority strings with spaces and capitalises inconsistently.
    Anything we don't recognise becomes ``INFO`` so the LLM sees a stable enum.

    Args:
        priority_field: Raw LANforge priority string.

    Returns:
        One of ``INFO``, ``WARN``, ``ERR``.
    """
    return _PRIORITY_TO_SEVERITY.get(priority_field.strip().lower(), "INFO")


def _port_from_raw(eid: str, raw: dict[str, Any]) -> Port:
    """Build a :class:`Port` from a single ``interfaces[*]`` entry.

    Args:
        eid: The full LANforge eid, e.g. ``1.1.wiphy0``. Used as a fallback
            for the ``name`` field.
        raw: The raw fields dict from the LANforge JSON response.

    Returns:
        A populated :class:`Port`.
    """
    name_field = raw.get("port") or raw.get("device") or raw.get("alias") or eid.split(".")[-1]
    link_raw = str(raw.get("link", "UNKNOWN")).upper()
    link_state = link_raw if link_raw in {"UP", "DOWN", "NO-LINK"} else "UNKNOWN"
    return Port(
        name=str(name_field),
        mac=str(raw.get("mac", "")),
        ip=str(raw.get("ip", "0.0.0.0")),
        alias=str(raw.get("alias", "")),
        radio=str(raw.get("parent dev", "")),
        channel=int(raw.get("channel", 0) or 0),
        bps_rx=int(raw.get("bps rx", 0) or 0),
        bps_tx=int(raw.get("bps tx", 0) or 0),
        link_state=link_state,
    )


def _event_from_raw(raw: dict[str, Any]) -> Event:
    """Build an :class:`Event` from a single LANforge event dict.

    Args:
        raw: The inner event dict (the value after the numeric key).

    Returns:
        A populated :class:`Event`.
    """
    return Event(
        timestamp=str(raw.get("time-stamp", "")),
        severity=_normalize_severity(str(raw.get("priority", "info"))),  # type: ignore[arg-type]
        message=str(raw.get("event description") or raw.get("event", "")),
        resource=1,
        port=str(raw.get("name", "")),
    )


def _cx_from_raw(cx_name: str, body: dict[str, Any]) -> CXStats:
    """Build a :class:`CXStats` from a ``/cx/...`` response body.

    LANforge wraps the cross-connect under a key like ``"1.1.cx_001"``. We
    locate that nested dict by suffix-matching on ``cx_name`` so callers
    don't need to know the full eid.

    Args:
        cx_name: Cross-connect name passed by the caller.
        body: The decoded JSON response.

    Returns:
        A populated :class:`CXStats`. Fields default to zero if absent.
    """
    inner: dict[str, Any] = {}
    for key, val in body.items():
        if isinstance(val, dict) and (key.endswith(f".{cx_name}") or val.get("name") == cx_name):
            inner = val
            break

    bps_rx = int(inner.get("bps rx a", 0) or 0) + int(inner.get("bps rx b", 0) or 0)
    bps_tx = int(inner.get("bps tx a", 0) or 0) + int(inner.get("bps tx b", 0) or 0)
    drop_a = int(inner.get("drop pkts a", 0) or 0)
    drop_b = int(inner.get("drop pkts b", 0) or 0)
    loss_a = float(inner.get("rx drop % a", 0.0) or 0.0)
    loss_b = float(inner.get("rx drop % b", 0.0) or 0.0)
    pkt_loss_pct = (loss_a + loss_b) / 2.0
    return CXStats(
        name=str(inner.get("name", cx_name)),
        state=str(inner.get("state", "Unknown")),
        bps_rx=bps_rx,
        bps_tx=bps_tx,
        latency_ms=float(inner.get("avg rtt", 0.0) or 0.0),
        pkt_loss_pct=pkt_loss_pct,
        dropped=drop_a + drop_b,
    )


class LANforgeClient:
    """Async client for the LANforge JSON HTTP API.

    Use as an async context manager. Construction is cheap; the underlying
    :class:`httpx.AsyncClient` is lazily created on ``__aenter__``.

    Attributes:
        settings: The :class:`Settings` instance configuring host/port/mock.
        store: The :class:`FixtureStore` used in mock mode (None in real mode).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        store: FixtureStore | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            settings: Runtime settings. Defaults to ``Settings.from_env()``.
            store: Mock fixture store. Defaults to a fresh :class:`FixtureStore`
                (only consulted when ``settings.mock`` is True).
        """
        self.settings = settings if settings is not None else Settings.from_env()
        self.store: FixtureStore | None = (
            store if store is not None else (FixtureStore() if self.settings.mock else None)
        )
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> LANforgeClient:
        """Open the underlying httpx client."""
        self._http = self._build_http()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Close the underlying httpx client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _build_http(self) -> httpx.AsyncClient:
        """Construct the httpx ``AsyncClient`` for the configured mode.

        Returns:
            An :class:`httpx.AsyncClient` ready for use.
        """
        if self.settings.mock:
            assert self.store is not None  # mypy refinement; True by construction in __init__.
            store = self.store

            async def handler(request: httpx.Request) -> httpx.Response:
                body = await store.get(request.url.path, request.method)
                return httpx.Response(200, json=body)

            return httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="http://mock.lanforge.local",
                timeout=self.settings.timeout_sec,
            )
        return httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout_sec,
            headers={"Accept": "application/json"},
        )

    @property
    def http(self) -> httpx.AsyncClient:
        """Return the underlying client; require ``async with`` first.

        Returns:
            The active :class:`httpx.AsyncClient`.

        Raises:
            RuntimeError: If accessed before entering the context manager.
        """
        if self._http is None:
            raise RuntimeError(
                "LANforgeClient must be used as an async context manager (async with ...)."
            )
        return self._http

    async def get(self, path: str) -> dict[str, Any] | list[Any]:
        """Issue an HTTP GET and return the decoded JSON body.

        Args:
            path: Request path, e.g. ``/ports/1/1/list``.

        Returns:
            Decoded JSON body (object or array).

        Raises:
            LANforgeConnectionError: On transport-level failure (DNS, refused, timeout).
            LANforgeAPIError: On non-2xx responses.
            LANforgeMockMissing: In mock mode when no fixture is mapped.
        """
        logger.debug("GET %s", path)
        try:
            response = await self.http.get(path)
        except LANforgeMockMissing:
            raise
        except httpx.HTTPError as exc:
            logger.error("HTTP transport error on GET %s: %s", path, exc)
            raise LANforgeConnectionError(str(exc)) from exc
        return self._unpack(response, "GET", path)

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """Issue an HTTP POST with a JSON payload and return the decoded body.

        Args:
            path: Request path, e.g. ``/cli-json/add_sta``.
            payload: JSON body.

        Returns:
            Decoded JSON body (object or array).

        Raises:
            LANforgeConnectionError: On transport-level failure.
            LANforgeAPIError: On non-2xx responses.
            LANforgeMockMissing: In mock mode when no fixture is mapped.
        """
        logger.debug("POST %s payload=%s", path, payload)
        try:
            response = await self.http.post(path, json=payload)
        except LANforgeMockMissing:
            raise
        except httpx.HTTPError as exc:
            logger.error("HTTP transport error on POST %s: %s", path, exc)
            raise LANforgeConnectionError(str(exc)) from exc
        return self._unpack(response, "POST", path)

    @staticmethod
    def _unpack(response: httpx.Response, method: str, path: str) -> dict[str, Any] | list[Any]:
        """Validate the HTTP status and decode the JSON body.

        Args:
            response: The httpx response.
            method: HTTP method (for log/error context).
            path: Request path (for log/error context).

        Returns:
            Decoded JSON body.

        Raises:
            LANforgeAPIError: If the response is not 2xx.
        """
        if response.status_code >= 400:
            body_text = response.text
            logger.error(
                "LANforge %s %s -> HTTP %d: %s", method, path, response.status_code, body_text
            )
            raise LANforgeAPIError(response.status_code, body_text)
        logger.debug("%s %s -> HTTP %d", method, path, response.status_code)
        body: dict[str, Any] | list[Any] = response.json()
        return body

    # Typed helpers --------------------------------------------------------

    async def list_ports(self, resource: int = 1) -> list[Port]:
        """Fetch ``/ports/1/{resource}/list`` and return :class:`Port` objects.

        Args:
            resource: Resource id; 1 on a single-box install.

        Returns:
            List of :class:`Port` instances, one per interface.
        """
        body = await self.get(f"/ports/1/{resource}/list")
        if not isinstance(body, dict):
            return []
        interfaces_raw: Any = body.get("interfaces", [])
        if not isinstance(interfaces_raw, list):
            return []
        ports: list[Port] = []
        for entry in interfaces_raw:
            if not isinstance(entry, dict):
                continue
            for eid, fields in entry.items():
                if isinstance(fields, dict):
                    ports.append(_port_from_raw(eid, fields))
        return ports

    async def get_port(self, port: str, resource: int = 1) -> Port:
        """Fetch ``/port/1/{resource}/{port}`` and return a :class:`Port`.

        Args:
            port: Port name (e.g. ``wiphy0``).
            resource: Resource id; 1 on a single-box install.

        Returns:
            A :class:`Port` for the requested interface.

        Raises:
            LANforgeAPIError: If the body shape is unexpected.
        """
        body = await self.get(f"/port/1/{resource}/{port}")
        if not isinstance(body, dict):
            raise LANforgeAPIError(200, f"unexpected body type for port detail: {type(body)!r}")
        fields_raw: Any = body.get("interface")
        if not isinstance(fields_raw, dict):
            raise LANforgeAPIError(200, "missing 'interface' object in port detail body")
        return _port_from_raw(port, fields_raw)

    async def get_events(self, limit: int = 100) -> list[Event]:
        """Fetch the last ``limit`` events.

        Args:
            limit: Max number of events to request from LANforge.

        Returns:
            List of :class:`Event` instances in arrival order.
        """
        body = await self.get(f"/events/last/{limit}")
        if not isinstance(body, dict):
            return []
        events_raw: Any = body.get("events", [])
        if not isinstance(events_raw, list):
            return []
        events: list[Event] = []
        for entry in events_raw:
            if not isinstance(entry, dict):
                continue
            for _eid, fields in entry.items():
                if isinstance(fields, dict):
                    events.append(_event_from_raw(fields))
        return events

    async def get_cx_stats(self, cx_name: str, resource: int = 1) -> CXStats:
        """Fetch CX stats and return :class:`CXStats`.

        Args:
            cx_name: Cross-connect name.
            resource: Resource id; 1 on a single-box install.

        Returns:
            A :class:`CXStats` snapshot.

        Raises:
            LANforgeAPIError: If the body shape is unexpected.
        """
        body = await self.get(f"/cx/1/{resource}/{cx_name}")
        if not isinstance(body, dict):
            raise LANforgeAPIError(200, f"unexpected body type for CX stats: {type(body)!r}")
        return _cx_from_raw(cx_name, body)

    async def add_station(self, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """POST an ``add_sta`` payload.

        Args:
            payload: CLI-JSON body for ``/cli-json/add_sta``.

        Returns:
            The decoded JSON response (LANforge returns ``{"status": "OK", ...}``).
        """
        return await self.post("/cli-json/add_sta", payload)

    async def add_cx(self, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """POST an ``add_cx`` payload.

        Args:
            payload: CLI-JSON body for ``/cli-json/add_cx``.

        Returns:
            The decoded JSON response.
        """
        return await self.post("/cli-json/add_cx", payload)

    async def set_cx_state(self, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """POST a ``set_cx_state`` payload.

        Args:
            payload: CLI-JSON body for ``/cli-json/set_cx_state``.

        Returns:
            The decoded JSON response.
        """
        return await self.post("/cli-json/set_cx_state", payload)
