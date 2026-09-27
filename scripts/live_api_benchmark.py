"""Run live benchmark of mlp-3072w-4l batch 1 on cpu and dml:1 through the FastAPI API."""

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
    print("LIVE API BENCHMARK: mlp-3072w-4l (B=1) on cpu and dml:1 (warmup=5, runs=30)")
    print("=" * 80)

    # Ensure worker is running
    start_worker()

    with Session(engine) as session:
        m = session.exec(select(AIModel).where(AIModel.name == "mlp-3072w-4l")).first()
        assert m is not None, "mlp-3072w-4l not found in database!"
        cpu = session.exec(select(Device).where(Device.key == "cpu")).first()
        dml1 = session.exec(select(Device).where(Device.key == "dml:1")).first()
        assert cpu is not None and dml1 is not None, "cpu or dml:1 not found!"

        model_id = m.id
        cpu_id = cpu.id
        dml1_id = dml1.id

    client = TestClient(app)

    payload = {
        "kind": "latency",
        "model_ids": [model_id],
        "device_ids": [cpu_id, dml1_id],
        "batches": [1],
        "warmup": 5,
        "runs": 30,
        "notes": "Live API re-run: mlp-3072w-4l batch 1 on cpu and dml:1 (warmup 5, runs 30)",
    }

    print("Submitting POST /api/benchmarks...")
    resp = client.post("/api/benchmarks", json=payload)
    print(f"Response status: {resp.status_code}")
    print(f"Response body: {resp.json()}")
    assert resp.status_code == 200, f"Submission failed: {resp.text}"

    session_id = resp.json()["session_id"]
    print(f"Tracking session {session_id} until completion...")

    for _ in range(60):
        time.sleep(1.0)
        s_resp = client.get(f"/api/benchmarks/{session_id}")
        s_data = s_resp.json()
        status = s_data.get("status")
        print(f"  Session {session_id} status: {status}")
        if status in ("done", "failed", "cancelled"):
            break

    # Fetch stored runs from database
    with Session(engine) as session:
        runs = session.exec(
            select(Run).where(Run.session_id == session_id).order_by(Run.id)
        ).all()
        print(f"\nFound {len(runs)} stored run(s) for session {session_id}:")
        for r in runs:
            r_dict = r.model_dump()
            print("\n" + "-" * 40)
            print(f"Run ID: {r.id} | Device ID: {r.device_id} | Batch: {r.batch}")
            print(json.dumps(r_dict, indent=2))

if __name__ == "__main__":
    main()
