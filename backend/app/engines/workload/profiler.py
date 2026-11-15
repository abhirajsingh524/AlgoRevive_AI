"""Workload characterization and profile derivation according to Contract G7."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.models.bottleneck import Bottleneck
from app.models.function import Function


class WorkloadProfile(BaseModel):
    """Derived workload profile for a bottleneck."""
    input_size: int = Field(default=100, description="Largest input size n")
    lookup_frequency: str = Field(default="MEDIUM", description="LOW | MEDIUM | HIGH | VERY_HIGH")
    insert_ratio: float = Field(default=0.0, description="Insert operation ratio (0..1)")
    delete_ratio: float = Field(default=0.0, description="Delete operation ratio (0..1)")
    read_write_ratio: float = Field(default=1.0, description="Ratio of read/lookup to write operations")
    data_distribution: str = Field(default="uniform", description="uniform | sorted | skewed")
    memory_constraint: str = Field(default="MEDIUM", description="LOW | MEDIUM | HIGH")
    latency_requirement: str = Field(default="MEDIUM", description="LOW | MEDIUM | HIGH | VERY_HIGH")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def derive_lookup_frequency(
    mix: Optional[Dict[str, float]],
    function: Optional[Function] = None,
) -> str:
    """Determine lookup frequency level from operation_mix thresholds (0.2/0.5/0.8) or pattern inference."""
    if mix and "lookup" in mix and mix["lookup"] is not None:
        lookup = float(mix["lookup"])
        if lookup >= 0.8:
            return "VERY_HIGH"
        elif lookup >= 0.5:
            return "HIGH"
        elif lookup >= 0.2:
            return "MEDIUM"
        else:
            return "LOW"

    # Infer from detected patterns when no mix is given
    if function and function.patterns:
        pattern_names = set()
        for p in function.patterns:
            if isinstance(p, dict):
                pattern_names.add(p.get("pattern_id") or p.get("pattern", ""))
            elif isinstance(p, str):
                pattern_names.add(p)

        if "LINEAR_MEMBERSHIP_IN_LOOP" in pattern_names or "NESTED_LOOP_LOOKUP" in pattern_names:
            return "HIGH"
        if "REPEATED_SORT_FOR_EXTREME" in pattern_names:
            return "HIGH"

    return "MEDIUM"


def derive_latency_requirement(latency_target_ms: Optional[float]) -> str:
    """Determine latency requirement level from latency_target_ms (default MEDIUM)."""
    if latency_target_ms is None or latency_target_ms <= 0:
        return "MEDIUM"
    if latency_target_ms <= 10.0:
        return "VERY_HIGH"
    elif latency_target_ms <= 50.0:
        return "HIGH"
    elif latency_target_ms <= 200.0:
        return "MEDIUM"
    else:
        return "LOW"


def derive_memory_constraint(constraint_str: Optional[str]) -> str:
    """Normalize memory constraint string to LOW | MEDIUM | HIGH."""
    if not constraint_str:
        return "MEDIUM"
    upper = constraint_str.upper()
    if upper in ("LOW", "MEDIUM", "HIGH"):
        return upper
    return "MEDIUM"


def derive_data_distribution(spec: Optional[Dict[str, Any]]) -> str:
    """Extract data distribution from generator options (default uniform)."""
    if not spec:
        return "uniform"

    entrypoints = spec.get("entrypoints", [])
    for ep in entrypoints:
        for arg in ep.get("args", []):
            opts = arg.get("options", {}) or {}
            dist = opts.get("distribution")
            if dist in ("uniform", "sorted", "skewed"):
                return dist
            if opts.get("sorted"):
                return "sorted"
            if opts.get("skewed"):
                return "skewed"

    return "uniform"


def build_workload_profile(
    spec: Optional[Dict[str, Any]],
    bottleneck: Bottleneck,
    function: Optional[Function] = None,
) -> WorkloadProfile:
    """Derive a WorkloadProfile for a bottleneck."""
    # 1. Input size (largest n)
    input_size = 100
    if spec and spec.get("sizes"):
        input_size = max(int(n) for n in spec["sizes"])
    elif bottleneck.evidence and isinstance(bottleneck.evidence, dict):
        if "input_size" in bottleneck.evidence:
            input_size = int(bottleneck.evidence["input_size"])

    # 2. Operation mix ratios
    mix = (spec.get("operation_mix", {}) or {}) if spec else {}
    lookup_freq = derive_lookup_frequency(mix, function=function)

    insert_ratio = float(mix.get("insert", 0.0))
    delete_ratio = float(mix.get("delete", 0.0))

    # Read/write ratio
    writes = insert_ratio + delete_ratio
    reads = float(mix.get("lookup", 0.0)) if "lookup" in mix else max(0.0, 1.0 - writes)

    if writes > 0:
        read_write_ratio = round(reads / writes, 2)
    elif reads > 0:
        read_write_ratio = 100.0
    else:
        read_write_ratio = 1.0

    # 3. Data distribution
    distribution = derive_data_distribution(spec)

    # 4. Memory constraint
    mem_constraint = derive_memory_constraint(spec.get("memory_constraint") if spec else None)

    # 5. Latency requirement
    latency_req = derive_latency_requirement(spec.get("latency_target_ms") if spec else None)

    return WorkloadProfile(
        input_size=input_size,
        lookup_frequency=lookup_freq,
        insert_ratio=insert_ratio,
        delete_ratio=delete_ratio,
        read_write_ratio=read_write_ratio,
        data_distribution=distribution,
        memory_constraint=mem_constraint,
        latency_requirement=latency_req,
    )
