"""Fixed ML feature vector contract for AlgoRevive AI (Phase 5 ML contract).

THIS SCHEMA AND ORDER IS AN IMMUTABLE CONTRACT:
1. input_size_log10 (float): log10(max(1, input_size))
2. current_algorithm_code (int): integer index of primary pattern id (Contract G3)
3. current_complexity_rank (int): complexity rank 0..6 (Contract G5)
4. lookup_freq_level (int): LOW=0, MEDIUM=1, HIGH=2, VERY_HIGH=3
5. insert_ratio (float): insert operation ratio (0..1)
6. delete_ratio (float): delete operation ratio (0..1)
7. read_write_ratio (float): ratio of read/lookup to write operations
8. data_distribution_code (int): uniform=0, sorted=1, skewed=2
9. memory_constraint_level (int): LOW=0, MEDIUM=1, HIGH=2
10. latency_requirement_level (int): LOW=0, MEDIUM=1, HIGH=2, VERY_HIGH=3
11. call_count_log10 (float): log10(1 + call_count)
12. runtime_pct (float): runtime contribution percentage (0..1)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.bottleneck import Bottleneck
from app.models.function import Function

# Stable mapping of Contract G3 Pattern IDs to integer codes
PATTERN_CODE_MAP: Dict[str, int] = {
    "LINEAR_MEMBERSHIP_IN_LOOP": 0,
    "NESTED_LOOP_LOOKUP": 1,
    "REPEATED_SORT_FOR_EXTREME": 2,
    "STRING_CONCAT_IN_LOOP": 3,
    "NAIVE_RECURSION": 4,
    "LIST_POP_FRONT": 5,
}

LOOKUP_FREQ_MAP: Dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "VERY_HIGH": 3,
}

DATA_DISTRIBUTION_MAP: Dict[str, int] = {
    "uniform": 0,
    "sorted": 1,
    "skewed": 2,
}

MEMORY_CONSTRAINT_MAP: Dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
}

LATENCY_REQUIREMENT_MAP: Dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "VERY_HIGH": 3,
}


class FeatureVector(BaseModel):
    """Fixed 12-dimensional feature vector for ML recommendation."""

    # 1. input_size_log10
    input_size_log10: float = Field(..., description="log10(max(1, input_size))")
    # 2. current_algorithm_code
    current_algorithm_code: int = Field(..., description="Integer code for primary pattern ID (-1 for none)")
    # 3. current_complexity_rank
    current_complexity_rank: int = Field(..., description="Asymptotic complexity rank (0..6)")
    # 4. lookup_freq_level
    lookup_freq_level: int = Field(..., description="Lookup frequency (0..3)")
    # 5. insert_ratio
    insert_ratio: float = Field(..., description="Insert ratio (0..1)")
    # 6. delete_ratio
    delete_ratio: float = Field(..., description="Delete ratio (0..1)")
    # 7. read_write_ratio
    read_write_ratio: float = Field(..., description="Read to write ratio")
    # 8. data_distribution_code
    data_distribution_code: int = Field(..., description="Data distribution (0=uniform, 1=sorted, 2=skewed)")
    # 9. memory_constraint_level
    memory_constraint_level: int = Field(..., description="Memory constraint (0=LOW, 1=MEDIUM, 2=HIGH)")
    # 10. latency_requirement_level
    latency_requirement_level: int = Field(..., description="Latency requirement (0=LOW, 1=MEDIUM, 2=HIGH, 3=VERY_HIGH)")
    # 11. call_count_log10
    call_count_log10: float = Field(..., description="log10(1 + call_count)")
    # 12. runtime_pct
    runtime_pct: float = Field(..., description="Runtime percentage (0..1)")

    def to_array(self) -> List[float]:
        """Return features as an ordered numerical list conforming strictly to the Contract."""
        return [
            float(self.input_size_log10),
            float(self.current_algorithm_code),
            float(self.current_complexity_rank),
            float(self.lookup_freq_level),
            float(self.insert_ratio),
            float(self.delete_ratio),
            float(self.read_write_ratio),
            float(self.data_distribution_code),
            float(self.memory_constraint_level),
            float(self.latency_requirement_level),
            float(self.call_count_log10),
            float(self.runtime_pct),
        ]


def extract_primary_pattern_code(patterns: Optional[Any]) -> int:
    """Extract primary pattern code from function patterns."""
    if not patterns:
        return -1

    for p in patterns:
        pid = None
        if isinstance(p, dict):
            pid = p.get("pattern_id") or p.get("pattern")
        elif isinstance(p, str):
            pid = p

        if pid and pid in PATTERN_CODE_MAP:
            return PATTERN_CODE_MAP[pid]

    return -1


def build_feature_vector(
    bottleneck: Bottleneck,
    function: Optional[Function] = None,
) -> FeatureVector:
    """Build the canonical 12-dimensional FeatureVector for a bottleneck."""
    evidence = (bottleneck.evidence or {}) if isinstance(bottleneck.evidence, dict) else {}
    workload_data = evidence.get("workload", {})

    # 1. input_size_log10
    input_size = workload_data.get("input_size") or evidence.get("input_size") or 100
    input_size_log10 = round(math.log10(max(1.0, float(input_size))), 4)

    # 2. current_algorithm_code
    fn_patterns = function.patterns if function else None
    alg_code = extract_primary_pattern_code(fn_patterns)

    # 3. current_complexity_rank
    complexity_rank = function.complexity_rank if function else 0

    # 4. lookup_freq_level
    lookup_str = workload_data.get("lookup_frequency", "MEDIUM")
    lookup_level = LOOKUP_FREQ_MAP.get(lookup_str, 1)

    # 5. insert_ratio
    insert_ratio = round(float(workload_data.get("insert_ratio", 0.0)), 4)

    # 6. delete_ratio
    delete_ratio = round(float(workload_data.get("delete_ratio", 0.0)), 4)

    # 7. read_write_ratio
    read_write_ratio = round(float(workload_data.get("read_write_ratio", 1.0)), 4)

    # 8. data_distribution_code
    dist_str = workload_data.get("data_distribution", "uniform")
    dist_code = DATA_DISTRIBUTION_MAP.get(dist_str, 0)

    # 9. memory_constraint_level
    mem_str = workload_data.get("memory_constraint", "MEDIUM")
    mem_level = MEMORY_CONSTRAINT_MAP.get(mem_str, 1)

    # 10. latency_requirement_level
    lat_str = workload_data.get("latency_requirement", "MEDIUM")
    lat_level = LATENCY_REQUIREMENT_MAP.get(lat_str, 1)

    # 11. call_count_log10
    call_count = max(0, bottleneck.call_count)
    call_count_log10 = round(math.log10(1.0 + call_count), 4)

    # 12. runtime_pct
    runtime_pct = round(max(0.0, min(1.0, float(bottleneck.runtime_pct))), 4)

    return FeatureVector(
        input_size_log10=input_size_log10,
        current_algorithm_code=alg_code,
        current_complexity_rank=complexity_rank,
        lookup_freq_level=lookup_level,
        insert_ratio=insert_ratio,
        delete_ratio=delete_ratio,
        read_write_ratio=read_write_ratio,
        data_distribution_code=dist_code,
        memory_constraint_level=mem_level,
        latency_requirement_level=lat_level,
        call_count_log10=call_count_log10,
        runtime_pct=runtime_pct,
    )
