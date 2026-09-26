"""Run querying and CSV export API endpoints."""

import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session, select

from app.db import Run, get_session

router = APIRouter(tags=["runs"])


@router.get("/api/runs", response_model=list[Run])
def list_runs(
    model_id: Optional[int] = Query(default=None),
    device_id: Optional[int] = Query(default=None),
    batch: Optional[int] = Query(default=None),
    limit: int = Query(default=500, le=5000),
    session: Session = Depends(get_session),
) -> list[Run]:
    """Retrieve measured benchmark runs with optional filtering."""
    statement = select(Run)
    if model_id is not None:
        statement = statement.where(Run.ai_model_id == model_id)
    if device_id is not None:
        statement = statement.where(Run.device_id == device_id)
    if batch is not None:
        statement = statement.where(Run.batch == batch)

    statement = statement.order_by(Run.id.desc()).limit(limit)
    return list(session.exec(statement).all())


@router.get("/api/export/runs.csv")
def export_runs_csv(session: Session = Depends(get_session)) -> Response:
    """Export all stored runs as CSV."""
    runs = session.exec(select(Run).order_by(Run.id)).all()

    output = io.StringIO()
    fields = [
        "id",
        "session_id",
        "ai_model_id",
        "device_id",
        "provider_used",
        "provider_mismatch",
        "batch",
        "intra_op_threads",
        "warmup_runs",
        "timed_runs",
        "inner_loop_k",
        "session_create_ms",
        "median_ms",
        "p10_ms",
        "p90_ms",
        "mean_ms",
        "min_ms",
        "max_ms",
        "stdev_ms",
        "cv",
        "spread",
        "unstable",
        "throughput_per_s",
        "output_matches_cpu",
        "max_rel_err",
        "plugged_in",
        "battery_pct",
        "created_at",
    ]

    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()

    for r in runs:
        writer.writerow({f: getattr(r, f, None) for f in fields})

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=runs.csv"},
    )
