# dashboard.py
import tkinter as tk
from tkinter import ttk
import time
import server
from config import UPDATE_INTERVAL_MS, NODES

# ── Color palette (dark theme) ───────────────────────────────────────────────
BG       = "#1e1e2e"
BG2      = "#16162a"
PANEL_BG = "#1e1e2e"
BORDER   = "#2a2a4e"
TEXT     = "#c0c0e0"
MUTED    = "#6060a0"
GREEN    = "#50fa7b"
YELLOW   = "#f1fa8c"
RED      = "#ff5555"
BLUE     = "#7dcfff"
PURPLE   = "#bd93f9"
CYAN     = "#8be9fd"

STATUS_COLORS = {
    "OK":        GREEN,
    "MODERATE":  YELLOW,
    "CONGESTED": RED,
}
SIGNAL_COLORS = {
    "GREEN":   GREEN,
    "YELLOW":  YELLOW,
    "RED":     RED,
    "UNKNOWN": MUTED,
}

CHART_HISTORY = 20   # how many seconds of bar chart history to keep
CHART_COLORS  = {"A": BLUE, "B": RED, "C": YELLOW}
_history = {nid: [0] * CHART_HISTORY for nid in NODES}


# ── Helper ───────────────────────────────────────────────────────────────────
def fmt_uptime(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── Build UI ─────────────────────────────────────────────────────────────────
class Dashboard:
    def __init__(self, root):
        self.root = root
        root.title("Smart Traffic Signal Monitor — Central Control Unit")
        root.configure(bg=BG)
        root.geometry("1100x680")
        root.resizable(True, True)

        self._build_titlebar()
        self._build_body()
        self._build_statusbar()

    # ── Title bar ────────────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=BG2, height=36)
        bar.pack(fill="x", side="top")
        tk.Label(bar, text="Smart Traffic Signal Monitor — Central Control Unit",
                 bg=BG2, fg=MUTED, font=("Courier", 10)).pack(side="left", padx=16, pady=8)

    # ── 2×2 body grid ────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self.root, bg=BORDER)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        self._build_stats_panel(body,   row=0, col=0)
        self._build_table_panel(body,   row=0, col=1)
        self._build_alerts_panel(body,  row=1, col=0)
        self._build_chart_panel(body,   row=1, col=1)

    def _panel(self, parent, title, row, col):
        frame = tk.Frame(parent, bg=PANEL_BG)
        frame.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
        tk.Label(frame, text=title.upper(), bg=PANEL_BG, fg=MUTED,
                 font=("Courier", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        sep = tk.Frame(frame, bg=BORDER, height=1)
        sep.pack(fill="x", padx=12, pady=(4, 8))
        return frame

    # ── Panel 1: Packet stats ─────────────────────────────────────────────────
    def _build_stats_panel(self, parent, row, col):
        frame = self._panel(parent, "Packet Stats / Throughput", row, col)

        defs = [
            ("Packets/sec",   "stat_pps",      BLUE),
            ("Total received","stat_total",     PURPLE),
            ("Packet loss",   "stat_loss",      RED),
            ("Avg latency",   "stat_latency",   YELLOW),
            ("Active nodes",  "stat_nodes",     GREEN),
            ("Uptime",        "stat_uptime",    CYAN),
        ]

        grid = tk.Frame(frame, bg=PANEL_BG)
        grid.pack(fill="x", padx=12)

        for i, (label, attr, color) in enumerate(defs):
            cell = tk.Frame(grid, bg=BG2, bd=0,
                            highlightthickness=1, highlightbackground=BORDER)
            cell.grid(row=i//3, column=i%3, padx=4, pady=4, sticky="nsew")
            grid.columnconfigure(i%3, weight=1)

            tk.Label(cell, text=label, bg=BG2, fg=MUTED,
                     font=("Courier", 7)).pack(pady=(6, 0))
            lbl = tk.Label(cell, text="—", bg=BG2, fg=color,
                           font=("Courier", 16, "bold"))
            lbl.pack(pady=(0, 6))
            setattr(self, attr, lbl)

    # ── Panel 2: Live node table ──────────────────────────────────────────────
    def _build_table_panel(self, parent, row, col):
        frame = self._panel(parent, "Live Node Table", row, col)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Traffic.Treeview",
                         background=BG2, foreground=TEXT,
                         fieldbackground=BG2, borderwidth=0,
                         rowheight=28, font=("Courier", 10))
        style.configure("Traffic.Treeview.Heading",
                         background=BG, foreground=MUTED,
                         font=("Courier", 8, "bold"), relief="flat")
        style.map("Traffic.Treeview", background=[("selected", BORDER)])

        cols = ("Node", "Location", "Vehicles", "Signal", "Status")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 style="Traffic.Treeview", height=6)
        widths = [60, 140, 70, 80, 100]
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # ── Panel 3: Congestion alert log ─────────────────────────────────────────
    def _build_alerts_panel(self, parent, row, col):
        frame = self._panel(parent, "Congestion Alert Log", row, col)

        self.alert_box = tk.Text(frame, bg=BG2, fg=RED,
                                 font=("Courier", 9), state="disabled",
                                 bd=0, highlightthickness=0,
                                 relief="flat", wrap="word")
        self.alert_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self.alert_box.tag_config("critical", foreground=RED)
        self.alert_box.tag_config("warning",  foreground=YELLOW)
        self.alert_box.tag_config("time",     foreground=MUTED)

    # ── Panel 4: Real-time bar chart ──────────────────────────────────────────
    def _build_chart_panel(self, parent, row, col):
        frame = self._panel(parent, "Vehicle Count — Real-Time Graph", row, col)

        self.canvas = tk.Canvas(frame, bg=BG2, bd=0,
                                highlightthickness=0, relief="flat")
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        legend = tk.Frame(frame, bg=PANEL_BG)
        legend.pack(anchor="w", padx=14, pady=(0, 8))
        for nid, color in CHART_COLORS.items():
            dot = tk.Label(legend, text="■", bg=PANEL_BG, fg=color, font=("Courier", 9))
            dot.pack(side="left")
            tk.Label(legend, text=f" Node-{nid}   ", bg=PANEL_BG, fg=MUTED,
                     font=("Courier", 8)).pack(side="left")

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG2, height=24)
        bar.pack(fill="x", side="bottom")

        items = [
            ("Server:", "RUNNING", GREEN),
            ("UDP Port:", "5005",   BLUE),
            ("Threshold:", "30 vehicles", YELLOW),
        ]
        for label, val, color in items:
            tk.Label(bar, text=label, bg=BG2, fg=MUTED,
                     font=("Courier", 8)).pack(side="left", padx=(12, 2), pady=4)
            tk.Label(bar, text=val, bg=BG2, fg=color,
                     font=("Courier", 8)).pack(side="left", padx=(0, 16), pady=4)

        self.sb_time = tk.Label(bar, text="", bg=BG2, fg=MUTED, font=("Courier", 8))
        self.sb_time.pack(side="right", padx=12)

    # ── Refresh cycle ─────────────────────────────────────────────────────────
    def refresh(self):
        snap = server.get_snapshot()
        self._refresh_stats(snap)
        self._refresh_table(snap)
        self._refresh_alerts(snap)
        self._refresh_chart(snap)
        self.sb_time.config(text=f"Last update: {time.strftime('%H:%M:%S')}")
        self.root.after(UPDATE_INTERVAL_MS, self.refresh)

    def _refresh_stats(self, snap):
        s = snap["stats"]
        nd = snap["node_data"]
        active = sum(1 for n in nd.values()
                     if time.time() - n["last_seen"] < 5)
        total = len(NODES)

        self.stat_pps.config(    text=str(s["packets_per_sec"]))
        self.stat_total.config(  text=f"{s['total_received']:,}")
        self.stat_loss.config(   text=f"{s['packet_loss_pct']}%")
        self.stat_latency.config(text=f"{s['avg_latency_ms']}ms")
        self.stat_nodes.config(  text=f"{active}/{total}")
        self.stat_uptime.config( text=fmt_uptime(snap["uptime"]))

    def _refresh_table(self, snap):
        for row in self.tree.get_children():
            self.tree.delete(row)

        for nid, info in snap["node_data"].items():
            vc    = info["vehicle_count"]
            sig   = info["signal"]
            stat  = info["status"]
            color = STATUS_COLORS.get(stat, TEXT)
            self.tree.insert("", "end",
                             values=(f"Node-{nid}", info["location"],
                                     vc, sig, stat),
                             tags=(stat,))
            self.tree.tag_configure(stat, foreground=color)

    def _refresh_alerts(self, snap):
        self.alert_box.config(state="normal")
        self.alert_box.delete("1.0", "end")
        for entry in snap["alert_log"]:
            tag = entry["level"]
            self.alert_box.insert("end", f"[{entry['time_str']}] ", "time")
            self.alert_box.insert("end", entry["message"] + "\n", tag)
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

        max_val = 50
        padding_x = 10
        padding_y = 10
        chart_h = h - padding_y * 2

        node_ids = list(CHART_COLORS.keys())
        group_count = CHART_HISTORY
        group_w = (w - padding_x * 2) / group_count
        bar_w = max(2, group_w / (len(node_ids) + 1))

        # Y-axis gridlines
        for pct in [0.25, 0.5, 0.75, 1.0]:
            y = padding_y + chart_h * (1 - pct)
            self.canvas.create_line(padding_x, y, w - padding_x, y,
                                    fill=BORDER, dash=(2, 4))
            self.canvas.create_text(padding_x + 2, y - 4,
                                    text=str(int(max_val * pct)),
                                    fill=MUTED, font=("Courier", 7), anchor="w")

        for g in range(group_count):
            for b, nid in enumerate(node_ids):
                val = _history[nid][g]
                bar_h = max(2, (val / max_val) * chart_h)
                x0 = padding_x + g * group_w + b * bar_w
                y0 = padding_y + chart_h - bar_h
                x1 = x0 + bar_w - 1
                y1 = padding_y + chart_h

                alpha = "55" if g < group_count - 1 else "ff"
                color = CHART_COLORS[nid]
                fill = color if g == group_count - 1 else color + "55"

                try:
                    self.canvas.create_rectangle(x0, y0, x1, y1,
                                                 fill=fill, outline="")
                except Exception:
                    pass


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server.start()
    root = tk.Tk()
    app = Dashboard(root)
    root.after(UPDATE_INTERVAL_MS, app.refresh)
    root.mainloop()