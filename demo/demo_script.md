# lanforge-mcp — 90-second demo script

A side-by-side recording: Claude Desktop on the left, a terminal running
`tail -f ~/.lanforge-mcp.log` on the right. Set both windows to the same
height before hitting record.

> **Setup (off-camera, before recording).** Install the package
> (`pip install -e ".[dev]"`), drop the snippet from
> `claude_desktop_config.json` into your Claude Desktop config, and
> redirect the server's stderr to `~/.lanforge-mcp.log` (e.g. wrap the
> `command` in a tiny shell stub). Restart Claude Desktop.

---

## Timing breakdown

### `[0:00 – 0:15]` — The problem

Voiceover, talking head:

> "Candela Technologies' LANforge is the gold standard for Wi-Fi test —
> a single rack drives hundreds of virtual stations, RF impairments,
> traffic profiles. But running a test today means writing Lua scripts
> against a CLI documented in a 200-page PDF. What if you could just
> *talk* to it?"

Cut to Claude Desktop's MCP server picker. The `lanforge` server is
visible alongside any others.

### `[0:15 – 0:45]` — First prompt: ramp + traffic + diagnose

Type into Claude Desktop:

> **Create 4 stations on wiphy0 joining 'Candela-Test' with WPA2 key
> 'demo-secret', then start UDP traffic between sta0000 and eth1 at
> 10–50 Mbps for 60 seconds. After it's running, tell me if there's
> packet loss.**

Claude streams its response. As it runs, the right-hand log shows:

```
[14:32:01] TOOL list_ports(resource=1) → 6 ports returned
[14:32:02] TOOL create_stations(count=4, ssid='Candela-Test', dry_run=True) → preview returned
```

Claude pauses to ask: *"Confirm execution? (dry-run shows it would create
sta0000..sta0003 on wiphy0 with WPA2.)"* — point to this on camera.
Reply **"go".**

```
[14:32:11] TOOL create_stations(count=4, ssid='Candela-Test', dry_run=False) → 4 stations posted
[14:32:14] TOOL start_l3_traffic(cx='cx_auto', protocol=lf_udp, dry_run=True) → preview returned
```

Approve again. Claude executes:

```
[14:32:22] TOOL start_l3_traffic(cx='cx_auto', protocol=lf_udp, dry_run=False) → CX started (4 steps)
[14:32:24] TOOL get_test_results(cx_name='cx_auto') → Running, 95916000 bps total, 1.95% loss
```

Claude reports: *"The CX is running at ~95 Mbps aggregate. Packet loss
is 1.95% — that's above the TR-398 1% threshold. Want me to dig in?"*

### `[0:45 – 1:15]` — Second prompt: `diagnose_failure`

Type:

> **Yes, diagnose.**

```
[14:32:31] TOOL diagnose_failure(cx_name='cx_auto', resource=1) → 1.95% loss, 8 events, summary generated
```

Claude returns a structured response — show the summary line on screen:

> *"cx_auto: CX has moderate packet loss (2.0%); 3 WARN and 1 ERR
> event(s); 1 station(s) with NO-LINK; suspect RF interference or weak
> signal. Looking at the events, sta0002 had three beacon-loss /
> auth-timeout events around 09:14:08 — likely the cause. Drop sta0002
> from the test and retry, or move the AP closer."*

Pan to the log line. The point: **the LLM didn't guess**. Every claim is
grounded in a specific tool call you can audit.

### `[1:15 – 1:30]` — Pitch close

Voiceover, talking head:

> "Six tools. Pure pydantic. Mock-mode out of the box so you can demo it
> without a rack. This works *today* against your public JSON API. Give
> me 90 days inside Candela and I'll ship v1: TR-398 prompt library,
> Chamber View automation, attenuator control. Ben — let's talk."

End card: GitHub URL, name, email.

---

## Tips for the take

- **Don't overrun.** The 90-second cap is a feature, not a constraint —
  it forces every cut.
- **Keep the prompt natural.** No engineered phrasing. The point is "I
  asked for it in English and Claude figured out which tools to call."
- **Show the dry-run pause.** That's the safety story. The version
  where Claude blasts production without confirming would lose this
  pitch.
- **Scrub the log on screen** if you've got runs from earlier in the
  day. Clean canvas reads better.
