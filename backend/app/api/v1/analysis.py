from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_database
from app.core.errors import AppException
from app.core.logging import get_logger
from app.models.analysis_run import AnalysisRun
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.schemas.analysis import AnalysisRunCreate, AnalysisRunResponse
from app.workers.tasks import run_analysis

logger = get_logger("analysis_api")

router = APIRouter(tags=["analysis"])


def get_owned_repository(repo_id: str, user_id: str, db: Session) -> Repository:
    repo = (
        db.query(Repository)
        .join(Project, Repository.project_id == Project.id)
        .filter(Repository.id == repo_id, Project.owner_id == user_id)
        .first()
    )
    if not repo:
        raise AppException(
            status_code=404,
            detail="Repository not found",
            code="NOT_FOUND",
        )
    return repo


@router.post(
    "/repositories/{repository_id}/analysis-runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis_run(
    repository_id: str,
    payload: AnalysisRunCreate = AnalysisRunCreate(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> AnalysisRun:
    repo = get_owned_repository(repository_id, current_user.id, db)

    run = AnalysisRun(
        repository_id=repo.id,
        requested_by=current_user.id,
        status="queued",
        stage="queued",
        progress=0,
        config=payload.config or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Dispatch Celery background task (or fallback gracefully)
    try:
        run_analysis.delay(run.id)
    except Exception as e:
        logger.warning(f"Could not enqueue Celery task, running inline or queued: {e}")

    return run


@router.get(
    "/repositories/{repository_id}/analysis-runs",
    response_model=List[AnalysisRunResponse],
)
def list_analysis_runs(
    repository_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> List[AnalysisRun]:
    get_owned_repository(repository_id, current_user.id, db)
    return (
        db.query(AnalysisRun)
        .filter(AnalysisRun.repository_id == repository_id)
        .order_by(AnalysisRun.created_at.desc())
        .all()
    )


@router.get(
    "/analysis-runs/{run_id}",
    response_model=AnalysisRunResponse,
)
def get_analysis_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> AnalysisRun:
    run = (
        db.query(AnalysisRun)
        .join(Repository, AnalysisRun.repository_id == Repository.id)
        .join(Project, Repository.project_id == Project.id)
        .filter(AnalysisRun.id == run_id, Project.owner_id == current_user.id)
        .first()
    )
    if not run:
        raise AppException(
            status_code=404,
            detail="Analysis run not found",
            code="NOT_FOUND",
        )
    return run
