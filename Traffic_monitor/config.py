# config.py — shared constants (controller + all node systems)

# ── Network ──────────────────────────────────────────────────────────────────
# On node systems: set CONTROLLER_HOST to the controller's actual LAN IP
# e.g. "192.168.1.100"
CONTROLLER_HOST   =  "127.0.0.1"      # ← CHANGE to controller's IP on node machines
NODE_SEND_PORT    = 5005              # nodes → controller (controller listens here)
SIGNAL_RECV_PORT  = 5006             # controller → nodes  (each node listens here)

# ── Thresholds ───────────────────────────────────────────────────────────────
CONGESTION_THRESHOLD = 30
HIGH_LOAD_THRESHOLD  = 20
MAX_ALERT_LOG        = 100

# ── Timing ───────────────────────────────────────────────────────────────────
UPDATE_INTERVAL_MS   = 1000    # dashboard refresh
NODE_SEND_INTERVAL   = 1       # seconds between node packets
SIGNAL_CYCLE_SEC     = 5      # how often controller re-evaluates all signals

# ── 4 Road Nodes ─────────────────────────────────────────────────────────────
NODES = {
    "A": {"name": "North Junction",  "port": 6001},
    "B": {"name": "South Junction",  "port": 6002},
    "C": {"name": "East Junction",   "port": 6003},
    "D": {"name": "West Junction",   "port": 6004},
}
# Each node listens on its own port for signal commands from the controller.
# The controller sends a UDP packet to (node_ip, NODES[id]["port"]).
# Nodes must tell the controller their IP — it's auto-captured from incoming packets.

# ── Signal logic ─────────────────────────────────────────────────────────────
# Controller assigns GREEN to the highest-traffic node, RED to the rest.
# YELLOW is a 3-second transition inserted by the controller between changes.
YELLOW_DURATION = 3    # seconds a node stays YELLOW before switching