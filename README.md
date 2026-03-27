# 🚦 Smart Traffic Signal Monitor — Central Control System

A distributed, real-time traffic signal control system built entirely in Python using UDP sockets, multithreading, and Tkinter. One central controller monitors and controls up to 4 road nodes across a network. All signal decisions are made by the controller — nodes only report traffic data and obey commands.

---

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [File Structure](#file-structure)
- [What Each File Does](#what-each-file-does)
- [Features](#features)
- [Evolution of the Project](#evolution-of-the-project)
- [Configuration Reference](#configuration-reference)
- [Running on One System](#running-on-one-system)
- [Running on Multiple Systems](#running-on-multiple-systems)
- [Running on VMs](#running-on-vms)
- [Network Simulation with tc netem](#network-simulation-with-tc-netem)
- [Signal Decision Logic](#signal-decision-logic)
- [Priority Vehicle System](#priority-vehicle-system)
- [Packet Loss — Will It Happen?](#packet-loss--will-it-happen)
- [Troubleshooting](#troubleshooting)

---

## Project Overview

This system simulates a smart city traffic signal network. Four road intersections (nodes) continuously report their vehicle counts to a central controller over UDP. The controller analyses the data, decides which intersection is most congested, and sends signal commands (GREEN / YELLOW / RED) back to each node in real time.

The controller's dashboard displays everything — live node data, packet statistics, congestion alerts, signal events, and a real-time bar chart — on one screen. The road nodes have no dashboard of their own; they only show a small GUI with a **Priority Vehicle** button.

```
┌─────────────────────────────────────────────────────┐
│             CONTROLLER  (1 machine)                 │
│         runs: dashboard.py + server.py              │
│         Shows everything. Decides all signals.      │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────┴────────────┐
         │  UDP :5005  ← nodes send traffic data
         │  UDP :6001–6004 → controller sends signals
         │
    ┌────┴────────────────────────────┐
    │   NODE HOST  (1 machine)        │
    │   4 lightweight VMs or systems  │
    │                                 │
    │  VM-A → python3 node_sim.py A   │
    │  VM-B → python3 node_sim.py B   │
    │  VM-C → python3 node_sim.py C   │
    │  VM-D → python3 node_sim.py D   │
    └─────────────────────────────────┘
```

---

## Architecture

### Communication Flow (Bidirectional UDP)

```
Node A  ──── UDP packet every 1 second ────▶  Controller :5005
             { node_id, vehicle_count,
               signal, timestamp, seq,
               priority }

Controller ──── Signal command ────────────▶  Node A :6001
                { node_id, signal }           Node B :6002
                                              Node C :6003
                                              Node D :6004
```

**Every second**, each node sends a JSON packet to the controller. The controller:

1. Records the vehicle count, latency, and sequence number
2. Computes packet loss using sequence gaps
3. Checks if a **priority vehicle** flag is set
4. Every `SIGNAL_CYCLE_SEC` seconds, picks the busiest node → GREEN
5. Sends the new signal command back to each node's dedicated port
6. Nodes obey the command and reflect it in subsequent packets

### Thread Map (Controller)

```
server.py threads:
  _listen()           → receives UDP from all nodes (blocking recv loop)
  _pps_ticker()       → counts packets per second (ticks every 1s)
  _signal_engine()    → decides GREEN/RED every SIGNAL_CYCLE_SEC seconds
  _yellow_watchdog()  → auto-advances YELLOW → RED after YELLOW_DURATION seconds

dashboard.py:
  root.after(1000)    → pulls snapshot from server and refreshes all widgets
```

### Thread Map (Each Node)

```
node_sim.py threads:
  _signal_listener()  → listens for commands from controller (blocking recv)
  _sender()           → sends traffic data to controller every second
  Tkinter mainloop()  → drives the GUI (priority button, signal display)
```

---

## How It Works

### Normal Signal Cycle

Every `SIGNAL_CYCLE_SEC` seconds (default: 5 seconds for demos, 30 in production), the controller's signal engine:

1. Looks at all nodes that sent a packet in the last 10 seconds (active nodes)
2. Picks the one with the **highest vehicle count** → assigns GREEN
3. All others → RED
4. If a node is transitioning away from GREEN, it passes through YELLOW for `YELLOW_DURATION` seconds (default: 3s) before going RED
5. The `_yellow_watchdog` thread handles the automatic YELLOW → RED transition

### Why RED nodes always have high vehicle counts

In `node_sim.py`, vehicle count is simulated based on the current signal:

```
RED    → random 20–50 vehicles   (cars pile up at red)
YELLOW → random 10–30 vehicles   (clearing)
GREEN  → random  0–20 vehicles   (cars moving freely)
```

This means whichever node is RED longest will accumulate the most vehicles — and become the next candidate for GREEN. This creates a natural rotating fairness system.

### Priority Vehicle Override

When the **🚨 PRIORITY VEHICLE** button is pressed on a node's GUI:

1. The node sets `"priority": true` in every subsequent UDP packet
2. The controller detects the transition from `false → true`
3. **Immediately** (without waiting for the next cycle):
   - Priority node → GREEN
   - All other nodes → RED (hard override, no YELLOW transition)
   - All yellow timers cleared
4. Dashboard shows a flashing red banner
5. Alert log records the event in orange
6. When **✅ CLEAR** is pressed, priority is lifted and normal engine resumes

### Packet Loss Detection

Every node packet includes a `seq` counter starting at 0 and incrementing by 1 each second. The server tracks the expected next sequence number per node:

```python
if seq > expected:
    lost = seq - expected          # gap = packets that never arrived
    loss_pct = lost / total * 100
_loss_expected[node_id] = seq + 1
```

If Node-A sends seq 0, 1, 2, 5 (packets 3 and 4 dropped), the server detects a gap of 2 when seq=5 arrives and updates the loss %.

---

## File Structure

```
Traffic_monitor/
├── config.py        ← shared constants (copy to ALL machines)
├── server.py        ← controller only: receives data, decides signals, sends commands
├── dashboard.py     ← controller only: Tkinter GUI, imports server
├── node_sim.py      ← road nodes only: GUI with priority button, sends/receives UDP
└── stress_test.py   ← optional: flood test from any machine on the LAN
```

---

## What Each File Does

### `config.py` — Shared Constants

The single source of truth for the entire system. Must be copied to every machine (controller and all nodes).

| Constant | Default | Purpose |
|---|---|---|
| `CONTROLLER_HOST` | `"192.168.1.100"` | IP of the controller — **change this** on every machine |
| `NODE_SEND_PORT` | `5005` | Port controller listens on for node data |
| `SIGNAL_RECV_PORT` | `5006` | Unused directly — each node uses its own port from NODES dict |
| `CONGESTION_THRESHOLD` | `30` | Vehicles above this = CONGESTED (red alert) |
| `HIGH_LOAD_THRESHOLD` | `20` | Vehicles above this = MODERATE (yellow warning) |
| `UPDATE_INTERVAL_MS` | `1000` | Dashboard refresh rate in milliseconds |
| `NODE_SEND_INTERVAL` | `1` | Seconds between each node's packets |
| `SIGNAL_CYCLE_SEC` | `30` | How often controller re-evaluates signals (use 5 for demos) |
| `YELLOW_DURATION` | `3` | Seconds a node stays YELLOW before going RED |
| `NODES` | A, B, C, D | Dict of 4 nodes with name + dedicated command port |

**Node port mapping:**
```python
NODES = {
    "A": {"name": "North Junction", "port": 6001},
    "B": {"name": "South Junction", "port": 6002},
    "C": {"name": "East Junction",  "port": 6003},
    "D": {"name": "West Junction",  "port": 6004},
}
```

---

### `server.py` — Controller Backend

Runs as background threads started by `dashboard.py`. Never run directly.

**Key functions:**

| Function | What it does |
|---|---|
| `_listen()` | Binds UDP socket on port 5005, receives packets from all nodes in a loop |
| `_handle_packet()` | Decodes JSON, updates node_data, computes latency/loss, detects priority transitions |
| `_signal_engine()` | Every SIGNAL_CYCLE_SEC: picks busiest node → GREEN, others → RED. Skipped during priority mode |
| `_yellow_watchdog()` | Every 1s: checks if any YELLOW node has timed out → sends RED. Skipped during priority mode |
| `_pps_ticker()` | Every 1s: updates packets/sec stat |
| `_apply_priority_override()` | Hard-overrides all signals immediately when priority is detected |
| `_clear_priority_override()` | Logs priority-cleared event, resumes normal engine |
| `_send_signal()` | Pushes a UDP signal command to a node's IP:port |
| `get_snapshot()` | Thread-safe copy of all state — called by dashboard every second |
| `start()` | Starts all 4 background threads — called once from dashboard.py |

**Important design — deadlock prevention:**
All `_add_alert()` and `_send_signal()` calls happen **outside** the `lock`. The lock is only held to read/write shared state. This prevents deadlock since `_add_alert()` itself acquires the lock internally.

---

### `dashboard.py` — Controller GUI

Imports and starts `server.py`, then builds the Tkinter window. Refreshes every `UPDATE_INTERVAL_MS` milliseconds by calling `server.get_snapshot()`.

**Layout — 2×2 grid:**

```
┌─────────────────────┬─────────────────────┐
│  Packet Stats /     │  Live Node Table    │
│  Throughput         │  (with Priority col)│
├─────────────────────┼─────────────────────┤
│  Congestion Alert   │  Vehicle Count      │
│  Log / Signal Events│  Real-Time Graph    │
└─────────────────────┴─────────────────────┘
```

**Stats panel** shows: Packets/sec, Total received, Packet loss %, Avg latency, Active nodes (X/4), Uptime

**Node table columns:** Node, Location, Vehicles, Assigned Signal, Priority (🚨 YES / —), Status, Node IP

**Alert log** colour coding:
- 🔴 Red = CONGESTION DETECTED
- 🟡 Yellow = HIGH LOAD, signal transitions
- 🟠 Orange = Priority vehicle events
- 🔵 Cyan = Info

**Priority banner:** A full-width flashing red bar appears at the top of the window whenever any node has an active priority vehicle. It alternates between red and orange on every refresh tick.

**Chart:** Real-time bar chart showing vehicle count history for all 4 nodes. Last 30 seconds shown. Red dashed line marks the congestion threshold (30 vehicles).

---

### `node_sim.py` — Road Node

Runs on each road system (or VM). Opens a small Tkinter window instead of being a plain terminal script.

**GUI elements:**
- Node ID and junction name in header
- Large signal display (GREEN / YELLOW / RED in matching colour)
- Status line showing priority mode state
- **🚨 PRIORITY VEHICLE** button — triggers priority mode
- **✅ CLEAR** button — clears priority mode (disabled until priority is active)

**Background threads:**
- `_signal_listener()` — binds to `NODES[node_id]["port"]`, receives signal commands from controller, updates `_current_signal`
- `_sender()` — every second, reads current signal and priority state, generates vehicle count, sends JSON packet to controller

**Packet payload:**
```json
{
  "node_id": "A",
  "location": "North Junction",
  "vehicle_count": 35,
  "signal": "RED",
  "timestamp": 1700000000.123,
  "seq": 42,
  "priority": false
}
```

---

### `stress_test.py` — Load Tester

Spawns 20 virtual nodes and floods the controller with UDP packets for 10 seconds as fast as possible. Reports total packets sent, duration, and throughput. Run from any machine on the LAN to stress-test the controller's receiver pipeline.

```bash
python stress_test.py
# Stress test: 20 nodes × 10s  →  192.168.1.100:5005
# Total sent   : 284,921
# Throughput   : 28,492 packets/sec
```

---

## Features

| Feature | Description |
|---|---|
| **Bidirectional UDP** | Nodes → controller (data), controller → nodes (commands) |
| **Controller-decided signals** | Nodes never decide their own signal — controller is the authority |
| **Auto-IP discovery** | Controller learns each node's IP from incoming packets — no manual config on controller |
| **Priority vehicle override** | Instant GREEN for emergency/priority vehicles, hard RED for all others |
| **YELLOW transition** | Smooth GREEN → YELLOW → RED transition (skipped in priority mode) |
| **Packet loss detection** | Sequence-number based loss tracking per node |
| **Latency measurement** | Rolling 50-sample average based on timestamp difference |
| **Deadlock-free threading** | Lock/unlock pattern ensures `_add_alert` and `_send_signal` never deadlock |
| **OFFLINE detection** | Nodes not seen in 5s shown as OFFLINE in table |
| **Signal engine pause** | Normal engine skips its cycle when priority mode is active |
| **Real-time bar chart** | 30-second rolling history with congestion threshold line |
| **Flashing priority banner** | Full-width alert banner on dashboard during priority mode |
| **Dark theme UI** | Consistent dark palette across both controller and node GUIs |

---

## Evolution of the Project

This project went through several major iterations. Here is the complete history of what changed and why.

### Version 1 — Original (Local Simulation)

**What it was:**
- 3 nodes (A, B, C)
- Everything on `127.0.0.1` (localhost only)
- Each node ran its own signal cycle internally — it decided its own GREEN/RED/YELLOW
- No bidirectional communication — the controller only received data, never sent commands
- Single `SERVER_HOST` constant for everything

**Limitations:**
- Could not run on multiple machines
- Signal was decided by the node itself, not the controller — not a real central control system
- Only 3 nodes

---

### Version 2 — Multi-System + 4 Nodes + Bidirectional Control

**What changed:**

**`config.py`**
- Added `CONTROLLER_HOST` — the LAN IP of the controller, shared by all nodes
- Changed `NODES` from 3 entries with just names to 4 entries (A, B, C, D) each with a `name` and a dedicated `port` (6001–6004)
- Added `SIGNAL_CYCLE_SEC` — controls how often the controller re-evaluates signals
- Added `YELLOW_DURATION` — how long YELLOW lasts before RED
- Added `NODE_SEND_INTERVAL` — seconds between each node's packets

**`node_sim.py`**
- Added `_signal_listener()` thread — each node now listens on its own port for signal commands from the controller
- Removed internal signal cycling — nodes no longer decide their own signal
- Node starts at RED and waits for the controller to assign it a signal
- Vehicle count simulation still based on current signal (which now comes from controller)
- Added `CONTROLLER_HOST` to send data to the real controller IP instead of localhost

**`server.py`**
- Added `_signal_engine()` — runs every `SIGNAL_CYCLE_SEC` seconds, picks busiest node → GREEN, others → RED
- Added `_yellow_watchdog()` — auto-advances YELLOW → RED
- Added `_send_signal()` — pushes UDP command packets to each node
- Auto-captures each node's IP from incoming packet's source address (no manual IP config needed on controller)
- Added `signal_state` to `get_snapshot()` for dashboard

**`dashboard.py`**
- Updated for 4 nodes
- Added Node IP and Last Seen columns to the table
- Added OFFLINE row for nodes not yet connected
- Added connection indicator (● X/4 nodes) in title bar with colour coding
- Added red dashed congestion threshold line to bar chart

---

### Version 3 — Deadlock Fix + Demo Speed

**What changed:**

**`server.py` — Critical bug fix**
- The original `_signal_engine()` called `_add_alert()` and `_send_signal()` **inside** a `with lock:` block
- `_add_alert()` also tries to `with lock:` internally → **deadlock** → signal engine silently froze
- **Fix:** Moved all `_add_alert()` and `_send_signal()` calls **outside** the lock using a `changes` dict pattern:
  1. Compute what needs to change (inside lock, read-only after)
  2. Apply changes and send alerts (outside lock)
- Same fix applied to `_yellow_watchdog()`

**`config.py`**
- Recommended changing `SIGNAL_CYCLE_SEC` from 30 to 5 for demos so GREEN appears within seconds instead of half a minute

---

### Version 4 — Priority Vehicle System

**What changed:**

**`node_sim.py` — Complete rewrite to GUI**
- No longer a plain terminal script
- Now opens a Tkinter window with:
  - Large signal display showing current assigned signal
  - **🚨 PRIORITY VEHICLE** button
  - **✅ CLEAR** button (disabled until priority is active)
  - Status line showing priority mode state
- Added `_priority_active` shared boolean flag
- Priority button sets flag → sender thread includes `"priority": true` in every packet
- Clear button unsets flag → `"priority": false` resumes
- Both `_signal_listener` and `_sender` run as daemon threads behind the GUI

**`server.py` — Priority override engine**
- Added `_priority_node` global — tracks which node (if any) is in priority mode
- In `_handle_packet()`, detects transition from `priority=false → true`:
  - Sets all signals immediately inside the lock
  - Clears all yellow timers
  - Schedules `_apply_priority_override()` call outside the lock
- `_apply_priority_override()` — sends GREEN to priority node, RED to all others **immediately**, bypassing the normal cycle
- `_clear_priority_override()` — logs event, sets `_priority_node = None`
- `_signal_engine()` and `_yellow_watchdog()` both check `_priority_node is not None` and skip their work entirely during priority mode
- Added `"priority_node"` to `get_snapshot()` output

**`dashboard.py` — Priority UI**
- Added `_build_priority_banner()` — a full-width red frame between the title bar and the body grid
- Banner only appears (`pack()`) when `priority_node` is set in the snapshot
- Banner text alternates between red and orange on every refresh tick (flash effect)
- Window background flashes dark red during priority mode
- Node table: added Priority column — shows `🚨 YES` in orange for the priority node, `—` for others
- Alert log: priority messages rendered in orange using a new `"priority"` text tag

---

## Configuration Reference

```python
# config.py — the one file that controls everything

CONTROLLER_HOST   = "192.168.1.100"  # ← MUST change on all machines to controller's LAN IP
                                      # Use "127.0.0.1" for single-system testing

NODE_SEND_PORT    = 5005   # controller listens here for node data
                           # open this port in controller's firewall (inbound UDP)

NODES = {
    "A": {"name": "North Junction", "port": 6001},  # open 6001 on Node A's firewall
    "B": {"name": "South Junction", "port": 6002},  # open 6002 on Node B's firewall
    "C": {"name": "East Junction",  "port": 6003},  # open 6003 on Node C's firewall
    "D": {"name": "West Junction",  "port": 6004},  # open 6004 on Node D's firewall
}

CONGESTION_THRESHOLD = 30   # vehicles; above this = CONGESTED (red alert)
HIGH_LOAD_THRESHOLD  = 20   # vehicles; above this = MODERATE  (yellow warning)
SIGNAL_CYCLE_SEC     = 5    # seconds between signal re-evaluations (5 for demo, 30 for production)
YELLOW_DURATION      = 3    # seconds a node stays YELLOW before going RED
NODE_SEND_INTERVAL   = 1    # seconds between each node's UDP packets
UPDATE_INTERVAL_MS   = 1000 # dashboard screen refresh in milliseconds
MAX_ALERT_LOG        = 100  # maximum number of alert entries kept in memory
```

---

## Running on One System

Change `CONTROLLER_HOST` to `127.0.0.1` in `config.py`, then open 5 terminals:

```bash
# Terminal 1 — start controller first
python dashboard.py

# Terminal 2
python node_sim.py A

# Terminal 3
python node_sim.py B

# Terminal 4
python node_sim.py C

# Terminal 5
python node_sim.py D
```

All 4 node GUIs open. Dashboard shows `● 4/4 nodes` within seconds. First GREEN signal assigned after `SIGNAL_CYCLE_SEC` seconds.

---

## Running on Multiple Systems

### Step 1 — Find controller IP

```bash
# Windows
ipconfig

# Linux / Mac
ip addr
```

Note the LAN IP, e.g. `192.168.1.100`.

### Step 2 — Edit config.py on ALL machines

```python
CONTROLLER_HOST = "192.168.1.100"   # your actual controller IP
SIGNAL_CYCLE_SEC = 5                # 5 for demo
```

### Step 3 — Open firewall ports

**On controller:**
```bash
# Windows (Administrator terminal)
netsh advfirewall firewall add rule name="Traffic_IN" protocol=UDP dir=in localport=5005 action=allow

# Linux
sudo ufw allow 5005/udp
```

**On each node machine (for the signal return channel):**
```bash
# Node A machine
netsh advfirewall firewall add rule name="Traffic_NodeA" protocol=UDP dir=in localport=6001 action=allow
# Node B → 6002, Node C → 6003, Node D → 6004
```

### Step 4 — Copy files

| Machine | Files needed |
|---|---|
| Controller | `config.py`, `server.py`, `dashboard.py` |
| Each node machine | `config.py`, `node_sim.py` |

### Step 5 — Run

```bash
# Controller
python dashboard.py

# Node machines (each on their own system)
python node_sim.py A   # system 1
python node_sim.py B   # system 2
python node_sim.py C   # system 3
python node_sim.py D   # system 4
```

---

## Running on VMs

### Recommended VM OS — Alpine Linux

Alpine Linux is the best choice for running 4 VMs simultaneously:

| OS | ISO Size | RAM per VM | Python setup |
|---|---|---|---|
| **Alpine Linux 3.19** | **130 MB** | **~50 MB** | `apk add python3 py3-pip tk` |
| Ubuntu Server 24.04 | 2.5 GB | ~200 MB | pre-installed |
| Debian 12 netinst | 400 MB | ~120 MB | `apt install python3` |

### VM Setup in VirtualBox

1. Create new VM: Linux → Other Linux 64-bit → 256 MB RAM → 4 GB disk
2. **Network: Bridged Adapter** ← critical, must NOT use NAT
   - Bridged gives the VM its own LAN IP so the controller can reach it
   - NAT hides the VM and blocks incoming UDP from the controller
3. Attach Alpine ISO → boot → run `setup-alpine`
4. After install: `apk add python3 py3-pip tk iproute2`
5. Copy `config.py` and `node_sim.py` via scp:

```bash
# Get VM IP
ip addr show eth0

# From another machine
scp config.py node_sim.py root@<vm-ip>:/root/
```

6. Clone the VM 3 times (VirtualBox right-click → Clone → Full clone → Generate new MACs)
7. On each clone, change the hostname:

```bash
echo 'node-b' > /etc/hostname && hostname node-b
```

### Running on Alpine VMs

SSH into each VM from the host machine and run:

```bash
# 4 terminals on host machine:
ssh root@192.168.1.101   →   python3 node_sim.py A
ssh root@192.168.1.102   →   python3 node_sim.py B
ssh root@192.168.1.103   →   python3 node_sim.py C
ssh root@192.168.1.104   →   python3 node_sim.py D
```

> **Note:** The node GUI (Tkinter) needs a display. On Alpine VMs without a desktop, run node_sim.py from a terminal with X11 forwarding (`ssh -X`) or use a VNC server. Alternatively, strip the GUI for pure CLI-only node operation.

---

## Network Simulation with tc netem

`tc netem` is a Linux kernel tool for injecting realistic network conditions into outgoing traffic. Run these commands on the **node VMs** to simulate bad links.

### Install on Alpine

```bash
apk add iproute2
```

### Common Commands

```bash
# Add 15% packet loss
tc qdisc add dev eth0 root netem loss 15%

# Add 100ms delay
tc qdisc add dev eth0 root netem delay 100ms

# Add delay with ±30ms jitter
tc qdisc add dev eth0 root netem delay 100ms 30ms

# Combine loss + delay + jitter (bad Wi-Fi simulation)
tc qdisc add dev eth0 root netem loss 8% delay 60ms 40ms

# Corrupt 1% of packets (tests JSON error handling)
tc qdisc add dev eth0 root netem corrupt 1%

# 100% loss (simulate dead node)
tc qdisc add dev eth0 root netem loss 100%

# Change rule without removing
tc qdisc change dev eth0 root netem loss 20%

# Remove all rules (restore normal)
tc qdisc del dev eth0 root

# Check current rules
tc qdisc show dev eth0
```

### Demo Scenarios

**Scenario A — Show packet loss detection:**
Apply 15% loss on Node-A → watch Packet Loss % rise on dashboard → remove → watch it stabilise.

**Scenario B — Show high latency:**
Apply 300ms delay on Node-B → watch Avg Latency climb → Last Seen column shows older timestamps.

**Scenario C — Bad wireless link:**
```bash
tc qdisc add dev eth0 root netem loss 8% delay 60ms 40ms
```
Both loss % and latency fluctuate. Then trigger Priority Vehicle — it still gets through, proving system resilience.

**Scenario D — Dead node:**
```bash
tc qdisc add dev eth0 root netem loss 100%
```
After 5s, node shows as OFFLINE. Signal engine skips it. Remove rule → node rejoins in 1 second.

**Scenario E — All nodes stressed:**
Apply 10% loss on all 4 VMs simultaneously, then trigger Priority Vehicle — controller still responds within 1–2 seconds due to the continuous 1-per-second packet stream.

---

## Signal Decision Logic

```
Every SIGNAL_CYCLE_SEC seconds:

1. Collect all nodes seen in last 10 seconds (active nodes)
2. busiest = node with max vehicle_count
3. For each active node:
     if node == busiest:
         assign GREEN
     else:
         assign RED
4. If a node was GREEN and is now becoming RED:
         assign YELLOW first
         start YELLOW timer
5. After YELLOW_DURATION seconds:
         _yellow_watchdog assigns RED

During PRIORITY mode:
   - Signal engine skips its cycle entirely
   - Yellow watchdog skips its cycle entirely
   - Priority node = GREEN
   - All others = RED (hard, immediate, no transition)
```

---

## Priority Vehicle System

| Step | What happens |
|---|---|
| User clicks 🚨 on node GUI | `_priority_active = True` |
| Next UDP packet | Includes `"priority": true` |
| Controller receives it | Detects `false → true` transition |
| Inside lock | Sets all `_assigned_signal`, clears yellow timers |
| Outside lock | Sends GREEN to priority node, RED to all others |
| Dashboard | Flashing banner appears, table row turns orange |
| Alert log | Orange priority event logged |
| User clicks ✅ CLEAR | `_priority_active = False` |
| Next packet | `"priority": false` |
| Controller | Sets `_priority_node = None`, logs clear event |
| Next cycle | Normal signal engine resumes on its next tick |

---

## Packet Loss — Will It Happen?

| Scenario | Expected Loss |
|---|---|
| Same LAN, wired | < 0.1% |
| Same LAN, Wi-Fi | 0.1% – 1% |
| VMs on same host, bridged adapter | < 0.05% |
| VMs on same host, NAT mode | Bidirectional communication breaks entirely |
| tc netem applied | Exactly what you configure |

The Packet Loss % on the dashboard is **cumulative from server start**. It does not go back down when loss stops — restart the dashboard to reset it.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Nodes not appearing in dashboard | Wrong `CONTROLLER_HOST` or firewall | Check config.py IP. Ping controller from node. Open port 5005. |
| Controller not sending signals back | NAT mode on VM or port blocked | Switch VM to Bridged Adapter. Open ports 6001–6004 on node machines. |
| All nodes OFFLINE immediately | UDP blocked both ways | Run `nc -ul 5005` on controller, `echo x \| nc -u <ip> 5005` from node to verify. |
| GREEN never appears | `SIGNAL_CYCLE_SEC` too high | Change to `5` in config.py and restart. |
| Signal engine frozen (no GREEN ever) | Deadlock bug (old version) | Use the fixed `server.py` where `_add_alert` is called outside the lock. |
| Node GUI not opening | tkinter not installed | `apk add tk` (Alpine) or `sudo apt install python3-tk` (Ubuntu). |
| `tc` command not found | iproute2 missing | `apk add iproute2` (Alpine) or `apt install iproute2` (Ubuntu). |
| 4 VMs too slow | Host RAM too low | Reduce each VM to 256 MB RAM. Use Alpine — it uses ~50 MB idle. |
| Priority button not working | Old node_sim.py without GUI | Use the updated node_sim.py from Version 4. |

---

## Requirements

- Python 3.8 or higher
- `tkinter` (included with standard Python on Windows and macOS; `sudo apt install python3-tk` on Ubuntu; `apk add tk` on Alpine)
- No external Python packages — uses `socket`, `json`, `time`, `threading`, `tkinter` only
- For tc netem: Linux node machines with `iproute2` installed

---

## Port Reference

| Port | Direction | Purpose |
|---|---|---|
| `5005` | Node → Controller | All 4 nodes send traffic data here |
| `6001` | Controller → Node A | Controller sends signal commands to Node A |
| `6002` | Controller → Node B | Controller sends signal commands to Node B |
| `6003` | Controller → Node C | Controller sends signal commands to Node C |
| `6004` | Controller → Node D | Controller sends signal commands to Node D |
