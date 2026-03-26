# dashboard.py — runs on the CONTROLLER system only
import tkinter as tk
from tkinter import ttk
import time
import server
from config import UPDATE_INTERVAL_MS, NODES, NODE_SEND_PORT, SIGNAL_CYCLE_SEC

# ── Color palette ─────────────────────────────────────────────────────────────
BG       = "#0d0d1a"
BG2      = "#13131f"
PANEL_BG = "#161625"
BORDER   = "#1e1e35"
BORDER2  = "#2a2a50"
TEXT     = "#c8c8f0"
MUTED    = "#5a5a90"
GREEN    = "#39ff87"
YELLOW   = "#f5e642"
RED      = "#ff4466"
BLUE     = "#4dc8ff"
PURPLE   = "#c084fc"
CYAN     = "#22e5d4"
ORANGE   = "#ff9944"

STATUS_COLORS = {"OK": GREEN, "MODERATE": YELLOW, "CONGESTED": RED}
SIGNAL_COLORS = {"GREEN": GREEN, "YELLOW": YELLOW, "RED": RED, "UNKNOWN": MUTED}

CHART_HISTORY = 30
CHART_COLORS  = {"A": BLUE, "B": RED, "C": GREEN, "D": ORANGE}
_history = {nid: [0] * CHART_HISTORY for nid in NODES}

# Flash state for priority banner
_flash_state = False


def fmt_uptime(s):
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


# ── Dashboard ─────────────────────────────────────────────────────────────────
class Dashboard:
    def __init__(self, root):
        self.root = root
        root.title("Smart Traffic — Central Controller")
        root.configure(bg=BG)
        root.geometry("1280x800")
        root.resizable(True, True)

        self._build_titlebar()
        self._build_priority_banner()   # ← NEW
        self._build_body()
        self._build_statusbar()

    # ── Title bar ─────────────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=BG2, height=42)
        bar.pack(fill="x", side="top")

        tk.Label(bar, text="◈", bg=BG2, fg=CYAN,
                 font=("Courier", 16)).pack(side="left", padx=(16, 6), pady=8)
        tk.Label(bar, text="SMART TRAFFIC  ·  CENTRAL CONTROLLER",
                 bg=BG2, fg=TEXT, font=("Courier", 11, "bold")).pack(side="left", pady=8)

        self.conn_label = tk.Label(bar, text="● 0/4 nodes", bg=BG2, fg=RED,
                                   font=("Courier", 9))
        self.conn_label.pack(side="right", padx=16)

    # ── Priority banner (hidden by default) ───────────────────────────────────
    def _build_priority_banner(self):
        self.banner = tk.Frame(self.root, bg="#3a0808", height=36)
        # Not packed yet — shown only when priority is active

        self.banner_label = tk.Label(
            self.banner,
            text="",
            bg="#3a0808", fg=RED,
            font=("Courier", 11, "bold")
        )
        self.banner_label.pack(expand=True, pady=8)

    # ── 2×2 body grid ─────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self.root, bg=BORDER)
        body.pack(fill="both", expand=True)
        for i in range(2): body.columnconfigure(i, weight=1)
        for i in range(2): body.rowconfigure(i, weight=1)

        self._build_stats_panel(body, 0, 0)
        self._build_table_panel(body, 0, 1)
        self._build_alerts_panel(body, 1, 0)
        self._build_chart_panel(body, 1, 1)

    def _panel(self, parent, title, row, col):
        f = tk.Frame(parent, bg=PANEL_BG)
        f.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
        hdr = tk.Frame(f, bg=PANEL_BG)
        hdr.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(hdr, text=title.upper(), bg=PANEL_BG, fg=MUTED,
                 font=("Courier", 8, "bold")).pack(side="left")
        tk.Frame(f, bg=BORDER2, height=1).pack(fill="x", padx=14, pady=(5, 8))
        return f

    # ── Panel 1: Stats ────────────────────────────────────────────────────────
    def _build_stats_panel(self, parent, row, col):
        f = self._panel(parent, "Packet Stats / Throughput", row, col)
        defs = [
            ("Packets/sec",    "stat_pps",     BLUE),
            ("Total received", "stat_total",   PURPLE),
            ("Packet loss",    "stat_loss",    RED),
            ("Avg latency",    "stat_latency", YELLOW),
            ("Active nodes",   "stat_nodes",   GREEN),
            ("Uptime",         "stat_uptime",  CYAN),
        ]
        grid = tk.Frame(f, bg=PANEL_BG)
        grid.pack(fill="x", padx=14)
        for i, (label, attr, color) in enumerate(defs):
            cell = tk.Frame(grid, bg=BG2,
                            highlightthickness=1, highlightbackground=BORDER2)
            cell.grid(row=i//3, column=i%3, padx=4, pady=4, sticky="nsew")
            grid.columnconfigure(i%3, weight=1)
            tk.Label(cell, text=label, bg=BG2, fg=MUTED,
                     font=("Courier", 7)).pack(pady=(7, 0))
            lbl = tk.Label(cell, text="—", bg=BG2, fg=color,
                           font=("Courier", 15, "bold"))
            lbl.pack(pady=(0, 7))
            setattr(self, attr, lbl)

    # ── Panel 2: Live node table ──────────────────────────────────────────────
    def _build_table_panel(self, parent, row, col):
        f = self._panel(parent, "Live Node Table", row, col)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("T.Treeview",
                        background=BG2, foreground=TEXT,
                        fieldbackground=BG2, borderwidth=0,
                        rowheight=30, font=("Courier", 10))
        style.configure("T.Treeview.Heading",
                        background=PANEL_BG, foreground=MUTED,
                        font=("Courier", 8, "bold"), relief="flat")
        style.map("T.Treeview", background=[("selected", BORDER2)])

        cols   = ("Node", "Location", "Vehicles", "Signal", "Priority", "Status", "Node IP")
        widths = [60, 120, 70, 80, 70, 90, 110]
        self.tree = ttk.Treeview(f, columns=cols, show="headings",
                                 style="T.Treeview", height=7)
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    # ── Panel 3: Alert log ────────────────────────────────────────────────────
    def _build_alerts_panel(self, parent, row, col):
        f = self._panel(parent, "Congestion Alert Log  /  Signal Events", row, col)
        self.alert_box = tk.Text(f, bg=BG2, fg=RED,
                                 font=("Courier", 9), state="disabled",
                                 bd=0, highlightthickness=0,
                                 relief="flat", wrap="word")
        self.alert_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        for tag, fg in [("critical", RED), ("warning", YELLOW),
                        ("time", MUTED), ("info", CYAN), ("priority", ORANGE)]:
            self.alert_box.tag_config(tag, foreground=fg)

    # ── Panel 4: Real-time bar chart ──────────────────────────────────────────
    def _build_chart_panel(self, parent, row, col):
        f = self._panel(parent, "Vehicle Count — Real-Time Graph", row, col)
        self.canvas = tk.Canvas(f, bg=BG2, bd=0,
                                highlightthickness=0, relief="flat")
        self.canvas.pack(fill="both", expand=True, padx=14, pady=(0, 4))

        legend = tk.Frame(f, bg=PANEL_BG)
        legend.pack(anchor="w", padx=16, pady=(0, 8))
        for nid, color in CHART_COLORS.items():
            tk.Label(legend, text="■", bg=PANEL_BG, fg=color,
                     font=("Courier", 9)).pack(side="left")
            tk.Label(legend, text=f" Node-{nid}  ",
                     bg=PANEL_BG, fg=MUTED,
                     font=("Courier", 8)).pack(side="left")

    # ── Status bar ─────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG2, height=26)
        bar.pack(fill="x", side="bottom")
        items = [
            ("Listening on port:", str(NODE_SEND_PORT), BLUE),
            ("Signal cycle:",      f"{SIGNAL_CYCLE_SEC}s", YELLOW),
            ("Congestion at:",     "30 vehicles",          RED),
        ]
        for label, val, color in items:
            tk.Label(bar, text=label, bg=BG2, fg=MUTED,
                     font=("Courier", 8)).pack(side="left", padx=(14, 2), pady=5)
            tk.Label(bar, text=val,   bg=BG2, fg=color,
                     font=("Courier", 8)).pack(side="left", padx=(0, 18), pady=5)
        self.sb_time = tk.Label(bar, text="", bg=BG2, fg=MUTED, font=("Courier", 8))
        self.sb_time.pack(side="right", padx=14)

    # ── Refresh ────────────────────────────────────────────────────────────────
    def refresh(self):
        global _flash_state
        snap = server.get_snapshot()
        _flash_state = not _flash_state   # toggle flash every refresh

        self._refresh_priority_banner(snap)
        self._refresh_stats(snap)
        self._refresh_table(snap)
        self._refresh_alerts(snap)
        self._refresh_chart(snap)
        self.sb_time.config(text=f"Updated: {time.strftime('%H:%M:%S')}")
        self.root.after(UPDATE_INTERVAL_MS, self.refresh)

    # ── Priority banner ───────────────────────────────────────────────────────
    def _refresh_priority_banner(self, snap):
        pnode = snap.get("priority_node")
        if pnode:
            location = NODES.get(pnode, {}).get("name", pnode)
            self.banner_label.config(
                text=f"🚨  PRIORITY VEHICLE ACTIVE  —  Node-{pnode} ({location})  —  ALL others forced RED  🚨",
                fg=RED if _flash_state else ORANGE
            )
            self.banner.pack(fill="x", after=self.root.winfo_children()[0])
            self.root.configure(bg="#1a0505")
        else:
            self.banner.pack_forget()
            self.root.configure(bg=BG)

    def _refresh_stats(self, snap):
        s      = snap["stats"]
        nd     = snap["node_data"]
        now    = time.time()
        active = sum(1 for n in nd.values() if now - n["last_seen"] < 5)

        self.stat_pps.config(    text=str(s["packets_per_sec"]))
        self.stat_total.config(  text=f"{s['total_received']:,}")
        self.stat_loss.config(   text=f"{s['packet_loss_pct']}%")
        self.stat_latency.config(text=f"{s['avg_latency_ms']}ms")
        self.stat_nodes.config(  text=f"{active}/{len(NODES)}")
        self.stat_uptime.config( text=fmt_uptime(snap["uptime"]))

        color = GREEN if active == len(NODES) else (YELLOW if active > 0 else RED)
        self.conn_label.config(text=f"● {active}/{len(NODES)} nodes", fg=color)

    def _refresh_table(self, snap):
        for row in self.tree.get_children():
            self.tree.delete(row)

        now    = time.time()
        sstate = snap["signal_state"]
        pnode  = snap.get("priority_node")

        for nid in sorted(NODES.keys()):
            info = snap["node_data"].get(nid)
            if info:
                vc        = info["vehicle_count"]
                sig       = sstate.get(nid, "RED")
                stat      = info["status"]
                node_ip   = info.get("node_ip", "—")
                is_pri    = info.get("priority", False)
                pri_txt   = "🚨 YES" if is_pri else "—"
                tag       = f"{nid}_pri" if is_pri else f"{nid}_sig"
                row_color = ORANGE if is_pri else SIGNAL_COLORS.get(sig, MUTED)

                self.tree.insert("", "end",
                                 values=(f"Node-{nid}", info["location"],
                                         vc, sig, pri_txt, stat, node_ip),
                                 tags=(tag,))
                self.tree.tag_configure(tag, foreground=row_color)
            else:
                self.tree.insert("", "end",
                                 values=(f"Node-{nid}", NODES[nid]["name"],
                                         "—", "—", "—", "OFFLINE", "—"),
                                 tags=("offline",))
                self.tree.tag_configure("offline", foreground=MUTED)

    def _refresh_alerts(self, snap):
        self.alert_box.config(state="normal")
        self.alert_box.delete("1.0", "end")
        for entry in snap["alert_log"]:
            lvl = entry["level"]
            # Map "critical" alerts that mention PRIORITY to "priority" tag
            if "PRIORITY" in entry["message"] or "Priority" in entry["message"]:
                lvl = "priority"
            self.alert_box.insert("end", f"[{entry['time_str']}] ", "time")
            self.alert_box.insert("end", entry["message"] + "\n", lvl)
        self.alert_box.config(state="disabled")

    def _refresh_chart(self, snap):
        for nid, info in snap["node_data"].items():
            if nid in _history:
                _history[nid].append(info["vehicle_count"])
                _history[nid].pop(0)

        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        max_val  = 55
        pad_x    = 30
        pad_y    = 12
        chart_h  = h - pad_y * 2
        node_ids = list(CHART_COLORS.keys())
        gc       = CHART_HISTORY
        group_w  = (w - pad_x * 2) / gc
        bar_w    = max(2, group_w / (len(node_ids) + 1))

        # Gridlines
        for pct in [0.25, 0.5, 0.75, 1.0]:
            y = pad_y + chart_h * (1 - pct)
            self.canvas.create_line(pad_x, y, w - pad_x, y,
                                    fill=BORDER2, dash=(2, 4))
            self.canvas.create_text(pad_x - 4, y,
                                    text=str(int(max_val * pct)),
                                    fill=MUTED, font=("Courier", 7), anchor="e")

        # Congestion threshold line
        th_y = pad_y + chart_h * (1 - 30 / max_val)
        self.canvas.create_line(pad_x, th_y, w - pad_x, th_y,
                                fill=RED, dash=(4, 4))
        self.canvas.create_text(w - pad_x - 2, th_y - 5,
                                text="CONGESTION", fill=RED,
                                font=("Courier", 7), anchor="e")

        for g in range(gc):
            for b, nid in enumerate(node_ids):
                val   = _history[nid][g]
                bar_h = max(2, (val / max_val) * chart_h)
                x0    = pad_x + g * group_w + b * bar_w
                y0    = pad_y + chart_h - bar_h
                x1    = x0 + bar_w - 1
                y1    = pad_y + chart_h
                color = CHART_COLORS[nid]
                fill  = color if g == gc - 1 else color + "44"
                try:
                    self.canvas.create_rectangle(x0, y0, x1, y1,
                                                 fill=fill, outline="")
                except Exception:
                    pass


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server.start()
    root = tk.Tk()
    app  = Dashboard(root)
    root.after(UPDATE_INTERVAL_MS, app.refresh)
    root.mainloop()