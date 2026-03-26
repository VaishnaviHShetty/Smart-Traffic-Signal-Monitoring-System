# node_sim.py  — runs on each ROAD system (not the controller)
#
# Usage:  python node_sim.py <node_id>
# Example: python node_sim.py A
#
# What it does:
#   1. Opens a small GUI with PRIORITY VEHICLE and CLEAR buttons
#   2. Sends vehicle-count packets (+priority flag) to the CONTROLLER every second
#   3. Listens for signal commands from the controller on its own port
#   4. Obeys whatever signal the controller assigns (GREEN / YELLOW / RED)

import socket
import json
import time
import random
import sys
import threading
import tkinter as tk
from config import (
    CONTROLLER_HOST, NODE_SEND_PORT, NODES, NODE_SEND_INTERVAL
)

# ── Shared state ──────────────────────────────────────────────────────────────
_current_signal  = "RED"
_priority_active = False
_state_lock      = threading.Lock()

# ── Colors ────────────────────────────────────────────────────────────────────
BG    = "#0d0d1a"
BG2   = "#13131f"
MUTED = "#5a5a90"
GREEN = "#39ff87"
YELLOW= "#f5e642"
RED   = "#ff4466"
ORANGE= "#ff9944"
CYAN  = "#22e5d4"


# ── Signal listener thread ────────────────────────────────────────────────────
def _signal_listener(node_id):
    global _current_signal
    listen_port = NODES[node_id]["port"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", listen_port))
    print(f"[Node-{node_id}] Signal listener on port {listen_port}")

    while True:
        try:
            data, _ = sock.recvfrom(1024)
            cmd = json.loads(data.decode("utf-8"))
            new_signal = cmd.get("signal", "RED")
            with _state_lock:
                _current_signal = new_signal
            print(f"[Node-{node_id}] ← Controller says: {new_signal}")
        except Exception as e:
            print(f"[Node-{node_id}] Listener error: {e}")


# ── Packet sender thread ──────────────────────────────────────────────────────
def _sender(node_id):
    location  = NODES[node_id]["name"]
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq       = 0

    print(f"[Node-{node_id}] {location} → sending to {CONTROLLER_HOST}:{NODE_SEND_PORT}")

    while True:
        with _state_lock:
            signal   = _current_signal
            priority = _priority_active

        # Vehicle count based on signal
        if priority:
            vehicle_count = 1   # priority vehicle — just 1 special vehicle
        elif signal == "RED":
            vehicle_count = random.randint(20, 50)
        elif signal == "YELLOW":
            vehicle_count = random.randint(10, 30)
        else:
            vehicle_count = random.randint(0, 20)

        payload = {
            "node_id":       node_id,
            "location":      location,
            "vehicle_count": vehicle_count,
            "signal":        signal,
            "timestamp":     time.time(),
            "seq":           seq,
            "priority":      priority,   # ← HIGH-PRIORITY FLAG
        }

        data = json.dumps(payload).encode("utf-8")
        send_sock.sendto(data, (CONTROLLER_HOST, NODE_SEND_PORT))
        seq += 1

        pri_tag = " [PRIORITY!]" if priority else ""
        print(f"[Node-{node_id}] seq={seq:04d} | {signal:6s} | vehicles={vehicle_count:3d}{pri_tag}")
        time.sleep(NODE_SEND_INTERVAL)


# ── Node GUI ──────────────────────────────────────────────────────────────────
class NodeGUI:
    def __init__(self, root, node_id):
        self.root    = root
        self.node_id = node_id
        location     = NODES[node_id]["name"]

        root.title(f"Node-{node_id}  |  {location}")
        root.configure(bg=BG)
        root.geometry("340x340")
        root.resizable(False, False)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"NODE-{node_id}  ·  {location.upper()}",
                 bg=BG2, fg=CYAN, font=("Courier", 10, "bold")).pack(pady=10)

        # ── Signal display ────────────────────────────────────────────────────
        sig_frame = tk.Frame(root, bg=BG)
        sig_frame.pack(pady=10)
        tk.Label(sig_frame, text="CURRENT SIGNAL", bg=BG, fg=MUTED,
                 font=("Courier", 8)).pack()
        self.sig_label = tk.Label(sig_frame, text="RED", bg=BG, fg=RED,
                                  font=("Courier", 28, "bold"))
        self.sig_label.pack()

        # ── Priority status label ─────────────────────────────────────────────
        self.pri_label = tk.Label(root, text="", bg=BG, fg=ORANGE,
                                  font=("Courier", 9, "bold"))
        self.pri_label.pack(pady=(0, 6))

        # ── Separator ─────────────────────────────────────────────────────────
        tk.Frame(root, bg="#2a2a50", height=1).pack(fill="x", padx=20, pady=6)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(pady=10)

        self.pri_btn = tk.Button(
            btn_frame,
            text="🚨  PRIORITY VEHICLE",
            bg="#4a1010", fg=RED,
            activebackground="#6a1515", activeforeground=RED,
            font=("Courier", 11, "bold"),
            relief="flat", bd=0, padx=16, pady=10,
            cursor="hand2",
            command=self._trigger_priority
        )
        self.pri_btn.pack(fill="x", padx=10, pady=(0, 8))

        self.clr_btn = tk.Button(
            btn_frame,
            text="✅  CLEAR  (resume normal)",
            bg="#0a3020", fg=GREEN,
            activebackground="#0d4a30", activeforeground=GREEN,
            font=("Courier", 10),
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2",
            state="disabled",
            command=self._clear_priority
        )
        self.clr_btn.pack(fill="x", padx=10)

        # ── Stats row ─────────────────────────────────────────────────────────
        tk.Frame(root, bg="#2a2a50", height=1).pack(fill="x", padx=20, pady=(12, 4))
        self.stats_label = tk.Label(root, text="Waiting for controller...",
                                    bg=BG, fg=MUTED, font=("Courier", 8))
        self.stats_label.pack()

        # ── Start background threads ──────────────────────────────────────────
        threading.Thread(target=_signal_listener, args=(node_id,), daemon=True).start()
        threading.Thread(target=_sender,          args=(node_id,), daemon=True).start()

        self._refresh()

    def _trigger_priority(self):
        global _priority_active
        with _state_lock:
            _priority_active = True
        self.pri_btn.config(state="disabled", bg="#2a0808")
        self.clr_btn.config(state="normal")
        print(f"[Node-{self.node_id}] 🚨 PRIORITY VEHICLE TRIGGERED")

    def _clear_priority(self):
        global _priority_active
        with _state_lock:
            _priority_active = False
        self.pri_btn.config(state="normal", bg="#4a1010")
        self.clr_btn.config(state="disabled")
        print(f"[Node-{self.node_id}] ✅ Priority cleared — resuming normal")

    def _refresh(self):
        with _state_lock:
            sig      = _current_signal
            priority = _priority_active

        color = {"GREEN": GREEN, "YELLOW": YELLOW, "RED": RED}.get(sig, MUTED)
        self.sig_label.config(text=sig, fg=color)

        if priority:
            self.pri_label.config(
                text="⚡ PRIORITY MODE ACTIVE — awaiting GREEN",
                fg=ORANGE
            )
            self.root.title(f"🚨 Node-{self.node_id} — PRIORITY ACTIVE")
        else:
            self.pri_label.config(text="")
            self.root.title(f"Node-{self.node_id}  |  {NODES[self.node_id]['name']}")

        self.root.after(500, self._refresh)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node_sim.py <node_id>")
        print(f"       node_id choices: {list(NODES.keys())}")
        sys.exit(1)

    node_id = sys.argv[1].upper()
    if node_id not in NODES:
        print(f"Invalid node ID '{node_id}'. Choose from: {list(NODES.keys())}")
        sys.exit(1)

    root = tk.Tk()
    app  = NodeGUI(root, node_id)
    root.mainloop()