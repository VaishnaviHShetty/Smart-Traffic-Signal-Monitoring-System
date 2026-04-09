# 🚦 Smart Traffic Monitor

A distributed, real-time traffic signal control system built on **UDP socket programming** as a Computer Networks project. Up to 4 road-side nodes report live vehicle counts to a central controller over a LAN. The controller dynamically assigns signals and handles priority vehicles (ambulances, fire trucks, police) with a weighted preemptive queue.

---

## 📸 System Overview

```
┌─────────────┐        UDP :5005        ┌──────────────────────┐
│  Node A     │ ──────────────────────► │                      │
│  Node B     │ ──────────────────────► │   Controller         │
│  Node C     │ ──────────────────────► │   server.py +        │
│  Node D     │ ──────────────────────► │   dashboard.py       │
└─────────────┘                         │                      │
      ▲  ▲  ▲  ▲   UDP :6001-6004       └──────────────────────┘
      └──┴──┴──┴─────────────────────────────────── signals ◄──┘
```

- **Star topology** — all nodes talk only to the controller
- **Node → Controller** : JSON payload every 1 second on port `5005`
- **Controller → Node** : signal commands (GREEN / YELLOW / RED) on dedicated ports `6001–6004`

---

## ✨ Features

- 🔴🟡🟢 **Dynamic signal control** — controller gives GREEN to the busiest junction every cycle
- 🚨 **Priority vehicle system** — ambulances/fire trucks/police preempt normal control instantly
- ⚖️ **Weighted priority queue** — 4-tier hierarchy with FCFS tiebreak within same tier
- 🔄 **Preemption** — higher-tier vehicle arriving mid-service bumps the active node back to queue
- 📊 **Live dashboard** — real-time vehicle counts, signal states, packet stats, alert log, bar chart
- 📉 **Packet loss detection** — application-layer sequence numbers track dropped UDP packets
- ⏱️ **Latency measurement** — one-way latency computed from embedded timestamps
- 🖥️ **Multi-machine** — designed to run across multiple computers on a LAN

---

## 🗂️ File Structure

```
Traffic_monitor/
├── config.py        # Shared constants — ports, thresholds, node definitions
├── node_sim.py      # Runs on each road-side machine (UDP client + GUI)
├── server.py        # Runs on controller (UDP server + signal logic)
├── dashboard.py     # Runs on controller alongside server.py (Tkinter GUI)
└── stress_test.py   # Optional — benchmarks server throughput and packet loss
```

---

## 🧰 Requirements

- Python 3.8+
- Standard library only — `socket`, `threading`, `tkinter`, `json`, `time`
- No `pip install` needed
- All machines on the same LAN (or `127.0.0.1` for single-machine demo)

---

## ⚙️ Configuration

Open `config.py` and set `CONTROLLER_HOST` to your controller machine's IP:

```python
# config.py
CONTROLLER_HOST = "192.168.1.100"   # ← change this on node machines
```

Everything else works out of the box.

---

## 🚀 Running the System

### Controller Machine
```bash
python dashboard.py       # launches server + GUI together
```

### Each Road Node (separate terminals or separate PCs)
```bash
python node_sim.py A      # North Junction
python node_sim.py B      # South Junction
python node_sim.py C      # East Junction
python node_sim.py D      # West Junction
```

### Single-Machine Demo (5 terminals)
```bash
# Terminal 1
python dashboard.py

# Terminals 2–5
python node_sim.py A
python node_sim.py B
python node_sim.py C
python node_sim.py D
```

---

## 🚨 Priority Vehicle System

| Tier | Vehicle Types | Behaviour |
|------|--------------|-----------|
| T1 — Highest | Ambulance, Fire Truck, Police | Preempts any active priority node |
| T2 | Military Convoy, Disaster Response | Preempts T3 and T4 |
| T3 | Minister Convoy, VIP Convoy | Preempts T4 only |
| T4 — Lowest | Official Vehicle, Unknown | Queues behind all others |

**How to trigger:**
1. On any `node_sim.py` window, select a vehicle type from the dropdown
2. Click **PRIORITY VEHICLE** — that node gets GREEN, all others go RED
3. Dashboard shows a flashing alert banner and logs the event
4. If another node triggers priority while one is active, it joins the sorted queue
5. Click **CLEAR** to release — next queued node is promoted automatically

---

## 📡 CN Concepts Covered

| Concept | Implementation |
|---------|---------------|
| UDP Sockets | `socket.SOCK_DGRAM` — connectionless, fire-and-forget |
| Port Multiplexing | Port 5005 (inbound), ports 6001–6004 (per-node commands) |
| Packet Design | Custom JSON application-layer protocol |
| Sequence Numbers | App-layer `seq` field for loss detection over UDP |
| One-Way Latency | `timestamp` embedded in each packet, measured on arrival |
| Packet Loss % | Per-node expected-seq tracking, gap = lost packets |
| Star Topology | All nodes connect only to controller |
| Concurrent Threads | 4 server threads with `threading.Lock()` for safety |
| Dynamic IP Discovery | Server learns node IP from `addr` of received packet |
| Priority Queueing | Weighted multi-level queue with tier-based preemption |

---

## 🧪 Stress Test (Optional)

```bash
python stress_test.py
```

Spawns 20 virtual nodes hammering the server for 10 seconds. Reports total packets sent, throughput (packets/sec), and per-node average. Check the dashboard for received count and loss %.

---

## 🔌 Port Reference

| Port | Direction | Purpose |
|------|-----------|---------|
| 5005 | Node → Controller | All nodes send traffic data here |
| 6001 | Controller → Node A | Signal commands to North Junction |
| 6002 | Controller → Node B | Signal commands to South Junction |
| 6003 | Controller → Node C | Signal commands to East Junction |
| 6004 | Controller → Node D | Signal commands to West Junction |

---

## 📊 Dashboard Panels

| Panel | What it shows |
|-------|--------------|
| Packet Stats | Packets/sec, total received, loss %, avg latency, active nodes, uptime |
| Live Node Table | Per-node vehicle count, signal state, priority status, queue position |
| Alert Log | Congestion events, signal changes, priority activations, preemptions |
| Real-Time Chart | 30-tick rolling bar chart of vehicle counts per node |
