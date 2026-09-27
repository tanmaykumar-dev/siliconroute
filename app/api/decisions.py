"""API endpoints for SiliconRoute decisions, routing, verification, and baseline statistics."""

import json
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import Decision, get_session
from app.router import compute_decision_statistics, execute_verification, route_model

router = APIRouter(prefix="/api", tags=["router", "decisions"])


class RouteRequest(BaseModel):
    """Payload to request an optimal hardware routing decision."""
    ai_model_id: int
    batch: int = 1
    mode: str = "fastest"  # fastest | battery | balanced | cool
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


@router.post("/route", response_model=DecisionResponse)
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
            context_json=json.dumps({"rules": decision_dict["context_rules"]}),
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
def get_decision_statistics(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Retrieve accuracy, mean and p90 regret for SiliconRoute and all static baselines."""
    return compute_decision_statistics(session)


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
