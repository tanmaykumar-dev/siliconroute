"""Hardening tests: no NVIDIA, no battery, and empty database resilience."""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select
from app.main import app
import app.db as app_db
from app.db import get_session, init_db, Device, AIModel, Fit, Run
from app.power import NVMLReader
from app.router import route_model


def test_nvml_reader_handles_no_nvidia():
    """Verify NVMLReader behaves gracefully when NVIDIA hardware / driver is absent."""
    reader = NVMLReader()
    with patch("pynvml.nvmlInit", side_effect=RuntimeError("NVML Shared Library Not Found")):
        reader._init_nvml()
        metrics = reader.read_metrics()
        assert metrics["gpu_power_w"] is None
        assert metrics["gpu_temp_c"] is None
        assert reader.is_available is False


def test_router_handles_no_battery():
    """Verify router functions cleanly on AC desktops / VMs where psutil reports no battery."""
    with Session(app_db.engine) as session:
        dev = session.exec(select(Device).where(Device.key == "cpu")).first()
        model = session.exec(select(AIModel)).first()
        if not dev or not model:
            pytest.skip("No devices/models in test database")

        # Ensure dev has a valid fit so route_model can score
        fit = session.exec(select(Fit).where(Fit.device_id == dev.id)).first()
        if not fit:
            fit = Fit(
                device_id=dev.id,
                target="latency",
                model_form="f1_roofline",
                loo_mape_all_json="{}",
                coef_json="[0.1, 0.05, 0.02]",
                r2_log=0.99,
                loo_mape_pct=5.0,
                overhead_ms=0.1,
                compute_gflops=50.0,
                bandwidth_gb_s=30.0,
                n_samples=10,
                is_active=True,
                trained_at="2026-09-28T00:00:00Z",
            )
            session.add(fit)
            session.commit()

        with patch("psutil.sensors_battery", return_value=None):
            dec = route_model(
                session=session,
                model_id=model.id,
                batch=1,
                mode="fastest",
                workload="sustained",
                allow_explore=False,
            )
            assert dec["chosen_device_id"] is not None
            assert "battery" not in dec["reason"].lower() or "plugged in" in dec["reason"].lower() or "battery none" not in dec["reason"].lower()


def test_empty_database_resilience(tmp_path):
    """Verify all critical API endpoints and router behave gracefully on an empty database."""
    test_db = tmp_path / "empty_siliconroute.db"
    test_engine = create_engine(f"sqlite:///{test_db.as_posix()}", connect_args={"check_same_thread": False})
    init_db(test_engine)

    def override_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    # 1. Verify GET endpoints return clean responses without 500
    r_sys = client.get("/api/system")
    assert r_sys.status_code == 200

    r_dev = client.get("/api/devices")
    assert r_dev.status_code == 200
    assert isinstance(r_dev.json(), list)

    r_mod = client.get("/api/models")
    assert r_mod.status_code == 200
    assert r_mod.json() == []

    r_run = client.get("/api/runs")
    assert r_run.status_code == 200
    assert r_run.json() == []

    r_fit = client.get("/api/fits")
    assert r_fit.status_code == 200
    assert r_fit.json() == []

    r_dec = client.get("/api/decisions")
    assert r_dec.status_code == 200
    assert r_dec.json() == []

    r_var = client.get("/api/analysis/variability")
    assert r_var.status_code == 200

    r_chart = client.get("/api/analysis/chart-data?family=mlp&batch=1")
    assert r_chart.status_code == 200

    r_co = client.get("/api/analysis/crossovers-all")
    assert r_co.status_code == 200

    r_stat = client.get("/api/decisions/stats")
    assert r_stat.status_code == 200
    assert r_stat.json().get("total_verified") == 0

    # 2. Verify router status and route endpoints return clean error message on empty DB
    r_router = client.get("/api/router")
    assert r_router.status_code == 200
    assert "no benchmark data; run benchmark first" in r_router.json()["detail"]

    # Route request fails cleanly with 400 and clear detail
    r_route = client.post("/api/route", json={"ai_model_id": 1, "batch": 1})
    assert r_route.status_code == 400
    assert "no benchmark data; run benchmark first" in r_route.json()["detail"]

    app.dependency_overrides.clear()
