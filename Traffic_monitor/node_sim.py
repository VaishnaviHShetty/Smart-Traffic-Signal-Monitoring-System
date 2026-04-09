# node_sim.py  — runs on each ROAD system (not the controller)
#
# Usage:  python node_sim.py <node_id>
# Example: python node_sim.py A

import socket
import json
import time
import random
import sys
import threading
import tkinter as tk
from tkinter import ttk
from config import (
    CONTROLLER_HOST, NODE_SEND_PORT, NODES, NODE_SEND_INTERVAL, VEHICLE_TYPES
)

# ── Shared state ──────────────────────────────────────────────────────────────
_current_signal  = "RED"
_priority_active = False
_vehicle_type    = "ambulance"
_state_lock      = threading.Lock()

BG     = "#0d0d1a"
BG2    = "#13131f"
MUTED  = "#5a5a90"
GREEN  = "#39ff87"
YELLOW = "#f5e642"
RED    = "#ff4466"
ORANGE = "#ff9944"
CYAN   = "#22e5d4"
PURPLE = "#c084fc"
BLUE   = "#4dc8ff"
TIER_COLORS = {1: RED, 2: ORANGE, 3: PURPLE, 4: BLUE}


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
            with _state_lock:
                _current_signal = cmd.get("signal", "RED")
            print(f"[Node-{node_id}] <- {cmd.get('signal','RED')}")
        except Exception as e:
            print(f"[Node-{node_id}] Listener error: {e}")


def _sender(node_id):
    location  = NODES[node_id]["name"]
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq       = 0

    # ── Stateful vehicle count — starts between 10 and 28 ────────────────────
    vehicle_count = random.randint(10, 28)

    print(f"[Node-{node_id}] Sending to {CONTROLLER_HOST}:{NODE_SEND_PORT}")
    print(f"[Node-{node_id}] Starting vehicle count: {vehicle_count}")

    while True:
        with _state_lock:
            signal       = _current_signal
            priority     = _priority_active
            vehicle_type = _vehicle_type

        if priority:
            # Priority active — snap to 1, bypass stateful logic entirely
            vehicle_count = 1

        else:
            # ── Stateful nudge based on current signal ────────────────────────
            # RED    → vehicles queue up    → count climbs
            # GREEN  → vehicles flow out    → count drains
            # YELLOW → slowing down         → slight drain
            if signal == "RED":
                vehicle_count += random.randint(3, 6)
            elif signal == "GREEN":
                vehicle_count -= random.randint(2, 4)
            elif signal == "YELLOW":
                vehicle_count -= random.randint(0, 2)

            # Clamp between 0 and 60
            vehicle_count = max(0, min(60, vehicle_count))

        payload = {
            "node_id":       node_id,
            "location":      location,
            "vehicle_count": vehicle_count,
            "signal":        signal,
            "timestamp":     time.time(),
            "seq":           seq,
            "priority":      priority,
            "vehicle_type":  vehicle_type,
        }
        send_sock.sendto(json.dumps(payload).encode("utf-8"),
                         (CONTROLLER_HOST, NODE_SEND_PORT))
        seq += 1
        if priority:
            vinfo = VEHICLE_TYPES.get(vehicle_type, {})
            print(f"[Node-{node_id}] seq={seq:04d} | {signal:6s} | vc={vehicle_count:3d} "
                  f"[{vinfo.get('label', vehicle_type)} T{vinfo.get('tier','?')}]")
        else:
            print(f"[Node-{node_id}] seq={seq:04d} | {signal:6s} | vc={vehicle_count:3d}")
        time.sleep(NODE_SEND_INTERVAL)


class NodeGUI:
    def __init__(self, root, node_id):
        self.root    = root
        self.node_id = node_id
        location     = NODES[node_id]["name"]

        root.title(f"Node-{node_id}  |  {location}")
        root.configure(bg=BG)
        root.geometry("360x450")
        root.resizable(False, False)

        hdr = tk.Frame(root, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"NODE-{node_id}  .  {location.upper()}",
                 bg=BG2, fg=CYAN, font=("Courier", 10, "bold")).pack(pady=10)

        sig_frame = tk.Frame(root, bg=BG)
        sig_frame.pack(pady=8)
        tk.Label(sig_frame, text="CURRENT SIGNAL", bg=BG, fg=MUTED,
                 font=("Courier", 8)).pack()
        self.sig_label = tk.Label(sig_frame, text="RED", bg=BG, fg=RED,
                                  font=("Courier", 28, "bold"))
        self.sig_label.pack()

        self.pri_label = tk.Label(root, text="", bg=BG, fg=ORANGE,
                                  font=("Courier", 9, "bold"))
        self.pri_label.pack(pady=(0, 4))

        tk.Frame(root, bg="#2a2a50", height=1).pack(fill="x", padx=20, pady=4)

        sel_frame = tk.Frame(root, bg=BG)
        sel_frame.pack(fill="x", padx=18, pady=(6, 2))
        tk.Label(sel_frame, text="Vehicle type:", bg=BG, fg=MUTED,
                 font=("Courier", 8)).pack(side="left")

        self._type_keys = list(VEHICLE_TYPES.keys())
        type_display    = [
            f"{VEHICLE_TYPES[k]['label']} (T{VEHICLE_TYPES[k]['tier']})"
            for k in self._type_keys
        ]
        self._type_var = tk.StringVar(root)
        self._type_var.set(type_display[0])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TCombobox",
                         fieldbackground=BG2, background=BG2,
                         foreground=CYAN, selectbackground=BG2,
                         selectforeground=CYAN, bordercolor="#2a2a50",
                         arrowcolor=MUTED)

        self.type_combo = ttk.Combobox(
            sel_frame, textvariable=self._type_var,
            values=type_display, state="readonly",
            width=26, style="Dark.TCombobox"
        )
        self.type_combo.pack(side="left", padx=(8, 0))
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_change)

        self.tier_label = tk.Label(root, text="Tier 1 - Highest priority",
                                   bg=BG, fg=RED, font=("Courier", 8))
        self.tier_label.pack()

        tk.Frame(root, bg="#2a2a50", height=1).pack(fill="x", padx=20, pady=6)

        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(pady=6)

        self.pri_btn = tk.Button(
            btn_frame, text="PRIORITY VEHICLE",
            bg="#4a1010", fg=RED,
            activebackground="#6a1515", activeforeground=RED,
            font=("Courier", 11, "bold"),
            relief="flat", bd=0, padx=16, pady=10,
            cursor="hand2", command=self._trigger_priority
        )
        self.pri_btn.pack(fill="x", padx=10, pady=(0, 8))

        self.clr_btn = tk.Button(
            btn_frame, text="CLEAR  (resume normal)",
            bg="#0a3020", fg=GREEN,
            activebackground="#0d4a30", activeforeground=GREEN,
            font=("Courier", 10),
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", state="disabled", command=self._clear_priority
        )
        self.clr_btn.pack(fill="x", padx=10)

        tk.Frame(root, bg="#2a2a50", height=1).pack(fill="x", padx=20, pady=(10, 4))
        self.stats_label = tk.Label(root, text="Waiting for controller...",
                                    bg=BG, fg=MUTED, font=("Courier", 8))
        self.stats_label.pack()

        threading.Thread(target=_signal_listener, args=(node_id,), daemon=True).start()
        threading.Thread(target=_sender,          args=(node_id,), daemon=True).start()
        self._refresh()

    def _on_type_change(self, event=None):
        global _vehicle_type
        idx = self._get_combo_index()
        key = self._type_keys[idx]
        with _state_lock:
            _vehicle_type = key
        vinfo = VEHICLE_TYPES[key]
        tier  = vinfo["tier"]
        color = TIER_COLORS.get(tier, BLUE)
        tier_text = {1: "Tier 1 - Highest priority", 2: "Tier 2 - High priority",
                     3: "Tier 3 - Medium priority",  4: "Tier 4 - Low priority"}
        self.tier_label.config(text=tier_text.get(tier, ""), fg=color)
        self.pri_btn.config(fg=color)

    def _get_combo_index(self):
        selected = self._type_var.get()
        display  = [
            f"{VEHICLE_TYPES[k]['label']} (T{VEHICLE_TYPES[k]['tier']})"
            for k in self._type_keys
        ]
        try:
            return display.index(selected)
        except ValueError:
            return 0

    def _trigger_priority(self):
        global _priority_active, _vehicle_type
        idx = self._get_combo_index()
        with _state_lock:
            _priority_active = True
            _vehicle_type    = self._type_keys[idx]
        self.pri_btn.config(state="disabled", bg="#2a0808")
        self.clr_btn.config(state="normal")
        self.type_combo.config(state="disabled")
        vinfo = VEHICLE_TYPES[_vehicle_type]
        print(f"[Node-{self.node_id}] PRIORITY: {vinfo['label']} (T{vinfo['tier']})")

    def _clear_priority(self):
        global _priority_active
        with _state_lock:
            _priority_active = False
        self.pri_btn.config(state="normal", bg="#4a1010")
        self.clr_btn.config(state="disabled")
        self.type_combo.config(state="readonly")
        print(f"[Node-{self.node_id}] Priority cleared")

    def _refresh(self):
        with _state_lock:
            sig          = _current_signal
            priority     = _priority_active
            vehicle_type = _vehicle_type

        color = {"GREEN": GREEN, "YELLOW": YELLOW, "RED": RED}.get(sig, MUTED)
        self.sig_label.config(text=sig, fg=color)

        if priority:
            vinfo = VEHICLE_TYPES.get(vehicle_type, {})
            tier  = vinfo.get("tier", 4)
            tc    = TIER_COLORS.get(tier, BLUE)
            self.pri_label.config(
                text=f"PRIORITY: {vinfo.get('label', vehicle_type)} (T{tier})",
                fg=tc
            )
            self.root.title(f"[PRIORITY] Node-{self.node_id} - {vinfo.get('label','')}")
        else:
            self.pri_label.config(text="")
            self.root.title(f"Node-{self.node_id}  |  {NODES[self.node_id]['name']}")

        self.root.after(500, self._refresh)


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