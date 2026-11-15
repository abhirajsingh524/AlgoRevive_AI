from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class AnalysisRunCreate(BaseModel):
    config: Optional[Dict[str, Any]] = None


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    requested_by: Optional[str] = None
    status: str
    stage: str
    progress: int
    config: Optional[Any] = None
    workload_spec: Optional[Any] = None
    workload_hash: Optional[str] = None
    environment: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
