from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    version_label: Optional[str] = None
    source_type: str
    storage_key: str
    status: str
    file_count: int
    total_loc: int
    created_at: datetime
    updated_at: datetime


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    path: str
    language: str
    loc: int
    sha256: str
    storage_key: str
    created_at: datetime
    updated_at: datetime


class FileContentResponse(BaseModel):
    id: str
    path: str
    language: str
    content: str
