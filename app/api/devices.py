"""Device management API endpoints for SiliconRoute."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import Device, get_session
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
