"""API endpoints for SiliconRoute decisions, routing, verification, and baseline statistics."""

import json
import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import BASE_DIR
from app.db import Decision, get_session
from app.router import compute_decision_statistics, execute_verification, route_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["router", "decisions"])


class RouteRequest(BaseModel):
    """Payload to request an optimal hardware routing decision."""
    ai_model_id: int
    batch: int = 1
    mode: str = "fastest"  # fastest | battery | balanced | cool
    workload: str = "sustained"  # sustained | idle_loaded | cold_start | single
    power_budget_w: Optional[float] = None
    verify: bool = False
    allow_explore: bool = True


class DecisionResponse(BaseModel):
    """Routing decision card with transparency breakdown."""
    id: Optional[int] = None
    ts: str
    ai_model_id: int
    batch: int
    mode: str
    workload: str = "sustained"
    power_budget_w: Optional[float] = None
    chosen_device_id: int
    chosen_device_key: str
    explored: bool
    reason: str
    context_rules: list[str]
    candidates: list[dict[str, Any]]
    excluded_candidates: list[dict[str, Any]]
    actual_ms: Optional[float] = None
    best_device_id_actual: Optional[int] = None
    was_best: Optional[bool] = None
    regret_pct: Optional[float] = None


@router.get("/router")
def get_router_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Status endpoint for the router reporting data readiness."""
    from app.db import Fit, Run
    has_runs = session.exec(select(Run.id)).first() is not None
    has_fits = session.exec(select(Fit.id)).first() is not None
    if not has_runs and not has_fits:
        return {"status": "uninitialized", "detail": "no benchmark data; run benchmark first"}
    return {"status": "ready", "detail": "router ready"}


@router.post("/route", response_model=DecisionResponse)
@router.post("/router", response_model=DecisionResponse)
def route_inference(
    req: RouteRequest,
    session: Session = Depends(get_session),
) -> DecisionResponse:
    """Evaluate all candidate devices, score according to goal, and return optimal routing decision.
    
    If verify=True, benchmarks chosen device and all candidates on hardware and records regret.
    """
    try:
        decision_dict = route_model(
            session=session,
            model_id=req.ai_model_id,
            batch=req.batch,
            mode=req.mode,
            workload=req.workload,
            power_budget_w=req.power_budget_w,
            allow_explore=req.allow_explore,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if req.verify:
        try:
            dec_record = execute_verification(session, decision_dict)
            return DecisionResponse(
                id=dec_record.id,
                ts=dec_record.ts,
                ai_model_id=dec_record.ai_model_id,
                batch=dec_record.batch,
                mode=dec_record.mode,
                workload=req.workload,
                power_budget_w=dec_record.power_budget_w,
                chosen_device_id=dec_record.chosen_device_id,
                chosen_device_key=decision_dict["chosen_device_key"],
                explored=dec_record.explored,
                reason=dec_record.reason,
                context_rules=decision_dict["context_rules"],
                candidates=decision_dict["candidates"],
                excluded_candidates=decision_dict["excluded_candidates"],
                actual_ms=dec_record.actual_ms,
                best_device_id_actual=dec_record.best_device_id_actual,
                was_best=dec_record.was_best,
                regret_pct=dec_record.regret_pct,
            )
        except RuntimeError as r_exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(r_exc))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Verification failed: {exc}")
    else:
        # Save unverified decision log
        dec_record = Decision(
            ts=decision_dict["ts"],
            ai_model_id=decision_dict["ai_model_id"],
            batch=decision_dict["batch"],
            mode=decision_dict["mode"],
            power_budget_w=decision_dict["power_budget_w"],
            context_json=json.dumps({
                "rules": decision_dict["context_rules"],
                "workload": req.workload,
                "excluded_candidates": decision_dict["excluded_candidates"],
            }),
            candidates_json=json.dumps(decision_dict["candidates"]),
            chosen_device_id=decision_dict["chosen_device_id"],
            explored=decision_dict["explored"],
            reason=decision_dict["reason"],
        )
        session.add(dec_record)
        session.commit()
        session.refresh(dec_record)

        return DecisionResponse(
            id=dec_record.id,
            ts=dec_record.ts,
            ai_model_id=dec_record.ai_model_id,
            batch=dec_record.batch,
            mode=dec_record.mode,
            workload=req.workload,
            power_budget_w=dec_record.power_budget_w,
            chosen_device_id=dec_record.chosen_device_id,
            chosen_device_key=decision_dict["chosen_device_key"],
            explored=dec_record.explored,
            reason=dec_record.reason,
            context_rules=decision_dict["context_rules"],
            candidates=decision_dict["candidates"],
            excluded_candidates=decision_dict["excluded_candidates"],
        )


@router.get("/decisions", response_model=list[Decision])
def list_decisions(
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[Decision]:
    """List recent router decisions and verification results."""
    decisions = session.exec(select(Decision).order_by(Decision.id.desc()).limit(limit)).all()
    return list(decisions)


@router.get("/decisions/stats")
def get_decision_statistics(
    ids: Optional[str] = Query(default=None, description="Comma-separated IDs or range e.g. '93-116'"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Retrieve accuracy, mean and p90 regret for SiliconRoute and all static baselines."""
    dec_ids = None
    if ids:
        if "-" in ids:
            parts = ids.split("-")
            dec_ids = list(range(int(parts[0]), int(parts[1]) + 1))
        else:
            dec_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    return compute_decision_statistics(session, decision_ids=dec_ids)


@router.get("/manifest")
def get_manifest_data() -> dict[str, Any]:
    """Retrieve published manifest.json with all provenance metrics."""
    manifest_path = BASE_DIR / "results" / "final" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="manifest.json not found")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed reading manifest: {exc}")


@router.get("/decisions/evaluation")
def get_evaluation_data(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Retrieve full hardware evaluation results for headline, cold-start rule, and earlier baselines.
    
    Dynamically discovers evaluation ranges from manifest.json to ensure no hardcoded IDs in the frontend.
    """
    manifest_path = BASE_DIR / "results" / "final" / "manifest.json"
    headline_range = [117, 140]
    cold_start_range = [141, 148]
    earlier_range = [93, 116]

    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                mf = json.load(f)
            metrics = mf.get("metrics", {})
            for k in metrics:
                if k.startswith("decisions_") and k.endswith("_total"):
                    parts = k.split("_")
                    if len(parts) == 4 and parts[1].isdigit() and parts[2].isdigit():
                        headline_range = [int(parts[1]), int(parts[2])]
                elif k.startswith("cold_start_") and k.endswith("_total"):
                    parts = k.split("_")
                    if len(parts) == 5 and parts[2].isdigit() and parts[3].isdigit():
                        cold_start_range = [int(parts[2]), int(parts[3])]
        except Exception as e:
            logger.warning("Failed parsing ranges from manifest: %s", e)

    headline_ids = list(range(headline_range[0], headline_range[1] + 1))
    cold_start_ids = list(range(cold_start_range[0], cold_start_range[1] + 1))
    earlier_ids = list(range(earlier_range[0], earlier_range[1] + 1))

    headline_stats = compute_decision_statistics(session, decision_ids=headline_ids)
    cold_start_stats = compute_decision_statistics(session, decision_ids=cold_start_ids)
    earlier_stats = compute_decision_statistics(session, decision_ids=earlier_ids)

    all_ids = set(headline_ids + cold_start_ids + earlier_ids)
    decs = session.exec(select(Decision).where(Decision.id.in_(all_ids))).all()
    dec_map = {d.id: d.model_dump() for d in decs}

    return {
        "headline": {
            "range": f"{headline_range[0]}-{headline_range[1]}",
            "start_id": headline_range[0],
            "end_id": headline_range[1],
            "stats": headline_stats,
            "decisions": [dec_map[i] for i in headline_ids if i in dec_map],
        },
        "cold_start_rule": {
            "range": f"{cold_start_range[0]}-{cold_start_range[1]}",
            "start_id": cold_start_range[0],
            "end_id": cold_start_range[1],
            "stats": cold_start_stats,
            "decisions": [dec_map[i] for i in cold_start_ids if i in dec_map],
        },
        "earlier": {
            "range": f"{earlier_range[0]}-{earlier_range[1]}",
            "start_id": earlier_range[0],
            "end_id": earlier_range[1],
            "stats": earlier_stats,
            "decisions": [dec_map[i] for i in earlier_ids if i in dec_map],
        },
    }


@router.get("/decisions/{decision_id}", response_model=Decision)
def get_decision_by_id(
    decision_id: int,
    session: Session = Depends(get_session),
) -> Decision:
    """Get full details of a specific routing decision."""
    dec = session.get(Decision, decision_id)
    if not dec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision {decision_id} not found")
    return dec
