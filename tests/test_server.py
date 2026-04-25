"""Tests for FastMCP registration: tools, resources, prompts."""

from __future__ import annotations

from lanforge_mcp.server import app


async def test_six_tools_registered() -> None:
    tools = await app.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "list_ports",
        "create_stations",
        "start_l3_traffic",
        "get_test_results",
        "get_events",
        "diagnose_failure",
    }


async def test_tool_schemas_have_descriptions() -> None:
    """Every tool description has to be present and substantive — it's the LLM's prompt."""
    tools = await app.list_tools()
    for t in tools:
        assert t.description is not None
        assert len(t.description) > 50, f"{t.name} description is too short: {t.description!r}"


async def test_dry_run_default_documented() -> None:
    """Mutating tools must call out dry_run=True default in their description."""
    tools = await app.list_tools()
    by_name = {t.name: t for t in tools}
    for name in ("create_stations", "start_l3_traffic"):
        desc = by_name[name].description or ""
        assert "dry_run=True" in desc
        assert "dry_run=False" in desc


async def test_resources_registered() -> None:
    res = await app.list_resources()
    uris = [str(r.uri) for r in res]
    assert "lanforge://docs/cli-reference" in uris


async def test_resource_template_registered() -> None:
    rt = await app.list_resource_templates()
    templates = [str(r.uriTemplate) for r in rt]
    assert "lanforge://port/{resource}/{port}" in templates


async def test_prompt_registered_and_expands() -> None:
    prompts = await app.list_prompts()
    by_name = {p.name: p for p in prompts}
    assert "run_wifi_capacity_test" in by_name
    result = await app.get_prompt(
        "run_wifi_capacity_test",
        arguments={"ssid": "Demo", "station_count": 8, "duration_sec": 30},
    )
    rendered = result.messages[0].content.text  # type: ignore[union-attr]
    assert "Demo" in rendered
    assert "8" in rendered
    assert "30s" in rendered


async def test_cli_reference_resource_returns_markdown() -> None:
    contents = await app.read_resource("lanforge://docs/cli-reference")
    body = contents[0].content
    assert "add_sta" in body
    assert "set_cx_state" in body
