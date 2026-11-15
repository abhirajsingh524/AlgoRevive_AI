from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_database
from app.core.errors import AppException
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    req: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Project:
    project = Project(
        owner_id=current_user.id,
        name=req.name,
        description=req.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> List[Project]:
    return db.query(Project).filter(Project.owner_id == current_user.id).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Project:
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.owner_id == current_user.id,
    ).first()
    if not project:
        raise AppException(
            status_code=404,
            detail="Project not found",
            code="NOT_FOUND",
        )
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    req: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Project:
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.owner_id == current_user.id,
    ).first()
    if not project:
        raise AppException(
            status_code=404,
            detail="Project not found",
            code="NOT_FOUND",
        )

    if req.name is not None:
        project.name = req.name
    if req.description is not None:
        project.description = req.description

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Response:
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.owner_id == current_user.id,
    ).first()
    if not project:
        raise AppException(
            status_code=404,
            detail="Project not found",
            code="NOT_FOUND",
        )

    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
