"""Pydantic schemas for Recommendation models according to Contract E and F."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class FeatureImportanceItem(BaseModel):
    """Normalized feature importance item."""

    feature: str = Field(..., description="Canonical FeatureVector field name")
    display_name: str = Field(..., description="Human-readable feature name")
    importance: float = Field(..., description="Normalized importance weight summing to ~1.0")
    value: float = Field(..., description="Raw numerical feature value")
    formatted_value: str = Field(..., description="Human-readable formatted real value")


class RecommendationResponse(BaseModel):
    """Recommendation response returned by GET /bottlenecks/{id}/recommendation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    bottleneck_id: str
    current_algorithm: str
    recommended_algorithm: str
    alternatives: Optional[List[str]] = None
    expected_complexity: Optional[str] = None
    confidence: float
    reason: str
    feature_importance: Optional[List[Dict[str, Any]]] = None
    source: str = "rules"  # rules | ml
    created_at: datetime
    updated_at: datetime
