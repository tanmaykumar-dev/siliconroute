"""AI model management API endpoints for SiliconRoute."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import AIModel, get_session
from app.models_gen import create_and_register_synthetic, scan_model_files

router = APIRouter(prefix="/api/models", tags=["models"])


class SyntheticCreateModel(BaseModel):
    """Payload for generating synthetic benchmark models."""
    family: str  # mlp | conv | attn
    sizes: list[int]
    layers: Optional[int] = None


@router.get("", response_model=list[AIModel])
def list_models(
    family: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> list[AIModel]:
    """List registered AI models, optionally filtered by family."""
    statement = select(AIModel)
    if family:
        statement = statement.where(AIModel.family == family)
    statement = statement.order_by(AIModel.id)
    return list(session.exec(statement).all())


@router.post("/synthetic", response_model=list[AIModel])
def create_synthetic_models(
    payload: SyntheticCreateModel,
    session: Session = Depends(get_session),
) -> list[AIModel]:
    """Generate and register a ladder of synthetic ONNX models."""
    valid_families = {"mlp", "conv", "attn"}
    if payload.family not in valid_families:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"family must be one of {valid_families}",
        )

    created_models: list[AIModel] = []
    for sz in payload.sizes:
        model = create_and_register_synthetic(
            session=session,
            family=payload.family,
            size=sz,
            layers=payload.layers,
        )
        created_models.append(model)

    return created_models


@router.post("/scan", response_model=list[AIModel])
def scan_models(session: Session = Depends(get_session)) -> list[AIModel]:
    """Scan models/ directory for local .onnx files and register them."""
    return scan_model_files(session)
