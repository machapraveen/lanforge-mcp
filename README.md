# lanforge-mcp

Built with Claude Code in 48 hours by Macha Praveen for Candela Technologies.

Drive Candela Technologies' LANforge Wi-Fi test platform with Claude — or any MCP client.

![demo placeholder](demo/demo.gif)

> 90-second walkthrough video: _link forthcoming. See `demo/demo_script.md` for the recording script._

> **v0.1.0** — six tools, mock-mode default, MIT licensed. 63 tests, 88% coverage, `mypy --strict` clean. Python 3.10+, `mcp` SDK 1.2+.

## Why

LANforge already speaks JSON over HTTP on port 8080 (`/cli-json/:cmd`, `/port/:resource/:port`,
`/events`, `/help/:cmd`). Structurally, that's an MCP server waiting to happen — a self-documenting
test harness an LLM can drive directly. **Nobody has shipped this**. Spirent Octobox can't, because
it's GUI-locked. LANforge can, because Ben Greear made the right architectural call a decade ago by
exposing the CLI over HTTP.

`lanforge-mcp` is the smallest possible bridge: six tools, one resource pack, one prompt template,
no LLM dependency. It runs in mock mode out of the box so you can demo it with no hardware. Point
`LANFORGE_HOST` and `LANFORGE_PORT` at a real LANforge GUI instance (launched with `-httpd`) to talk
to a real box.

## Install

```bash
# (future) pip install lanforge-mcp

git clone https://github.com/machapraveen/lanforge-mcp.git
cd lanforge-mcp
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Claude Desktop config

Drop this into `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "lanforge": {
      "command": "python",
      "args": ["-m", "lanforge_mcp"],
      "env": {
        "LANFORGE_HOST": "localhost",
        "LANFORGE_PORT": "8080",
        "LANFORGE_MOCK": "1",
        "LANFORGE_TIMEOUT_SEC": "10"
      }
    }
  }
}
```

Restart Claude Desktop. You should see `lanforge` in the MCP server list and six tools available.

## The six tools

| # | Tool | Description | Example prompt |
|---|------|-------------|---------------|
| 1 | `list_ports` | List all ports/radios on a resource (read-only). | _"What ports are on resource 1?"_ |
| 2 | `create_stations` | Create N virtual Wi-Fi stations on a radio. Defaults to `dry_run=True`. | _"Create 4 stations on wiphy0 joining 'Candela-Test' with WPA2."_ |
| 3 | `start_l3_traffic` | Start a Layer-3 cross-connect (traffic flow). Defaults to `dry_run=True`. | _"Start UDP traffic between sta0000 and eth1 at 10–50 Mbps for 60 seconds."_ |
| 4 | `get_test_results` | Fetch CX stats: throughput, latency, packet loss (read-only). | _"How is cx_001 doing?"_ |
| 5 | `get_events` | Last N events, optionally filtered by severity (read-only). | _"Show me the last 20 WARN-or-worse events."_ |
| 6 | `diagnose_failure` | Composite: CX stats + last 100 events + radio info, with a rule-based summary (read-only). | _"Diagnose cx_001 — why is it dropping packets?"_ |

Mutating tools (#2, #3) **default to `dry_run=True`**. They return the exact CLI-JSON payload that
would have been POSTed plus a human-readable preview. The LLM must explicitly pass `dry_run=False`
to execute against the box. This is the safety contract for v0.1.

## Mock mode

`LANFORGE_MOCK=1` (the default) routes all HTTP through `httpx.MockTransport` and serves recorded
JSON fixtures from `tests/fixtures/`. The fixture shapes match the publicly documented JSON examples
on the [Candela cookbook](https://www.candelatech.com/cookbook.php?vol=cli&book=JSON__Querying_the_LANforge_Client_for_JSON_Data).
Set `LANFORGE_MOCK=0` to talk to a real LANforge GUI on `LANFORGE_HOST:LANFORGE_PORT` (default
`localhost:8080`).

To record your own fixtures from a live LANforge:

```bash
curl -s http://YOUR_LANFORGE:8080/ports/1/1/list > tests/fixtures/ports_list.json
curl -s http://YOUR_LANFORGE:8080/events/last/100 > tests/fixtures/events.json
# ...etc.
```

## Architecture

```
+----------------+        stdio (MCP)         +----------------+        HTTP+JSON         +-----------------+
|                | <------------------------> |                | <----------------------> |                 |
| Claude Desktop |                            |  lanforge-mcp  |                          | LANforge server |
| / Claude Code  |   tools / resources /      |   (FastMCP)    |   /cli-json/:cmd         |   GUI -httpd    |
|                |       prompts              |                |   /port/:resource/:port  |   port 8080     |
+----------------+                            +----------------+   /events                +-----------------+
                                                      |               /help/:cmd
                                                      | LANFORGE_MOCK=1
                                                      v
                                               tests/fixtures/*.json
                                               (recorded JSON shapes)
```

## Roadmap (v0.2)

- Real-hardware verification against a Candela demo lab (no schema changes expected).
- Chamber View automation (turntable position, attenuator level).
- TR-398 issue 4 prompt library (capacity, range, roaming, multi-station latency).
- LANforge Lua/Perl script generation prompt for `lanforge-scripts` integration.
- Optional auth/TLS shim for remote use over a VPN.

## Changelog

### v0.1.0

- Six MCP tools: `list_ports`, `create_stations`, `start_l3_traffic`, `get_test_results`,
  `get_events`, `diagnose_failure`.
- Two resources: `lanforge://docs/cli-reference`, `lanforge://port/{resource}/{port}`.
- One prompt template: `run_wifi_capacity_test`.
- Async `httpx` client with `MockTransport`-backed mock mode (default on).
- Pydantic v2 schemas for every tool input/output.
- Rule-based diagnostic summaries — no LLM calls.
- `mypy --strict`, `ruff` clean, `pytest` ≥ 80% coverage.

## Credits

Built with Claude Code in 48 hours. Not affiliated with Candela Technologies.

- LANforge platform: <https://www.candelatech.com/>
- Reference scripts: <https://github.com/greearb/lanforge-scripts>
- Model Context Protocol: <https://modelcontextprotocol.io/>
