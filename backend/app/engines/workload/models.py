"""Workload specification schema conforming to Contract G7 with validation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

ENTRYPOINT_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$")

ArgKind = Literal[
    "int_list",
    "str_list",
    "records",
    "int",
    "str",
    "two_record_lists",
]


class ArgSpec(BaseModel):
    kind: ArgKind
    size_factor: float = Field(default=1.0, gt=0)
    fixed: Optional[Any] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class EntrypointSpec(BaseModel):
    function: str
    args: List[ArgSpec] = Field(default_factory=list)

    @field_validator("function")
    @classmethod
    def validate_function_target(cls, v: str) -> str:
        v = v.strip()
        if not ENTRYPOINT_REGEX.match(v):
            raise ValueError(
                f"Invalid entrypoint format '{v}'. Must be formatted as 'module.path:function_name'"
            )
        return v


class WorkloadSpec(BaseModel):
    sizes: List[int] = Field(..., min_length=1, max_length=8)
    entrypoints: List[EntrypointSpec] = Field(..., min_length=1, max_length=10)
    operation_mix: Dict[str, float] = Field(
        default_factory=lambda: {"lookup": 0.9, "insert": 0.05, "delete": 0.05}
    )
    memory_constraint: Literal["low", "medium", "high"] = "medium"
    latency_target_ms: Optional[float] = None
    seed: int = 42

    @field_validator("sizes")
    @classmethod
    def validate_sizes(cls, v: List[int]) -> List[int]:
        if not (1 <= len(v) <= 8):
            raise ValueError("sizes must contain between 1 and 8 sizes")
        for size in v:
            if not isinstance(size, int) or size <= 0:
                raise ValueError(f"Each size in sizes must be a positive integer, got {size}")
            if size > 2_000_000:
                raise ValueError(f"Size {size} exceeds maximum limit of 2,000,000")
        return v

    @field_validator("entrypoints")
    @classmethod
    def validate_entrypoints(cls, v: List[EntrypointSpec]) -> List[EntrypointSpec]:
        if not (1 <= len(v) <= 10):
            raise ValueError("entrypoints must contain between 1 and 10 entrypoints")
        return v

    @model_validator(mode="after")
    def validate_spec(self) -> "WorkloadSpec":
        return self
