"""Benchmark job submission and tracking API endpoints."""

from datetime import datetime, timezone
import json
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.benchmark import execute_latency_job
from app.config import TIMED_RUNS, WARMUP_RUNS
from app.db import BenchSession, get_session
from app.energy import execute_energy_job
from app.jobs import cancel_job, get_progress, try_submit

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


class BenchmarkRequest(BaseModel):
    """Payload to request a benchmark execution session."""
    kind: str = "latency"  # latency | energy | verify
    model_ids: list[int]
    device_ids: list[int]
    batches: list[int] = Field(default_factory=lambda: [1, 8])
    warmup: int = WARMUP_RUNS
    runs: int = TIMED_RUNS
    notes: Optional[str] = ""


@router.post("", status_code=status.HTTP_200_OK)
def create_benchmark_job(
    req: BenchmarkRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Submit a benchmark job. Returns HTTP 409 if another job is running."""
    if req.kind not in ("latency", "energy"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kind must be 'latency' or 'energy'",
        )

    if not req.model_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="model_ids cannot be empty")
    if not req.device_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="device_ids cannot be empty")
    if not req.batches:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="batches cannot be empty")

    now_iso = datetime.now(timezone.utc).isoformat()
    config_dict = req.model_dump()

    # Pre-create session row in database
    bench_session = BenchSession(
        kind=req.kind,
        status="queued",
        config_json=json.dumps(config_dict),
        created_at=now_iso,
        notes=req.notes,
    )
    session.add(bench_session)
    session.commit()
    session.refresh(bench_session)

    # Attempt to submit to the single job worker
    def run_task(progress_state: dict[str, Any]) -> None:
        if req.kind == "energy":
            execute_energy_job(
                bench_session_id=bench_session.id,
                model_ids=req.model_ids,
                device_ids=req.device_ids,
                batches=req.batches,
                progress_state=progress_state,
            )
        else:
            execute_latency_job(
                bench_session_id=bench_session.id,
                model_ids=req.model_ids,
                device_ids=req.device_ids,
                batches=req.batches,
                warmup_runs=req.warmup,
                timed_runs=req.runs,
                progress_state=progress_state,
            )

    submitted = try_submit(bench_session.id, run_task)
    if not submitted:
        # Mark queued session as failed due to concurrency collision
        bench_session.status = "failed"
        bench_session.error = "A benchmark job is already running"
        session.add(bench_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A benchmark job is already running. Only one benchmark is permitted at a time.",
        )

    return {"session_id": bench_session.id, "status": "queued"}


@router.get("/{session_id}")
def get_benchmark_status(
    session_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Poll the status and progress of a benchmark session."""
    bench = session.get(BenchSession, session_id)
    if not bench:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark session {session_id} not found",
        )

    prog = get_progress(session_id)
    done_count = prog["done"] if prog else 0
    total_count = prog["total"] if prog else 0
    current_item = prog["item"] if prog else None

    return {
        "id": bench.id,
        "kind": bench.kind,
        "status": bench.status,
        "progress": {"done": done_count, "total": total_count},
        "current_item": current_item,
        "started_at": bench.started_at,
        "finished_at": bench.finished_at,
        "error": bench.error,
        "notes": bench.notes,
    }


@router.post("/{session_id}/cancel")
def cancel_benchmark_job(session_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Request cancellation for a running benchmark session."""
    bench = session.get(BenchSession, session_id)
    if not bench:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark session {session_id} not found",
        )

    if bench.status in {"done", "failed", "cancelled"}:
        return {"session_id": session_id, "status": bench.status}

    cancelled = cancel_job(session_id)
    return {"session_id": session_id, "status": "cancelling" if cancelled else bench.status}
