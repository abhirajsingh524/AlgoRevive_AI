"""Deterministic rule-based recommendation engine and expected complexity mapping.

Provides deterministic fallback mapping pattern -> candidate class with
workload gating (small-n, low lookup frequency, high memory constraint),
plus expected complexity transitions for each Contract G4 class.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.engines.workload.features import FeatureVector
from app.models.bottleneck import Bottleneck
from app.models.function import Function

# Contract G3 pattern ID to Contract G4 target recommendation class
PATTERN_TO_CLASS: Dict[str, str] = {
    "LINEAR_MEMBERSHIP_IN_LOOP": "hash_set",
    "NESTED_LOOP_LOOKUP": "hash_map_index",
    "REPEATED_SORT_FOR_EXTREME": "min_max_builtin_or_heap",
    "STRING_CONCAT_IN_LOOP": "list_join",
    "NAIVE_RECURSION": "memoization_lru",
    "LIST_POP_FRONT": "deque",
}

# Code to pattern ID mapping
CODE_TO_PATTERN: Dict[int, str] = {
    0: "LINEAR_MEMBERSHIP_IN_LOOP",
    1: "NESTED_LOOP_LOOKUP",
    2: "REPEATED_SORT_FOR_EXTREME",
    3: "STRING_CONCAT_IN_LOOP",
    4: "NAIVE_RECURSION",
    5: "LIST_POP_FRONT",
}

# Expected complexity transition for each Contract G4 class
EXPECTED_COMPLEXITY: Dict[str, str] = {
    "hash_set": "O(n * m) -> O(n + m)",
    "hash_map_index": "O(n * m) -> O(n + m)",
    "min_max_builtin_or_heap": "O(k * n log n) -> O(n)",
    "list_join": "O(n^2) -> O(n)",
    "memoization_lru": "O(2^n) -> O(n)",
    "deque": "O(n^2) -> O(n)",
    "keep_current": "Unchanged",
}

# Current algorithmic name mapping for reporting
CURRENT_ALGORITHM_NAMES: Dict[str, str] = {
    "LINEAR_MEMBERSHIP_IN_LOOP": "linear_scan_membership",
    "NESTED_LOOP_LOOKUP": "nested_loop_search",
    "REPEATED_SORT_FOR_EXTREME": "repeated_full_sort",
    "STRING_CONCAT_IN_LOOP": "repeated_string_concat",
    "NAIVE_RECURSION": "naive_exponential_recursion",
    "LIST_POP_FRONT": "list_pop_front_o_n",
    "keep_current": "current_implementation",
}

# Secondary alternatives per recommended class
CLASS_ALTERNATIVES: Dict[str, List[str]] = {
    "hash_set": ["keep_current"],
    "hash_map_index": ["hash_set", "keep_current"],
    "min_max_builtin_or_heap": ["heapq", "keep_current"],
    "list_join": ["io.StringIO", "keep_current"],
    "memoization_lru": ["dict_memoization", "keep_current"],
    "deque": ["list_pop", "keep_current"],
    "keep_current": [],
}


class RuleRecommendation(BaseModel):
    """Result of rule-based recommendation."""

    current_algorithm: str = Field(..., description="Current detected algorithm name")
    recommended_algorithm: str = Field(..., description="Recommended Contract G4 class")
    expected_complexity: str = Field(..., description="Complexity transition e.g. O(n*m) -> O(n+m)")
    confidence: float = Field(default=1.0, description="Confidence score 0.0 - 1.0")
    alternatives: List[str] = Field(default_factory=list, description="Alternative candidate classes")
    reason: str = Field(..., description="Plain-English explanation of rule and workload gating")
    source: str = Field(default="rules", description="Source indicator: rules")


def get_expected_complexity(rec_class: str) -> str:
    """Return expected asymptotic complexity transition text."""
    return EXPECTED_COMPLEXITY.get(rec_class, "Unchanged")


def get_current_algorithm_name(pattern_id: Optional[str]) -> str:
    """Return human-readable current algorithm name."""
    if not pattern_id:
        return "current_implementation"
    return CURRENT_ALGORITHM_NAMES.get(pattern_id, pattern_id.lower())


def evaluate_rules(
    bottleneck: Optional[Bottleneck] = None,
    features: Optional[FeatureVector] = None,
    function: Optional[Function] = None,
) -> RuleRecommendation:
    """Deterministic rule-based recommendation with workload gating.
    
    Workload gating rules:
    - input_size < 50: keep_current (overhead exceeds asymptotic savings)
    - lookup_freq_level == 0 (LOW) for membership/lookup: keep_current
    - No pattern detected (code == -1): keep_current
    """
    # 1. Determine primary pattern ID
    pattern_id: Optional[str] = None
    if features is not None and features.current_algorithm_code in CODE_TO_PATTERN:
        pattern_id = CODE_TO_PATTERN[features.current_algorithm_code]
    elif function and function.patterns:
        for p in function.patterns:
            pid = p.get("pattern_id") if isinstance(p, dict) else str(p)
            if pid in PATTERN_TO_CLASS:
                pattern_id = pid
                break

    # 2. Extract workload metrics
    input_size = 100.0
    lookup_level = 1
    if features is not None:
        input_size = 10.0 ** features.input_size_log10
        lookup_level = features.lookup_freq_level
    elif bottleneck and isinstance(bottleneck.evidence, dict):
        workload = bottleneck.evidence.get("workload", {})
        input_size = float(workload.get("input_size", 100.0))
        freq_str = workload.get("lookup_frequency", "MEDIUM")
        lookup_level = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERY_HIGH": 3}.get(freq_str, 1)

    current_alg = get_current_algorithm_name(pattern_id)

    # 3. Workload gating: No anti-pattern detected
    if not pattern_id or pattern_id not in PATTERN_TO_CLASS:
        return RuleRecommendation(
            current_algorithm=current_alg,
            recommended_algorithm="keep_current",
            expected_complexity="Unchanged",
            confidence=0.98,
            alternatives=[],
            reason="No performance anti-pattern detected. The current implementation is optimal for this workload.",
            source="rules",
        )

    candidate_class = PATTERN_TO_CLASS[pattern_id]

    # 4. Workload gating: Small-n threshold (input_size < 50)
    if input_size < 50:
        return RuleRecommendation(
            current_algorithm=current_alg,
            recommended_algorithm="keep_current",
            expected_complexity=f"O({int(input_size)}) -> O({int(input_size)})",
            confidence=0.92,
            alternatives=[candidate_class],
            reason=(
                f"Workload input size ({int(input_size)}) is below threshold 50. "
                f"Data structure conversion overhead outweighs asymptotic benefits."
            ),
            source="rules",
        )

    # 5. Workload gating: Low lookup frequency for set/index structures
    if candidate_class in ("hash_set", "hash_map_index") and lookup_level == 0:
        return RuleRecommendation(
            current_algorithm=current_alg,
            recommended_algorithm="keep_current",
            expected_complexity="Unchanged",
            confidence=0.90,
            alternatives=[candidate_class],
            reason=(
                f"Workload lookup frequency is LOW. Building a {candidate_class} index "
                f"is not amortized by the sparse lookup queries."
            ),
            source="rules",
        )

    # 6. Definitive match
    complexity_text = get_expected_complexity(candidate_class)
    alternatives = CLASS_ALTERNATIVES.get(candidate_class, ["keep_current"])

    reasons_map = {
        "hash_set": (
            f"Detected LINEAR_MEMBERSHIP_IN_LOOP on input size {int(input_size)}. "
            f"Converting list to hash set reduces membership check complexity from O(n) to O(1) average."
        ),
        "hash_map_index": (
            f"Detected NESTED_LOOP_LOOKUP on input size {int(input_size)}. "
            f"Pre-indexing key-value entries reduces join complexity from O(n * m) to O(n + m)."
        ),
        "min_max_builtin_or_heap": (
            f"Detected REPEATED_SORT_FOR_EXTREME on input size {int(input_size)}. "
            f"Replacing full sort with min()/max() or heap eliminates unnecessary O(n log n) sorting."
        ),
        "list_join": (
            f"Detected STRING_CONCAT_IN_LOOP across {int(input_size)} items. "
            f"Using str.join() eliminates repeated string buffer reallocations, reducing complexity to O(n)."
        ),
        "memoization_lru": (
            "Detected NAIVE_RECURSION with exponential branching. "
            "Applying functools.lru_cache memoizes subproblems, reducing complexity from O(2^n) to O(n)."
        ),
        "deque": (
            f"Detected LIST_POP_FRONT on queue of {int(input_size)} elements. "
            f"Using collections.deque.popleft() replaces O(n) element shifts with O(1) pointer updates."
        ),
    }

    reason_text = reasons_map.get(
        candidate_class,
        f"Recommended {candidate_class} for pattern {pattern_id} ({complexity_text})."
    )

    return RuleRecommendation(
        current_algorithm=current_alg,
        recommended_algorithm=candidate_class,
        expected_complexity=complexity_text,
        confidence=0.95,
        alternatives=alternatives,
        reason=reason_text,
        source="rules",
    )
