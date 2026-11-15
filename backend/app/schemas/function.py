from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class FunctionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    repository_id: str
    qualified_name: str
    name: str
    lineno: int
    end_lineno: int
    params: Optional[Any] = None
    complexity_class: Optional[str] = None
    complexity_rank: int
    loop_depth: int
    has_recursion: bool
    patterns: Optional[Any] = None
    severity: str
    metrics: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
