"""Tests for hardware telemetry sampler, power readers, and identify endpoint."""

from fastapi.testclient import TestClient

from app.db import Device, engine, init_db
from app.main import app
from app.power import BatteryReader, NVMLReader, nvml_reader
from app.telemetry import sample_telemetry
from sqlmodel import Session, select

client = TestClient(app)


def test_nvml_reader_interface():
    """Verify NVMLReader interface adheres strictly to rule: never throw, return None if unavailable."""
    reader = NVMLReader()
    assert hasattr(reader, "is_available")
    assert hasattr(reader, "device_name")
    metrics = reader.read_metrics()
    assert isinstance(metrics, dict)
    expected_keys = {
        "gpu_power_w",
        "gpu_temp_c",
        "gpu_util_pct",
        "gpu_mem_used_mb",
        "gpu_pstate",
        "gpu_clock_sm_mhz",
    }
    assert expected_keys.issubset(metrics.keys())
    energy_mj = reader.get_total_energy_mj()
    assert energy_mj is None or (isinstance(energy_mj, (int, float)) and energy_mj >= 0)


def test_battery_reader_interface():
    """Verify BatteryReader interface returns dict with discharge_w and power_online."""
    reader = BatteryReader()
    data = reader.read()
    assert isinstance(data, dict)
    assert "discharge_w" in data
    assert "power_online" in data
    if data["discharge_w"] is not None:
        assert isinstance(data["discharge_w"], float)
        assert data["discharge_w"] >= 0


def test_sample_telemetry():
    """Verify sample_telemetry returns complete dictionary with real metrics."""
    reader = BatteryReader()
    sample = sample_telemetry(reader)
    assert isinstance(sample, dict)
    assert "ts" in sample
    assert "cpu_pct" in sample
    assert isinstance(sample["cpu_pct"], float)
    assert "ram_pct" in sample
    assert isinstance(sample["ram_pct"], float)


def test_telemetry_latest_api():
    """Verify GET /api/telemetry/latest returns 200 and a valid snapshot."""
    res = client.get("/api/telemetry/latest")
    assert res.status_code == 200
    data = res.json()
    assert "cpu_pct" in data
    assert "ram_pct" in data
    assert "ts" in data


def test_telemetry_recent_api():
    """Verify GET /api/telemetry returns recent ring-buffer samples."""
    res = client.get("/api/telemetry?seconds=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_identify_device_api():
    """Verify POST /api/devices/{id}/identify initiates identify session."""
    init_db()
    with Session(engine) as session:
        cpu = session.exec(select(Device).where(Device.key == "cpu")).first()
        assert cpu is not None
        dev_id = cpu.id

    res = client.post(f"/api/devices/{dev_id}/identify")
    # Should either succeed (200) with queued status, or 409 if a job was already running
    assert res.status_code in (200, 409)
    if res.status_code == 200:
        data = res.json()
        assert "session_id" in data
        assert data["status"] == "queued"
