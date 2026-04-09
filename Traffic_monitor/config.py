# config.py — shared constants (controller + all node systems)

# ── Network ──────────────────────────────────────────────────────────────────
CONTROLLER_HOST   = "127.0.0.1"      # <- CHANGE to controller's IP on node machines
NODE_SEND_PORT    = 5005
SIGNAL_RECV_PORT  = 5006

# ── Thresholds ───────────────────────────────────────────────────────────────
CONGESTION_THRESHOLD = 30
HIGH_LOAD_THRESHOLD  = 20
MAX_ALERT_LOG        = 100

# ── Timing ───────────────────────────────────────────────────────────────────
UPDATE_INTERVAL_MS   = 1000
NODE_SEND_INTERVAL   = 1
SIGNAL_CYCLE_SEC     = 5

# ── 4 Road Nodes ─────────────────────────────────────────────────────────────
NODES = {
    "A": {"name": "North Junction", "port": 6001},
    "B": {"name": "South Junction", "port": 6002},
    "C": {"name": "East Junction",  "port": 6003},
    "D": {"name": "West Junction",  "port": 6004},
}

# ── Signal logic ─────────────────────────────────────────────────────────────
YELLOW_DURATION = 3

# ── Priority vehicle types & tiers ───────────────────────────────────────────
# Lower tier number = higher priority.
# Tier 1 always preempts Tier 2, 3, 4.
# Same tier = FCFS (first come, first served).
#
# Add or rename entries here to match your demo scenario.
# "color" is used by the dashboard for row highlighting.

VEHICLE_TYPES = {
    "ambulance": {"tier": 1, "label": "Ambulance",        "color": "#ff4466"},
    "fire":      {"tier": 1, "label": "Fire Truck",        "color": "#ff4466"},
    "police":    {"tier": 1, "label": "Police Emergency",  "color": "#ff4466"},
    "military":  {"tier": 2, "label": "Military Convoy",   "color": "#ff9944"},
    "disaster":  {"tier": 2, "label": "Disaster Response", "color": "#ff9944"},
    "minister":  {"tier": 3, "label": "Minister Convoy",   "color": "#c084fc"},
    "vip":       {"tier": 3, "label": "VIP Convoy",        "color": "#c084fc"},
    "official":  {"tier": 4, "label": "Official Vehicle",  "color": "#4dc8ff"},
    "unknown":   {"tier": 4, "label": "Priority Vehicle",  "color": "#5a5a90"},
}

DEFAULT_VEHICLE_TIER = 4