"""Unit tests for Phase 4 predictor, LOO error, model selection, and crossover."""

import json
import uuid
from fastapi.testclient import TestClient
import numpy as np
from sqlmodel import Session, select

from app.db import AIModel, Device, Fit, Run, engine, init_db
from app.main import app
from app.predictor import (
    calculate_crossover,
    fit_device,
    fit_f1,
    fit_f3,
    loo_mape,
    predict_f1,
    predict_f3,
)

client = TestClient(app)


def test_recover_known_params_f1():
    """Verify that weighted NNLS on F1 recovers known physical parameters exactly."""
    # Ground truth parameters: t0 = 0.50 ms, a = 0.02 ms/GFLOP (50,000 GFLOP/s), b = 0.10 ms/GB (10,000 GB/s)
    t0_true = 0.50
    a_true = 0.02
    b_true = 0.10

    rng = np.random.default_rng(1234)
    n = 20
    work_gflop = rng.uniform(0.1, 10.0, size=n)
    data_gb = rng.uniform(0.01, 1.0, size=n)
    X = np.column_stack([np.ones(n), work_gflop, data_gb])

    y = t0_true + a_true * work_gflop + b_true * data_gb
    coef = fit_f1(X, y)

    assert np.isclose(coef[0], t0_true, atol=1e-3)
    assert np.isclose(coef[1], a_true, atol=1e-3)
    assert np.isclose(coef[2], b_true, atol=1e-3)


def test_loo_mape_calculation():
    """Verify leave-one-out MAPE computation."""
    n = 10
    X = np.column_stack([np.ones(n), np.linspace(1, 10, n)])
    # Perfectly linear relation y = 2.0 + 3.0 * x
    y = 2.0 + 3.0 * X[:, 1]
    mape = loo_mape(X, y, fit_f1, predict_f1)
    # Perfect fit should have near-zero LOO error
    assert mape < 0.05


def test_min_samples_constraint_409():
    """Verify that attempting to fit a device with < 6 samples returns 409 Conflict."""
    init_db()
    u = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        # Create a fresh test device with only 2 runs
        test_dev = Device(
            key=f"test_dev_few_{u}",
            label=f"Test Few {u}",
            kind="unknown",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(test_dev)
        session.commit()
        session.refresh(test_dev)
        dev_id = test_dev.id

    res = client.post("/api/fit", json={"device_id": dev_id, "target": "latency"})
    assert res.status_code == 409
    assert "at least 6" in res.json()["detail"]

    with Session(engine) as session:
        d = session.get(Device, dev_id)
        if d:
            d.is_available = False
            session.add(d)
            session.commit()


def test_fit_and_crossover_pipeline():
    """Verify end-to-end fit selection, physical parameters, and crossover calculation."""
    init_db()
    u = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        # Create 2 test devices: DevFast (low t0, high compute) and DevSlow (high t0, lower compute)
        dev_fast = Device(
            key=f"test_dev_fast_{u}",
            label=f"Test Fast {u}",
            kind="dgpu",
            provider="DmlExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        dev_slow = Device(
            key=f"test_dev_slow_{u}",
            label=f"Test Slow {u}",
            kind="cpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(dev_fast)
        session.add(dev_slow)
        session.commit()
        session.refresh(dev_fast)
        session.refresh(dev_slow)

        # Create 8 synthetic models across small and large sizes
        models = []
        for w in [32, 64, 128, 256, 512, 1024, 1536, 2048]:
            p = 4 * w * w
            m = AIModel(
                name=f"test_mlp_{w}_{u}",
                family="mlp",
                source="synthetic",
                path=f"models/test_mlp_{w}_{u}.onnx",
                sha256="testsha",
                params=p,
                flops_per_sample=float(8 * w * w),
                weight_bytes=p * 4,
                size_mb=(p * 4) / (1024 * 1024),
                precision="fp32",
                input_shape_json=f"[[1, {w}]]",
                created_at="2026-09-28T00:00:00Z",
            )
            session.add(m)
            models.append(m)
        session.commit()
        for m in models:
            session.refresh(m)

        # Generate >= 8 steady-state runs for each device
        # DevFast: t0 = 0.50 ms, high compute speed
        # DevSlow: t0 = 0.02 ms, low compute speed (wins at small sizes, loses at large sizes)
        for m in models:
            for b in [1, 8]:
                work_gflop = (m.flops_per_sample * b) / 1e9
                data_gb = m.weight_bytes / 1e9

                t_fast = 0.05 + 0.01 * work_gflop + 0.05 * data_gb
                t_slow = 0.02 + 5.00 * work_gflop + 2.00 * data_gb

                rf = Run(
                    ai_model_id=m.id,
                    device_id=dev_fast.id,
                    provider_used="DmlExecutionProvider",
                    batch=b,
                    intra_op_threads=4,
                    warmup_runs=5,
                    timed_runs=30,
                    session_create_ms=1.0,
                    first_run_ms=t_fast * 3,
                    median_ms=round(t_fast, 4),
                    p10_ms=round(t_fast * 0.95, 4),
                    p90_ms=round(t_fast * 1.05, 4),
                    mean_ms=round(t_fast, 4),
                    min_ms=round(t_fast * 0.9, 4),
                    max_ms=round(t_fast * 1.1, 4),
                    stdev_ms=0.001,
                    cv=0.01,
                    spread=0.05,
                    ci_rel=0.01,
                    unstable=False,
                    throughput_per_s=1000.0,
                    raw_ms_json="[]",
                    created_at="2026-09-28T00:00:00Z",
                )
                rs = Run(
                    ai_model_id=m.id,
                    device_id=dev_slow.id,
                    provider_used="CPUExecutionProvider",
                    batch=b,
                    intra_op_threads=4,
                    warmup_runs=5,
                    timed_runs=30,
                    session_create_ms=1.0,
                    first_run_ms=t_slow * 1.5,
                    median_ms=round(t_slow, 4),
                    p10_ms=round(t_slow * 0.95, 4),
                    p90_ms=round(t_slow * 1.05, 4),
                    mean_ms=round(t_slow, 4),
                    min_ms=round(t_slow * 0.9, 4),
                    max_ms=round(t_slow * 1.1, 4),
                    stdev_ms=0.001,
                    cv=0.01,
                    spread=0.05,
                    ci_rel=0.01,
                    unstable=False,
                    throughput_per_s=1000.0,
                    raw_ms_json="[]",
                    created_at="2026-09-28T00:00:00Z",
                )
                session.add(rf)
                session.add(rs)
        session.commit()

        # Fit both devices
        fit_f = fit_device(session, dev_fast.id)
        fit_s = fit_device(session, dev_slow.id)

        assert fit_f.id is not None
        assert fit_s.id is not None
        assert fit_f.is_active is True
        assert fit_s.is_active is True
        assert fit_f.t0_ms is not None
        assert fit_s.t0_ms is not None

        # Calculate crossover at batch=1
        xo = calculate_crossover(session, dev_slow.id, dev_fast.id, family="mlp", batch=1)
        assert xo["crossover"] is not None
        # DevSlow should start faster at width 32, then DevFast becomes faster at larger widths
        assert xo["grid"][0]["faster_device"] == dev_slow.key
        assert xo["crossover"]["switched_to"] == dev_fast.key

        dev_fast.is_available = False
        dev_slow.is_available = False
        session.add(dev_fast)
        session.add(dev_slow)
        session.commit()
