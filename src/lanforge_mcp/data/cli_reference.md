# LANforge CLI-JSON command reference

A curated subset of the LANforge CLI commands most relevant to driving Wi-Fi
tests via the JSON HTTP API. Each command can be:

* posted to `http://lanforge:8080/cli-json/<cmd>` with a JSON body, or
* discovered at runtime via `GET /help/<cmd>` (returns the parameter schema).

This is a quick reference, not the full user guide. For exhaustive parameter
docs see <https://www.candelatech.com/lfcli_ug.php>.

---

### add_sta
Create a virtual Wi-Fi station on a radio.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","sta_name":"sta0000","ssid":"Candela-Test","key":"secret","mode":0,"flags":0x10000,"flags_mask":0xffffffff}`

### rm_sta
Remove a virtual station.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","sta_name":"sta0000"}`

### set_port
Configure IP/MAC/mode/admin state on a port.
Example: `{"shelf":1,"resource":1,"port":"sta0000","ip_addr":"192.168.1.50","netmask":"255.255.255.0","gateway":"192.168.1.1"}`

### show_port
Trigger a port refresh — useful before reading detail.
Example: `{"shelf":1,"resource":1,"port":"sta0000"}`

### add_endp
Create a single Layer-3 endpoint (one half of a cross-connect).
Example: `{"alias":"cx_uplink-A","shelf":1,"resource":1,"port":"sta0000","type":"lf_udp","min_rate":10000000,"max_rate":50000000}`

### rm_endp
Remove an endpoint.
Example: `{"endp_name":"cx_uplink-A"}`

### add_cx
Bind two endpoints into a cross-connect (traffic flow).
Example: `{"alias":"cx_uplink","test_mgr":"default_tm","tx_endp":"cx_uplink-A","rx_endp":"cx_uplink-B"}`

### rm_cx
Remove a cross-connect.
Example: `{"test_mgr":"default_tm","cx_name":"cx_uplink"}`

### set_cx_state
Start, stop, or quiesce a cross-connect.
Example: `{"test_mgr":"default_tm","cx_name":"cx_uplink","cx_state":"RUNNING"}` (or `STOPPED`, `QUIESCE`)

### set_cx_report_timer
How often LANforge updates CX statistics, in milliseconds.
Example: `{"test_mgr":"default_tm","cx_name":"cx_uplink","milliseconds":1000}`

### show_cx
Force a CX refresh.
Example: `{"test_mgr":"default_tm","cx_name":"cx_uplink"}`

### show_endp
Force an endpoint refresh.
Example: `{"endp_name":"cx_uplink-A"}`

### show_events
Trigger event-log replay (rarely needed; events stream automatically).
Example: `{}`

### add_l4_endp
Create a Layer-4 endpoint (HTTP/HTTPS/FTP/etc.).
Example: `{"alias":"l4_get","shelf":1,"resource":1,"port":"sta0000","url":"dl http://server/100M","ssl_cert_fname":""}`

### rm_l4_endp
Remove a Layer-4 endpoint.
Example: `{"endp_name":"l4_get"}`

### add_vap
Create a virtual access point on a radio.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","ap_name":"vap0","ssid":"Candela-Test","ap":"00:0e:8e:00:11:22"}`

### rm_vap
Remove a virtual access point.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","ap_name":"vap0"}`

### set_wifi_radio
Change radio channel, country, antenna, tx-power.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","channel":36,"frequency":5180,"country":840,"antenna":-1}`

### add_dut
Register a Device Under Test profile (helpful for reports).
Example: `{"name":"client_xyz","model":"AX210","mac":"de:ad:be:ef:00:01"}`

### rm_dut
Remove a DUT entry.
Example: `{"name":"client_xyz"}`

### add_text_blob
Save a named text blob (useful for run notes, certificate bodies, etc.).
Example: `{"name":"notes","type":"text","text":"day-1 baseline"}`

### add_file_endp
File transfer endpoint (NFS/CIFS/iSCSI throughput tests).
Example: `{"alias":"smb_pull","shelf":1,"resource":1,"port":"sta0000","fs_type":"smb","mount_dir":"/mnt/smb"}`

### add_monitor
Sniff packets on a port and write to pcap.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","port_name":"moni0a","flags":0,"aid_or_iface":""}`

### rm_monitor
Remove a monitor port.
Example: `{"shelf":1,"resource":1,"radio":"wiphy0","port_name":"moni0a"}`

### add_event
Inject a custom event into the LANforge log (useful for marking phases of a test).
Example: `{"name":"banner","priority":"info","details":"baseline phase begin"}`

### add_traffic_profile
Reusable traffic recipe.
Example: `{"name":"video_streaming","type":"lf_udp","min_pps":1000,"max_pps":10000}`

### rm_traffic_profile
Remove a traffic profile.
Example: `{"name":"video_streaming"}`

### add_wlan_endp
Higher-level wrapper that creates an STA, an endpoint, and links them.
Example: `{"alias":"wl0","shelf":1,"resource":1,"radio":"wiphy0","ssid":"Candela-Test","key":"secret"}`

### nc_show_ports
Re-discover ports from the kernel without touching them.
Example: `{"shelf":1,"resource":1}`

### help
Self-describing parameter help for any other command.
Example: `GET /help/add_sta` returns the parameter schema for `add_sta`.

---

**Tip:** All commands accept extra params that LANforge doesn't recognise as
no-ops — use `[BLANK]` for "leave unset" string fields and `NA` for "leave
unset" numeric fields.
