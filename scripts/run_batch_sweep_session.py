"""Execute batch sweep (B = 1, 2, 4, 8, 16, 32) for mlp-3072w-4l and conv-96c-4l on dml:0 and dml:1."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import AIModel, BenchSession, Device, Run, engine
from app.jobs import start_worker
from app.main import app

def main():
    print("=" * 80)
    print("BATCH SWEEP SESSION: B = 1, 2, 4, 8, 16, 32 on dml:0 and dml:1")
    print("=" * 80)

    start_worker()

    with Session(engine) as session:
        m_mlp = session.exec(select(AIModel).where(AIModel.name == "mlp-3072w-4l")).first()
        m_conv = session.exec(select(AIModel).where(AIModel.name == "conv-96c-4l")).first()
        assert m_mlp and m_conv, "Required models not found in DB!"

        dml0 = session.exec(select(Device).where(Device.key == "dml:0")).first()
        dml1 = session.exec(select(Device).where(Device.key == "dml:1")).first()
        assert dml0 and dml1, "Required devices not found in DB!"

        model_ids = [m_mlp.id, m_conv.id]
        device_ids = [dml0.id, dml1.id]

    client = TestClient(app)

    batches = [1, 2, 4, 8, 16, 32]
    payload = {
        "kind": "latency",
        "model_ids": model_ids,
        "device_ids": device_ids,
        "batches": batches,
        "warmup": 5,
        "runs": 20,
        "notes": "Phase 4.2 Batch Anomaly Investigation: B in [1, 2, 4, 8, 16, 32] on mlp-3072 and conv-96",
    }

    print("Submitting POST /api/benchmarks...")
    resp = client.post("/api/benchmarks", json=payload)
    assert resp.status_code == 200, f"Submission failed: {resp.text}"
    session_id = resp.json()["session_id"]
    print(f"Created Session ID {session_id}. Waiting for worker to complete 24 runs...")

    while True:
        time.sleep(2.0)
        s_resp = client.get(f"/api/benchmarks/{session_id}")
        s_data = s_resp.json()
        status = s_data.get("status")
        progress = client.get("/api/benchmarks/progress").json()
        item = progress.get("item") or {}
        print(f"  Status: {status:<8} | Current: {item.get('device_key','')} - {item.get('model_name','')} (B={item.get('batch','')})")
        if status in ("done", "failed", "cancelled"):
            break

    # Fetch results
    with Session(engine) as session:
        runs = session.exec(
            select(Run).where(Run.session_id == session_id).order_by(Run.ai_model_id, Run.device_id, Run.batch)
        ).all()

        print("\n" + "=" * 95)
        print("BATCH SWEEP RESULTS TABLE (Session ID %d):" % session_id)
        print("=" * 95)
        print(f"{'Model':<16} {'Chip':<6} {'Batch':<6} {'Median(ms)':<12} {'Per Sample(ms)':<16} {'Throughput(/s)':<16} {'Spread':<8} {'CI rel':<8}")
        print("-" * 95)
        for r in runs:
            m = session.exec(select(AIModel).where(AIModel.id == r.ai_model_id)).first()
            d = session.exec(select(Device).where(Device.id == r.device_id)).first()
            ms_per_sample = r.median_ms / r.batch
            print(f"{m.name:<16} {d.key:<6} {r.batch:<6} {r.median_ms:<12.3f} {ms_per_sample:<16.4f} {r.throughput_per_s:<16.1f} {r.spread:<8.4f} {r.ci_rel or 0:<8.4f}")

if __name__ == "__main__":
    main()
