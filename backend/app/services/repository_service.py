import hashlib
import io
import stat
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppException
from app.core.logging import get_logger
from app.models.file import File
from app.models.project import Project
from app.models.repository import Repository
from app.services.audit_service import log_audit
from app.services.storage import StorageService

logger = get_logger("repository_service")

IGNORED_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules"}


def should_ignore_path(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/").strip("/")
    parts = normalized.split("/")
    return any(part in IGNORED_DIRS for part in parts)


def count_loc(data: bytes) -> int:
    try:
        text = data.decode("utf-8", errors="replace")
        return len(text.splitlines())
    except Exception:
        return 0


def process_zip_archive(archive_bytes: bytes) -> List[Tuple[str, bytes]]:
    # Check archive size vs MAX_UPLOAD_MB
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(archive_bytes) > max_bytes:
        raise AppException(
            status_code=400,
            detail=f"Archive exceeds maximum upload size of {settings.MAX_UPLOAD_MB} MB",
            code="ARCHIVE_TOO_LARGE",
        )

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile:
        raise AppException(
            status_code=400,
            detail="Invalid zip archive",
            code="INVALID_ARCHIVE",
        )

    infolist = zip_file.infolist()

    # Rule H3: reject more than 5000 files
    if len(infolist) > 5000:
        raise AppException(
            status_code=400,
            detail="Archive exceeds maximum file limit of 5000 files",
            code="TOO_MANY_FILES",
        )

    files_to_index: List[Tuple[str, bytes]] = []

    for info in infolist:
        name = info.filename
        # Rule H3: reject absolute paths
        if name.startswith("/") or name.startswith("\\") or (len(name) > 1 and name[1] == ":"):
            raise AppException(
                status_code=400,
                detail=f"Absolute paths not allowed in archive: {name}",
                code="ABSOLUTE_PATH_DETECTED",
            )

        # Rule H3: reject path traversal (zip-slip)
        pure_path = PurePosixPath(name)
        if ".." in pure_path.parts:
            raise AppException(
                status_code=400,
                detail=f"Path traversal detected in archive: {name}",
                code="ZIP_SLIP_DETECTED",
            )

        # Rule H3: reject symlinks
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise AppException(
                status_code=400,
                detail=f"Symlinks not allowed in archive: {name}",
                code="SYMLINK_DETECTED",
            )

        # Skip directories
        if info.is_dir() or name.endswith("/"):
            continue

        # Rule H3: reject any single file over 2 MB decompressed
        if info.file_size > 2 * 1024 * 1024:
            raise AppException(
                status_code=400,
                detail=f"File exceeds maximum decompressed size limit of 2MB: {name}",
                code="FILE_TOO_LARGE",
            )

        # Skip ignored paths (.git, __pycache__, venv, .venv, node_modules)
        normalized_name = pure_path.as_posix()
        if should_ignore_path(normalized_name):
            continue

        data = zip_file.read(info)
        files_to_index.append((normalized_name, data))

    return files_to_index


def ingest_repository(
    db: Session,
    storage: StorageService,
    project: Project,
    upload_files: List[UploadFile],
    version_label: Optional[str] = None,
) -> Repository:
    if not upload_files:
        raise AppException(
            status_code=400,
            detail="No files provided for upload",
            code="NO_FILES_PROVIDED",
        )

    repo_id = str(uuid.uuid4())
    source_type = "files"

    first_file = upload_files[0]
    first_name = first_file.filename or ""

    if len(upload_files) == 1 and (
        first_name.lower().endswith(".zip")
        or (first_file.content_type and "zip" in first_file.content_type.lower())
    ):
        source_type = "zip"
        archive_bytes = first_file.file.read()
        extracted_files = process_zip_archive(archive_bytes)
    else:
        # Multiple .py files (or single .py file)
        extracted_files = []
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for uf in upload_files:
                fname = uf.filename or "unknown.py"
                if not fname.lower().endswith(".py"):
                    continue

                pure_path = PurePosixPath(fname)
                if ".." in pure_path.parts:
                    raise AppException(
                        status_code=400,
                        detail=f"Path traversal detected in file: {fname}",
                        code="ZIP_SLIP_DETECTED",
                    )
                if fname.startswith("/") or fname.startswith("\\"):
                    raise AppException(
                        status_code=400,
                        detail=f"Absolute path detected: {fname}",
                        code="ABSOLUTE_PATH_DETECTED",
                    )

                content = uf.file.read()
                if len(content) > 2 * 1024 * 1024:
                    raise AppException(
                        status_code=400,
                        detail=f"File exceeds maximum size limit of 2MB: {fname}",
                        code="FILE_TOO_LARGE",
                    )

                normalized_name = pure_path.as_posix()
                if not should_ignore_path(normalized_name):
                    extracted_files.append((normalized_name, content))
                    zf.writestr(normalized_name, content)

        archive_bytes = zip_buffer.getvalue()

    if not extracted_files:
        raise AppException(
            status_code=400,
            detail="No valid files found in upload",
            code="NO_VALID_FILES",
        )

    # Store original.zip under repos/{repository_id}/original.zip
    original_zip_key = f"repos/{repo_id}/original.zip"
    storage.put_file(original_zip_key, archive_bytes)

    # Create repository record
    repo = Repository(
        id=repo_id,
        project_id=project.id,
        version_label=version_label,
        source_type=source_type,
        storage_key=original_zip_key,
        status="ingested",
        file_count=0,
        total_loc=0,
    )
    db.add(repo)
    db.flush()

    total_loc = 0
    file_count = 0

    # Store each file and create File record
    for file_path, file_data in extracted_files:
        sha256 = hashlib.sha256(file_data).hexdigest()
        loc = count_loc(file_data)
        language = "python" if file_path.lower().endswith(".py") else "other"
        file_key = f"repos/{repo_id}/files/{file_path}"

        storage.put_file(file_key, file_data)

        file_record = File(
            repository_id=repo_id,
            path=file_path,
            language=language,
            loc=loc,
            sha256=sha256,
            storage_key=file_key,
        )
        db.add(file_record)

        total_loc += loc
        file_count += 1

    repo.file_count = file_count
    repo.total_loc = total_loc
    repo.status = "ingested"

    db.commit()
    db.refresh(repo)

    # Log audit
    log_audit(
        db=db,
        user_id=project.owner_id,
        action="UPLOAD",
        entity="repository",
        entity_id=repo.id,
        meta={"file_count": repo.file_count, "total_loc": repo.total_loc},
    )

    return repo
