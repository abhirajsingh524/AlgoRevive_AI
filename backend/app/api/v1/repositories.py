from typing import List, Optional
from fastapi import APIRouter, Depends, File as FastAPIFile, Form, UploadFile, status
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_database, get_storage
from app.core.errors import AppException
from app.models.file import File
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import FileContentResponse, FileResponse, RepositoryResponse
from app.services.repository_service import ingest_repository
from app.services.storage import StorageService

router = APIRouter(tags=["repositories"])


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
    "/projects/{project_id}/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_repository(
    project_id: str,
    files: List[UploadFile] = FastAPIFile(...),
    version_label: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    storage: StorageService = Depends(get_storage),
) -> Repository:
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

    return ingest_repository(
        db=db,
        storage=storage,
        project=project,
        upload_files=files,
        version_label=version_label,
    )


@router.get("/projects/{project_id}/repositories", response_model=List[RepositoryResponse])
def list_repositories(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> List[Repository]:
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

    return db.query(Repository).filter(Repository.project_id == project_id).order_by(Repository.created_at.desc()).all()


@router.get("/repositories/{repository_id}", response_model=RepositoryResponse)
def get_repository(
    repository_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> Repository:
    return get_owned_repository(repository_id, current_user.id, db)


@router.get("/repositories/{repository_id}/files", response_model=List[FileResponse])
def list_repository_files(
    repository_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> List[File]:
    get_owned_repository(repository_id, current_user.id, db)
    return db.query(File).filter(File.repository_id == repository_id).order_by(File.path.asc()).all()


@router.get("/repositories/{repository_id}/files/{file_id}/content", response_model=FileContentResponse)
def get_file_content(
    repository_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    storage: StorageService = Depends(get_storage),
) -> FileContentResponse:
    get_owned_repository(repository_id, current_user.id, db)
    file_record = db.query(File).filter(File.id == file_id, File.repository_id == repository_id).first()
    if not file_record:
        raise AppException(
            status_code=404,
            detail="File not found",
            code="NOT_FOUND",
        )

    file_bytes = storage.get_file(file_record.storage_key)
    try:
        content_str = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_str = file_bytes.decode("latin1", errors="replace")

    return FileContentResponse(
        id=file_record.id,
        path=file_record.path,
        language=file_record.language,
        content=content_str,
    )
