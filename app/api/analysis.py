"""Hardware performance analysis API endpoints (crossover and cold-start)."""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import Device, get_session
from app.predictor import calculate_crossover, get_cold_start_summary

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/crossover")
def get_crossover_analysis(
    dev_a: str = Query(default="cpu", description="Key of first device, e.g. cpu"),
    dev_b: str = Query(default="dml:1", description="Key of second device, e.g. dml:1"),
    family: str = Query(default="mlp", description="Model family (mlp | conv)"),
    batch: int = Query(default=1, ge=1, le=256),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Calculate the crossover model size between two devices for a given family and batch."""
    da = session.exec(select(Device).where(Device.key == dev_a)).first()
    db = session.exec(select(Device).where(Device.key == dev_b)).first()

    if not da:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {dev_a} not found")
    if not db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Device {dev_b} not found")

    try:
        return calculate_crossover(session, da.id, db.id, family=family, batch=batch)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/cold-start")
def get_cold_start_data(
    device_id: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Retrieve cold-start latencies and wake-up penalties per device."""
    return get_cold_start_summary(session, device_id=device_id)
