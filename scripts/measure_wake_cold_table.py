"""Measure and populate the WorkloadMeasurement table for idle_loaded and cold_start workloads.

Measures:
- "idle_loaded": existing warm session, 10s idle sleep (ensuring GPU drops to P8), time 1 inference.
- "cold_start": fresh session creation + first inference after 10s idle sleep.

Target configurations:
- mlp-256w-4l (B=1, 8, 32)
- mlp-1024w-4l (B=1)
- mlp-3072w-4l (B=1, 8, 32)
- conv-16c-4l (B=1, 8)
- conv-96c-4l (B=1, 8, 32)

Stores every measurement in SQLite (WorkloadMeasurement table).
"""

from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from sqlmodel import Session, select, delete

from app.benchmark import run_cold_start_measurement, run_idle_loaded_measurement
from app.db import AIModel, Device, WorkloadMeasurement, engine, init_db
from app.devices import verify_gpu_identity_mapping


def main():
    init_db()
    # 0. Verify physical GPU adapter mapping via DXGI and NVML load fingerprint
    verify_gpu_identity_mapping()

    with Session(engine) as session:
        # Clear previous workload measurements to ensure clean re-measurement
        session.exec(delete(WorkloadMeasurement))
        session.commit()

        models = {m.name: m for m in session.exec(select(AIModel)).all()}
        devices = {d.key: d for d in session.exec(select(Device).where(Device.is_available == True)).all()}

        target_configs = [
            ("mlp-256w-4l", 1),
            ("mlp-256w-4l", 8),
            ("mlp-256w-4l", 32),
            ("mlp-1024w-4l", 1),
            ("mlp-3072w-4l", 1),
            ("mlp-3072w-4l", 8),
            ("mlp-3072w-4l", 32),
            ("conv-16c-4l", 1),
            ("conv-16c-4l", 8),
            ("conv-96c-4l", 1),
            ("conv-96c-4l", 8),
            ("conv-96c-4l", 32),
        ]

        # Verify all target models exist
        for mname, _ in target_configs:
            if mname not in models:
                print(f"ERROR: Model {mname} not found in database!")
                sys.exit(1)

        print("=" * 95)
        print("MEASURING WAKE/COLD WORKLOAD TABLE ON REAL HARDWARE")
        print("=" * 95)

        records_added = 0
        order_devices = ["cpu", "dml:0", "dml:1"]

        for idx, (mname, batch) in enumerate(target_configs, 1):
            model = models[mname]
            print(f"\n[{idx}/{len(target_configs)}] Model: {mname} (B={batch})")

            for dev_key in order_devices:
                dev = devices.get(dev_key)
                if not dev:
                    continue

                # Device-appropriate idle sleep: 10s for discrete RTX to enter P8 sleep
                idle_s = 10.0 if dev_key == "dml:1" else (2.0 if dev_key == "dml:0" else 0.5)

                # 1. Measure idle_loaded (warm session, idle_s sleep, 1 inference)
                print(f"  {dev_key:<6} measuring idle_loaded (sleep {idle_s}s)...", end=" ", flush=True)
                idle_res = run_idle_loaded_measurement(model, dev, batch, idle_s=idle_s)
                print(f"{idle_res['latency_ms']:.3f} ms (P-state: {idle_res.get('nvml_pstate', 'N/A')})")

                now_iso = datetime.now(timezone.utc).isoformat()
                wm_idle = WorkloadMeasurement(
                    ai_model_id=model.id,
                    device_id=dev.id,
                    batch=batch,
                    workload="idle_loaded",
                    latency_ms=idle_res["latency_ms"],
                    idle_s=idle_s,
                    nvml_pstate=idle_res.get("nvml_pstate"),
                    created_at=now_iso,
                )
                session.add(wm_idle)
                records_added += 1

                # 2. Measure cold_start (session creation + first inference after idle_s sleep)
                print(f"  {dev_key:<6} measuring cold_start (sleep {idle_s}s)...", end=" ", flush=True)
                cold_res = run_cold_start_measurement(model, dev, batch, idle_s=idle_s)
                print(f"{cold_res['latency_ms']:.3f} ms (create: {cold_res['session_create_ms']:.3f} ms, inf: {cold_res['first_run_ms']:.3f} ms)")

                now_iso = datetime.now(timezone.utc).isoformat()
                wm_cold = WorkloadMeasurement(
                    ai_model_id=model.id,
                    device_id=dev.id,
                    batch=batch,
                    workload="cold_start",
                    latency_ms=cold_res["latency_ms"],
                    session_create_ms=cold_res.get("session_create_ms"),
                    first_run_ms=cold_res.get("first_run_ms"),
                    idle_s=idle_s,
                    nvml_pstate=cold_res.get("nvml_pstate"),
                    created_at=now_iso,
                )
                session.add(wm_cold)
                records_added += 1

            session.commit()

        print("\n" + "=" * 95)
        print(f"STORED {records_added} WORKLOAD MEASUREMENTS IN SQLITE DATABASE")
        print("=" * 95)

        # Print summary table of empirical slowdown ratios per family and device
        print(f"\n{'Device':<8} {'Family':<8} {'Workload':<12} {'Median Ratio':>12} {'Min Ratio':>10} {'Max Ratio':>10} {'Count':>6}")
        print("-" * 72)
        from app.router import get_workload_slowdown_ratio

        for dev_key in order_devices:
            dev = devices.get(dev_key)
            if not dev:
                continue
            for fam in ["mlp", "conv"]:
                for wl in ["idle_loaded", "cold_start"]:
                    ratio = get_workload_slowdown_ratio(session, dev.id, fam, wl)
                    print(f"{dev_key:<8} {fam:<8} {wl:<12} {ratio:>11.2f}x")


if __name__ == "__main__":
    main()
