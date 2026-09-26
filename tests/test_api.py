"""Phase 1 API endpoint tests using FastAPI TestClient."""

from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify GET /api/health contract."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


def test_system_endpoint():
    """Verify GET /api/system returns valid host hardware data."""
    response = client.get("/api/system")
    assert response.status_code == 200
    data = response.json()

    assert "cpu_name" in data and len(data["cpu_name"]) > 0
    assert data["physical_cores"] is not None and data["physical_cores"] > 0
    assert data["logical_cores"] is not None and data["logical_cores"] >= data["physical_cores"]
    assert data["ram_gb"] > 0
    assert "os" in data
    assert "ort_version" in data
    assert isinstance(data["providers"], list)
    assert "CPUExecutionProvider" in data["providers"]
    assert "nvml" in data


def test_devices_detect_and_list():
    """Verify POST /api/devices/detect and GET /api/devices return detected hardware."""
    # Detect devices
    detect_res = client.post("/api/devices/detect")
    assert detect_res.status_code == 200
    devices = detect_res.json()
    assert isinstance(devices, list)
    assert len(devices) >= 1

    # Verify CPU is always present
    keys = [d["key"] for d in devices]
    assert "cpu" in keys

    # Verify GET /api/devices returns the same devices
    list_res = client.get("/api/devices")
    assert list_res.status_code == 200
    list_devices = list_res.json()
    assert len(list_devices) == len(devices)


def test_device_patch_label():
    """Verify PATCH /api/devices/{id} updates label and kind."""
    # Get all devices
    devices = client.get("/api/devices").json()
    assert len(devices) > 0
    target = devices[0]
    dev_id = target["id"]
    orig_label = target["label"]
    new_label = "Test Custom Label"
    try:
        patch_res = client.patch(f"/api/devices/{dev_id}", json={"label": new_label})
        assert patch_res.status_code == 200
        updated = patch_res.json()
        assert updated["label"] == new_label

        # Verify persistence via GET /api/devices
        persisted = client.get("/api/devices").json()
        matched = next(d for d in persisted if d["id"] == dev_id)
        assert matched["label"] == new_label

        # Verify 404 on non-existent device
        not_found = client.patch("/api/devices/99999", json={"label": "Ghost"})
        assert not_found.status_code == 404
    finally:
        client.patch(f"/api/devices/{dev_id}", json={"label": orig_label})


def test_frontend_static_root():
    """Verify GET / serves the placeholder frontend index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert "SiliconRoute" in response.text
    assert "text/html" in response.headers.get("content-type", "")
