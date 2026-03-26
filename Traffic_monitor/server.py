# server.py  — runs on the CONTROLLER system only
#
# Responsibilities:
#   1. Receive UDP packets from all 4 road nodes  (port 5005)
#   2. Detect HIGH-PRIORITY flag → immediately override all signals
#   3. Normal mode: decide GREEN by highest vehicle count every SIGNAL_CYCLE_SEC
#   4. Send signal commands back to each node     (node's own port)
#   5. Expose get_snapshot() for the dashboard

import socket
import json
import time
import threading
from config import (
    NODE_SEND_PORT, NODES,
    CONGESTION_THRESHOLD, HIGH_LOAD_THRESHOLD,
    MAX_ALERT_LOG, SIGNAL_CYCLE_SEC, YELLOW_DURATION
)

# ── Shared state ──────────────────────────────────────────────────────────────
lock = threading.Lock()

node_data = {}
# node_data[node_id] = {
#   "location", "vehicle_count", "signal", "status",
#   "last_seen", "node_ip", "priority"
# }

stats = {
    "total_received":   0,
    "packets_per_sec":  0,
    "packet_loss_pct":  0.0,
    "avg_latency_ms":   0.0,
    "start_time":       time.time(),
}

alert_log      = []
_latency_buf   = []
_pps_counter   = 0
_loss_expected = {}

# ── Signal state ──────────────────────────────────────────────────────────────
# _assigned_signal[node_id] = "GREEN" | "YELLOW" | "RED"
_assigned_signal = {nid: "RED" for nid in NODES}
_yellow_timers   = {}    # node_id → timestamp YELLOW started

# Priority override tracking
# _priority_node = node_id currently in priority mode, or None
_priority_node   = None

# UDP socket for pushing commands to nodes
_cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _compute_status(vc):
    if vc >= CONGESTION_THRESHOLD: return "CONGESTED"
    if vc >= HIGH_LOAD_THRESHOLD:  return "MODERATE"
    return "OK"


def _add_alert(node_id, message, level="critical"):
    entry = {
        "time_str": time.strftime("%H:%M:%S"),
        "node_id":  node_id,
        "message":  message,
        "level":    level,
    }
    with lock:
        alert_log.insert(0, entry)
        if len(alert_log) > MAX_ALERT_LOG:
            alert_log.pop()


def _send_signal(node_id, signal, node_ip):
    """Push a signal command UDP packet to a road node."""
    if not node_ip:
        return
    port = NODES[node_id]["port"]
    cmd  = json.dumps({"node_id": node_id, "signal": signal}).encode()
    try:
        _cmd_sock.sendto(cmd, (node_ip, port))
    except Exception as e:
        print(f"[Server] Failed to send to Node-{node_id} @ {node_ip}:{port} — {e}")


# ── Priority override ─────────────────────────────────────────────────────────
def _apply_priority_override(priority_nid, all_node_data):
    """
    Immediately:
      - priority node  → GREEN
      - all others     → RED  (hard override, no YELLOW transition)
    Called OUTSIDE the lock.
    """
    global _priority_node
    for nid, info in all_node_data.items():
        new_sig = "GREEN" if nid == priority_nid else "RED"
        _send_signal(nid, new_sig, info.get("node_ip"))

    _add_alert(
        priority_nid,
        f"🚨 PRIORITY VEHICLE at Node-{priority_nid} — ALL others forced RED",
        level="critical"
    )
    print(f"[Server] 🚨 Priority override: Node-{priority_nid} → GREEN, all others → RED")


def _clear_priority_override(priority_nid):
    """
    Priority cleared — log the event and let the normal signal engine
    take over on its next cycle.
    """
    _add_alert(
        priority_nid,
        f"✅ Priority cleared at Node-{priority_nid} — resuming normal signal control",
        level="warning"
    )
    print(f"[Server] ✅ Priority cleared for Node-{priority_nid}, normal mode resumed")


# ── Packet handler ────────────────────────────────────────────────────────────
def _handle_packet(data, addr):
    global _pps_counter, _priority_node

    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return

    node_id = payload.get("node_id")
    if not node_id or node_id not in NODES:
        return

    recv_time  = time.time()
    send_time  = payload.get("timestamp", recv_time)
    latency_ms = max(0.0, (recv_time - send_time) * 1000)
    seq        = payload.get("seq", 0)
    vc         = payload.get("vehicle_count", 0)
    status     = _compute_status(vc)
    node_ip    = addr[0]
    priority   = payload.get("priority", False)   # ← read priority flag

    # --- Decide if priority state changed (needs action outside lock) ---------
    priority_action  = None   # "start" | "clear" | None
    priority_snap    = {}     # snapshot of all node_data for sending signals

    with lock:
        # Latency
        _latency_buf.append(latency_ms)
        if len(_latency_buf) > 50:
            _latency_buf.pop(0)
        stats["avg_latency_ms"] = round(sum(_latency_buf) / len(_latency_buf), 2)

        # Packet loss
        if node_id in _loss_expected:
            exp = _loss_expected[node_id]
            if seq > exp:
                lost  = seq - exp
                total = stats["total_received"] + lost
                stats["packet_loss_pct"] = round(lost / max(total, 1) * 100, 2)
        _loss_expected[node_id] = seq + 1

        stats["total_received"] += 1
        _pps_counter += 1

        prev_status   = node_data.get(node_id, {}).get("status")
        prev_priority = node_data.get(node_id, {}).get("priority", False)

        # Update node record
        node_data[node_id] = {
            "location":      payload.get("location", "Unknown"),
            "vehicle_count": vc,
            "signal":        _assigned_signal.get(node_id, "RED"),
            "status":        status,
            "last_seen":     recv_time,
            "node_ip":       node_ip,
            "priority":      priority,
        }

        # Detect priority transitions
        if priority and not prev_priority:
            # Node just activated priority
            if _priority_node is None:
                _priority_node = node_id
                # Update assigned signals immediately inside lock
                for nid in NODES:
                    _assigned_signal[nid] = "GREEN" if nid == node_id else "RED"
                # Clear any yellow timers — hard override
                _yellow_timers.clear()
                priority_action = "start"
                priority_snap   = {k: dict(v) for k, v in node_data.items()}

        elif not priority and prev_priority:
            # Node just cleared priority
            if _priority_node == node_id:
                _priority_node = None
                priority_action = "clear"

        # Normal congestion alerts (only in non-priority mode)
        if _priority_node is None:
            if status == "CONGESTED" and prev_status != "CONGESTED":
                # Will add alert outside lock
                pass
            elif status == "MODERATE" and prev_status not in ("MODERATE", "CONGESTED"):
                pass

    # --- Actions outside the lock --------------------------------------------
    if priority_action == "start":
        _apply_priority_override(node_id, priority_snap)

    elif priority_action == "clear":
        _clear_priority_override(node_id)

    elif priority_action is None and _priority_node is None:
        # Normal congestion alerts
        if status == "CONGESTED" and prev_status != "CONGESTED":
            _add_alert(node_id,
                       f"Node-{node_id} — {vc} vehicles — CONGESTION DETECTED",
                       level="critical")
        elif status == "MODERATE" and prev_status not in ("MODERATE", "CONGESTED"):
            _add_alert(node_id,
                       f"Node-{node_id} — {vc} vehicles — HIGH LOAD",
                       level="warning")


# ── Normal signal engine ──────────────────────────────────────────────────────
def _signal_engine():
    """
    Runs every SIGNAL_CYCLE_SEC seconds.
    Skipped entirely when a priority override is active.
    Strategy: highest vehicle count → GREEN, others → RED.
    """
    while True:
        time.sleep(SIGNAL_CYCLE_SEC)

        # Step 1: decide changes (inside lock)
        changes = {}
        with lock:
            # Skip if priority override is active
            if _priority_node is not None:
                continue
            if not node_data:
                continue

            now    = time.time()
            active = {
                nid: dict(info) for nid, info in node_data.items()
                if now - info["last_seen"] < 10
            }
            if not active:
                continue

            busiest = max(active, key=lambda nid: active[nid]["vehicle_count"])

            for nid, info in active.items():
                old = _assigned_signal.get(nid, "RED")
                new = "GREEN" if nid == busiest else "RED"

                if new != old:
                    if old == "GREEN":
                        _assigned_signal[nid] = "YELLOW"
                        _yellow_timers[nid]   = now
                        changes[nid] = ("YELLOW", info)
                    else:
                        _assigned_signal[nid] = new
                        changes[nid] = (new, info)

        # Step 2: send + alert (outside lock)
        for nid, (sig, info) in changes.items():
            _send_signal(nid, sig, info.get("node_ip"))
            if sig == "GREEN":
                _add_alert(nid,
                           f"Node-{nid} → GREEN (highest traffic: {info['vehicle_count']} vehicles)",
                           level="warning")
            elif sig == "YELLOW":
                _add_alert(nid,
                           f"Node-{nid} → YELLOW (transitioning to RED)",
                           level="warning")


def _yellow_watchdog():
    """Advances YELLOW → RED after YELLOW_DURATION seconds. Skips during priority mode."""
    while True:
        time.sleep(1)
        now     = time.time()
        expired = {}

        with lock:
            if _priority_node is not None:
                continue   # priority mode handles signals directly
            for nid, ts in list(_yellow_timers.items()):
                if now - ts >= YELLOW_DURATION:
                    _assigned_signal[nid] = "RED"
                    del _yellow_timers[nid]
                    info = node_data.get(nid, {})
                    expired[nid] = info.get("node_ip")

        for nid, node_ip in expired.items():
            _send_signal(nid, "RED", node_ip)


# ── Background threads ────────────────────────────────────────────────────────
def _pps_ticker():
    global _pps_counter
    while True:
        time.sleep(1)
        with lock:
            stats["packets_per_sec"] = _pps_counter
            _pps_counter = 0


def _listen():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", NODE_SEND_PORT))
    print(f"[Server] Listening for node packets on port {NODE_SEND_PORT}")
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            _handle_packet(data, addr)
        except Exception as e:
            print(f"[Server] Recv error: {e}")


def start():
    """Start all server background threads. Call once from dashboard."""
    threading.Thread(target=_listen,          daemon=True).start()
    threading.Thread(target=_pps_ticker,      daemon=True).start()
    threading.Thread(target=_signal_engine,   daemon=True).start()
    threading.Thread(target=_yellow_watchdog, daemon=True).start()
    print("[Server] All threads started (listener, PPS, signal engine, yellow watchdog).")


def get_snapshot():
    """Thread-safe snapshot for the dashboard."""
    with lock:
        return {
            "node_data":    {k: dict(v) for k, v in node_data.items()},
            "stats":        dict(stats),
            "alert_log":    list(alert_log),
            "uptime":       int(time.time() - stats["start_time"]),
            "signal_state": dict(_assigned_signal),
            "priority_node": _priority_node,   # ← NEW: which node is in priority mode
        }