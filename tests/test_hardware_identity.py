"""Unit tests for Phase 5.3 Hardware Identity, DXGI Enumeration, NVML Fingerprint, and Suspect Filtering."""

from unittest.mock import MagicMock
import numpy as np
import pytest
from sqlmodel import Session, select

from app.db import AIModel, BenchSession, Device, Fit, Run, engine, init_db
from app.devices import (
    get_dxgi_adapters,
    resolve_adapter_for_device,
    verify_gpu_identity_mapping,
)
from app.predictor import prepare_fit_dataset
from app.router import resolve_candidate_prediction


# -----------------------------------------------------------------------------
# 1. DXGI Adapter Enumeration & Fallback Tests
# -----------------------------------------------------------------------------

def test_dxgi_adapter_enumeration():
    """Verify that get_dxgi_adapters correctly parses adapter descriptors on Windows."""
    adapters = get_dxgi_adapters()
    assert isinstance(adapters, list)
    if adapters:
        first = adapters[0]
        assert "index" in first
        assert "description" in first
        assert "vendor_id" in first
        assert "vendor_name" in first
        assert "luid" in first
        assert "is_software" in first
        # Vendor ID should be a valid hex string e.g. 0x10DE, 0x1002, 0x8086, 0x1414
        assert first["vendor_id"].startswith("0x")


def test_dxgi_adapter_enumeration_non_windows_fallback(monkeypatch):
    """Verify graceful empty list return when DXGI is unavailable (e.g. non-Windows or driver missing)."""
    import ctypes
    monkeypatch.setattr(ctypes, "oledll", None, raising=False)
    adapters = get_dxgi_adapters()
    assert adapters == []


# -----------------------------------------------------------------------------
# 2. NVML Fingerprint & Swap Detection Tests
# -----------------------------------------------------------------------------

def test_nvml_fingerprint_mapping_confirmed(monkeypatch):
    """Verify that when candidate NVIDIA adapter produces NVML activity, mapping is confirmed."""
    fake_adapters = [
        {"index": 0, "description": "NVIDIA GeForce RTX 5070 Laptop GPU", "vendor_id": "0x10DE", "vendor_name": "NVIDIA", "device_id": 1, "luid": "0:100", "is_software": False},
        {"index": 1, "description": "AMD Radeon 610M", "vendor_id": "0x1002", "vendor_name": "AMD", "device_id": 2, "luid": "0:200", "is_software": False},
    ]
    monkeypatch.setattr("app.devices.get_dxgi_adapters", lambda: fake_adapters)

    active_adapter = [0]
    def fake_session(*args, **kwargs):
        provs = kwargs.get("providers", [])
        if provs and len(provs) > 0:
            opts = provs[0][1] if isinstance(provs[0], tuple) and len(provs[0]) > 1 else {}
            active_adapter[0] = opts.get("device_id", 0)
        mock_input = MagicMock()
        mock_input.name = "input"
        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [mock_input]
        mock_session.run.return_value = [np.zeros((1, 10), dtype=np.float32)]
        return mock_session

    monkeypatch.setattr("app.devices.ort.InferenceSession", fake_session)

    def fake_read_metrics():
        # Adapter 0 is the real NVIDIA adapter -> produces high util
        if active_adapter[0] == 0:
            return {"gpu_power_w": 65.0, "gpu_util_pct": 85, "gpu_clock_sm_mhz": 1800, "gpu_pstate": 0}
        return {"gpu_power_w": 15.0, "gpu_util_pct": 0, "gpu_clock_sm_mhz": 400, "gpu_pstate": 4}

    mock_nvml = MagicMock()
    mock_nvml.is_available = True
    mock_nvml.read_metrics = fake_read_metrics
    monkeypatch.setattr("app.devices.nvml_reader", mock_nvml)

    mapping = verify_gpu_identity_mapping(probe_model_path="dummy.onnx")
    assert mapping["NVIDIA"]["index"] == 0  # Adapter 0 confirmed for NVIDIA
    assert mapping["AMD"]["index"] == 1     # Adapter 1 confirmed for AMD


def test_nvml_fingerprint_swap_detected(monkeypatch):
    """Verify that if candidate adapter produces NO NVML rise, swap detection corrects the mapping."""
    fake_adapters = [
        {"index": 0, "description": "NVIDIA GeForce RTX 5070 Laptop GPU", "vendor_id": "0x10DE", "vendor_name": "NVIDIA", "device_id": 1, "luid": "0:100", "is_software": False},
        {"index": 1, "description": "AMD Radeon 610M", "vendor_id": "0x1002", "vendor_name": "AMD", "device_id": 2, "luid": "0:200", "is_software": False},
    ]
    monkeypatch.setattr("app.devices.get_dxgi_adapters", lambda: fake_adapters)

    active_adapter = [0]
    def fake_session(*args, **kwargs):
        provs = kwargs.get("providers", [])
        if provs and len(provs) > 0:
            opts = provs[0][1] if isinstance(provs[0], tuple) and len(provs[0]) > 1 else {}
            active_adapter[0] = opts.get("device_id", 0)
        mock_input = MagicMock()
        mock_input.name = "input"
        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [mock_input]
        mock_session.run.return_value = [np.zeros((1, 10), dtype=np.float32)]
        return mock_session

    monkeypatch.setattr("app.devices.ort.InferenceSession", fake_session)

    def fake_read_metrics():
        # Adapter 0 produces NO rise (it's actually AMD!)
        # Adapter 1 produces high rise (it's actually NVIDIA!)
        if active_adapter[0] == 1:
            return {"gpu_power_w": 70.0, "gpu_util_pct": 95, "gpu_clock_sm_mhz": 1850, "gpu_pstate": 0}
        return {"gpu_power_w": 15.0, "gpu_util_pct": 0, "gpu_clock_sm_mhz": 400, "gpu_pstate": 4}

    mock_nvml = MagicMock()
    mock_nvml.is_available = True
    mock_nvml.read_metrics = fake_read_metrics
    monkeypatch.setattr("app.devices.nvml_reader", mock_nvml)

    mapping = verify_gpu_identity_mapping(probe_model_path="dummy.onnx")
    assert mapping["NVIDIA"]["index"] == 1  # Successfully swapped: adapter 1 is NVIDIA
    assert mapping["AMD"]["index"] == 0     # Successfully swapped: adapter 0 is AMD


# -----------------------------------------------------------------------------
# 3. Identity Suspect Exclusion Tests (Predictor & Router)
# -----------------------------------------------------------------------------

def test_prepare_fit_dataset_excludes_suspect_runs():
    """Verify that prepare_fit_dataset strictly excludes runs flagged identity_suspect == True."""
    init_db()
    with Session(engine) as session:
        dev = session.exec(select(Device).where(Device.key == "dml:0")).first()
        assert dev is not None

        bs = BenchSession(kind="latency", status="done", config_json="{}", created_at="2026-09-29T00:00:00Z")
        session.add(bs)
        session.commit()
        session.refresh(bs)

        model = AIModel(
            name="test-mlp-model-fit",
            family="mlp",
            source="synthetic",
            path="dummy.onnx",
            sha256="dummy",
            params=1000,
            flops_per_sample=2000.0,
            weight_bytes=4000,
            size_mb=0.004,
            precision="fp32",
            input_shape_json="[1, 10]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        clean_ids = []
        # Add 6 clean runs (satisfying MIN_FIT_SAMPLES = 6)
        for i in range(6):
            r = Run(
                session_id=bs.id,
                ai_model_id=model.id,
                device_id=dev.id,
                provider_used="DmlExecutionProvider",
                batch=1 + i,
                intra_op_threads=4,
                warmup_runs=2,
                timed_runs=10,
                session_create_ms=10.0,
                first_run_ms=1.5,
                median_ms=1.0 + i * 0.2,
                p10_ms=0.9 + i * 0.2,
                p90_ms=1.1 + i * 0.2,
                mean_ms=1.0 + i * 0.2,
                min_ms=0.8 + i * 0.2,
                max_ms=1.2 + i * 0.2,
                stdev_ms=0.1,
                cv=0.08,
                unstable=False,
                throughput_per_s=833.0,
                raw_ms_json="[]",
                identity_suspect=False,
                created_at="2026-09-29T00:00:00Z",
            )
            session.add(r)
            session.commit()
            session.refresh(r)
            clean_ids.append(r.id)

        # Add 2 suspect runs (flawed / inverted)
        suspect_ids = []
        for i in range(2):
            s = Run(
                session_id=bs.id,
                ai_model_id=model.id,
                device_id=dev.id,
                provider_used="DmlExecutionProvider",
                batch=10 + i,
                intra_op_threads=4,
                warmup_runs=2,
                timed_runs=10,
                session_create_ms=10.0,
                first_run_ms=55.0,
                median_ms=50.0,
                p10_ms=48.0,
                p90_ms=52.0,
                mean_ms=50.0,
                min_ms=45.0,
                max_ms=55.0,
                stdev_ms=2.0,
                cv=0.04,
                unstable=False,
                throughput_per_s=20.0,
                raw_ms_json="[]",
                identity_suspect=True,  # Flawed / swapped run
                created_at="2026-09-29T00:00:00Z",
            )
            session.add(s)
            session.commit()
            session.refresh(s)
            suspect_ids.append(s.id)

        runs, matrices, y = prepare_fit_dataset(session, dev.id, target="latency")
        included_ids = [r.id for r in runs]
        for cid in clean_ids:
            assert cid in included_ids
        for sid in suspect_ids:
            assert sid not in included_ids


def test_router_candidate_lookup_excludes_suspect_runs():
    """Verify that router resolve_candidate_prediction ignores suspect runs when looking up measured latency."""
    init_db()
    with Session(engine) as session:
        dev = session.exec(select(Device).where(Device.key == "dml:1")).first()
        assert dev is not None

        bs1 = BenchSession(kind="latency", status="done", config_json="{}", created_at="2026-09-29T01:00:00Z")
        bs2 = BenchSession(kind="latency", status="done", config_json="{}", created_at="2026-09-29T02:00:00Z")
        session.add(bs1)
        session.add(bs2)
        session.commit()

        model = AIModel(
            name="test-cand-model-clean",
            family="conv",
            source="synthetic",
            path="dummy.onnx",
            sha256="dummy",
            params=5000,
            flops_per_sample=10000.0,
            weight_bytes=20000,
            size_mb=0.02,
            precision="fp32",
            input_shape_json="[1, 10]",
            created_at="2026-09-29T00:00:00Z",
        )
        session.add(model)
        session.commit()
        session.refresh(model)

        # Suspect run recorded with wrong slow latency (25.0 ms)
        suspect_run = Run(
            session_id=bs1.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used="DmlExecutionProvider",
            batch=1,
            intra_op_threads=4,
            warmup_runs=2,
            timed_runs=10,
            session_create_ms=10.0,
            first_run_ms=30.0,
            median_ms=25.0,
            p10_ms=24.0,
            p90_ms=26.0,
            mean_ms=25.0,
            min_ms=23.0,
            max_ms=27.0,
            stdev_ms=1.0,
            cv=0.04,
            unstable=False,
            throughput_per_s=40.0,
            raw_ms_json="[]",
            identity_suspect=True,
            created_at="2026-09-29T01:00:00Z",
        )
        # Clean run with true RTX latency (0.8 ms)
        clean_run = Run(
            session_id=bs2.id,
            ai_model_id=model.id,
            device_id=dev.id,
            provider_used="DmlExecutionProvider",
            batch=1,
            intra_op_threads=4,
            warmup_runs=2,
            timed_runs=10,
            session_create_ms=10.0,
            first_run_ms=1.2,
            median_ms=0.8,
            p10_ms=0.75,
            p90_ms=0.85,
            mean_ms=0.8,
            min_ms=0.7,
            max_ms=0.9,
            stdev_ms=0.05,
            cv=0.06,
            unstable=False,
            throughput_per_s=1250.0,
            raw_ms_json="[]",
            identity_suspect=False,
            created_at="2026-09-29T02:00:00Z",
        )
        session.add(suspect_run)
        session.add(clean_run)
        session.commit()

        cand = resolve_candidate_prediction(session, dev, model, batch=1, workload="sustained")
        assert cand["source"] == "measured"
        assert np.isclose(cand["base_latency_ms"], 0.8)  # Picked clean run, ignored 25.0 ms suspect run!


# -----------------------------------------------------------------------------
# 4. Suspect Rule Logic: Winograd vs Swap Evidence
# -----------------------------------------------------------------------------

def test_suspect_rule_winograd_vs_swap():
    """Verify that Winograd convolution speed is a physics note, while a dml:0 run faster than dml:1 is a swap suspect."""
    # Scenario A: Winograd convolution on Radeon (dml:0)
    # conv-96c-4l B=1: total flops = 2,717,908,992.
    # Latency: 3.55 ms -> implied GFLOP/s = 765.6 GFLOP/s (>600 GFLOP/s peak).
    # But RTX latency on this model is 0.70 ms, so Radeon is 5x slower than RTX.
    med_ms_a = 3.55
    gflops_a = 2717908992.0 / (med_ms_a * 1e6)
    t_rtx_a = 0.70
    t_rad_a = 3.60

    is_swap_a = (med_ms_a < t_rtx_a * 1.2) and (med_ms_a < t_rad_a * 0.5)
    has_physics_note_a = (gflops_a > 600.0)

    assert not is_swap_a  # NOT a swap! Ran at true Radeon speed
    assert has_physics_note_a  # Gets physics note for Winograd/FFT convolution

    # Scenario B: Inverted swap run on dml:0
    # A run labeled dml:0 ran in 0.684 ms (faster than RTX 0.70 ms and 5x faster than Radeon 3.60 ms)
    med_ms_b = 0.684
    is_swap_b = (med_ms_b < t_rtx_a * 1.2) and (med_ms_b < t_rad_a * 0.5)

    assert is_swap_b  # True identity swap!
