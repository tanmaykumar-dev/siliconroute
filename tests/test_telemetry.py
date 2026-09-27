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


def test_nvml_retry_logic():
    """Verify NVMLReader retries initialization after retry_interval_s instead of permanent failure."""
    from unittest.mock import patch

    # 1. Simulate initial failure
    with patch("pynvml.nvmlInit", side_effect=RuntimeError("Simulated NVML initialization failure")):
        reader = NVMLReader(retry_interval_s=0.1)
        assert reader.is_available is False
        assert "Simulated NVML" in (reader.last_error or "")
        metrics = reader.read_metrics()
        assert metrics["gpu_power_w"] is None
        assert "Simulated NVML" in metrics.get("gpu_error", "")

    # 2. Before retry interval expires, should not re-attempt
    with patch("pynvml.nvmlInit") as mock_init:
        # Directly call ensure without waiting
        reader._ensure_initialized()
        mock_init.assert_not_called()

    # 3. After retry interval expires, should re-attempt initialization
    import time
    time.sleep(0.15)
    with patch("pynvml.nvmlInit") as mock_init, \
         patch("pynvml.nvmlDeviceGetCount", return_value=1), \
         patch("pynvml.nvmlDeviceGetHandleByIndex", return_value="dummy_handle"), \
         patch("pynvml.nvmlDeviceGetName", return_value="Mocked NVIDIA GPU"):
        reader._ensure_initialized()
        mock_init.assert_called_once()
        assert reader.is_available is True
        assert reader.device_name == "Mocked NVIDIA GPU"


def test_telemetry_sse_stream_single_json_encoding():
    """Verify that SSE stream yields plain JSON dicts rather than double-encoded JSON strings."""
    import asyncio
    from app.telemetry import telemetry_stream, subscribers
    from unittest.mock import AsyncMock

    mock_req = AsyncMock()
    mock_req.is_disconnected.side_effect = [False, True]

    async def _run():
        gen = telemetry_stream(mock_req)
        task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.01)
        assert len(subscribers) > 0
        q = list(subscribers)[0]
        test_sample = {"ts": "2026-09-28T00:00:00Z", "cpu_pct": 5.0}
        q.put_nowait(test_sample)
        event = await task
        assert event.event == "message"
        assert event.data == test_sample
        assert isinstance(event.data, dict)
        await gen.aclose()

    asyncio.run(_run())

