"""API endpoint tests using FastAPI TestClient."""

import time
from fastapi.testclient import TestClient
import pytest

from app.jobs import current_job, _lock, start_worker
from app.main import app

start_worker()
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
    detect_res = client.post("/api/devices/detect")
    assert detect_res.status_code == 200
    devices = detect_res.json()
    assert isinstance(devices, list)
    assert len(devices) >= 1

    keys = [d["key"] for d in devices]
    assert "cpu" in keys

    list_res = client.get("/api/devices")
    assert list_res.status_code == 200
    list_devices = list_res.json()
    assert len(list_devices) >= len(devices)
    list_keys = {d["key"] for d in list_devices}
    for k in keys:
        assert k in list_keys


def test_device_patch_label():
    """Verify PATCH /api/devices/{id} updates label and kind."""
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

        persisted = client.get("/api/devices").json()
        matched = next(d for d in persisted if d["id"] == dev_id)
        assert matched["label"] == new_label

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


def test_models_api():
    """Verify POST /api/models/synthetic and GET /api/models."""
    # Create a small synthetic MLP
    synth_res = client.post(
        "/api/models/synthetic",
        json={"family": "mlp", "sizes": [64], "layers": 2},
    )
    assert synth_res.status_code == 200
    models = synth_res.json()
    assert len(models) == 1
    assert models[0]["family"] == "mlp"
    assert models[0]["params"] == 2 * 64 * 64

    # List models
    list_res = client.get("/api/models?family=mlp")
    assert list_res.status_code == 200
    listed = list_res.json()
    assert any(m["name"] == models[0]["name"] for m in listed)

    # Scan models
    scan_res = client.post("/api/models/scan")
    assert scan_res.status_code == 200
    assert isinstance(scan_res.json(), list)


def test_benchmarks_api_and_conflict_409():
    """Verify benchmark creation, 409 conflict when busy, progress polling, and runs."""
    # Get model and CPU device
    models = client.get("/api/models").json()
    devices = client.get("/api/devices").json()
    assert len(models) > 0 and len(devices) > 0

    cpu_device = next(d for d in devices if d["key"] == "cpu")

    bench_payload = {
        "kind": "latency",
        "model_ids": [models[0]["id"]],
        "device_ids": [cpu_device["id"]],
        "batches": [1],
        "warmup": 1,
        "runs": 2,
        "notes": "Test API Run",
    }

    # Verify 409 when worker is busy
    with _lock:
        current_job["session_id"] = 88888
    try:
        busy_res = client.post("/api/benchmarks", json=bench_payload)
        assert busy_res.status_code == 409
        assert "already running" in busy_res.json()["detail"]
    finally:
        with _lock:
            current_job["session_id"] = None

    # Submit valid benchmark job
    res = client.post("/api/benchmarks", json=bench_payload)
    assert res.status_code == 200
    sess_id = res.json()["session_id"]

    # Poll status until done
    for _ in range(50):
        status_res = client.get(f"/api/benchmarks/{sess_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        if status_data["status"] in {"done", "failed"}:
            break
        time.sleep(0.1)

    assert status_data["status"] == "done"

    # Query runs
    runs_res = client.get(f"/api/runs?model_id={models[0]['id']}")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) >= 1
    assert runs[0]["provider_used"] == "CPUExecutionProvider"

    # Test CSV export
    csv_res = client.get("/api/export/runs.csv")
    assert csv_res.status_code == 200
    assert "median_ms" in csv_res.text
    assert "text/csv" in csv_res.headers.get("content-type", "")
