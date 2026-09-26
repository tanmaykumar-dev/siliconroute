"""Tests for latency benchmark engine."""

import json
from sqlmodel import Session, select

from app.benchmark import run_latency_measurement
from app.db import BenchSession, Device, engine, init_db
from app.models_gen import create_and_register_synthetic


def test_tiny_mlp_cpu_benchmark():
    """Verify latency benchmark execution on CPU for a tiny model."""
    init_db()
    with Session(engine) as session:
        # Create a tiny MLP model
        model = create_and_register_synthetic(session, family="mlp", size=32, layers=2)

        # Ensure CPU device exists
        cpu_dev = session.exec(select(Device).where(Device.key == "cpu")).first()
        if not cpu_dev:
            cpu_dev = Device(
                key="cpu",
                label="CPU",
                kind="cpu",
                provider="CPUExecutionProvider",
                provider_options_json="{}",
                is_available=True,
                detected_at="2026-09-27T00:00:00Z",
            )
            session.add(cpu_dev)
            session.commit()
            session.refresh(cpu_dev)

        # Create bench session
        bench_sess = BenchSession(
            kind="latency",
            status="running",
            config_json="{}",
            created_at="2026-09-27T00:00:00Z",
        )
        session.add(bench_sess)
        session.commit()
        session.refresh(bench_sess)

        # Run latency measurement with warmup=2, timed=5
        run = run_latency_measurement(
            session=session,
            bench_session_id=bench_sess.id,
            model=model,
            device=cpu_dev,
            batch=1,
            warmup_runs=2,
            timed_runs=5,
        )

        assert run.id is not None
        assert run.provider_used == "CPUExecutionProvider"
        assert not run.provider_mismatch
        assert run.timed_runs == 5
        assert run.output_matches_cpu is True

        # Check statistical sanity: min <= p10 <= median <= p90 <= max
        assert run.min_ms <= run.p10_ms <= run.median_ms <= run.p90_ms <= run.max_ms

        raw_timings = json.loads(run.raw_ms_json)
        assert len(raw_timings) == 5
        assert all(t > 0 for t in raw_timings)
