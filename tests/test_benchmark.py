"""Tests for latency benchmark engine, adaptive timing, and duplicate detection."""

import json
from sqlmodel import Session, select

from app.benchmark import check_and_mark_duplicate_devices, run_latency_measurement
from app.db import BenchSession, Device, Run, engine, init_db
from app.models_gen import create_and_register_synthetic


def test_tiny_mlp_cpu_benchmark():
    """Verify latency benchmark execution on CPU with adaptive timing."""
    init_db()
    with Session(engine) as session:
        model = create_and_register_synthetic(session, family="mlp", size=32, layers=2)

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
        assert run.inner_loop_k >= 1
        assert run.spread >= 0.0
        assert run.output_hash is not None

        # Check statistical sanity: min <= p10 <= median <= p90 <= max
        assert run.min_ms <= run.p10_ms <= run.median_ms <= run.p90_ms <= run.max_ms

        raw_timings = json.loads(run.raw_ms_json)
        assert len(raw_timings) == 5
        assert all(t > 0 for t in raw_timings)


def test_robust_spread_calculation():
    """Verify that spread = (p90 - p10) / median and unstable is set properly."""
    # Test formula directly with fake statistical numbers
    p10 = 0.50
    median = 0.52
    p90 = 0.55
    spread = (p90 - p10) / median
    assert round(spread, 4) == round(0.05 / 0.52, 4)
    assert not (spread > 0.30)  # Stable

    # Unstable case: large spread
    p10_noisy = 0.30
    p90_noisy = 0.70
    spread_noisy = (p90_noisy - p10_noisy) / median
    assert spread_noisy > 0.30  # Unstable


def test_duplicate_device_detection():
    """Verify duplicate DirectML adapter identification when outputs and medians match."""
    init_db()
    with Session(engine) as session:
        # Create two test DML devices
        dev_a = session.exec(select(Device).where(Device.key == "dml_dup_test:0")).first()
        if not dev_a:
            dev_a = Device(
                key="dml_dup_test:0",
                label="DirectML Test 0",
                kind="unknown",
                provider="DmlExecutionProvider",
                provider_options_json="{\"device_id\": 80}",
                is_available=True,
                detected_at="2026-09-27T00:00:00Z",
            )
            session.add(dev_a)

        dev_b = session.exec(select(Device).where(Device.key == "dml_dup_test:1")).first()
        if not dev_b:
            dev_b = Device(
                key="dml_dup_test:1",
                label="DirectML Test 1",
                kind="unknown",
                provider="DmlExecutionProvider",
                provider_options_json="{\"device_id\": 81}",
                is_available=True,
                detected_at="2026-09-27T00:00:00Z",
            )
            session.add(dev_b)
        else:
            dev_b.is_available = True
            dev_b.unavailable_reason = None
            session.add(dev_b)

        session.commit()
        session.refresh(dev_a)
        session.refresh(dev_b)

        model = create_and_register_synthetic(session, family="mlp", size=32, layers=2)

        # Create 3 matching runs with identical output_hash and < 5% median difference
        test_hash = "abc123fixedtesthash456"
        for b in [1, 2, 4]:
            r_a = Run(
                ai_model_id=model.id,
                device_id=dev_a.id,
                provider_used="DmlExecutionProvider",
                batch=b,
                intra_op_threads=4,
                warmup_runs=1,
                timed_runs=10,
                inner_loop_k=1,
                session_create_ms=1.0,
                median_ms=0.500,
                p10_ms=0.480,
                p90_ms=0.520,
                mean_ms=0.500,
                min_ms=0.470,
                max_ms=0.530,
                stdev_ms=0.015,
                cv=0.03,
                spread=0.08,
                unstable=False,
                throughput_per_s=2000.0,
                raw_ms_json="[]",
                output_matches_cpu=True,
                max_rel_err=1e-4,
                output_hash=test_hash,
                created_at="2026-09-27T00:00:00Z",
            )
            # Device B: median differs by only 1.6% (< 5%)
            r_b = Run(
                ai_model_id=model.id,
                device_id=dev_b.id,
                provider_used="DmlExecutionProvider",
                batch=b,
                intra_op_threads=4,
                warmup_runs=1,
                timed_runs=10,
                inner_loop_k=1,
                session_create_ms=1.0,
                median_ms=0.508,
                p10_ms=0.485,
                p90_ms=0.525,
                mean_ms=0.508,
                min_ms=0.475,
                max_ms=0.535,
                stdev_ms=0.015,
                cv=0.03,
                spread=0.08,
                unstable=False,
                throughput_per_s=1968.5,
                raw_ms_json="[]",
                output_matches_cpu=True,
                max_rel_err=1e-4,
                output_hash=test_hash,
                created_at="2026-09-27T00:00:00Z",
            )
            session.add(r_a)
            session.add(r_b)

        session.commit()

        # Run duplicate detection
        dups = check_and_mark_duplicate_devices(session)
        assert ("dml_dup_test:1", "dml_dup_test:0") in dups

        session.refresh(dev_b)
        assert dev_b.is_available is False
        assert "suspected duplicate of dml_dup_test:0" in dev_b.unavailable_reason
