# 🚦 Smart Traffic Signal Monitoring System

A distributed traffic monitoring system that simulates multiple Raspberry Pi nodes reporting real-time traffic data to a central control unit over UDP. Built entirely in Python — no hardware required.

> **Course Project — Computer Networks (CN Lab)**
> PES University | B.Tech CSE | Semester 4

---

## 📌 Overview

This project simulates a network of traffic signal controllers (Raspberry Pi nodes) that periodically send sensor data — vehicle count and signal status — to a central server using **UDP sockets**. The central unit aggregates the data, detects congestion, generates alerts, and displays everything on a **live Tkinter GUI dashboard**.

```
Simulated Node A ─┐
Simulated Node B ──►  UDP (port 5005)  ──►  Central Server  ──►  Live Dashboard
Simulated Node C ─┘
```

---

## ✨ Features

- **UDP-based communication** between simulated nodes and the central server
- **Multi-threaded server** that handles multiple nodes simultaneously
- **Live Tkinter dashboard** with 4 real-time panels:
  - Packet stats and throughput meter
  - Live node status table (vehicle count, signal state, congestion status)
  - Congestion alert log with timestamps
  - Real-time bar chart of vehicle counts per node
- **Automatic congestion detection** with threshold-based alerting
- **Performance stress test** — measures throughput, packet loss, and latency under high data rates
- **Pure Python** — no external libraries, no hardware, runs on Windows

---

## 🗂️ Project Structure

```
traffic_monitor/
├── config.py         # Shared constants (port, thresholds, node list)
├── node_sim.py       # Simulated Raspberry Pi node (run one per terminal)
├── server.py         # UDP server + data aggregation engine
├── dashboard.py      # Tkinter GUI dashboard (auto-starts the server)
└── stress_test.py    # High-load performance evaluation tool
```

---

## ⚙️ Requirements

- Python 3.8 or higher
- No external packages required — uses only Python standard library:
  - `socket`, `threading`, `json`, `time`, `tkinter`, `sys`, `random`

---

## 🚀 How to Run

### Step 1 — Clone the repository

```bash
git clone https://github.com/<your-username>/smart-traffic-monitor.git
cd smart-traffic-monitor
```

### Step 2 — Open 4 terminals side by side

**Terminal 1 — Launch the dashboard (also starts the server)**
```bash
python dashboard.py
```

**Terminal 2 — Start Node A**
```bash
python node_sim.py A
```

**Terminal 3 — Start Node B**
```bash
python node_sim.py B
```

**Terminal 4 — Start Node C**
```bash
python node_sim.py C
```

The dashboard will begin updating within 1 second of nodes coming online.

### Step 3 — Run the stress test (optional)

While the dashboard is open, open a 5th terminal:
```bash
python stress_test.py
```

This spawns 10 simulated nodes sending packets as fast as possible for 10 seconds and prints a throughput/loss summary.

---

## 🖥️ Dashboard Preview

The dashboard is a dark-themed Tkinter window divided into 4 panels:

| Panel | Description |
|---|---|
| **Packet Stats** | Packets/sec, total received, packet loss %, avg latency, active nodes, uptime |
| **Live Node Table** | Per-node vehicle count, signal state (RED/GREEN/YELLOW), congestion status |
| **Alert Log** | Timestamped congestion and high-load alerts, color-coded by severity |
| **Real-Time Chart** | Scrolling bar chart of vehicle counts across the last 20 seconds |

---

## 📡 System Design

### Node Simulator (`node_sim.py`)

Each node runs as an independent Python process. It:
- Cycles through `GREEN → YELLOW → RED → YELLOW` on a timed schedule
- Generates vehicle counts that reflect the current signal state (higher on RED, lower on GREEN)
- Serializes data as JSON and sends it via UDP every second
- Embeds a sequence number and timestamp in every packet for loss/latency tracking

### Central Server (`server.py`)

- Binds a UDP socket on `localhost:5005`
- Runs a **background listener thread** that decodes incoming JSON packets
- Maintains a shared `node_data` dictionary protected by a `threading.Lock`
- Tracks rolling latency (last 50 samples), packets/sec, and sequence-based packet loss
- Fires alerts only on **status transitions** (e.g. OK → CONGESTED) to avoid alert spam
- Exposes a `get_snapshot()` function that returns a safe copy of all state

### Dashboard (`dashboard.py`)

- Imports and starts the server on launch
- Uses `root.after(1000, refresh)` for a non-blocking 1-second refresh cycle
- Draws the bar chart manually using `tk.Canvas.create_rectangle()`
- Alert log uses a `tk.Text` widget with color tags for critical/warning levels

### Stress Tester (`stress_test.py`)

- Spawns N threads (default: 10), each sending UDP packets continuously for 10 seconds
- Embeds sequence numbers to let the server detect packet loss
- Prints: total sent, duration, throughput (packets/sec), and per-node average

---

## 📊 Configuration

All tunable parameters live in `config.py`:

| Parameter | Default | Description |
|---|---|---|
| `UDP_PORT` | `5005` | Port the server listens on |
| `CONGESTION_THRESHOLD` | `30` | Vehicle count that triggers a CONGESTED alert |
| `HIGH_LOAD_THRESHOLD` | `20` | Vehicle count that triggers a MODERATE warning |
| `UPDATE_INTERVAL_MS` | `1000` | Dashboard refresh rate in milliseconds |
| `MAX_ALERT_LOG` | `100` | Maximum number of alerts kept in memory |

---

## 🧪 Performance Evaluation

The stress test (`stress_test.py`) evaluates the system under high data rates:

- **Throughput** — total packets received per second at the server
- **Packet loss** — gap detection using per-node sequence numbers
- **Latency** — send timestamp embedded in each packet, delta computed on receipt

Sample output:
```
Stress test: 10 nodes × 10s
----------------------------------------
Total packets sent :  48,320
Duration           :  10.03s
Throughput         :  4,817 packets/sec
Per node avg       :  4,832 packets
----------------------------------------
Check the dashboard for server-side received count and loss %.
```

---

## 🔌 How UDP is Used

This project intentionally uses **UDP** (not TCP) to reflect real-world IoT and embedded systems constraints:

- Traffic sensors send small, frequent datagrams where delivery guarantee is not critical
- UDP has significantly lower overhead than TCP, enabling higher throughput
- The system tolerates occasional packet loss gracefully — the dashboard simply shows the last known state
- Sequence numbers are used to measure loss without relying on TCP's built-in mechanisms

---

## 📝 Notes

- All nodes connect to `127.0.0.1` (localhost). To run across real machines, change `SERVER_HOST` in `config.py` to the server's IP and ensure the firewall allows UDP on port 5005.
- The Raspberry Pi simulation is behavioral — signal timing, vehicle count distributions, and sensor reporting intervals are modeled to reflect realistic embedded hardware behavior.
- The dashboard uses only `tkinter` (Python built-in) — no `pip install` required.

---

## 👤 Author

**Eshwar** — [GitHub](https://github.com/ESHWAR1024) · [LinkedIn](https://linkedin.com/in/)

B.Tech Computer Science and Engineering
PES University, Bangalore

---

## 📄 License

This project is for academic purposes. Feel free to use or adapt it with attribution.
