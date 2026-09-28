"""Device management API endpoints for SiliconRoute."""

from datetime import datetime, timezone
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import BenchSession, Device, engine, get_session
from app.devices import sync_devices_to_db

router = APIRouter(prefix="/api/devices", tags=["devices"])


class DeviceUpdate(BaseModel):
    """Payload for updating user-assigned device metadata."""
    label: Optional[str] = None
    kind: Optional[str] = None


@router.post("/detect", response_model=list[Device])
def detect_and_sync_devices(session: Session = Depends(get_session)) -> list[Device]:
    """Scan hardware for CPU and DirectML adapters, sync to DB, and return devices."""
    return sync_devices_to_db(session)


@router.get("", response_model=list[Device])
def list_devices(session: Session = Depends(get_session)) -> list[Device]:
    """List all registered devices in the database."""
    devices = session.exec(select(Device).order_by(Device.id)).all()
    # If no devices are saved yet, perform an initial detection
    if not devices:
        return sync_devices_to_db(session)
    return list(devices)


@router.patch("/{device_id}", response_model=Device)
def update_device(
    device_id: int,
    patch: DeviceUpdate,
    session: Session = Depends(get_session),
) -> Device:
    """Update friendly label or kind for a device (e.g. after identify test)."""
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with id {device_id} not found",
        )

    if patch.label is not None:
        device.label = patch.label.strip()
    if patch.kind is not None:
        valid_kinds = {"cpu", "igpu", "dgpu", "npu", "software", "unknown"}
        if patch.kind not in valid_kinds:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"kind must be one of {valid_kinds}",
            )
        device.kind = patch.kind

    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def _run_identify_job(device_id: int, bench_session_id: int, progress: dict) -> None:
    """Run an 8 s continuous load loop on the target device for visual Task Manager identification."""
    import time
    import numpy as np
    from app.config import IDENTIFY_S
    from app.devices import make_session
    from app.models_gen import generate_mlp

    with Session(engine) as session:
        bench_sess = session.get(BenchSession, bench_session_id)
        device = session.get(Device, device_id)
        if not bench_sess or not device:
            return

        bench_sess.status = "running"
        bench_sess.started_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_sess)
        session.commit()

        progress["total"] = IDENTIFY_S
        progress["item"] = f"Blinking {device.label} ({device.key}) for {IDENTIFY_S}s"

        try:
            path, _, _, _, _ = generate_mlp(width=1024, layers=4)
            x_in = np.ones((8, 1024), dtype=np.float32)
            dev_opts = json.loads(device.provider_options_json or "{}")
            sess = make_session(str(path), device.provider, device_id=dev_opts.get("device_id"), device=device)

            t_start = time.time()
            t_end = t_start + IDENTIFY_S
            while time.time() < t_end and not progress.get("cancel"):
                sess.run(None, {"X": x_in})
                progress["done"] = int(time.time() - t_start)

            bench_sess.status = "cancelled" if progress.get("cancel") else "done"
        except Exception as exc:
            bench_sess.status = "failed"
            bench_sess.error = str(exc)

        bench_sess.finished_at = datetime.now(timezone.utc).isoformat()
        session.add(bench_sess)
        session.commit()


@router.post("/{device_id}/identify")
def identify_device(
    device_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Run an 8 s load test on device for the user to identify it in Task Manager."""
    from app.jobs import try_submit

    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with id {device_id} not found",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    bench_session = BenchSession(
        kind="verify",
        status="queued",
        config_json=json.dumps({"identify_device_id": device_id}),
        created_at=now_iso,
        notes=f"Identify test on {device.label} ({device.key})",
    )
    session.add(bench_session)
    session.commit()
    session.refresh(bench_session)

    submitted = try_submit(
        bench_session.id,
        lambda prog: _run_identify_job(device_id, bench_session.id, prog),
    )
    if not submitted:
        bench_session.status = "failed"
        bench_session.error = "A benchmark job is already running"
        session.add(bench_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A benchmark job is already running",
        )

    return {"session_id": bench_session.id, "status": "queued"}
