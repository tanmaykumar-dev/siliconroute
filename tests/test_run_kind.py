"""Tests for run_kind classification, nullable unstable, and sustained-quality filters."""

import json
import numpy as np
import pytest
from sqlmodel import Session, select

from app.benchmark import compute_run_stats
from app.db import AIModel, Device, Fit, Run, WorkloadMeasurement, create_db_engine, init_db
from app.predictor import prepare_fit_dataset
from app.router import calculate_device_volatility_bands, resolve_candidate_prediction


def test_compute_run_stats_unstable_nullable():
    """Verify that runs with fewer than 10 samples return unstable=None ('not assessable')."""
    # 1 sample: should be None
    stats_1 = compute_run_stats(np.array([12.5]), batch=1)
    assert stats_1["unstable"] is None
    assert stats_1["median_ms"] == 12.5

    # 9 samples: should be None
    stats_9 = compute_run_stats(np.array([10.0 + i * 0.1 for i in range(9)]), batch=1)
    assert stats_9["unstable"] is None

    # 10 samples: should be assessable (bool)
    stats_10 = compute_run_stats(np.array([10.0 + i * 0.01 for i in range(10)]), batch=1)
    assert isinstance(stats_10["unstable"], bool)
    assert stats_10["unstable"] is False

    # 10 highly varying samples: should be unstable=True
    stats_unstable = compute_run_stats(np.array([1.0, 10.0, 1.0, 10.0, 1.0, 10.0, 1.0, 10.0, 1.0, 10.0]), batch=1)
    assert stats_unstable["unstable"] is True


def test_prepare_fit_dataset_excludes_single_cold_and_energy(tmp_path):
    """Verify that predictor fits strictly exclude single_cold and energy runs."""
    test_db = tmp_path / "test_fit_filter.db"
    eng = create_db_engine(test_db)
    init_db(eng)

    with Session(eng) as session:
        dev = Device(
            key="test_gpu",
            label="Test GPU",
            kind="dgpu",
            provider="DmlExecutionProvider",
            detected_at="2026-09-29T00:00:00Z",
            is_available=True,
        )
        model = AIModel(
            name="test_mlp",
            family="mlp",
            source="synthetic",
            path="models/test_mlp.onnx",
            sha256="abc",
            params=1000,
            flops_per_sample=2000,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[1, 10]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(dev)
        session.add(model)
        session.commit()
        session.refresh(dev)
        session.refresh(model)

        # Add 12 sustained runs (qualifies for MIN_FIT_SAMPLES)
        for i in range(12):
            session.add(Run(
                ai_model_id=model.id,
                device_id=dev.id,
                provider_used=dev.provider,
                batch=1,
                intra_op_threads=1,
                warmup_runs=2,
                timed_runs=10,
                session_create_ms=1.0,
                median_ms=1.0 + i * 0.1,
                p10_ms=0.9,
                p90_ms=1.1,
                mean_ms=1.0,
                min_ms=0.9,
                max_ms=1.1,
                stdev_ms=0.05,
                cv=0.05,
                unstable=False,
                run_kind="sustained",
                throughput_per_s=1000.0,
                raw_ms_json="[1.0]*10",
                created_at="2026-09-29T00:00:00Z",
            ))

        # Add a single_cold run (should be excluded)
        session.add(Run(
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used=dev.provider,
            batch=1,
            intra_op_threads=1,
            warmup_runs=0,
            timed_runs=1,
            session_create_ms=1.0,
            median_ms=99.9,
            p10_ms=99.9,
            p90_ms=99.9,
            mean_ms=99.9,
            min_ms=99.9,
            max_ms=99.9,
            stdev_ms=0.0,
            cv=0.0,
            unstable=None,
            run_kind="single_cold",
            throughput_per_s=10.0,
            raw_ms_json="[99.9]",
            created_at="2026-09-29T00:00:00Z",
        ))

        # Add an energy run (should be excluded)
        session.add(Run(
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used=dev.provider,
            batch=1,
            intra_op_threads=1,
            warmup_runs=0,
            timed_runs=100,
            session_create_ms=1.0,
            median_ms=1.5,
            p10_ms=0.0,
            p90_ms=0.0,
            mean_ms=0.0,
            min_ms=0.0,
            max_ms=0.0,
            stdev_ms=0.0,
            cv=0.0,
            unstable=None,
            run_kind="energy",
            energy_method="nvml",
            energy_mj_per_inf=5.0,
            throughput_per_s=500.0,
            raw_ms_json="[]",
            created_at="2026-09-29T00:00:00Z",
        ))
        session.commit()

        runs, matrices, y = prepare_fit_dataset(session, dev.id, target="latency")
        assert len(runs) == 12
        assert all(r.run_kind in ("sustained", "verify_sustained") for r in runs)
        assert all(r.timed_runs >= 10 for r in runs)
        assert all(r.warmup_runs >= 2 for r in runs)


def test_resolve_candidate_prediction_sustained_lookup(tmp_path):
    """Verify that steady-state candidate lookup in router uses sustained-only runs."""
    test_db = tmp_path / "test_router_lookup.db"
    eng = create_db_engine(test_db)
    init_db(eng)

    with Session(eng) as session:
        dev = Device(
            key="cpu",
            label="Host CPU",
            kind="cpu",
            provider="CPUExecutionProvider",
            detected_at="2026-09-29T00:00:00Z",
            is_available=True,
        )
        model = AIModel(
            name="test_conv",
            family="conv",
            source="synthetic",
            path="models/test_conv.onnx",
            sha256="def",
            params=5000,
            flops_per_sample=10000,
            weight_bytes=20000,
            size_mb=0.02,
            precision="fp32",
            input_shape_json="[1, 16, 16, 16]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(dev)
        session.add(model)
        session.commit()
        session.refresh(dev)
        session.refresh(model)

        from app.db import BenchSession
        bs1 = BenchSession(kind="latency", status="done", config_json="{}", created_at="2026-09-29T00:00:00Z")
        bs2 = BenchSession(kind="verify", status="done", config_json="{}", created_at="2026-09-29T01:00:00Z")
        session.add(bs1)
        session.add(bs2)
        session.commit()
        session.refresh(bs1)
        session.refresh(bs2)

        # Add earlier sustained run (session bs1)
        session.add(Run(
            session_id=bs1.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used=dev.provider,
            batch=8,
            intra_op_threads=4,
            warmup_runs=2,
            timed_runs=10,
            session_create_ms=1.0,
            median_ms=22.389,
            p10_ms=21.0,
            p90_ms=23.0,
            mean_ms=22.0,
            min_ms=20.0,
            max_ms=24.0,
            stdev_ms=1.0,
            cv=0.04,
            unstable=False,
            run_kind="sustained",
            throughput_per_s=400.0,
            raw_ms_json="[22.389]*10",
            created_at="2026-09-29T00:00:00Z",
        ))

        # Add later single_cold run (session bs2) with 20.564 ms
        session.add(Run(
            session_id=bs2.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used=dev.provider,
            batch=8,
            intra_op_threads=4,
            warmup_runs=0,
            timed_runs=1,
            session_create_ms=1.0,
            median_ms=20.564,
            p10_ms=20.564,
            p90_ms=20.564,
            mean_ms=20.564,
            min_ms=20.564,
            max_ms=20.564,
            stdev_ms=0.0,
            cv=0.0,
            unstable=None,
            run_kind="single_cold",
            throughput_per_s=40.0,
            raw_ms_json="[20.564]",
            created_at="2026-09-29T01:00:00Z",
        ))
        session.commit()

        # The candidate prediction should pick the sustained run (22.389 ms), NOT 20.564 ms!
        cand = resolve_candidate_prediction(session, dev, model, batch=8, workload="sustained")
        assert cand["source"] == "measured"
        assert cand["base_latency_ms"] == pytest.approx(22.389, abs=1e-3)
        assert cand["measured_session_id"] == bs1.id


def test_workload_measurement_schema():
    """Verify that WorkloadMeasurement persists decision_id and pstate_before."""
    wm = WorkloadMeasurement(
        ai_model_id=1,
        device_id=2,
        batch=1,
        workload="cold_start",
        latency_ms=15.42,
        session_create_ms=12.1,
        first_run_ms=3.32,
        idle_s=5.0,
        nvml_pstate=8,
        pstate_before=8,
        decision_id=100,
        created_at="2026-09-29T00:00:00Z",
    )
    assert wm.decision_id == 100
    assert wm.pstate_before == 8
    assert wm.workload == "cold_start"
