# server.py  — runs on the CONTROLLER system only
#
# Responsibilities:
#   1. Receive UDP packets from all 4 road nodes  (port 5005)
#   2. Priority handling: weighted tier queue with preemption
#      - Tier 1 (ambulance/fire/police) always preempts Tier 2, 3, 4
#      - Same tier = FCFS order preserved
#      - Higher tier arriving mid-service preempts active node back to queue
#   3. Normal mode: GREEN to busiest road every SIGNAL_CYCLE_SEC
#   4. Send signal commands back to each node     (node's own port)
#   5. Expose get_snapshot() for the dashboard

import socket
import json
import time
import threading
from config import (
    NODE_SEND_PORT, NODES,
    CONGESTION_THRESHOLD, HIGH_LOAD_THRESHOLD,
    MAX_ALERT_LOG, SIGNAL_CYCLE_SEC, YELLOW_DURATION,
    VEHICLE_TYPES, DEFAULT_VEHICLE_TIER
)

# ── Shared state ──────────────────────────────────────────────────────────────
lock = threading.Lock()

node_data = {}
# node_data[node_id] = {
#   "location", "vehicle_count", "signal", "status",
#   "last_seen", "node_ip", "priority", "vehicle_type"
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
_assigned_signal = {nid: "RED" for nid in NODES}
_yellow_timers   = {}

# ── Priority queue state ──────────────────────────────────────────────────────
# Each entry in _priority_queue is a dict:
#   {
#     "node_id":      str,
#     "vehicle_type": str,
#     "tier":         int,   (1=highest, 4=lowest)
#     "timestamp":    float  (arrival time — FCFS tiebreak within same tier)
#   }
#
# Queue is always kept sorted: primary = tier ASC, secondary = timestamp ASC
# _active_priority_node: node_id of the one currently being served, or None

_priority_queue       = []
_active_priority_node = None

# UDP socket for pushing commands to nodes
_cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _compute_status(vc):
    if vc >= CONGESTION_THRESHOLD: return "CONGESTED"
    if vc >= HIGH_LOAD_THRESHOLD:  return "MODERATE"
    return "OK"


def _get_tier(vehicle_type):
    return VEHICLE_TYPES.get(vehicle_type, {}).get("tier", DEFAULT_VEHICLE_TIER)


def _get_label(vehicle_type):
    return VEHICLE_TYPES.get(vehicle_type, {}).get("label", str(vehicle_type))


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
    if not node_ip:
        return
    port = NODES[node_id]["port"]
    cmd  = json.dumps({"node_id": node_id, "signal": signal}).encode()
    try:
        _cmd_sock.sendto(cmd, (node_ip, port))
    except Exception as e:
        print(f"[Server] Failed to send to Node-{node_id} @ {node_ip}:{port} - {e}")


def _sorted_insert(queue, entry):
    """
    Insert entry maintaining sort order:
    primary = tier ASC (1 = highest priority),
    secondary = timestamp ASC (earlier = served first within same tier).
    """
    queue.append(entry)
    queue.sort(key=lambda e: (e["tier"], e["timestamp"]))


def _broadcast_signals(active_nid, node_ips):
    """Send GREEN to active_nid, RED to all others. Called outside the lock."""
    for nid, ip in node_ips.items():
        _send_signal(nid, "GREEN" if nid == active_nid else "RED", ip)


# ── Packet handler ────────────────────────────────────────────────────────────
def _handle_packet(data, addr):
    global _pps_counter, _priority_queue, _active_priority_node

    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return

    node_id = payload.get("node_id")
    if not node_id or node_id not in NODES:
        return

    recv_time    = time.time()
    send_time    = payload.get("timestamp", recv_time)
    latency_ms   = max(0.0, (recv_time - send_time) * 1000)
    seq          = payload.get("seq", 0)
    vc           = payload.get("vehicle_count", 0)
    status       = _compute_status(vc)
    node_ip      = addr[0]
    priority     = payload.get("priority", False)
    vehicle_type = payload.get("vehicle_type", "unknown")
    new_tier     = _get_tier(vehicle_type)

    priority_action   = None
    node_ips_snapshot = {}
    preempted_node    = None
    promoted_node     = None

    with lock:
        # ── Stats ─────────────────────────────────────────────────────────────
        _latency_buf.append(latency_ms)
        if len(_latency_buf) > 50:
            _latency_buf.pop(0)
        stats["avg_latency_ms"] = round(sum(_latency_buf) / len(_latency_buf), 2)

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

        # ── Update node record ────────────────────────────────────────────────
        node_data[node_id] = {
            "location":      payload.get("location", "Unknown"),
            "vehicle_count": vc,
            "signal":        _assigned_signal.get(node_id, "RED"),
            "status":        status,
            "last_seen":     recv_time,
            "node_ip":       node_ip,
            "priority":      priority,
            "vehicle_type":  vehicle_type if priority else None,
        }

        # ── Priority state machine ────────────────────────────────────────────
        in_queue = any(e["node_id"] == node_id for e in _priority_queue)

        if priority and not prev_priority:
            # New priority activation
            if not in_queue:
                new_entry = {
                    "node_id":      node_id,
                    "vehicle_type": vehicle_type,
                    "tier":         new_tier,
                    "timestamp":    recv_time,
                }

                if _active_priority_node is None:
                    # Queue empty — serve immediately
                    _active_priority_node = node_id
                    _priority_queue.append(new_entry)
                    for nid in NODES:
                        _assigned_signal[nid] = "GREEN" if nid == node_id else "RED"
                    _yellow_timers.clear()
                    priority_action = "start_immediate"

                else:
                    # Check if we should preempt the active node
                    active_entry = next(
                        (e for e in _priority_queue if e["node_id"] == _active_priority_node),
                        None
                    )
                    active_tier = active_entry["tier"] if active_entry else DEFAULT_VEHICLE_TIER

                    if new_tier < active_tier:
                        # PREEMPT: new vehicle has higher priority (lower tier number)
                        preempted_node = _active_priority_node
                        _sorted_insert(_priority_queue, new_entry)
                        _active_priority_node = node_id
                        for nid in NODES:
                            _assigned_signal[nid] = "GREEN" if nid == node_id else "RED"
                        _yellow_timers.clear()
                        priority_action = "preempt"

                    else:
                        # Same or lower priority — just queue behind active
                        _sorted_insert(_priority_queue, new_entry)
                        priority_action = "queued"

                node_ips_snapshot = {k: v.get("node_ip") for k, v in node_data.items()}

        elif not priority and prev_priority:
            # Priority cleared by operator
            was_active = (_active_priority_node == node_id)
            _priority_queue[:] = [e for e in _priority_queue if e["node_id"] != node_id]

            if was_active:
                _active_priority_node = None

                if _priority_queue:
                    next_entry    = _priority_queue[0]
                    promoted_node = next_entry["node_id"]
                    _active_priority_node = promoted_node
                    for nid in NODES:
                        _assigned_signal[nid] = "GREEN" if nid == promoted_node else "RED"
                    _yellow_timers.clear()
                    priority_action = "promote"
                else:
                    priority_action = "clear_all"

                node_ips_snapshot = {k: v.get("node_ip") for k, v in node_data.items()}
            # else: was waiting in queue, quietly removed

    # ── Actions outside the lock ──────────────────────────────────────────────
    if priority_action == "start_immediate":
        _broadcast_signals(node_id, node_ips_snapshot)
        label = _get_label(vehicle_type)
        _add_alert(
            node_id,
            f"PRIORITY: Node-{node_id} -> GREEN | {label} (T{new_tier})",
            level="critical"
        )
        print(f"[Server] PRIORITY immediate: Node-{node_id} [{label} T{new_tier}] -> GREEN")

    elif priority_action == "preempt":
        _broadcast_signals(node_id, node_ips_snapshot)
        new_label = _get_label(vehicle_type)
        with lock:
            pre_entry = next(
                (e for e in _priority_queue if e["node_id"] == preempted_node), None
            )
        pre_label = _get_label(pre_entry["vehicle_type"] if pre_entry else "unknown")
        pre_tier  = pre_entry["tier"] if pre_entry else "?"
        _add_alert(
            node_id,
            f"PREEMPT: Node-{node_id} [{new_label} T{new_tier}] overrides "
            f"Node-{preempted_node} [{pre_label} T{pre_tier}]",
            level="critical"
        )
        _add_alert(
            preempted_node,
            f"Node-{preempted_node} [{pre_label}] preempted — re-queued, waiting for T{new_tier} to clear",
            level="warning"
        )
        print(f"[Server] PREEMPT: T{new_tier} Node-{node_id} beats T{pre_tier} Node-{preempted_node}")

    elif priority_action == "queued":
        with lock:
            pos = next(
                (i + 1 for i, e in enumerate(_priority_queue) if e["node_id"] == node_id),
                "?"
            )
        label = _get_label(vehicle_type)
        _add_alert(
            node_id,
            f"PRIORITY queued: Node-{node_id} [{label} T{new_tier}] — queue position {pos}",
            level="priority"
        )
        print(f"[Server] QUEUED: Node-{node_id} [{label} T{new_tier}] at position {pos}")

    elif priority_action == "promote":
        _broadcast_signals(promoted_node, node_ips_snapshot)
        with lock:
            prom_entry = next(
                (e for e in _priority_queue if e["node_id"] == promoted_node), None
            )
        prom_label = _get_label(prom_entry["vehicle_type"] if prom_entry else "unknown")
        prom_tier  = prom_entry["tier"] if prom_entry else "?"
        remaining  = len(_priority_queue)
        _add_alert(
            node_id,
            f"Node-{node_id} cleared — promoting Node-{promoted_node} "
            f"[{prom_label} T{prom_tier}] ({remaining} in queue)",
            level="warning"
        )
        _add_alert(
            promoted_node,
            f"PRIORITY: Node-{promoted_node} [{prom_label} T{prom_tier}] -> GREEN (promoted)",
            level="critical"
        )
        print(f"[Server] PROMOTE: Node-{promoted_node} [{prom_label} T{prom_tier}] -> GREEN")

    elif priority_action == "clear_all":
        _add_alert(
            node_id,
            f"Node-{node_id} cleared — priority queue empty, resuming normal control",
            level="warning"
        )
        print(f"[Server] CLEAR ALL: queue empty, normal mode resumed")

    elif priority_action is None and _active_priority_node is None:
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
    while True:
        time.sleep(SIGNAL_CYCLE_SEC)

        changes = {}
        with lock:
            if _active_priority_node is not None:
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

        for nid, (sig, info) in changes.items():
            _send_signal(nid, sig, info.get("node_ip"))
            if sig == "GREEN":
                _add_alert(nid,
                           f"Node-{nid} -> GREEN (highest traffic: {info['vehicle_count']} vehicles)",
                           level="warning")
            elif sig == "YELLOW":
                _add_alert(nid,
                           f"Node-{nid} -> YELLOW (transitioning to RED)",
                           level="warning")


def _yellow_watchdog():
    while True:
        time.sleep(1)
        now     = time.time()
        expired = {}

        with lock:
            if _active_priority_node is not None:
                continue
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
    threading.Thread(target=_listen,          daemon=True).start()
    threading.Thread(target=_pps_ticker,      daemon=True).start()
    threading.Thread(target=_signal_engine,   daemon=True).start()
    threading.Thread(target=_yellow_watchdog, daemon=True).start()
    print("[Server] All threads started (listener, PPS, signal engine, yellow watchdog).")


def get_snapshot():
    with lock:
        return {
            "node_data":      {k: dict(v) for k, v in node_data.items()},
            "stats":          dict(stats),
            "alert_log":      list(alert_log),
            "uptime":         int(time.time() - stats["start_time"]),
            "signal_state":   dict(_assigned_signal),
            "priority_node":  _active_priority_node,
            "priority_queue": [dict(e) for e in _priority_queue],
        }