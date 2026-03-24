# config.py

SERVER_HOST = "127.0.0.1"
UDP_PORT = 5005
CONGESTION_THRESHOLD = 30
HIGH_LOAD_THRESHOLD = 20
UPDATE_INTERVAL_MS = 1000
MAX_ALERT_LOG = 100

NODES = {
    "A": "Intersection 1",
    "B": "Intersection 2",
    "C": "Intersection 3",
}

SIGNAL_CYCLE = ["GREEN", "GREEN", "GREEN", "YELLOW", "RED", "RED", "RED", "YELLOW"]
SIGNAL_DURATIONS = {
    "GREEN": 6,
    "YELLOW": 2,
    "RED": 6,
}