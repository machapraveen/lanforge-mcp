/**
 * lanforge-mcp interactive demo.
 *
 * Runs three scripted scenarios that animate Claude Desktop on the left and
 * the lanforge-mcp stderr log on the right. Tool inputs and outputs are
 * derived from the same JSON fixtures in tests/fixtures/ that the test suite
 * uses, fetched at runtime so this page stays honest as fixtures evolve.
 *
 * Pure DOM APIs throughout (createElement / appendChild / textContent), no
 * innerHTML, no eval — every value rendered is author-controlled and the
 * page never invokes the shell.
 */

(() => {
  'use strict';

  // ---- Constants ----
  const REPO = 'machapraveen/lanforge-mcp';
  const TOOLS_PY_LINES = {
    list_ports: 163,
    create_stations: 185,
    start_l3_traffic: 243,
    get_test_results: 306,
    get_events: 331,
    diagnose_failure: 430,
  };

  const TYPE_SPEED_USER = 24;
  const TYPE_SPEED_CLAUDE = 14;
  const PAUSE_BETWEEN = 380;

  const conversationEl = document.getElementById('conversation');
  const serverLogEl = document.getElementById('server-log');
  const scenarioBtns = document.querySelectorAll('.scenario-btn');
  const skipBtn = document.getElementById('skip-btn');
  const resetBtn = document.getElementById('reset-btn');

  let skipFlag = false;
  let runToken = 0;

  // ---- Tiny DOM builder. No innerHTML. ----
  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null) continue;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
      }
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return node;
  }

  // ---- Fixture cache ----
  const fixtureCache = {};
  async function loadFixture(name) {
    if (fixtureCache[name]) return fixtureCache[name];
    const res = await fetch('fixtures/' + name + '.json');
    if (!res.ok) throw new Error('failed to load fixture ' + name + ': ' + res.status);
    const data = await res.json();
    fixtureCache[name] = data;
    return data;
  }

  // ---- LANforge JSON shape -> tidy projection (mirrors src/lanforge_mcp/client.py) ----
  function portsFromList(raw) {
    const out = [];
    for (const entry of raw.interfaces || []) {
      const eid = Object.keys(entry)[0];
      const f = entry[eid];
      const linkRaw = String(f.link || 'UNKNOWN').toUpperCase();
      const linkState = ['UP', 'DOWN', 'NO-LINK'].includes(linkRaw) ? linkRaw : 'UNKNOWN';
      out.push({
        name: f.port || f.device || f.alias || eid.split('.').pop(),
        mac: f.mac || '',
        ip: f.ip || '0.0.0.0',
        radio: f['parent dev'] || '',
        channel: f.channel || 0,
        bps_rx: f['bps rx'] || 0,
        bps_tx: f['bps tx'] || 0,
        link_state: linkState,
        ssid: f.ssid,
        signal: f.signal,
      });
    }
    return out;
  }

  const PRIORITY_TO_SEVERITY = {
    info: 'INFO', notice: 'INFO',
    warning: 'WARN', warn: 'WARN',
    error: 'ERR', err: 'ERR', critical: 'ERR', fatal: 'ERR',
  };
  function eventsFromRaw(raw) {
    const out = [];
    for (const entry of raw.events || []) {
      const id = Object.keys(entry)[0];
      const f = entry[id];
      const sev = PRIORITY_TO_SEVERITY[String(f.priority || 'info').trim().toLowerCase()] || 'INFO';
      out.push({
        timestamp: f['time-stamp'] || '',
        severity: sev,
        message: f['event description'] || f.event || '',
        port: f.name || '',
      });
    }
    return out;
  }

  function cxFromRaw(cxName, body) {
    let inner = {};
    for (const [k, v] of Object.entries(body)) {
      if (typeof v === 'object' && v !== null && (k.endsWith('.' + cxName) || v.name === cxName)) {
        inner = v;
        break;
      }
    }
    const bpsRx = (inner['bps rx a'] || 0) + (inner['bps rx b'] || 0);
    const bpsTx = (inner['bps tx a'] || 0) + (inner['bps tx b'] || 0);
    const dropA = inner['drop pkts a'] || 0;
    const dropB = inner['drop pkts b'] || 0;
    const lossA = inner['rx drop % a'] || 0;
    const lossB = inner['rx drop % b'] || 0;
    return {
      name: inner.name || cxName,
      state: inner.state || 'Unknown',
      bps_rx: bpsRx,
      bps_tx: bpsTx,
      latency_ms: inner['avg rtt'] || 0,
      pkt_loss_pct: (lossA + lossB) / 2,
      dropped: dropA + dropB,
    };
  }

  // Mirrors tools.py builders.
  function buildAddStaPayload(spec, idx) {
    return {
      shelf: spec.shelf || 1,
      resource: spec.resource || 1,
      radio: spec.radio,
      sta_name: 'sta' + String(idx).padStart(4, '0'),
      flags: 0,
      ssid: spec.ssid_prefix,
      key: spec.key || '[BLANK]',
      ap: 'AUTO',
      mode: 0,
      mac: 'NA',
      flags_mask: 0,
    };
  }
  function buildTrafficPayloads(spec) {
    const epA = spec.cx_name + '-A';
    const epB = spec.cx_name + '-B';
    return [
      { path: '/cli-json/add_endp', body: { alias: epA, shelf: 1, resource: 1, port: spec.endpoint_a, type: spec.protocol, ip_port: -1, min_rate: spec.bps_min, max_rate: spec.bps_max } },
      { path: '/cli-json/add_endp', body: { alias: epB, shelf: 1, resource: 1, port: spec.endpoint_b, type: spec.protocol, ip_port: -1, min_rate: spec.bps_min, max_rate: spec.bps_max } },
      { path: '/cli-json/add_cx',   body: { alias: spec.cx_name, test_mgr: 'default_tm', tx_endp: epA, rx_endp: epB } },
      { path: '/cli-json/set_cx_state', body: { test_mgr: 'default_tm', cx_name: spec.cx_name, cx_state: 'RUNNING' } },
    ];
  }

  function summarizeDiagnostic(cx, events, ports, cxName) {
    const bits = [];
    if (cx.pkt_loss_pct >= 5.0)      bits.push('CX has high packet loss (' + cx.pkt_loss_pct.toFixed(1) + '%)');
    else if (cx.pkt_loss_pct >= 1.0) bits.push('CX has moderate packet loss (' + cx.pkt_loss_pct.toFixed(1) + '%)');
    else if (cx.pkt_loss_pct > 0)    bits.push('CX has minor packet loss (' + cx.pkt_loss_pct.toFixed(2) + '%)');
    else                              bits.push('CX is loss-free');
    const we = events.filter(e => e.severity === 'WARN' || e.severity === 'ERR');
    const errCount = we.filter(e => e.severity === 'ERR').length;
    const warnCount = we.length - errCount;
    const rfHits = we.filter(e => /beacon|signal|auth|disconn/i.test(e.message)).length;
    if (we.length) {
      bits.push(warnCount && errCount
        ? warnCount + ' WARN and ' + errCount + ' ERR event(s)'
        : we.length + ' ' + we[0].severity + ' event(s)');
    }
    const weakLinks = ports.filter(p => p.link_state === 'NO-LINK' && p.name.startsWith('sta'));
    if (weakLinks.length) bits.push(weakLinks.length + ' station(s) with NO-LINK');
    if (cx.pkt_loss_pct >= 1.0 && rfHits >= 1) bits.push('suspect RF interference or weak signal');
    else if (cx.pkt_loss_pct >= 5.0)            bits.push('suspect overdrive or radio congestion');
    else if (weakLinks.length && rfHits)        bits.push('suspect RF coverage gap on stations failing to associate');
    else if (!we.length && cx.pkt_loss_pct === 0) bits.push('no failure indicators');
    return cxName + ': ' + bits.join('; ') + '.';
  }

  // ---- Render helpers ----
  function clearChildren(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function clearStage() { clearChildren(conversationEl); clearChildren(serverLogEl); }

  function nowHHMMSS() {
    const d = new Date();
    return String(d.getHours()).padStart(2, '0') + ':' +
           String(d.getMinutes()).padStart(2, '0') + ':' +
           String(d.getSeconds()).padStart(2, '0');
  }

  function appendLogLine(toolName, args, result) {
    const line = h('span', { class: 'log-line' },
      h('span', { class: 'log-time' }, '[' + nowHHMMSS() + ']'),
      ' ',
      h('span', { class: 'log-tag-info' }, 'INFO'),
      ' lanforge_mcp: ',
      h('span', { class: 'log-tag-tool' }, 'TOOL'),
      ' ',
      h('span', { class: 'log-tool-name' }, toolName),
      '(' + args + ') ',
      h('span', { class: 'log-arrow' }, '→'),
      ' ',
      h('span', { class: 'log-result' }, result),
      '\n'
    );
    serverLogEl.appendChild(line);
    serverLogEl.scrollTop = serverLogEl.scrollHeight;
  }

  function appendStaticLog(text) {
    const line = h('span', { class: 'log-line' },
      h('span', { class: 'log-time' }, '[' + nowHHMMSS() + ']'),
      ' ',
      h('span', { class: 'log-tag-info' }, 'INFO'),
      ' lanforge_mcp: ',
      text,
      '\n'
    );
    serverLogEl.appendChild(line);
    serverLogEl.scrollTop = serverLogEl.scrollHeight;
  }

  function makeMessage(role) {
    const body = h('div', { class: 'msg-body' },
      h('div', { class: 'msg-role' }, role === 'user' ? 'User' : 'Claude'),
      h('div', { class: 'msg-content' })
    );
    const wrap = h('div', { class: 'msg msg-' + role },
      h('div', { class: 'msg-avatar' }, role === 'user' ? 'U' : 'C'),
      body
    );
    conversationEl.appendChild(wrap);
    conversationEl.scrollTop = conversationEl.scrollHeight;
    return body.querySelector('.msg-content');
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  async function typeInto(el, text, baseSpeed, token) {
    el.classList.add('cursor-blink');
    el.textContent = '';
    for (let i = 0; i < text.length; i++) {
      if (token !== runToken) return;
      if (skipFlag) {
        el.textContent = text;
        break;
      }
      el.textContent += text[i];
      conversationEl.scrollTop = conversationEl.scrollHeight;
      const ch = text[i];
      const jitter = (ch === ' ' || ch === ',') ? baseSpeed * 0.3 : baseSpeed * (0.7 + Math.random() * 0.6);
      await sleep(jitter);
    }
    el.classList.remove('cursor-blink');
  }

  // Pretty-print JSON as a DocumentFragment with class-tagged spans (uses
  // matchAll, not regex.exec).
  function renderJSON(obj) {
    const json = JSON.stringify(obj, null, 2);
    const frag = document.createDocumentFragment();
    const pattern = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}\[\],])|(\s+)/g;
    let last = 0;
    for (const m of json.matchAll(pattern)) {
      if (m.index > last) frag.appendChild(document.createTextNode(json.slice(last, m.index)));
      if (m[1] !== undefined) {
        frag.appendChild(h('span', { class: m[2] ? 'json-key' : 'json-string' }, m[1]));
        if (m[2]) frag.appendChild(h('span', { class: 'json-punc' }, m[2]));
      } else if (m[3] !== undefined) {
        frag.appendChild(h('span', { class: 'json-num' }, m[3]));
      } else if (m[4] !== undefined) {
        frag.appendChild(h('span', { class: m[4] === 'null' ? 'json-null' : 'json-bool' }, m[4]));
      } else if (m[5] !== undefined) {
        frag.appendChild(h('span', { class: 'json-punc' }, m[5]));
      } else {
        frag.appendChild(document.createTextNode(m[0]));
      }
      last = m.index + m[0].length;
    }
    if (last < json.length) frag.appendChild(document.createTextNode(json.slice(last)));
    return frag;
  }

  function makeToolCard(toolName, args, result) {
    const line = TOOLS_PY_LINES[toolName] || 1;
    const sourceURL = 'https://github.com/' + REPO + '/blob/main/src/lanforge_mcp/tools.py#L' + line;
    return h('div', { class: 'tool-card' },
      h('div', { class: 'tool-card-header' },
        h('span', { class: 'tool-tag' }, 'tool call'),
        h('span', { class: 'tool-name' }, toolName + '()'),
        h('a', { class: 'tool-source-link', href: sourceURL, target: '_blank', rel: 'noopener' }, 'view source ↗')
      ),
      h('div', { class: 'tool-card-body' },
        h('div', { class: 'tool-pane' },
          h('span', { class: 'tool-pane-label' }, 'Input'),
          h('pre', null, renderJSON(args))
        ),
        h('div', { class: 'tool-pane' },
          h('span', { class: 'tool-pane-label' }, 'Output'),
          h('pre', null, renderJSON(result))
        )
      )
    );
  }

  // Mini DSL for rich Claude responses without using innerHTML:
  // entries are strings, or [tag, text] tuples for inline elements,
  // or ['br'] / ['approve'] for special markers.
  function renderRich(parts) {
    const frag = document.createDocumentFragment();
    for (const p of parts) {
      if (p == null) continue;
      if (typeof p === 'string') {
        frag.appendChild(document.createTextNode(p));
      } else if (Array.isArray(p)) {
        const tag = p[0];
        const txt = p[1];
        if (tag === 'br') frag.appendChild(h('br'));
        else if (tag === 'approve') frag.appendChild(h('span', { class: 'approve' }, 'awaiting approve'));
        else if (tag === 'code') frag.appendChild(h('code', null, txt));
        else if (tag === 'strong') frag.appendChild(h('strong', null, txt));
        else if (tag === 'em') frag.appendChild(h('em', null, txt));
      }
    }
    return frag;
  }

  // ---- Step engine ----
  async function runSteps(steps, token) {
    for (const step of steps) {
      if (token !== runToken) return;
      await runStep(step, token);
      if (token !== runToken) return;
      if (!skipFlag) await sleep(PAUSE_BETWEEN);
    }
    skipFlag = false;
  }

  async function runStep(step, token) {
    if (step.type === 'user') {
      const el = makeMessage('user');
      await typeInto(el, step.text, TYPE_SPEED_USER, token);
    } else if (step.type === 'claude') {
      const el = makeMessage('claude');
      await typeInto(el, step.text, TYPE_SPEED_CLAUDE, token);
    } else if (step.type === 'claude-rich') {
      const el = makeMessage('claude');
      el.appendChild(renderRich(step.parts));
      conversationEl.scrollTop = conversationEl.scrollHeight;
      if (!skipFlag) await sleep(120);
    } else if (step.type === 'tool') {
      let host = conversationEl.querySelector('.msg-claude:last-of-type .msg-body');
      if (!host) {
        const wrap = h('div', { class: 'msg msg-claude' },
          h('div', { class: 'msg-avatar' }, 'C'),
          h('div', { class: 'msg-body' })
        );
        conversationEl.appendChild(wrap);
        host = wrap.querySelector('.msg-body');
      }
      host.appendChild(makeToolCard(step.name, step.args, step.result));
      conversationEl.scrollTop = conversationEl.scrollHeight;
      appendLogLine(step.name, step.argsLabel, step.summary);
    } else if (step.type === 'pause') {
      if (!skipFlag) await sleep(step.ms || 400);
    }
  }

  // ---- Scenario builders ----
  async function buildCapacityScenario() {
    const portsRaw = await loadFixture('ports_list');
    const ports = portsFromList(portsRaw);
    const portsForLLM = ports.map(p => ({
      name: p.name, mac: p.mac, ip: p.ip, radio: p.radio,
      channel: p.channel, bps_rx: p.bps_rx, bps_tx: p.bps_tx, link_state: p.link_state,
    }));

    const staSpec = { radio: 'wiphy0', count: 4, ssid_prefix: 'Candela-Test', security: 'wpa2', key: 'demo-secret', resource: 1, shelf: 1 };
    const staPayloads = Array.from({ length: staSpec.count }, (_, i) => buildAddStaPayload(staSpec, i));
    const staDryOut = {
      dry_run: true,
      payloads: staPayloads,
      preview: "Would create 4 stations (sta0000..sta0003) on wiphy0 joining 'Candela-Test' with WPA2.",
    };
    const okResp = await loadFixture('cli_post_ok');
    const staWetOut = { dry_run: false, payloads: staPayloads, preview: staDryOut.preview, results: staPayloads.map(() => okResp) };

    const trafSpec = { endpoint_a: 'sta0000', endpoint_b: 'eth1', bps_min: 10000000, bps_max: 50000000, duration_sec: 60, protocol: 'lf_udp', cx_name: 'cx_uplink' };
    const trafPayloads = buildTrafficPayloads(trafSpec);
    const trafDryOut = {
      dry_run: true,
      payloads: trafPayloads,
      preview: "Would create LF_UDP CX 'cx_uplink' sta0000 <-> eth1 at 10-50 Mbps for 60s.",
    };
    const trafWetOut = { dry_run: false, payloads: trafPayloads, preview: trafDryOut.preview, results: trafPayloads.map(() => okResp) };

    const cxRaw = await loadFixture('cx_stats');
    const cx = cxFromRaw('cx_001', cxRaw);
    const cxForUI = Object.assign({}, cx, { name: 'cx_uplink' });

    const totalMbps = ((cxForUI.bps_rx + cxForUI.bps_tx) / 1e6).toFixed(0);
    const rxMbps = (cxForUI.bps_rx / 1e6).toFixed(0);
    const txMbps = (cxForUI.bps_tx / 1e6).toFixed(0);

    return [
      { type: 'user', text: "Create 4 stations on wiphy0 joining 'Candela-Test' with WPA2 key 'demo-secret', then start UDP traffic between sta0000 and eth1 at 10-50 Mbps for 60 seconds. After it's running, tell me if there's packet loss." },
      { type: 'claude', text: "I'll start by listing the ports on resource 1 to confirm wiphy0 is up, then walk through create_stations and start_l3_traffic in dry-run mode so you can approve before anything mutates." },
      { type: 'tool', name: 'list_ports', args: { resource: 1 }, result: portsForLLM,
        argsLabel: 'resource=1', summary: portsForLLM.length + ' ports returned' },
      { type: 'claude', text: "wiphy0 is up on channel 36 (802.11abgn-AC). I see sta0000 and sta0001 already attached at -42/-47 dBm, so adding four new stations on the same SSID will land cleanly. Building the dry-run payload." },
      { type: 'tool', name: 'create_stations', args: { spec: staSpec, dry_run: true }, result: staDryOut,
        argsLabel: "count=4, ssid='Candela-Test', dry_run=True", summary: 'preview returned' },
      { type: 'claude-rich', parts: [
        'Dry-run preview: four ', ['code', 'add_sta'], ' payloads, names ',
        ['code', 'sta0000'], '..', ['code', 'sta0003'], ', joining ',
        ['code', 'Candela-Test'], '. ', ['approve'], ' — reply with ', ['em', '"go"'], ' to execute against the box.'
      ]},
      { type: 'pause', ms: 700 },
      { type: 'user', text: 'go' },
      { type: 'tool', name: 'create_stations', args: { spec: staSpec, dry_run: false }, result: staWetOut,
        argsLabel: "count=4, ssid='Candela-Test', dry_run=False", summary: '4 stations posted' },
      { type: 'claude', text: "Four stations created. Now the traffic flow — dry-run again so you see the four-step LANforge sequence (add_endp x2, add_cx, set_cx_state RUNNING)." },
      { type: 'tool', name: 'start_l3_traffic', args: { spec: trafSpec, dry_run: true }, result: trafDryOut,
        argsLabel: "cx='cx_uplink', protocol=lf_udp, dry_run=True", summary: 'preview returned' },
      { type: 'claude-rich', parts: [
        'Dry-run shows the four-step LANforge sequence at 10-50 Mbps for 60 seconds. ',
        ['approve'], ' — reply ', ['em', '"go"'], '.'
      ]},
      { type: 'pause', ms: 600 },
      { type: 'user', text: 'go' },
      { type: 'tool', name: 'start_l3_traffic', args: { spec: trafSpec, dry_run: false }, result: trafWetOut,
        argsLabel: "cx='cx_uplink', protocol=lf_udp, dry_run=False", summary: 'CX started (4 steps)' },
      { type: 'claude', text: 'CX is running. Pulling stats now.' },
      { type: 'tool', name: 'get_test_results', args: { cx_name: 'cx_uplink' }, result: cxForUI,
        argsLabel: "cx_name='cx_uplink'", summary: cxForUI.state + ', ' + (cxForUI.bps_rx + cxForUI.bps_tx) + ' bps total, ' + cxForUI.pkt_loss_pct.toFixed(2) + '% loss' },
      { type: 'claude', text: 'cx_uplink is Running at ~' + totalMbps + ' Mbps aggregate (' + rxMbps + ' rx + ' + txMbps + ' tx). Average RTT ' + cxForUI.latency_ms.toFixed(1) + ' ms. Packet loss is ' + cxForUI.pkt_loss_pct.toFixed(2) + '% — that is above the TR-398 1% threshold, so it is worth investigating. Want me to call diagnose_failure?' },
    ];
  }

  async function buildDiagnoseScenario() {
    const cxRaw = await loadFixture('cx_stats');
    const eventsRaw = await loadFixture('events');
    const portsRaw = await loadFixture('ports_list');
    const cx = cxFromRaw('cx_001', cxRaw);
    const events = eventsFromRaw(eventsRaw);
    const ports = portsFromList(portsRaw);
    const radios = ports.filter(p => p.name.includes('phy') && !p.name.startsWith('sta'));
    const summary = summarizeDiagnostic(cx, events, ports, 'cx_001');
    const report = {
      cx_stats: cx,
      recent_events: events,
      port_state: ports.map(p => ({ name: p.name, mac: p.mac, ip: p.ip, radio: p.radio, channel: p.channel, bps_rx: p.bps_rx, bps_tx: p.bps_tx, link_state: p.link_state })),
      radio_info: radios.map(p => ({ name: p.name, mac: p.mac, channel: p.channel, link_state: p.link_state })),
      summary,
    };

    const sta2Events = events.filter(e => e.port === 'sta0002');
    const beaconEv = sta2Events.find(e => /beacon/i.test(e.message));
    const cxDropEv = events.find(e => /CX Drop|drop/i.test(e.message) && e.port === 'cx_001');
    const dropA = cxRaw['1.1.cx_001']['drop pkts a'];
    const dropB = cxRaw['1.1.cx_001']['drop pkts b'];

    const beaconTime = beaconEv ? (beaconEv.timestamp.split(' ')[1] || '09:14:08') : '09:14:08';
    const dropMsg = cxDropEv ? cxDropEv.message : '47 packets dropped on endpoint A (RF interference suspected)';

    return [
      { type: 'user', text: 'Diagnose cx_001. Walk me through what is wrong, citing specific events.' },
      { type: 'claude', text: 'Calling diagnose_failure — it pulls CX stats, the last 100 events, and the port list concurrently with asyncio.gather, then runs a rule-based summary.' },
      { type: 'tool', name: 'diagnose_failure', args: { cx_name: 'cx_001', resource: 1 }, result: report,
        argsLabel: "cx_name='cx_001', resource=1", summary: cx.pkt_loss_pct.toFixed(2) + '% loss, ' + events.length + ' events, summary generated' },
      { type: 'claude-rich', parts: [
        ['strong', 'Summary: '], summary, ['br'], ['br'],
        'Walking the evidence:', ['br'], ['br'],
        '• ', ['strong', 'Loss'], ': ', cx.pkt_loss_pct.toFixed(2), '% packet loss across both endpoints. drop pkts a=', String(dropA), ', drop pkts b=', String(dropB), '. RTT ', cx.latency_ms.toFixed(1), ' ms.', ['br'],
        '• ', ['strong', 'Cluster on sta0002'], ': three events around ', ['code', beaconTime], ' — beacon loss, auth timeout, then disassoc due to inactivity. Signal at sta0002 is -82 dBm in the port list, link state NO-LINK.', ['br'],
        '• ', ['strong', 'CX-side'], ': ', dropMsg, '.', ['br'], ['br'],
        ['strong', 'Recommendation'], ': drop sta0002 from the test (it is an outlier dragging the aggregate loss above 1%) or move the AP closer for that station’s coverage. The other three stations on cx_001 are healthy.'
      ]},
    ];
  }

  async function buildTriageScenario() {
    const eventsRaw = await loadFixture('events');
    const allEvents = eventsFromRaw(eventsRaw);
    const filtered = allEvents.filter(e => e.severity === 'WARN' || e.severity === 'ERR');

    const byPort = {};
    for (const ev of filtered) {
      const k = ev.port || '(system)';
      (byPort[k] = byPort[k] || []).push(ev);
    }

    const parts = [filtered.length + ' WARN-or-worse event(s), grouped by source:', ['br'], ['br']];
    let first = true;
    for (const [port, evs] of Object.entries(byPort)) {
      if (!first) parts.push(['br'], ['br']);
      first = false;
      const sevCount = evs.reduce((acc, e) => { acc[e.severity] = (acc[e.severity] || 0) + 1; return acc; }, {});
      const sevLabel = ['ERR', 'WARN'].filter(s => sevCount[s]).map(s => sevCount[s] + ' ' + s).join(', ');
      parts.push(['strong', port], ' — ', sevLabel, ['br']);
      for (const e of evs) {
        const t = e.timestamp.split(' ')[1] || '';
        parts.push('  • ', ['code', t], ' ', e.message, ['br']);
      }
    }
    parts.push(['br'], ['strong', 'RF cluster'], ': ', ['code', 'sta0002'],
      ' shows the classic Wi-Fi failure cascade — beacon loss, auth timeout, then inactivity-based disassoc within ~1 second. Combined with the ',
      ['code', 'CX Drop'], ' on cx_001 (packets dropped on endpoint A flagged "RF interference suspected"), the signal is consistent with sta0002 being out of coverage. Suggested action: re-position the AP, increase tx-power on wiphy0, or drop sta0002 from the run.'
    );

    return [
      { type: 'user', text: 'Show me the last 30 events with severity WARN or worse on resource 1. Group them by station and call out anything that looks like an RF issue.' },
      { type: 'claude', text: 'Pulling filtered events.' },
      { type: 'tool', name: 'get_events', args: { limit: 30, min_severity: 'WARN' }, result: filtered,
        argsLabel: 'limit=30, min_severity=WARN', summary: filtered.length + ' events returned' },
      { type: 'claude-rich', parts },
    ];
  }

  // ---- Wire up ----
  const builders = {
    capacity: buildCapacityScenario,
    diagnose: buildDiagnoseScenario,
    triage: buildTriageScenario,
  };

  function setButtonsDisabled(state) {
    scenarioBtns.forEach(b => { b.disabled = state; });
  }

  async function runScenario(name) {
    setButtonsDisabled(true);
    skipFlag = false;
    runToken += 1;
    const token = runToken;
    clearStage();
    appendStaticLog('lanforge-mcp v0.1.0 — starting on stdio');
    appendStaticLog('lanforge-mcp starting (host=localhost port=8080 mock=True timeout=10s)');
    try {
      const builder = builders[name];
      if (!builder) throw new Error('unknown scenario: ' + name);
      const steps = await builder();
      await runSteps(steps, token);
    } catch (err) {
      console.error(err);
      appendStaticLog('ERR ' + err.message);
    } finally {
      if (token === runToken) setButtonsDisabled(false);
    }
  }

  function buildPlaceholder() {
    return h('div', { class: 'placeholder' },
      h('p', { class: 'placeholder-headline' }, 'Pick a scenario below to start the demo.'),
      h('p', { class: 'placeholder-sub' },
        'The chat on the left shows what Claude Desktop displays. The log on the right shows what ',
        h('code', null, 'lanforge-mcp'),
        ' emits to ', h('code', null, 'stderr'),
        ' for every tool call. Tool inputs and outputs are pulled from the same JSON fixtures the test suite uses — nothing is hardcoded.'
      )
    );
  }

  // Replace the SSR placeholder with our DOM-built one (lets reset rebuild it).
  clearChildren(conversationEl);
  conversationEl.appendChild(buildPlaceholder());

  scenarioBtns.forEach(btn => {
    btn.addEventListener('click', () => runScenario(btn.dataset.scenario));
  });
  skipBtn.addEventListener('click', () => { skipFlag = true; });
  resetBtn.addEventListener('click', () => {
    runToken += 1;
    skipFlag = false;
    setButtonsDisabled(false);
    clearChildren(conversationEl);
    clearChildren(serverLogEl);
    conversationEl.appendChild(buildPlaceholder());
  });
})();
