# lanforge-mcp — copy-pasteable demo prompts

Five prompts that exercise different tool combinations. All work in mock
mode (`LANFORGE_MOCK=1`, the default) so the demo runs offline. Replace
SSIDs and keys with your real values when pointing at a live LANforge.

---

## 1. Discovery — "What's on the rack?"

> List every port on resource 1 and tell me which radios are 802.11ax
> capable. Mention any stations that are stuck with NO-LINK.

Tools fired: `list_ports`. Showcases: structured output, the LLM
filtering on `mode` and `link_state`.

---

## 2. Capacity ramp + traffic — the headline demo

> Create 4 stations on wiphy0 joining 'Candela-Test' with WPA2 key
> 'demo-secret', then start UDP traffic between sta0000 and eth1 at
> 10–50 Mbps for 60 seconds. After it's running, tell me if there's
> packet loss.

Tools fired in order: `list_ports` (auto sanity check), `create_stations`
(dry-run, then execute), `start_l3_traffic` (dry-run, then execute),
`get_test_results`. Showcases: the dry-run safety contract and the
multi-tool orchestration the LLM does on its own.

---

## 3. Diagnose-only on an existing CX

> Diagnose cx_001. Walk me through what's wrong, citing specific events.

Tools fired: `diagnose_failure`. Showcases: the rule-based summary plus
the LLM's ability to pull individual events out of the structured
report and ground its narrative.

---

## 4. Event triage — "anything broken?"

> Show me the last 30 events with severity WARN or worse on resource 1.
> Group them by station and call out anything that looks like an RF
> issue.

Tools fired: `get_events`. Showcases: severity filtering plus an LLM-side
group-by that turns a raw event list into a story.

---

## 5. Templated test plan via the prompt resource

> Run a Wi-Fi capacity test on SSID 'Candela-Stress' with 32 stations
> for two minutes. Use the run_wifi_capacity_test prompt as your starting
> point and execute the plan end-to-end. Stop and ask before you do
> anything irreversible.

Tools fired: the prompt expansion, then `list_ports`, `create_stations`,
`start_l3_traffic`, `get_test_results`, `diagnose_failure` (in dry-run
first per the prompt's instructions). Showcases: the prompt resource as
a template the LLM follows, plus the safety boundary the LLM honours
because the dry-run default is in every tool description.
