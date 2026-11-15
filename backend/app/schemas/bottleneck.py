"""Pydantic schemas for Bottleneck models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict

from app.schemas.function import FunctionResponse


class BottleneckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_run_id: str
    function_id: str
    static_score: float
    runtime_score: float
    call_count: int
    runtime_pct: float
    memory_peak_kb: float
    impact_score: float
    severity: str
    evidence: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    function: Optional[FunctionResponse] = None
