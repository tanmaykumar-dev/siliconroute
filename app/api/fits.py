"""Predictor model fitting API endpoints."""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import Device, Fit, get_session
from app.predictor import fit_device

router = APIRouter(prefix="/api/fit", tags=["fit"])


class FitRequest(BaseModel):
    """Payload to trigger a predictor fit."""
    device_id: Optional[int] = None
    target: str = "latency"  # latency | energy


@router.post("", response_model=list[Fit])
def trigger_fit(
    req: Optional[FitRequest] = None,
    session: Session = Depends(get_session),
) -> list[Fit]:
    """Fit predictor hardware models. Requires >= 6 valid samples per device."""
    target = req.target if req else "latency"
    results: list[Fit] = []

    if req and req.device_id is not None:
        devices = [session.get(Device, req.device_id)]
        devices = [d for d in devices if d is not None]
        if not devices:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {req.device_id} not found")
    else:
        devices = session.exec(select(Device).where(Device.is_available == True)).all()

    errors = []
    for d in devices:
        try:
            fit_rec = fit_device(session, d.id, target=target)
            results.append(fit_rec)
        except ValueError as exc:
            errors.append(f"{d.key}: {exc}")

    if not results and errors:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="; ".join(errors),
        )

    return results


@router.get("", response_model=list[Fit])
def list_active_fits(session: Session = Depends(get_session)) -> list[Fit]:
    """List all currently active predictor fits for available devices."""
    fits = session.exec(
        select(Fit)
        .join(Device, Fit.device_id == Device.id)
        .where(Fit.is_active == True, Device.is_available == True)
        .order_by(Fit.device_id)
    ).all()
    return list(fits)


@router.get("/{device_id}", response_model=Fit)
def get_device_fit(
    device_id: int,
    target: str = Query(default="latency"),
    session: Session = Depends(get_session),
) -> Fit:
    """Get active predictor fit for a specific device."""
    fit = session.exec(
        select(Fit).where(Fit.device_id == device_id, Fit.target == target, Fit.is_active == True)
    ).first()
    if not fit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active {target} fit found for device {device_id}",
        )
    return fit
