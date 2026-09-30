"""Unit tests for SiliconRoute Phase 5 Router, Decision Engine, Verification, and Baselines."""

import json
import uuid
from typing import Optional
from fastapi.testclient import TestClient
import numpy as np
from sqlmodel import Session, select

from app.db import AIModel, BenchSession, Decision, Device, Fit, Run, engine, init_db
from app.main import app
from app.router import (
    calculate_device_volatility_bands,
    compute_decision_statistics,
    get_workload_slowdown_ratio,
    is_nvidia_device,
    resolve_candidate_prediction,
    route_model,
)

client = TestClient(app)


def make_test_run(
    session_id: int,
    ai_model_id: int,
    device_id: int,
    median_ms: float,
    run_kind: str = "sustained",
    energy_mj_per_inf: Optional[float] = None,
    timed_runs: int = 10,
    warmup_runs: int = 2,
    batch: int = 1,
) -> Run:
    return Run(
        session_id=session_id,
        ai_model_id=ai_model_id,
        device_id=device_id,
        provider_used="CPUExecutionProvider",
        provider_mismatch=False,
        batch=batch,
        intra_op_threads=1,
        warmup_runs=warmup_runs,
        timed_runs=timed_runs,
        inner_loop_k=1,
        session_create_ms=2.0,
        first_run_ms=median_ms,
        median_ms=median_ms,
        p10_ms=median_ms * 0.95,
        p90_ms=median_ms * 1.05,
        mean_ms=median_ms,
        min_ms=median_ms * 0.9,
        max_ms=median_ms * 1.1,
        stdev_ms=median_ms * 0.05,
        cv=0.05,
        spread=0.1,
        ci_rel=0.05,
        unstable=False,
        run_kind=run_kind,
        throughput_per_s=1000.0 / max(median_ms, 1e-4),
        raw_ms_json="[]",
        energy_mj_per_inf=energy_mj_per_inf,
        created_at="2026-09-30T00:00:00Z",
    )


def test_router_measured_vs_fit_source():
    """Verify that router picks 'measured' when an exact run exists, and 'fit' otherwise."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        # Create test session
        bs = BenchSession(
            kind="latency",
            status="done",
            config_json="{}",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(bs)
        session.commit()
        session.refresh(bs)

        # Create test device
        dev = Device(
            key=f"test_dev_{u}",
            label=f"Test Dev {u}",
            kind="dgpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(dev)
        session.commit()
        session.refresh(dev)

        # Create model
        model = AIModel(
            name=f"test_m_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_m.onnx",
            sha256="testsha",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        # 1. No runs exist yet, but create a fit
        fit = Fit(
            device_id=dev.id,
            target="latency",
            model_form="f1_roofline",
            loo_mape_all_json="{}",
            coef_json="[0.5, 0.01, 0.05]",
            n_samples=10,
            r2_log=0.95,
            loo_mape_pct=5.0,
            t0_ms=0.5,
            compute_gflops=100.0,
            bandwidth_gb_s=20.0,
            trained_at="2026-09-28T00:00:00Z",
            is_active=True,
        )
        session.add(fit)
        session.commit()

        # Check candidate resolution without run -> should be "fit"
        cand_fit = resolve_candidate_prediction(session, dev, model, batch=1)
        assert cand_fit["source"] == "fit"
        assert cand_fit["is_volatile"] is False

        # 2. Now add an exact measured run with session_id=bs.id
        r = Run(
            session_id=bs.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used="CPUExecutionProvider",
            provider_mismatch=False,
            batch=1,
            intra_op_threads=1,
            warmup_runs=2,
            timed_runs=10,
            run_kind="sustained",
            session_create_ms=1.0,
            median_ms=0.345,
            p10_ms=0.340,
            p90_ms=0.350,
            mean_ms=0.345,
            min_ms=0.330,
            max_ms=0.360,
            stdev_ms=0.005,
            cv=0.01,
            spread=0.03,
            ci_rel=0.01,
            unstable=False,
            throughput_per_s=2898.0,
            raw_ms_json="[]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(r)
        session.commit()

        cand_meas = resolve_candidate_prediction(session, dev, model, batch=1)
        assert cand_meas["source"] == "measured"
        assert cand_meas["base_latency_ms"] == 0.345

        # Clean up
        dev.is_available = False
        session.add(dev)
        session.commit()


def test_router_volatility_flag_on_session_disagreement():
    """Verify that multiple sessions disagreeing by >20% triggers is_volatile=True."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        # Create test sessions
        bs1 = BenchSession(
            kind="latency",
            status="done",
            config_json="{}",
            created_at="2026-09-28T00:00:00Z",
        )
        bs2 = BenchSession(
            kind="latency",
            status="done",
            config_json="{}",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(bs1)
        session.add(bs2)
        session.commit()
        session.refresh(bs1)
        session.refresh(bs2)

        dev = Device(
            key=f"test_dev_vol_{u}",
            label=f"Test Dev Vol {u}",
            kind="dgpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(dev)
        session.commit()
        session.refresh(dev)

        model = AIModel(
            name=f"test_m_vol_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_m.onnx",
            sha256="testsha",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        # Run from Session bs1: median = 1.0 ms
        r1 = Run(
            session_id=bs1.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used="CPUExecutionProvider",
            provider_mismatch=False,
            batch=1,
            intra_op_threads=1,
            warmup_runs=2,
            timed_runs=10,
            run_kind="sustained",
            session_create_ms=1.0,
            median_ms=1.000,
            p10_ms=0.98,
            p90_ms=1.02,
            mean_ms=1.00,
            min_ms=0.95,
            max_ms=1.05,
            stdev_ms=0.02,
            cv=0.02,
            spread=0.04,
            ci_rel=0.01,
            unstable=False,
            throughput_per_s=1000.0,
            raw_ms_json="[]",
            created_at="2026-09-28T00:00:00Z",
        )
        # Run from Session bs2: median = 1.60 ms (+60% jump!)
        r2 = Run(
            session_id=bs2.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used="CPUExecutionProvider",
            provider_mismatch=False,
            batch=1,
            intra_op_threads=1,
            warmup_runs=2,
            timed_runs=10,
            run_kind="sustained",
            session_create_ms=1.0,
            median_ms=1.600,
            p10_ms=1.58,
            p90_ms=1.62,
            mean_ms=1.60,
            min_ms=1.55,
            max_ms=1.65,
            stdev_ms=0.02,
            cv=0.02,
            spread=0.04,
            ci_rel=0.01,
            unstable=False,
            throughput_per_s=625.0,
            raw_ms_json="[]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(r1)
        session.add(r2)
        session.commit()

        cand = resolve_candidate_prediction(session, dev, model, batch=1)
        assert cand["source"] == "measured"
        assert cand["base_latency_ms"] == 1.600  # Uses latest session
        assert cand["is_volatile"] is True
        assert cand["volatility_pct"] == 60.0

        dev.is_available = False
        session.add(dev)
        session.commit()


def test_swapped_device_keys_and_ids():
    """Verify that device kind and DXGI vendor_id (0x10DE = NVIDIA) drive routing, not hardcoded keys."""
    # dml:0 is NVIDIA dGPU, dml:1 is AMD iGPU (swapped from this laptop's configuration)
    dev_nvidia_dml0 = Device(id=101, key="dml:0", label="NVIDIA RTX 5070", kind="dgpu", vendor_id="0x10DE", vendor="NVIDIA")
    dev_amd_dml1 = Device(id=102, key="dml:1", label="AMD Radeon Graphics", kind="igpu", vendor_id="0x1002", vendor="AMD")
    dev_cpu = Device(id=103, key="cpu", label="AMD Ryzen 9", kind="cpu", vendor_id="0x1022", vendor="AMD")

    assert is_nvidia_device(dev_nvidia_dml0) is True
    assert is_nvidia_device(dev_amd_dml1) is False
    assert is_nvidia_device(dev_cpu) is False

    # Check candidate dict format
    cand_nvidia = {"device_id": 101, "device_key": "dml:0", "device_label": "NVIDIA RTX 5070", "device_vendor_id": "0x10DE", "device_vendor": "NVIDIA"}
    cand_amd = {"device_id": 102, "device_key": "dml:1", "device_label": "AMD Radeon Graphics", "device_vendor_id": "0x1002", "device_vendor": "AMD"}
    assert is_nvidia_device(cand_nvidia) is True
    assert is_nvidia_device(cand_amd) is False


def test_no_invented_numbers_when_unmeasured():
    """Verify that unmeasured slowdown ratios and volatility bands return None, never invented defaults."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        dev = Device(
            key=f"test_empty_{u}",
            label=f"Empty Dev {u}",
            kind="dgpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-30T00:00:00Z",
        )
        session.add(dev)
        session.commit()
        session.refresh(dev)

        model = AIModel(
            name=f"test_empty_m_{u}",
            family="conv",
            source="synthetic",
            path="models/test_empty.onnx",
            sha256="testsha_empty",
            params=500,
            flops_per_sample=1000.0,
            weight_bytes=2000,
            size_mb=0.002,
            precision="fp32",
            input_shape_json="[[1, 3, 32, 32]]",
            created_at="2026-09-30T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        # 1. Slowdown ratio without measurements MUST be None (no 1.1x, 3.0x, 15.0x)
        ratio_cold = get_workload_slowdown_ratio(session, dev.id, model.family, "cold_start")
        assert ratio_cold is None

        ratio_idle = get_workload_slowdown_ratio(session, dev.id, model.family, "idle_loaded")
        assert ratio_idle is None

        # 2. Volatility bands without multi-session runs MUST be None (no 15.0% default)
        vol_bands = calculate_device_volatility_bands(session)
        assert vol_bands.get(dev.id) is None

        # Add a single warm run to allow resolve_candidate_prediction
        bs = BenchSession(kind="latency", status="done", config_json="{}", created_at="2026-09-30T00:00:00Z")
        session.add(bs)
        session.commit()
        session.refresh(bs)

        r = make_test_run(
            session_id=bs.id,
            ai_model_id=model.id,
            device_id=dev.id,
            median_ms=5.0,
            run_kind="sustained",
        )
        session.add(r)
        session.commit()

        cand = resolve_candidate_prediction(session, dev, model, batch=1, workload="cold_start")
        assert cand["source"] == "warm_unmeasured_cold_start"
        assert "no cold_start measurements for this chip" in cand["wake_status"]
        assert cand["effective_latency_ms"] == 5.0  # Uses warm latency directly without invented multiplier

        dev.is_available = False
        session.add(dev)
        session.commit()


def test_exploration_fires_at_expected_rate_without_seed():
    """Verify that calling route_model without seed uses process RNG and explores ~10% of the time."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        # Create two devices with close predictions (< 20% margin)
        dev1 = Device(key=f"test_exp1_{u}", label=f"Exp Dev 1 {u}", kind="cpu", provider="CPUExecutionProvider", is_available=True, detected_at="2026-09-30T00:00:00Z")
        dev2 = Device(key=f"test_exp2_{u}", label=f"Exp Dev 2 {u}", kind="dgpu", provider="CPUExecutionProvider", is_available=True, detected_at="2026-09-30T00:00:00Z")
        session.add_all([dev1, dev2])
        session.commit()
        session.refresh(dev1)
        session.refresh(dev2)

        model = AIModel(
            name=f"test_exp_m_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_exp.onnx",
            sha256="testsha_exp",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-30T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        bs = BenchSession(kind="latency", status="done", config_json="{}", created_at="2026-09-30T00:00:00Z")
        session.add(bs)
        session.commit()
        session.refresh(bs)

        # dev1: 1.00 ms (winner), dev2: 1.05 ms (runner up within 5% <= 20% explore margin)
        r1 = make_test_run(session_id=bs.id, ai_model_id=model.id, device_id=dev1.id, median_ms=1.00)
        r2 = make_test_run(session_id=bs.id, ai_model_id=model.id, device_id=dev2.id, median_ms=1.05)
        session.add_all([r1, r2])
        session.commit()

        # Temporarily make all other devices unavailable
        other_devs = session.exec(select(Device).where(Device.id.notin_([dev1.id, dev2.id]), Device.is_available == True)).all()
        for od in other_devs:
            od.is_available = False
            session.add(od)
        session.commit()

        try:
            explored_count = 0
            trials = 1000
            for _ in range(trials):
                dec = route_model(session, model.id, batch=1, allow_explore=True, rng_seed=None)
                if dec["explored"]:
                    explored_count += 1

            # With EPSILON=0.10, out of 1000 trials, expect roughly 100 explored (between 50 and 150)
            assert 50 <= explored_count <= 150, f"Exploration rate out of expected range: {explored_count} / {trials}"
        finally:
            # Restore other devices
            for od in other_devs:
                od.is_available = True
                session.add(od)
            dev1.is_available = False
            dev2.is_available = False
            session.add_all([dev1, dev2])
            session.commit()


def test_energy_run_lookup_in_battery_mode():
    """Verify that resolve_candidate_prediction queries separate energy runs (run_kind='energy')."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        dev = Device(key=f"test_en_{u}", label=f"Energy Dev {u}", kind="dgpu", provider="CPUExecutionProvider", is_available=True, detected_at="2026-09-30T00:00:00Z")
        session.add(dev)
        session.commit()
        session.refresh(dev)

        model = AIModel(
            name=f"test_en_m_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_en.onnx",
            sha256="testsha_en",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-30T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        bs = BenchSession(kind="energy", status="done", config_json="{}", created_at="2026-09-30T00:00:00Z")
        session.add(bs)
        session.commit()
        session.refresh(bs)

        # 1. Latency run (energy_mj_per_inf is None)
        r_lat = make_test_run(session_id=bs.id, ai_model_id=model.id, device_id=dev.id, median_ms=2.0)
        # 2. Separate energy run (run_kind='energy', energy_mj_per_inf populated)
        r_en = make_test_run(session_id=bs.id, ai_model_id=model.id, device_id=dev.id, median_ms=2.0, run_kind="energy", energy_mj_per_inf=42.5)
        session.add_all([r_lat, r_en])
        session.commit()

        cand = resolve_candidate_prediction(session, dev, model, batch=1)
        assert cand["energy_mj"] == 42.5

        dev.is_available = False
        session.add(dev)
        session.commit()


def test_router_context_and_exclusion_rules():
    """Verify that mismatch exclusion and low-battery context rules function properly."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        # Create test session
        bs = BenchSession(
            kind="latency",
            status="done",
            config_json="{}",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(bs)
        session.commit()
        session.refresh(bs)

        dev_bad = Device(
            key=f"test_dev_bad_{u}",
            label=f"Test Dev Bad {u}",
            kind="igpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(dev_bad)
        session.commit()
        session.refresh(dev_bad)

        model = AIModel(
            name=f"test_m_bad_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_m.onnx",
            sha256="testsha",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        # Give cpu a fit so valid candidate exists
        cpu_dev = session.exec(select(Device).where(Device.key == "cpu")).first()
        assert cpu_dev is not None
        fit_cpu = Fit(
            device_id=cpu_dev.id,
            target="latency",
            model_form="f1_roofline",
            loo_mape_all_json="{}",
            coef_json="[0.1, 0.01, 0.05]",
            n_samples=10,
            r2_log=0.95,
            loo_mape_pct=5.0,
            t0_ms=0.1,
            compute_gflops=100.0,
            bandwidth_gb_s=20.0,
            trained_at="2026-09-28T00:00:00Z",
            is_active=True,
        )
        session.add(fit_cpu)

        # Record a run where output diverged from CPU reference
        r_mismatch = Run(
            session_id=bs.id,
            ai_model_id=model.id,
            device_id=dev_bad.id,
            provider_used="CPUExecutionProvider",
            provider_mismatch=False,
            output_matches_cpu=False,
            batch=1,
            intra_op_threads=1,
            warmup_runs=1,
            timed_runs=5,
            session_create_ms=1.0,
            median_ms=0.5,
            p10_ms=0.5,
            p90_ms=0.5,
            mean_ms=0.5,
            min_ms=0.5,
            max_ms=0.5,
            stdev_ms=0.0,
            cv=0.0,
            spread=0.0,
            unstable=False,
            throughput_per_s=2000.0,
            raw_ms_json="[]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(r_mismatch)
        session.commit()

        # Route request should exclude dev_bad
        decision = route_model(session, model.id, batch=1, mode="fastest")
        excluded_keys = [e["device_key"] for e in decision["excluded_candidates"]]
        assert dev_bad.key in excluded_keys
        assert any("diverged" in e["reason"] for e in decision["excluded_candidates"])

        dev_bad.is_available = False
        session.add(dev_bad)
        session.commit()


def test_api_route_and_stats():
    """Verify POST /api/route and GET /api/decisions/stats endpoints."""
    with Session(engine) as session:
        # Get an active model
        m = session.exec(select(AIModel)).first()
        assert m is not None
        model_id = m.id

        # Ensure all available devices have a fit so routing resolves all candidates
        devices = session.exec(select(Device).where(Device.is_available == True)).all()
        for dev in devices:
            fit = session.exec(select(Fit).where(Fit.device_id == dev.id)).first()
            if not fit:
                fit = Fit(
                    device_id=dev.id,
                    target="latency",
                    model_form="f1_roofline",
                    loo_mape_all_json="{}",
                    coef_json="[0.1, 0.01, 0.05]",
                    n_samples=10,
                    r2_log=0.95,
                    loo_mape_pct=5.0,
                    t0_ms=0.1,
                    compute_gflops=100.0,
                    bandwidth_gb_s=20.0,
                    trained_at="2026-09-28T00:00:00Z",
                    is_active=True,
                )
                session.add(fit)
        session.commit()

    res = client.post("/api/route", json={"ai_model_id": model_id, "batch": 1, "mode": "fastest", "verify": False})
    assert res.status_code == 200
    data = res.json()
    assert "chosen_device_key" in data
    assert "reason" in data
    assert len(data["candidates"]) >= 1
    # Default workload should be "sustained"
    assert data.get("workload") == "sustained"

    stats_res = client.get("/api/decisions/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert "total_verified" in stats
    # Validate new baseline format has wins/total counts
    if stats["total_verified"] > 0:
        for baseline in ["always_cpu", "always_rtx"]:
            b = stats["baselines"][baseline]
            assert "wins" in b
            assert "total" in b
        # ORT policy should be "not available"
        ort = stats["baselines"]["ort_policy"]
        assert ort["status"] == "not available"


def test_workload_sustained_skips_wake_penalty():
    """Verify that workload='sustained' sets wake_penalty_ms=0 for all devices."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        bs = BenchSession(
            kind="latency",
            status="done",
            config_json="{}",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(bs)
        session.commit()
        session.refresh(bs)

        dev = Device(
            key=f"test_wk_{u}",
            label=f"Test WK {u}",
            kind="dgpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-28T00:00:00Z",
        )
        session.add(dev)
        session.commit()
        session.refresh(dev)

        model = AIModel(
            name=f"test_wk_m_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_wk.onnx",
            sha256="testsha_wk",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=16 * 1024 * 1024,  # 16 MB to trigger wake penalty logic
            size_mb=16.0,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-28T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        fit = Fit(
            device_id=dev.id,
            target="latency",
            model_form="f1_roofline",
            loo_mape_all_json="{}",
            coef_json="[0.5, 0.01, 0.05]",
            n_samples=10,
            r2_log=0.95,
            loo_mape_pct=5.0,
            t0_ms=0.5,
            compute_gflops=100.0,
            bandwidth_gb_s=20.0,
            trained_at="2026-09-28T00:00:00Z",
            is_active=True,
        )
        session.add(fit)
        session.commit()

        # Sustained workload: wake penalty always 0
        cand_sus = resolve_candidate_prediction(session, dev, model, batch=1, workload="sustained")
        assert cand_sus["wake_penalty_ms"] == 0.0
        assert "sustained" in cand_sus["wake_status"]

        # Single workload on a non-dml:1 device: also 0 (only dml:1 has NVML wake detection)
        cand_single = resolve_candidate_prediction(session, dev, model, batch=1, workload="single")
        assert cand_single["wake_penalty_ms"] == 0.0

        # Clean up
        dev.is_available = False
        session.add(dev)
        session.commit()


def test_workload_parameter_in_api():
    """Verify that /api/route accepts workload parameter and echoes it back."""
    with Session(engine) as session:
        m = session.exec(select(AIModel)).first()
        assert m is not None
        model_id = m.id

        # Ensure all available devices have a fit so routing resolves all candidates
        devices = session.exec(select(Device).where(Device.is_available == True)).all()
        for dev in devices:
            fit = session.exec(select(Fit).where(Fit.device_id == dev.id)).first()
            if not fit:
                fit = Fit(
                    device_id=dev.id,
                    target="latency",
                    model_form="f1_roofline",
                    loo_mape_all_json="{}",
                    coef_json="[0.1, 0.01, 0.05]",
                    n_samples=10,
                    r2_log=0.95,
                    loo_mape_pct=5.0,
                    t0_ms=0.1,
                    compute_gflops=100.0,
                    bandwidth_gb_s=20.0,
                    trained_at="2026-09-28T00:00:00Z",
                    is_active=True,
                )
                session.add(fit)
        session.commit()

    # Test sustained
    res = client.post("/api/route", json={
        "ai_model_id": model_id, "batch": 1, "mode": "fastest",
        "workload": "sustained", "verify": False,
    })
    assert res.status_code == 200
    assert res.json()["workload"] == "sustained"

    # Test single
    res2 = client.post("/api/route", json={
        "ai_model_id": model_id, "batch": 1, "mode": "fastest",
        "workload": "single", "verify": False,
    })
    assert res2.status_code == 200
    assert res2.json()["workload"] == "single"

    # Test invalid workload
    res3 = client.post("/api/route", json={
        "ai_model_id": model_id, "batch": 1, "mode": "fastest",
        "workload": "bogus", "verify": False,
    })
    assert res3.status_code == 400

    # Test idle_loaded and cold_start via API
    res4 = client.post("/api/route", json={
        "ai_model_id": model_id, "batch": 1, "mode": "fastest",
        "workload": "idle_loaded", "verify": False,
    })
    assert res4.status_code == 200
    assert res4.json()["workload"] == "idle_loaded"

    res5 = client.post("/api/route", json={
        "ai_model_id": model_id, "batch": 1, "mode": "fastest",
        "workload": "cold_start", "verify": False,
    })
    assert res5.status_code == 200
    assert res5.json()["workload"] == "cold_start"


def test_idle_loaded_and_cold_start_routing():
    """Verify that route_model resolves idle_loaded and cold_start workloads with proper sources."""
    init_db()
    u = uuid.uuid4().hex[:8]

    with Session(engine) as session:
        bs = BenchSession(
            kind="latency",
            status="done",
            config_json="{}",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(bs)
        session.commit()
        session.refresh(bs)

        dev = Device(
            key=f"test_wl_{u}",
            label=f"Test WL {u}",
            kind="dgpu",
            provider="CPUExecutionProvider",
            provider_options_json="{}",
            is_available=True,
            detected_at="2026-09-29T00:00:00Z",
        )
        session.add(dev)
        session.commit()
        session.refresh(dev)

        model = AIModel(
            name=f"test_wl_m_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_wl.onnx",
            sha256="testsha_wl2",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        # Add warm run
        r = Run(
            session_id=bs.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used="CPUExecutionProvider",
            provider_mismatch=False,
            batch=1,
            intra_op_threads=1,
            warmup_runs=2,
            timed_runs=10,
            run_kind="sustained",
            session_create_ms=2.0,
            median_ms=1.0,
            p10_ms=0.9,
            p90_ms=1.1,
            mean_ms=1.0,
            min_ms=0.9,
            max_ms=1.1,
            stdev_ms=0.05,
            cv=0.05,
            spread=0.2,
            ci_rel=0.05,
            unstable=False,
            throughput_per_s=1000.0,
            raw_ms_json="[]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(r)
        session.commit()

        # 1. Test unmeasured fallback when no WorkloadMeasurement exists
        cand_idle_unmeasured = resolve_candidate_prediction(session, dev, model, batch=1, workload="idle_loaded")
        assert "warm_unmeasured_idle_loaded" in cand_idle_unmeasured["source"]
        assert "no idle_loaded measurements for this chip" in cand_idle_unmeasured["wake_status"]

        # Add WorkloadMeasurement for another model in the same family to create a ratio fallback
        from app.db import WorkloadMeasurement
        model_other = AIModel(
            name=f"test_wl_other_{u}",
            family="mlp",
            source="synthetic",
            path="models/test_wl_other.onnx",
            sha256="testsha_wl_other",
            params=2000,
            flops_per_sample=4000.0,
            weight_bytes=8000,
            size_mb=0.008,
            precision="fp32",
            input_shape_json="[[1, 32]]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(model_other)
        session.commit()
        session.refresh(model_other)

        r_other = make_test_run(
            session_id=bs.id,
            ai_model_id=model_other.id,
            device_id=dev.id,
            median_ms=1.0,
        )
        session.add(r_other)
        wm_other = WorkloadMeasurement(
            ai_model_id=model_other.id,
            device_id=dev.id,
            batch=1,
            workload="idle_loaded",
            latency_ms=1.5,
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(wm_other)
        session.commit()

        # Now ratio fallback exists for mlp family (1.5 / 1.0 = 1.5x)
        cand_idle_ratio = resolve_candidate_prediction(session, dev, model, batch=1, workload="idle_loaded")
        assert "ratio_idle_loaded" in cand_idle_ratio["source"]
        assert cand_idle_ratio["effective_latency_ms"] == 1.5

        # 2. Add exact WorkloadMeasurement and verify measured-first overrides ratio
        wm = WorkloadMeasurement(
            ai_model_id=model.id,
            device_id=dev.id,
            batch=1,
            workload="idle_loaded",
            latency_ms=2.345,
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(wm)
        session.commit()

        cand_idle_meas = resolve_candidate_prediction(session, dev, model, batch=1, workload="idle_loaded")
        assert cand_idle_meas["source"] == "measured_idle_loaded"
        assert cand_idle_meas["base_latency_ms"] == 2.345

        # Cleanup
        dev.is_available = False
        session.add(dev)
        session.commit()

