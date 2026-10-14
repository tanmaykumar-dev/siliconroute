"""SiliconRoute Desktop Application.

A standalone native Windows desktop application that displays real-time IRL
hardware telemetry (CPU, RAM, NVIDIA RTX 5070, Battery) and executes real
on-device AI model benchmarking and load balancing directly on hardware.

No web browser or localhost address bar needed.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import font as tkfont, messagebox, ttk
from typing import Any, Optional

import psutil
from sqlmodel import Session, select

from app.db import AIModel, Decision, Device, engine
from app.power import BatteryReader, nvml_reader
from app.router import execute_verification, route_model
from app.telemetry import sample_telemetry

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("siliconroute_desktop")

# Enable high-DPI scaling on Windows 10/11
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# Theme Colors (Dark modern semiconductor workstation)
C_BG = "#0B0E14"           # Deep dark canvas
C_PANEL = "#151B26"        # Surface cards
C_PANEL_ALT = "#1E2638"    # Accent panel
C_BORDER = "#2B3548"       # Hairline rules
C_TEXT = "#F0F4FC"         # Crisp primary text
C_TEXT_MUTED = "#8B9BB4"   # Secondary label text
C_SIGNAL = "#FF453A"       # SiliconRoute signal red
C_EMERALD = "#00E599"      # Hardware live active green
C_BLUE = "#3B82F6"         # NVIDIA / compute blue
C_AMBER = "#F59E0B"        # Warning / thermal amber
C_CPU = "#00D26A"          # CPU green
C_IGPU = "#A855F7"         # AMD iGPU purple
C_DGPU = "#3B82F6"         # RTX dGPU blue


class SiliconRouteApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SiliconRoute — Hardware AI Load Balancer & Physical Monitor")
        self.root.geometry("1260x860")
        self.root.minsize(1050, 720)
        self.root.configure(bg=C_BG)

        self.battery_reader = BatteryReader()
        self.running = True

        # Telemetry rolling history for 60s sparkline
        self.history_len = 60
        self.history_cpu_pct: list[float] = [0.0] * self.history_len
        self.history_gpu_w: list[float] = [0.0] * self.history_len

        # Benchmarking state
        self.is_benchmarking = False

        self._init_styles()
        self._build_ui()

        # Start background 1 Hz telemetry sampling loop
        self.telemetry_thread = threading.Thread(target=self._telemetry_worker, daemon=True)
        self.telemetry_thread.start()

        # Protocol cleanup
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        # Configure base styles
        style.configure(".", background=C_BG, foreground=C_TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=C_BG)
        style.configure("Panel.TFrame", background=C_PANEL)
        style.configure("PanelAlt.TFrame", background=C_PANEL_ALT)

        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=C_TEXT, background=C_BG)
        style.configure("Subhead.TLabel", font=("Segoe UI", 11), foreground=C_TEXT_MUTED, background=C_BG)

        style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"), foreground=C_TEXT, background=C_PANEL)
        style.configure("CardMuted.TLabel", font=("Segoe UI", 9), foreground=C_TEXT_MUTED, background=C_PANEL)
        style.configure("MetricBig.TLabel", font=("Segoe UI", 24, "bold"), foreground=C_EMERALD, background=C_PANEL)
        style.configure("MetricUnit.TLabel", font=("Segoe UI", 10), foreground=C_TEXT_MUTED, background=C_PANEL)

        style.configure(
            "Action.TButton",
            font=("Segoe UI", 11, "bold"),
            background=C_EMERALD,
            foreground="#000000",
            borderwidth=0,
            padding=10,
        )
        style.map("Action.TButton", background=[("active", "#00C782"), ("disabled", "#334155")])

        style.configure(
            "TCombobox",
            background=C_PANEL_ALT,
            foreground=C_TEXT,
            fieldbackground=C_PANEL_ALT,
            darkcolor=C_BORDER,
            lightcolor=C_BORDER,
        )

    def _build_ui(self) -> None:
        # Main layout: Top Header, Middle Grid (Telemetry & Controls), Bottom Log
        self.main_container = tk.Frame(self.root, bg=C_BG, padx=20, pady=16)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self._build_header(self.main_container)

        # Content split: Left column (Hardware Sensors & Live Graph), Right column (Router Workbench & Verification)
        content_frame = tk.Frame(self.main_container, bg=C_BG)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        content_frame.columnconfigure(0, weight=5)
        content_frame.columnconfigure(1, weight=6)
        content_frame.rowconfigure(0, weight=1)

        self.left_col = tk.Frame(content_frame, bg=C_BG)
        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.right_col = tk.Frame(content_frame, bg=C_BG)
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        self._build_telemetry_panel(self.left_col)
        self._build_router_panel(self.right_col)

    def _build_header(self, parent: tk.Widget) -> None:
        hdr_frame = tk.Frame(parent, bg=C_BG)
        hdr_frame.pack(fill=tk.X, pady=(0, 10))

        # Title & Branding
        title_box = tk.Frame(hdr_frame, bg=C_BG)
        title_box.pack(side=tk.LEFT)

        app_title = tk.Label(
            title_box,
            text="SILICONROUTE",
            font=("Segoe UI", 18, "bold"),
            fg=C_TEXT,
            bg=C_BG,
            letter_spacing=1 if hasattr(tk.Label, "letter_spacing") else None,
        )
        app_title.pack(anchor="w")

        tagline = tk.Label(
            title_box,
            text="Hardware-in-the-Loop AI Load Balancer • Physical Multi-Processor Telemetry",
            font=("Segoe UI", 10),
            fg=C_TEXT_MUTED,
            bg=C_BG,
        )
        tagline.pack(anchor="w")

        # Top-right live heartbeat indicator
        status_box = tk.Frame(hdr_frame, bg=C_PANEL, padx=12, pady=6, highlightbackground=C_BORDER, highlightthickness=1)
        status_box.pack(side=tk.RIGHT)

        self.lbl_heartbeat = tk.Label(
            status_box,
            text="● LIVE HARDWARE POLLING (1 Hz)",
            font=("Segoe UI", 9, "bold"),
            fg=C_EMERALD,
            bg=C_PANEL,
        )
        self.lbl_heartbeat.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_time = tk.Label(status_box, text="", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_PANEL)
        self.lbl_time.pack(side=tk.LEFT)

    def _build_telemetry_panel(self, parent: tk.Widget) -> None:
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        # 1. Hardware Devices Status Strip
        dev_strip = tk.Frame(parent, bg=C_PANEL, padx=14, pady=10, highlightbackground=C_BORDER, highlightthickness=1)
        dev_strip.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        tk.Label(dev_strip, text="PHYSICAL PROCESSOR TOPOLOGY", font=("Segoe UI", 9, "bold"), fg=C_TEXT_MUTED, bg=C_PANEL).pack(anchor="w", pady=(0, 6))

        chips_row = tk.Frame(dev_strip, bg=C_PANEL)
        chips_row.pack(fill=tk.X)

        self._chip_badge(chips_row, "CPU", "AMD Ryzen 9 8940HX", "16 Cores / 32 Threads", C_CPU)
        self._chip_badge(chips_row, "iGPU", "AMD Radeon 610M", "DirectML (Adapter 0)", C_IGPU)
        self._chip_badge(chips_row, "dGPU", "NVIDIA RTX 5070", "8GB VRAM • NVML Active", C_DGPU)

        # 2. Live Telemetry Metrics Cards (2x2 Grid)
        metrics_grid = tk.Frame(parent, bg=C_BG)
        metrics_grid.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        metrics_grid.columnconfigure(0, weight=1)
        metrics_grid.columnconfigure(1, weight=1)

        # Card A: CPU & RAM
        card_cpu = tk.Frame(metrics_grid, bg=C_PANEL, padx=14, pady=12, highlightbackground=C_BORDER, highlightthickness=1)
        card_cpu.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=5)

        tk.Label(card_cpu, text="CPU & MEMORY LOAD", font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w")
        self.lbl_cpu_val = tk.Label(card_cpu, text="0.0 %", font=("Segoe UI", 22, "bold"), fg=C_CPU, bg=C_PANEL)
        self.lbl_cpu_val.pack(anchor="w", pady=(2, 0))

        self.bar_cpu = ttk.Progressbar(card_cpu, orient="horizontal", length=100, mode="determinate")
        self.bar_cpu.pack(fill=tk.X, pady=(4, 6))

        self.lbl_ram_val = tk.Label(card_cpu, text="RAM: -- / -- GB (--%)", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_PANEL)
        self.lbl_ram_val.pack(anchor="w")

        # Card B: NVIDIA RTX 5070
        card_gpu = tk.Frame(metrics_grid, bg=C_PANEL, padx=14, pady=12, highlightbackground=C_BORDER, highlightthickness=1)
        card_gpu.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=5)

        tk.Label(card_gpu, text="NVIDIA RTX 5070 POWER & TEMP", font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w")
        gpu_stat_row = tk.Frame(card_gpu, bg=C_PANEL)
        gpu_stat_row.pack(anchor="w", pady=(2, 0))

        self.lbl_gpu_power = tk.Label(gpu_stat_row, text="-- W", font=("Segoe UI", 22, "bold"), fg=C_DGPU, bg=C_PANEL)
        self.lbl_gpu_power.pack(side=tk.LEFT)
        self.lbl_gpu_temp = tk.Label(gpu_stat_row, text="  (-- °C)", font=("Segoe UI", 16, "bold"), fg=C_TEXT_MUTED, bg=C_PANEL)
        self.lbl_gpu_temp.pack(side=tk.LEFT)

        self.lbl_gpu_details = tk.Label(card_gpu, text="Util: --%  •  Clock: -- MHz  •  VRAM: -- MB", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_PANEL)
        self.lbl_gpu_details.pack(anchor="w", pady=(6, 0))

        self.lbl_gpu_pstate = tk.Label(card_gpu, text="Power State: P-- (Active/Idle)", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_PANEL)
        self.lbl_gpu_pstate.pack(anchor="w")

        # Card C: Battery & Power Delivery
        card_bat = tk.Frame(metrics_grid, bg=C_PANEL, padx=14, pady=12, highlightbackground=C_BORDER, highlightthickness=1)
        card_bat.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)

        tk.Label(card_bat, text="POWER SOURCE & BATTERY DELIVERY", font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w")
        self.lbl_bat_status = tk.Label(card_bat, text="Plugged In (AC Mains)  •  Battery: 100%", font=("Segoe UI", 11), fg=C_EMERALD, bg=C_PANEL)
        self.lbl_bat_status.pack(anchor="w", pady=(4, 0))

        self.lbl_bat_rate = tk.Label(card_bat, text="Battery Discharge Rate: 0.0 W (Running on Wall Power)", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_PANEL)
        self.lbl_bat_rate.pack(anchor="w")

        # 3. Live 60-Second Rolling Graph
        graph_box = tk.Frame(parent, bg=C_PANEL, padx=14, pady=12, highlightbackground=C_BORDER, highlightthickness=1)
        graph_box.grid(row=2, column=0, sticky="nsew", pady=(5, 0))

        graph_hdr = tk.Frame(graph_box, bg=C_PANEL)
        graph_hdr.pack(fill=tk.X, pady=(0, 6))
        tk.Label(graph_hdr, text="REAL-TIME 60-SECOND TELEMETRY GRAPH", font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_PANEL).pack(side=tk.LEFT)

        # Legend
        leg_frame = tk.Frame(graph_hdr, bg=C_PANEL)
        leg_frame.pack(side=tk.RIGHT)
        tk.Label(leg_frame, text="■ CPU Load %", font=("Segoe UI", 9, "bold"), fg=C_CPU, bg=C_PANEL).pack(side=tk.LEFT, padx=6)
        tk.Label(leg_frame, text="■ RTX Power (W)", font=("Segoe UI", 9, "bold"), fg=C_DGPU, bg=C_PANEL).pack(side=tk.LEFT, padx=6)

        # Canvas for custom sparklines
        self.canvas = tk.Canvas(graph_box, bg="#0E131D", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def _chip_badge(self, parent: tk.Widget, chip_type: str, name: str, detail: str, color: str) -> None:
        badge = tk.Frame(parent, bg=C_PANEL_ALT, padx=10, pady=6, highlightbackground=C_BORDER, highlightthickness=1)
        badge.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        top = tk.Frame(badge, bg=C_PANEL_ALT)
        top.pack(fill=tk.X)
        tk.Label(top, text=chip_type, font=("Segoe UI", 8, "bold"), fg=color, bg=C_PANEL_ALT).pack(side=tk.LEFT)

        tk.Label(badge, text=name, font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_PANEL_ALT).pack(anchor="w", pady=(2, 0))
        tk.Label(badge, text=detail, font=("Segoe UI", 8), fg=C_TEXT_MUTED, bg=C_PANEL_ALT).pack(anchor="w")

    def _build_router_panel(self, parent: tk.Widget) -> None:
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        # Workbench Control Box
        bench_box = tk.Frame(parent, bg=C_PANEL, padx=16, pady=14, highlightbackground=C_BORDER, highlightthickness=1)
        bench_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        tk.Label(bench_box, text="AI WORKLOAD ROUTER & ON-HARDWARE BENCHMARK", font=("Segoe UI", 11, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w")
        tk.Label(bench_box, text="Select neural network parameters and execute real physical inference across CPU, iGPU, and dGPU.", font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_PANEL).pack(anchor="w", pady=(0, 12))

        # Selectors Grid
        controls_grid = tk.Frame(bench_box, bg=C_PANEL)
        controls_grid.pack(fill=tk.X, pady=(0, 14))
        controls_grid.columnconfigure(0, weight=1)
        controls_grid.columnconfigure(1, weight=1)
        controls_grid.columnconfigure(2, weight=1)

        # Model Selector
        tk.Label(controls_grid, text="Model Architecture:", font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL).grid(row=0, column=0, sticky="w")
        self.combo_model = ttk.Combobox(
            controls_grid,
            values=[
                "mlp-256w-4l (Small, Cache-res)",
                "mlp-3072w-4l (Large Compute)",
                "conv-96c-4l (Vision Layer)",
                "mlp-1024w-4l (Medium MLP)",
                "conv-16c-4l (Light Conv)",
            ],
            state="readonly",
        )
        self.combo_model.current(0)
        self.combo_model.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))

        # Objective Selector
        tk.Label(controls_grid, text="Optimization Goal:", font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL).grid(row=0, column=1, sticky="w")
        self.combo_mode = ttk.Combobox(
            controls_grid,
            values=["fastest (Minimize Latency)", "battery (Minimize Energy)", "cool (Minimize Heat)", "balanced"],
            state="readonly",
        )
        self.combo_mode.current(0)
        self.combo_mode.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(4, 0))

        # Workload Selector
        tk.Label(controls_grid, text="Execution Context:", font=("Segoe UI", 9, "bold"), fg=C_TEXT, bg=C_PANEL).grid(row=0, column=2, sticky="w")
        self.combo_workload = ttk.Combobox(
            controls_grid,
            values=["sustained (Warm Execution)", "single (Cold Start Penalty)"],
            state="readonly",
        )
        self.combo_workload.current(0)
        self.combo_workload.grid(row=1, column=2, sticky="ew", padx=(4, 0), pady=(4, 0))

        # Action Buttons Row
        action_row = tk.Frame(bench_box, bg=C_PANEL)
        action_row.pack(fill=tk.X, pady=(6, 0))

        self.btn_run = tk.Button(
            action_row,
            text="⚡  ROUTE & BENCHMARK ON PHYSICAL HARDWARE NOW",
            font=("Segoe UI", 11, "bold"),
            bg=C_EMERALD,
            fg="#000000",
            activebackground="#00C782",
            activeforeground="#000000",
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=10,
            command=self._on_run_clicked,
        )
        self.btn_run.pack(fill=tk.X)

        self.lbl_run_status = tk.Label(
            bench_box,
            text="Ready. Select parameters and click above to benchmark live silicon.",
            font=("Segoe UI", 9),
            fg=C_TEXT_MUTED,
            bg=C_PANEL,
        )
        self.lbl_run_status.pack(anchor="w", pady=(8, 0))

        # Verification Results Display Card
        self.results_box = tk.Frame(parent, bg=C_PANEL, padx=16, pady=14, highlightbackground=C_BORDER, highlightthickness=1)
        self.results_box.grid(row=1, column=0, sticky="nsew")

        tk.Label(self.results_box, text="LIVE VERIFICATION RESULTS", font=("Segoe UI", 11, "bold"), fg=C_TEXT, bg=C_PANEL).pack(anchor="w")

        # Winner Banner
        self.winner_banner = tk.Frame(self.results_box, bg=C_PANEL_ALT, padx=12, pady=10, highlightbackground=C_EMERALD, highlightthickness=1)
        self.winner_banner.pack(fill=tk.X, pady=(8, 10))

        self.lbl_winner_title = tk.Label(self.winner_banner, text="Awaiting execution run...", font=("Segoe UI", 13, "bold"), fg=C_TEXT, bg=C_PANEL_ALT)
        self.lbl_winner_title.pack(anchor="w")

        self.lbl_winner_reason = tk.Label(
            self.winner_banner,
            text="Click 'ROUTE & BENCHMARK' above to physically run inference on this machine.",
            font=("Segoe UI", 9),
            fg=C_TEXT_MUTED,
            bg=C_PANEL_ALT,
            wraplength=520,
            justify="left",
        )
        self.lbl_winner_reason.pack(anchor="w", pady=(4, 0))

        # Results Table
        table_frame = tk.Frame(self.results_box, bg=C_PANEL)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.tree = ttk.Treeview(
            table_frame,
            columns=("device", "predicted", "actual", "speedup", "status"),
            show="headings",
            height=5,
        )
        self.tree.heading("device", text="Hardware Device")
        self.tree.heading("predicted", text="Predicted Latency")
        self.tree.heading("actual", text="Actual Measured")
        self.tree.heading("speedup", text="Speedup / Regret")
        self.tree.heading("status", text="Decision Status")

        self.tree.column("device", width=180)
        self.tree.column("predicted", width=105, anchor="e")
        self.tree.column("actual", width=105, anchor="e")
        self.tree.column("speedup", width=110, anchor="e")
        self.tree.column("status", width=110, anchor="center")

        self.tree.pack(fill=tk.BOTH, expand=True)

        # Explanation note
        self.lbl_explanation = tk.Label(
            self.results_box,
            text="Every measurement executes real mathematical forward passes with physical timings.",
            font=("Segoe UI", 9, "italic"),
            fg=C_TEXT_MUTED,
            bg=C_PANEL,
        )
        self.lbl_explanation.pack(anchor="w", pady=(8, 0))

    def _telemetry_worker(self) -> None:
        """Background 1 Hz sampler for real physical hardware readings."""
        # Prime psutil cpu
        psutil.cpu_percent(interval=None)

        while self.running:
            t0 = time.time()
            try:
                sample = sample_telemetry(self.battery_reader)
                self.root.after(0, self._update_telemetry_ui, sample)
            except Exception as exc:
                logger.error("Telemetry sampling error: %s", exc)

            elapsed = time.time() - t0
            sleep_time = max(1.0 - elapsed, 0.1)
            time.sleep(sleep_time)

    def _update_telemetry_ui(self, sample: dict[str, Any]) -> None:
        """Called on main UI thread with fresh 1 Hz hardware sample."""
        # Header clock
        now_str = datetime.now().strftime("%H:%M:%S")
        self.lbl_time.config(text=now_str)

        # 1. CPU & RAM
        cpu_pct = sample.get("cpu_pct", 0.0)
        ram_pct = sample.get("ram_pct", 0.0)

        self.lbl_cpu_val.config(text=f"{cpu_pct:.1f} %")
        self.bar_cpu["value"] = cpu_pct

        vm = psutil.virtual_memory()
        used_gb = vm.used / (1024 ** 3)
        total_gb = vm.total / (1024 ** 3)
        self.lbl_ram_val.config(text=f"RAM: {used_gb:.1f} / {total_gb:.1f} GB ({ram_pct:.1f}%)")

        # 2. NVIDIA GPU
        gpu_power_w = sample.get("gpu_power_w")
        gpu_temp_c = sample.get("gpu_temp_c")
        gpu_util_pct = sample.get("gpu_util_pct")
        gpu_mem_mb = sample.get("gpu_mem_used_mb")
        gpu_clock_mhz = sample.get("gpu_clock_sm_mhz")
        gpu_pstate = sample.get("gpu_pstate")

        if gpu_power_w is not None:
            self.lbl_gpu_power.config(text=f"{gpu_power_w:.1f} W")
        else:
            self.lbl_gpu_power.config(text="-- W")

        if gpu_temp_c is not None:
            color = C_TEXT_MUTED
            if gpu_temp_c >= 80:
                color = C_SIGNAL
            elif gpu_temp_c >= 70:
                color = C_AMBER
            else:
                color = C_EMERALD
            self.lbl_gpu_temp.config(text=f"  ({gpu_temp_c:.0f} °C)", fg=color)
        else:
            self.lbl_gpu_temp.config(text="  (-- °C)", fg=C_TEXT_MUTED)

        util_str = f"{gpu_util_pct:.0f}%" if gpu_util_pct is not None else "--%"
        clock_str = f"{gpu_clock_mhz} MHz" if gpu_clock_mhz is not None else "-- MHz"
        mem_str = f"{gpu_mem_mb:.0f} MB" if gpu_mem_mb is not None else "-- MB"
        self.lbl_gpu_details.config(text=f"Util: {util_str}  •  Clock: {clock_str}  •  VRAM: {mem_str}")

        if gpu_pstate is not None:
            pstate_desc = "P0 (Max 3D)" if gpu_pstate == 0 else f"P{gpu_pstate} (Video/Compute)" if gpu_pstate <= 5 else f"P{gpu_pstate} (Low Power/Idle)"
            self.lbl_gpu_pstate.config(text=f"PCIe Power State: {pstate_desc}")
        else:
            self.lbl_gpu_pstate.config(text="PCIe Power State: P--")

        # 3. Battery
        plugged_in = sample.get("plugged_in")
        bat_pct = sample.get("battery_pct")
        disch_w = sample.get("discharge_w")

        plug_text = "Plugged In (AC Mains)" if plugged_in else "On Battery"
        bat_str = f"{bat_pct:.0f}%" if bat_pct is not None else "--%"
        self.lbl_bat_status.config(
            text=f"{plug_text}  •  Charge: {bat_str}",
            fg=C_EMERALD if plugged_in else C_AMBER,
        )

        if not plugged_in and disch_w is not None and disch_w > 0:
            self.lbl_bat_rate.config(text=f"Battery Discharge Rate: {disch_w:.1f} W (Active Power Draw)")
        elif plugged_in:
            self.lbl_bat_rate.config(text="Battery Discharge Rate: 0.0 W (Running on Wall Power)")
        else:
            self.lbl_bat_rate.config(text="Battery Discharge Rate: Standby")

        # 4. Update Rolling History & Canvas Graph
        self.history_cpu_pct.append(cpu_pct)
        self.history_cpu_pct.pop(0)

        gpu_w_val = gpu_power_w if (gpu_power_w is not None and gpu_power_w > 0) else 0.0
        self.history_gpu_w.append(gpu_w_val)
        self.history_gpu_w.pop(0)

        self._draw_graph()

    def _draw_graph(self) -> None:
        """Render rolling 60-second hardware sparkline on Tkinter canvas."""
        canvas = self.canvas
        canvas.delete("all")

        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 20 or h < 20:
            return

        # Grid lines (25%, 50%, 75%)
        for frac in (0.25, 0.50, 0.75):
            y = int(h * frac)
            canvas.create_line(0, y, w, y, fill="#1B2230", dash=(2, 4))

        # Max scale: 100 for CPU, up to 100W for GPU
        n = len(self.history_cpu_pct)
        step = w / max(n - 1, 1)

        # Draw CPU series (green)
        cpu_coords = []
        for i, val in enumerate(self.history_cpu_pct):
            x = i * step
            norm = min(max(val / 100.0, 0.0), 1.0)
            y = h - (norm * (h - 10)) - 5
            cpu_coords.extend([x, y])

        if len(cpu_coords) >= 4:
            canvas.create_line(cpu_coords, fill=C_CPU, width=2, smooth=True)

        # Draw GPU Power series (blue)
        gpu_max_scale = 80.0  # 80 Watts full scale
        gpu_coords = []
        for i, val in enumerate(self.history_gpu_w):
            x = i * step
            norm = min(max(val / gpu_max_scale, 0.0), 1.0)
            y = h - (norm * (h - 10)) - 5
            gpu_coords.extend([x, y])

        if len(gpu_coords) >= 4:
            canvas.create_line(gpu_coords, fill=C_DGPU, width=2, smooth=True)

    def _on_run_clicked(self) -> None:
        if self.is_benchmarking:
            return

        self.is_benchmarking = True
        self.btn_run.config(state="disabled", text="⏳ EXECUTING ON PHYSICAL HARDWARE...")
        self.lbl_run_status.config(text="Benchmarking active. Running physical inference on CPU, iGPU, and dGPU...")

        # Parse selected options
        model_selection = self.combo_model.get().split()[0]
        mode_selection = self.combo_mode.get().split()[0]
        workload_selection = self.combo_workload.get().split()[0]

        threading.Thread(
            target=self._benchmark_worker,
            args=(model_selection, mode_selection, workload_selection),
            daemon=True,
        ).start()

    def _benchmark_worker(self, model_name: str, mode: str, workload: str) -> None:
        """Executes the route and physical verification on physical chips."""
        try:
            with Session(engine) as session:
                model = session.exec(select(AIModel).where(AIModel.name == model_name)).first()
                if not model:
                    raise RuntimeError(f"Model '{model_name}' not found in database")

                logger.info("Computing routing decision for %s (mode=%s, workload=%s)...", model.name, mode, workload)
                decision_dict = route_model(
                    session=session,
                    model_id=model.id,
                    batch=1,
                    mode=mode,
                    workload=workload,
                    allow_explore=False,
                )

                logger.info("Executing on-hardware verification across all physical chips...")
                decision = execute_verification(
                    session=session,
                    decision_dict=decision_dict,
                    runs_count=5 if workload == "sustained" else 1,
                    workload=workload,
                )

                self.root.after(0, self._display_benchmark_results, decision_dict, decision)

        except Exception as exc:
            logger.error("Benchmark error: %s", exc, exc_info=True)
            self.root.after(0, self._display_benchmark_error, str(exc))
        finally:
            self.root.after(0, self._finish_benchmark)

    def _display_benchmark_results(self, decision_dict: dict[str, Any], decision: Decision) -> None:
        chosen_key = decision_dict["chosen_device_key"]
        chosen_cand = next((c for c in decision_dict["candidates"] if c["device_key"] == chosen_key), None)
        chosen_label = chosen_cand["device_label"] if chosen_cand else chosen_key

        # Winner banner
        actual_str = f"{decision.actual_ms:.3f} ms" if decision.actual_ms else "N/A"
        self.lbl_winner_title.config(
            text=f"WINNER: {chosen_label} ({actual_str})",
            fg=C_EMERALD if decision.was_best else C_AMBER,
        )
        self.winner_banner.config(highlightbackground=C_EMERALD if decision.was_best else C_AMBER)

        reason_text = decision_dict.get("reason", "Optimal processor selected based on empirical scaling and wake penalty.")
        self.lbl_winner_reason.config(text=reason_text)

        # Clear and repopulate table
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Parse verified measured times from decision context
        context = json.loads(decision.context_json) if decision.context_json else {}
        measured_times = context.get("measured_times", {})

        # Find best time
        valid_times = [t for t in measured_times.values() if t is not None]
        best_time = min(valid_times) if valid_times else None

        for c in decision_dict.get("candidates", []):
            dev_id = str(c["device_id"])
            pred_ms = f"{c['effective_latency_ms']:.3f} ms"
            actual_time = measured_times.get(dev_id)
            actual_ms_str = f"{actual_time:.3f} ms" if actual_time is not None else "--"

            is_chosen = (c["device_key"] == chosen_key)
            is_best = (actual_time is not None and best_time is not None and abs(actual_time - best_time) < 1e-4)

            if is_best:
                status = "★ WINNER"
            elif is_chosen:
                status = "SELECTED"
            else:
                status = "CANDIDATE"

            # Compute relative speedup
            if actual_time and best_time and actual_time > best_time:
                regret = ((actual_time - best_time) / best_time) * 100.0
                speedup_str = f"+{regret:.1f}% slower"
            elif is_best:
                speedup_str = "Optimal (0.0%)"
            else:
                speedup_str = "--"

            self.tree.insert(
                "",
                tk.END,
                values=(c["device_label"], pred_ms, actual_ms_str, speedup_str, status),
            )

        self.lbl_run_status.config(
            text=f"Inference verified successfully on real physical hardware at {datetime.now().strftime('%H:%M:%S')}."
        )

    def _display_benchmark_error(self, err_msg: str) -> None:
        self.lbl_run_status.config(text=f"Benchmark error: {err_msg}", fg=C_SIGNAL)
        messagebox.showerror("Execution Error", f"Hardware verification failed:\n\n{err_msg}")

    def _finish_benchmark(self) -> None:
        self.is_benchmarking = False
        self.btn_run.config(state="normal", text="⚡  ROUTE & BENCHMARK ON PHYSICAL HARDWARE NOW")

    def _on_close(self) -> None:
        self.running = False
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = SiliconRouteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
