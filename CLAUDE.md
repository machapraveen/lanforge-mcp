# CLAUDE.md — lanforge-mcp

Source of truth for how Claude Code works in this repo. Read fully before writing code. Re-read before any non-trivial change.

## Mission

Build `lanforge-mcp` — a Model Context Protocol server that lets an LLM drive **Candela Technologies' LANforge** Wi-Fi test platform by wrapping its existing JSON-over-HTTP API (`/cli-json/:cmd`, `/port/:resource/:port`, `/events`, `/help/:cmd`).

This is a job-winning demo for Candela. Ben Greear (CEO, kernel hacker) will read this code. **Correctness and restraint beat cleverness.**

## Hard rules — never violate

1. **No frameworks.** Use `mcp` Python SDK (FastMCP), `httpx`, `pydantic`. Do NOT import LangChain, LlamaIndex, CrewAI, agents libs, or LLM clients (openai/anthropic SDKs). The MCP server exposes tools; it does not call an LLM.
2. **Mock-first.** No real LANforge hardware during dev. Every tool works end-to-end against JSON fixtures in `tests/fixtures/`. Env var `LANFORGE_MOCK=1` (default on) routes all HTTP to the fixture loader.
3. **Python ≥ 3.10.** `from __future__ import annotations`. Use `list[str]`, `X | None`. No `typing.List`, no `typing.Optional`.
4. **Type hints everywhere.** `mypy --strict` on `src/`. Zero `Any` except at the httpx boundary with a justifying comment.
5. **Docstrings on every public function.** Google-style (Args/Returns/Raises). MCP tool docstrings are the LLM's tool description — write them for the LLM.
6. **No hardcoded secrets/IPs.** Env vars: `LANFORGE_HOST=localhost`, `LANFORGE_PORT=8080`, `LANFORGE_MOCK=1`.
7. **No scope creep.** If asked for anything outside the six tools, stop and ask. Shipping on time is the product.
8. **Don't touch anything outside this repo.** Do not clone/modify `greearb/lanforge-scripts` — that PR is a separate task.

## Tech stack (locked)

```
python         >= 3.10
mcp            >= 1.2, < 2.0
httpx          >= 0.27
pydantic       >= 2.0
pytest         >= 8.0
pytest-asyncio >= 0.23
ruff           >= 0.6
mypy           >= 1.10
```

Packaging: `pyproject.toml` with `hatchling`. No `setup.py`, no `requirements.txt` (dev extras under `[project.optional-dependencies].dev`).

## Repo layout (locked)

```
lanforge-mcp/
├── README.md
├── CLAUDE.md
├── LICENSE                      # MIT
├── pyproject.toml
├── .gitignore
├── .python-version              # 3.10
├── claude_desktop_config.json
├── demo/
│   ├── demo_script.md
│   └── demo_prompts.md
├── src/lanforge_mcp/
│   ├── __init__.py
│   ├── __main__.py              # python -m lanforge_mcp
│   ├── server.py                # FastMCP app
│   ├── client.py                # async LANforge HTTP client
│   ├── models.py                # pydantic schemas
│   ├── tools.py                 # the 6 tools
│   ├── resources.py
│   ├── prompts.py
│   ├── fixtures.py              # mock loader
│   ├── errors.py
│   └── config.py
└── tests/
    ├── conftest.py
    ├── fixtures/                # real JSON shapes from candelatech cookbook
    │   ├── ports_list.json
    │   ├── port_detail.json
    │   ├── events.json
    │   ├── cx_stats.json
    │   ├── help_add_sta.json
    │   └── resource_1_1.json
    ├── test_client.py
    ├── test_tools.py
    ├── test_server.py
    └── test_integration.py
```

## The six tools (locked scope for v0.1)

Do not add, rename, or split without asking.

| # | Tool | Purpose | Safety |
|---|------|---------|--------|
| 1 | `list_ports` | List all ports/radios on a resource | read-only |
| 2 | `create_stations` | Create N virtual Wi-Fi stations (`add_sta`) | `dry_run=True` default |
| 3 | `start_l3_traffic` | Start a Layer-3 cross-connect | `dry_run=True` default |
| 4 | `get_test_results` | Fetch CX stats (throughput, latency, loss) | read-only |
| 5 | `get_events` | Last N events, optional severity filter | read-only |
| 6 | `diagnose_failure` | Composite: CX stats + last 100 events + link state + radio info in one call | read-only — the money tool |

**Safety contract for every non-read-only tool:**
- Parameter `dry_run: bool = True`.
- If `dry_run=True`, return the exact CLI-JSON payload that would have been POSTed plus a human preview. No HTTP call.
- Docstring must say: "defaults to dry_run=True — LLM must explicitly set dry_run=False to execute."

## Resources and prompts (v0.1)

- `lanforge://docs/cli-reference` — curated markdown of the 30 most-used CLI commands. Static file in `src/lanforge_mcp/data/cli_reference.md`.
- `lanforge://port/{resource}/{port}` — live port detail (mock in dev).
- Prompt `run_wifi_capacity_test(ssid, station_count, duration_sec)` — parameterized template the LLM expands into a test plan.

## Code style

- **Formatter:** `ruff format`. Line length 100.
- **Linter:** `ruff check` rules: `E, F, W, I, N, UP, B, A, C4, SIM, PTH, RUF`. No `# noqa` without inline justification.
- **Type checker:** `mypy --strict` on `src/`.
- **Imports:** stdlib / third-party / local, blank line between. `ruff` enforces.
- **Errors:** specific exceptions from `lanforge_mcp.errors` (`LANforgeConnectionError`, `LANforgeAPIError`, `LANforgeMockMissing`). Never bare `Exception`.
- **Logging:** `logging.getLogger("lanforge_mcp")`. No `print` in library code. Server startup banner goes to stderr.
- **Demo logging:** every tool invocation logs a single human-readable INFO line to stderr in the form `[HH:MM:SS] TOOL <name>(<args>) -> <short result>`. This is what the demo video captures with `tail -f`. Don't switch to JSON formatting.
- **Async:** all I/O async. Sync wrappers only if MCP SDK requires.

## Testing standards

- `pytest` + `pytest-asyncio`, `asyncio_mode = "auto"`.
- Every tool: ≥1 test against `httpx.MockTransport` with fixture.
- Every non-read-only tool: a `dry_run=True` test proving zero HTTP calls.
- `test_integration.py` runs the server in-process and invokes each tool through MCP stdio.
- Minimum coverage **80%** on `src/lanforge_mcp/`. Don't chase 100% — chase meaningful tests.
- Fixtures are real JSON shapes from the candelatech cookbook. If a field is unknown, `TODO` with source URL. Don't invent.

## Commit discipline

- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- One logical change per commit. Body explains *why*, not *what*.
- Final commit: `chore: prepare v0.1.0 release` with changelog in README.

## README requirements (write FIRST, before any code)

Structure:
1. One-sentence tagline.
2. 90-second demo video link + GIF placeholder.
3. **Why** — 2 paragraphs: LANforge JSON API is structurally an MCP target; nobody's shipped this; Spirent Octobox can't because it's GUI-locked.
4. Install (editable + future pip path).
5. Full `claude_desktop_config.json` snippet, copy-pasteable.
6. The six tools — one-line each + example prompt.
7. Mock mode explanation, how to record fixtures.
8. ASCII architecture diagram: Claude → MCP stdio → lanforge-mcp → LANforge JSON API.
9. Roadmap for v0.2.
10. Credits: "Built with Claude Code in 48 hours. Not affiliated with Candela Technologies." Links to candelatech.com and greearb/lanforge-scripts.

## Definition of done for v0.1

- [ ] `pip install -e ".[dev]"` succeeds on clean Python 3.10 venv
- [ ] `ruff check src tests` — zero warnings
- [ ] `mypy --strict src` — passes
- [ ] `pytest` — passes, ≥80% coverage
- [ ] `python -m lanforge_mcp` starts server on stdio
- [ ] All 6 tools callable via MCP Inspector (`npx @modelcontextprotocol/inspector python -m lanforge_mcp`)
- [ ] README renders cleanly on GitHub
- [ ] `claude_desktop_config.json` works end-to-end in mock mode
- [ ] `demo/demo_script.md` — 90-second walkthrough

## When in doubt

Bias: **smaller diffs, fewer deps, more tests, clearer docstrings.** If adding a class where a function works — stop. If adding config "in case someone needs it later" — stop. Ben Greear merges boring, correct code.

## Out of scope for v0.1 (do not build)

Real hardware integration, auth/TLS, Chamber View, attenuator control, PDF reports, web UI, LLM-powered analysis, NL-to-script translation. If asked, respond: "out of v0.1 scope per CLAUDE.md — noted for v0.2."