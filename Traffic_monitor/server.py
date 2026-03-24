# server.py
import socket
import json
import time
import threading
from config import SERVER_HOST, UDP_PORT, CONGESTION_THRESHOLD, HIGH_LOAD_THRESHOLD, MAX_ALERT_LOG

# ── Shared state (thread-safe via lock) ─────────────────────────────────────
lock = threading.Lock()

node_data = {}
# node_data[node_id] = {
#   "location", "vehicle_count", "signal",
#   "status", "last_seen", "seq_last"
# }

stats = {
    "total_received": 0,
    "packets_per_sec": 0,
    "packet_loss_pct": 0.0,
    "avg_latency_ms": 0.0,
    "start_time": time.time(),
}

alert_log = []
# alert_log entries: {"time_str", "node_id", "message", "level"}  level = "critical"/"warning"

_seq_tracker = {}       # node_id -> last seq seen
_latency_samples = []   # rolling window of latency values
_pps_counter = 0        # packets counted in current second
_loss_expected = {}     # node_id -> expected next seq


def _compute_status(vehicle_count):
    if vehicle_count >= CONGESTION_THRESHOLD:
        return "CONGESTED"
    elif vehicle_count >= HIGH_LOAD_THRESHOLD:
        return "MODERATE"
    return "OK"


def _add_alert(node_id, message, level="critical"):
    entry = {
        "time_str": time.strftime("%H:%M:%S"),
        "node_id": node_id,
        "message": message,
        "level": level,
    }
    with lock:
        alert_log.insert(0, entry)
        if len(alert_log) > MAX_ALERT_LOG:
            alert_log.pop()


def _handle_packet(data, addr):
    global _pps_counter
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return

    node_id = payload.get("node_id")
    if not node_id:
        return

    recv_time = time.time()
    send_time = payload.get("timestamp", recv_time)
    latency_ms = max(0.0, (recv_time - send_time) * 1000)

    seq = payload.get("seq", 0)
    vehicle_count = payload.get("vehicle_count", 0)
    status = _compute_status(vehicle_count)

    with lock:
        # Latency rolling window (keep last 50)
        _latency_samples.append(latency_ms)
        if len(_latency_samples) > 50:
            _latency_samples.pop(0)
        stats["avg_latency_ms"] = round(sum(_latency_samples) / len(_latency_samples), 2)

        # Packet loss tracking
        if node_id in _loss_expected:
            expected = _loss_expected[node_id]
            if seq > expected:
                lost = seq - expected
                total_expected = stats["total_received"] + lost
                stats["packet_loss_pct"] = round(lost / max(total_expected, 1) * 100, 2)
        _loss_expected[node_id] = seq + 1

        # Counters
        stats["total_received"] += 1
        _pps_counter += 1

        # Node state update
        prev_status = node_data.get(node_id, {}).get("status")
        node_data[node_id] = {
            "location": payload.get("location", "Unknown"),
            "vehicle_count": vehicle_count,
            "signal": payload.get("signal", "UNKNOWN"),
            "status": status,
            "last_seen": recv_time,
        }

    # Fire alert only on status transitions into bad states
    if status == "CONGESTED" and prev_status != "CONGESTED":
        _add_alert(node_id,
                   f"Node-{node_id} — vehicles: {vehicle_count} — CONGESTION DETECTED",
                   level="critical")
    elif status == "MODERATE" and prev_status not in ("MODERATE", "CONGESTED"):
        _add_alert(node_id,
                   f"Node-{node_id} — vehicles: {vehicle_count} — HIGH LOAD WARNING",
                   level="warning")


def _pps_ticker():
    """Updates packets/sec stat every second."""
    global _pps_counter
    while True:
        time.sleep(1)
        with lock:
            stats["packets_per_sec"] = _pps_counter
            _pps_counter = 0


def _listen():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((SERVER_HOST, UDP_PORT))
    print(f"[Server] Listening on {SERVER_HOST}:{UDP_PORT}")
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            _handle_packet(data, addr)
        except Exception as e:
            print(f"[Server] Error: {e}")


def start():
    """Call this once to start the server in background threads."""
    threading.Thread(target=_listen, daemon=True).start()
    threading.Thread(target=_pps_ticker, daemon=True).start()
    print("[Server] Background threads started.")


def get_snapshot():
    """Returns a safe copy of all state for the dashboard to read."""
    with lock:
        return {
            "node_data": dict(node_data),
            "stats": dict(stats),
            "alert_log": list(alert_log),
            "uptime": int(time.time() - stats["start_time"]),
        }