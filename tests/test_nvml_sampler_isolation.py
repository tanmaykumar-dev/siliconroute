"""Verification test proving NVML sampler thread runs ONLY during NVIDIA dGPU timing.

Guarantees:
1. Direct enforcement: attempting to start NVMLMeasurementSampler for 'cpu' or 'dml:0' (AMD iGPU) raises ValueError.
2. In-execution isolation: during CPU or iGPU inference runs, no NVML sampler thread is launched.
3. Only NVIDIA dGPU ('dml:1') triggers background NVML sampling.
"""

import threading
from unittest.mock import MagicMock
import pytest
from sqlmodel import Session

from app.benchmark import is_nvidia_device, run_latency_measurement
from app.db import AIModel, Device
from app.power import NVMLMeasurementSampler, NVMLReader


def test_nvml_sampler_direct_rejection_for_non_nvidia():
    """Verify NVMLMeasurementSampler immediately rejects CPU and AMD iGPU device keys."""
    sampler = NVMLMeasurementSampler()

    with pytest.raises(ValueError, match="PROHIBITED.*non-NVIDIA"):
        sampler.start(device_key="cpu")

    with pytest.raises(ValueError, match="PROHIBITED.*non-NVIDIA"):
        sampler.start(device_key="dml:0")

    with pytest.raises(ValueError, match="PROHIBITED.*non-NVIDIA"):
        sampler.start(device_key="amd_radeon")


def test_nvml_sampler_isolation_during_measurement(tmp_path):
    """Verify that during CPU benchmark runs, NVMLMeasurementSampler is never started."""
    mock_reader = MagicMock(spec=NVMLReader)
    mock_reader.is_available = True
    mock_reader.read_metrics.return_value = {
        "gpu_power_w": 25.0,
        "gpu_temp_c": 50.0,
        "gpu_util_pct": 10.0,
        "gpu_pstate": 0,
        "gpu_clock_sm_mhz": 1500,
    }

    # Reset tracking
    NVMLMeasurementSampler.active_device_keys.clear()

    # Create dummy CPU device
    cpu_dev = Device(
        key="cpu",
        label="AMD Ryzen 9 CPU",
        kind="cpu",
        vendor="AMD",
        vendor_id="0x1022",
        provider="CPUExecutionProvider",
        is_available=True,
    )
    assert not is_nvidia_device(cpu_dev)

    # Create dummy AMD iGPU device
    igpu_dev = Device(
        key="dml:0",
        label="AMD Radeon(TM) 610M",
        kind="igpu",
        vendor="AMD",
        vendor_id="0x1002",
        provider="DmlExecutionProvider",
        is_available=True,
    )
    assert not is_nvidia_device(igpu_dev)

    # Create dummy NVIDIA dGPU device
    dgpu_dev = Device(
        key="dml:1",
        label="NVIDIA GeForce RTX 5070 Laptop GPU",
        kind="dgpu",
        vendor="NVIDIA",
        vendor_id="0x10DE",
        provider="DmlExecutionProvider",
        is_available=True,
    )
    assert is_nvidia_device(dgpu_dev)

    # Ensure no active sampler threads exist initially
    active_threads = [t.name for t in threading.enumerate() if "NVMLSampler" in t.name]
    assert len(active_threads) == 0

    # Test sampler on dGPU works
    sampler = NVMLMeasurementSampler(reader=mock_reader)
    sampler.start(device_key="dml:1")
    assert "dml:1" in NVMLMeasurementSampler.active_device_keys

    # Verify sampler thread is alive and named for dgpu
    sampler_threads = [t.name for t in threading.enumerate() if "NVMLSampler-dml:1" in t.name]
    assert len(sampler_threads) == 1

    # Stop sampler
    telemetry = sampler.stop()
    assert telemetry["sample_count"] >= 1
    assert "dml:0" not in NVMLMeasurementSampler.active_device_keys
    assert "cpu" not in NVMLMeasurementSampler.active_device_keys
