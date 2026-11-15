"""Optimizations API endpoints according to Contract Section F, G2, G3."""

from __future__ import annotations

import socket
from typing import Any, List
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_database
from app.core.errors import AppException
from app.core.logging import get_logger
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.optimization import Optimization
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.repository import Repository
from app.models.user import User
from app.schemas.optimization import (
    OptimizationCreateRequest,
    OptimizationResponse,
)
from app.services.optimization_service import execute_optimization
from app.services.storage import get_storage_service
from app.workers.celery_app import celery_app
from app.workers.tasks import run_optimization

logger = get_logger("optimizations_api")

router = APIRouter(tags=["optimizations"])


def _verify_bottleneck_owner(bottleneck_id: str, user_id: str, db: Session) -> Bottleneck:
    """Verify bottleneck belongs to the authenticated user."""
    bottleneck = (
        db.query(Bottleneck)
        .join(AnalysisRun, Bottleneck.analysis_run_id == AnalysisRun.id)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .filter(Bottleneck.id == bottleneck_id, Project.owner_id == user_id)
        .first()
    )
    if not bottleneck:
        raise AppException(
            status_code=404,
            detail="Bottleneck not found",
            code="NOT_FOUND",
        )
    return bottleneck


def _verify_optimization_owner(optimization_id: str, user_id: str, db: Session) -> Optimization:
    """Verify optimization belongs to the authenticated user."""
    opt = (
        db.query(Optimization)
        .join(Recommendation, Optimization.recommendation_id == Recommendation.id)
        .join(Bottleneck, Recommendation.bottleneck_id == Bottleneck.id)
        .join(AnalysisRun, Bottleneck.analysis_run_id == AnalysisRun.id)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .filter(Optimization.id == optimization_id, Project.owner_id == user_id)
        .first()
    )
    if not opt:
        raise AppException(
            status_code=404,
            detail="Optimization not found",
            code="NOT_FOUND",
        )
    return opt


def _dispatch_optimization(opt_id: str, db: Session, force_sync: bool = False) -> None:
    """Attempt background dispatch via Celery; fallback to inline sync execution if broker unavailable or forced."""
    if force_sync:
        storage = get_storage_service()
        execute_optimization(db=db, storage=storage, optimization_id=opt_id)
        db.expire_all()
        return

    # In eager mode (e.g. testing), run directly through task
    if getattr(celery_app.conf, "task_always_eager", False):
        run_optimization.apply_async(args=[opt_id])
        return

    dispatched = False
    try:
        parsed = urlparse(settings.REDIS_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            s.connect((host, port))
        run_optimization.apply_async(args=[opt_id])
        dispatched = True
        logger.info(f"Dispatched run_optimization for {opt_id} to Celery worker")
    except Exception as e:
        logger.debug(f"Celery check/dispatch failed ({e}), falling back to synchronous execution")

    if not dispatched:
        logger.info(f"Executing optimization {opt_id} synchronously")
        storage = get_storage_service()
        execute_optimization(db=db, storage=storage, optimization_id=opt_id)
        db.expire_all()


@router.post(
    "/bottlenecks/{bottleneck_id}/optimizations",
    response_model=OptimizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_optimization(
    bottleneck_id: str,
    payload: OptimizationCreateRequest = OptimizationCreateRequest(),
    sync: bool = Query(False, description="Force synchronous execution"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Optimization:
    """Initiate candidate optimization generation for a bottleneck."""
    bottleneck = _verify_bottleneck_owner(bottleneck_id, current_user.id, db)

    rec = bottleneck.recommendation
    if not rec:
        rec = db.query(Recommendation).filter(Recommendation.bottleneck_id == bottleneck.id).first()

    if not rec:
        raise AppException(
            status_code=404,
            detail="Recommendation not ready for this bottleneck",
            code="NOT_READY",
        )

    mode = (payload.mode or "template").lower().strip()
    if mode not in ("template", "llm"):
        raise AppException(
            status_code=400,
            detail=f"Invalid optimization mode '{payload.mode}'. Allowed: 'template', 'llm'",
            code="INVALID_MODE",
        )

    opt = Optimization(
        id=str(uuid.uuid4()),
        recommendation_id=rec.id,
        mode=mode,
        template_id=payload.template_id,
        status="generated",
    )
    db.add(opt)
    db.commit()
    db.refresh(opt)

    _dispatch_optimization(opt.id, db, force_sync=sync)
    db.refresh(opt)

    return opt


@router.get(
    "/bottlenecks/{bottleneck_id}/optimizations",
    response_model=List[OptimizationResponse],
)
def list_bottleneck_optimizations(
    bottleneck_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> List[Optimization]:
    """List all optimization candidate runs for a bottleneck."""
    bottleneck = _verify_bottleneck_owner(bottleneck_id, current_user.id, db)

    rec = bottleneck.recommendation
    if not rec:
        rec = db.query(Recommendation).filter(Recommendation.bottleneck_id == bottleneck.id).first()

    if not rec:
        return []

    return (
        db.query(Optimization)
        .filter(Optimization.recommendation_id == rec.id)
        .order_by(Optimization.created_at.desc())
        .all()
    )


@router.get("/optimizations/config")
def get_optimizations_config(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve optimization generator configuration (supported templates and LLM status)."""
    p_name = settings.LLM_PROVIDER.lower().strip()
    is_enabled = p_name not in ("none", "null", "")
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "llm_enabled": is_enabled,
        "llm_model": settings.LLM_MODEL if is_enabled else None,
        "templates": [
            "T1_SET_MEMBERSHIP",
            "T2_DICT_INDEX_JOIN",
            "T3_MIN_MAX_HEAP",
            "T4_JOIN_STRINGS",
            "T5_LRU_CACHE",
            "T6_DEQUE_POPLEFT",
        ],
    }


@router.get(
    "/optimizations/{optimization_id}",
    response_model=OptimizationResponse,
)
def get_optimization(
    optimization_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Optimization:
    """Retrieve details of a specific optimization candidate."""
    return _verify_optimization_owner(optimization_id, current_user.id, db)
