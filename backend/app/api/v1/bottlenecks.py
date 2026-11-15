"""Bottlenecks API endpoints according to Contract F."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_database
from app.core.errors import AppException
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.schemas.bottleneck import BottleneckResponse

router = APIRouter(tags=["bottlenecks"])


def _verify_run_owner(run_id: str, user_id: str, db: Session) -> AnalysisRun:
    """Verify analysis run belongs to the authenticated user."""
    run = (
        db.query(AnalysisRun)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .filter(AnalysisRun.id == run_id, Project.owner_id == user_id)
        .first()
    )
    if not run:
        raise AppException(
            status_code=404,
            detail="Analysis run not found",
            code="NOT_FOUND",
        )
    return run


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


@router.get(
    "/analysis-runs/{run_id}/bottlenecks",
    response_model=List[BottleneckResponse],
)
def list_analysis_bottlenecks(
    run_id: str,
    severity: Optional[str] = Query(None, description="Filter by severity: LOW|MEDIUM|HIGH|CRITICAL"),
    min_impact: Optional[float] = Query(None, description="Minimum impact score threshold"),
    pattern: Optional[str] = Query(None, description="Filter by detected pattern ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> List[Bottleneck]:
    """Retrieve ranked bottlenecks for an owned analysis run, sorted by impact_score desc."""
    _verify_run_owner(run_id, current_user.id, db)

    query = db.query(Bottleneck).filter(Bottleneck.analysis_run_id == run_id)

    if severity:
        query = query.filter(Bottleneck.severity == severity.upper())

    if min_impact is not None:
        query = query.filter(Bottleneck.impact_score >= min_impact)

    # Sort by impact_score descending
    query = query.order_by(Bottleneck.impact_score.desc())
    bottlenecks = query.all()

    if pattern:
        pattern_lower = pattern.lower()
        filtered = []
        for b in bottlenecks:
            fn = b.function
            if fn and fn.patterns:
                fn_patterns = [
                    p.get("pattern_id", "") if isinstance(p, dict) else str(p)
                    for p in fn.patterns
                ]
                if any(pattern_lower in p.lower() for p in fn_patterns):
                    filtered.append(b)
        bottlenecks = filtered

    return bottlenecks


@router.get(
    "/bottlenecks/{bottleneck_id}",
    response_model=BottleneckResponse,
)
def get_bottleneck(
    bottleneck_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Bottleneck:
    """Retrieve detailed information and evidence for a specific bottleneck."""
    return _verify_bottleneck_owner(bottleneck_id, current_user.id, db)


@router.get(
    "/bottlenecks/{bottleneck_id}/recommendation",
)
def get_bottleneck_recommendation(
    bottleneck_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
):
    """Retrieve recommendation for a bottleneck. Returns 404 NOT_READY until Phase 5."""
    bottleneck = _verify_bottleneck_owner(bottleneck_id, current_user.id, db)

    if not bottleneck.recommendation:
        raise AppException(
            status_code=404,
            detail="Recommendation not ready",
            code="NOT_READY",
        )

    return bottleneck.recommendation
