"""Optimization schemas conforming to Contract Section F, G2, G3."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class OptimizationCreateRequest(BaseModel):
    """Request payload to initiate optimization generation."""

    mode: str = Field(default="template", description="Optimization mode: template or llm")
    template_id: Optional[str] = Field(default=None, description="Optional Contract G3 template ID")


class OptimizationResponse(BaseModel):
    """Optimization response schema."""

    id: str
    recommendation_id: str
    mode: str
    template_id: Optional[str] = None
    candidate_code: Optional[str] = None
    patch: Optional[str] = None
    status: str
    decision: Optional[str] = None
    decision_reason: Optional[Any] = None
    human_review: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
