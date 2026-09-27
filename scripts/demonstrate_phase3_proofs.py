"""Demonstrate Phase 3 proofs:
1. Real NVML energy measurement on dml:1 (mlp-1024, batch 8).
2. Live SSE telemetry stream via curl.exe.
"""

from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from sqlmodel import Session, select
import numpy as np

from app.db import AIModel, BenchSession, Device, Run, engine
from app.energy import run_energy_measurement
from app.power import nvml_reader


def run_real_energy_job():
    print("=" * 80)
    print("PROOF 1: REAL ENERGY JOB ON dml:1 (mlp-1024, batch 8) VIA NVML COUNTER")
    print("=" * 80)

    with Session(engine) as session:
        # Find mlp-1024 and dml:1
        model = session.exec(select(AIModel).where(AIModel.name.like("mlp-1024%"))).first()
        if not model:
            model = session.exec(select(AIModel).where(AIModel.name.like("mlp_1024%"))).first()
        device = session.exec(select(Device).where(Device.key == "dml:1")).first()

        assert model is not None, "Model mlp-1024 not found in database"
        assert device is not None, "Device dml:1 not found in database"

        now_iso = datetime.now(timezone.utc).isoformat()
        bench_sess = BenchSession(
            kind="energy",
            status="running",
            config_json=json.dumps({"model_id": model.id, "device_id": device.id, "batch": 8}),
            created_at=now_iso,
            notes="Phase 3 Proof: Real NVML energy measurement on dml:1",
        )
        session.add(bench_sess)
        session.commit()
        session.refresh(bench_sess)

        # 1. Sample idle GPU baseline power
        print("Measuring idle GPU power baseline (5s)...")
        idle_samples: list[float] = []
        for _ in range(5):
            m = nvml_reader.read_metrics()
            pw = m.get("gpu_power_w")
            if pw is not None:
                idle_samples.append(pw)
            time.sleep(1.0)
        idle_w = float(np.median(idle_samples)) if idle_samples else 0.0

        # Before energy counter
        e_before = nvml_reader.get_total_energy_mj()

        # Run 10-second load window with 2-second settle
        print(f"Running energy load window on {device.label} ({model.name}, batch=8)...")
        run = run_energy_measurement(
            session=session,
            bench_session_id=bench_sess.id,
            model=model,
            device=device,
            batch=8,
            idle_baseline_w=idle_w,
            load_duration_s=10,
            settle_s=2,
        )

        e_after = nvml_reader.get_total_energy_mj()
        delta_mj = (e_after - e_before) if (e_after is not None and e_before is not None) else None

        bench_sess.status = "done"
        bench_sess.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_sess)
        session.commit()

        print("-" * 80)
        print("REAL MEASUREMENT RESULTS:")
        print(f"  Device:             {device.label} ({device.key})")
        print(f"  Model & Batch:      {model.name}, Batch=8")
        print(f"  Energy Method:      {run.energy_method}")
        print(f"  Idle Power:         {run.idle_w:.3f} W")
        print(f"  Load Power (median):{run.load_w:.3f} W")
        print(f"  Delta Energy:       {delta_mj:.1f} mJ" if delta_mj is not None else "  Delta Energy:       N/A")
        print(f"  Inferences Counted: {run.timed_runs}")
        print(f"  Energy per Inf:     {run.energy_mj_per_inf:.3f} mJ/inf")
        print("-" * 80)
        print()


def run_live_sse_stream_proof():
    print("=" * 80)
    print("PROOF 2: LIVE SSE TELEMETRY STREAM VIA curl.exe")
    print("=" * 80)

    # Launch local uvicorn in subprocess
    print("Starting temporary uvicorn server on 127.0.0.1:8000...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for server startup
        time.sleep(3.0)

        cmd = ["curl.exe", "-N", "--max-time", "6", "http://127.0.0.1:8000/api/telemetry/stream"]
        print(f"Executing: {' '.join(cmd)}")
        print("-" * 80)
        curl_proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = curl_proc.stdout
        if output:
            print(output.strip())
        else:
            print(f"(stderr): {curl_proc.stderr}")
        print("-" * 80)
    finally:
        print("Stopping uvicorn server...")
        proc.terminate()
        proc.wait(timeout=5)
    print()


if __name__ == "__main__":
    run_real_energy_job()
    run_live_sse_stream_proof()
