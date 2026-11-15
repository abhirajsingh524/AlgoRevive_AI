"""Pydantic schemas for validating runtime profiling results."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FunctionProfile(BaseModel):
    file: str
    function: str
    lineno: int
    calls: int
    total_time: float
    cumulative_time: float


class MeasurementResult(BaseModel):
    n: int
    runtime_s: float
    cpu_time_s: float
    peak_memory_kb: float
    top_functions: List[FunctionProfile] = Field(default_factory=list)


class EntrypointProfile(BaseModel):
    function: str
    status: str  # "success" | "error"
    growth_exponent: float = 0.0
    sizes: List[int] = Field(default_factory=list)
    measurements: List[MeasurementResult] = Field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None
    traceback: Optional[str] = None


class ProfileSummary(BaseModel):
    total_entrypoints: int
    successful_entrypoints: int
    failed_entrypoints: int


class ProfileResult(BaseModel):
    status: str
    entrypoints: Dict[str, EntrypointProfile]
    summary: ProfileSummary
    extra: Dict[str, Any] = Field(default_factory=dict)
