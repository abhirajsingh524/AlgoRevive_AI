"""Data Structure Recommendation Engine and Combined Recommendation Engine.

Provides workload-aware data structure mapping:
- Repeated membership -> List to Set/Hash
- Repeated linear search -> Nested list to Indexed Dict
- Priority/extreme queries -> List to Heap (heapq)
- FIFO queue -> List to collections.deque
- LIFO stack -> List stack
- String building -> str concat to list buffer + str.join

Combines algorithm and data structure recommendations into a unified
RecommendationEngine.recommend(bottleneck, features).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.engines.recommender.explain import explain_prediction
from app.engines.recommender.ml import load_model_and_metadata, predict_recommendation
from app.engines.recommender.rules import CODE_TO_PATTERN
from app.engines.workload.features import FeatureVector, build_feature_vector
from app.models.bottleneck import Bottleneck
from app.models.function import Function

logger = logging.getLogger("recommender.datastructures")


class DataStructureRecommendation(BaseModel):
    """Workload-aware data structure recommendation."""

    current_structure: str = Field(..., description="Current data structure used in bottleneck")
    recommended_structure: str = Field(..., description="Target recommended data structure")
    workload_reason: str = Field(..., description="Workload-specific rationale for data structure choice")


def recommend_data_structure(
    bottleneck: Optional[Bottleneck] = None,
    features: Optional[FeatureVector] = None,
    function: Optional[Function] = None,
) -> DataStructureRecommendation:
    """Recommend optimal data structure based on detected pattern and workload characteristics."""
    if features is None and bottleneck is not None:
        features = build_feature_vector(bottleneck, function=function)

    p_code = features.current_algorithm_code if features is not None else -1
    pattern_id = CODE_TO_PATTERN.get(p_code)

    input_size = 100
    lookup_level = 1
    if features is not None:
        input_size = int(round(10.0 ** features.input_size_log10))
        lookup_level = features.lookup_freq_level
    elif bottleneck and isinstance(bottleneck.evidence, dict):
        workload = bottleneck.evidence.get("workload", {})
        input_size = int(workload.get("input_size", 100))
        freq_str = workload.get("lookup_frequency", "MEDIUM")
        lookup_level = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERY_HIGH": 3}.get(freq_str, 1)

    # 1. LINEAR_MEMBERSHIP_IN_LOOP -> List to Set/Hash
    if pattern_id == "LINEAR_MEMBERSHIP_IN_LOOP":
        if input_size < 50 or lookup_level == 0:
            return DataStructureRecommendation(
                current_structure="list",
                recommended_structure="list",
                workload_reason=(
                    f"Workload input size ({input_size}) or lookup frequency is low; "
                    f"retaining list avoids set creation and hashing overhead."
                ),
            )
        return DataStructureRecommendation(
            current_structure="list",
            recommended_structure="set",
            workload_reason=(
                f"Workload performs repeated membership queries across {input_size} items. "
                f"Replacing list with a hash set provides O(1) average lookup time."
            ),
        )

    # 2. NESTED_LOOP_LOOKUP -> List of Dicts to Indexed Dict
    elif pattern_id == "NESTED_LOOP_LOOKUP":
        if input_size < 50:
            return DataStructureRecommendation(
                current_structure="list",
                recommended_structure="list",
                workload_reason=f"Small input size ({input_size}) does not warrant secondary dictionary indexing.",
            )
        return DataStructureRecommendation(
            current_structure="list",
            recommended_structure="indexed dict",
            workload_reason=(
                "Workload performs join queries between collections. Pre-indexing entries "
                "into a dict by join key provides O(1) direct record lookup."
            ),
        )

    # 3. REPEATED_SORT_FOR_EXTREME -> List to Heap / Min-Max
    elif pattern_id == "REPEATED_SORT_FOR_EXTREME":
        return DataStructureRecommendation(
            current_structure="list (repeatedly sorted)",
            recommended_structure="heap (heapq) / min-max",
            workload_reason=(
                f"Workload repeatedly extracts extreme values from {input_size} items. "
                f"A min/max builtin or binary heap tracks extremes without O(n log n) full sorts."
            ),
        )

    # 4. STRING_CONCAT_IN_LOOP -> str to list buffer
    elif pattern_id == "STRING_CONCAT_IN_LOOP":
        return DataStructureRecommendation(
            current_structure="str (repeated concatenation)",
            recommended_structure="list of strings (str.join)",
            workload_reason=(
                f"Workload concatenates {input_size} string pieces. Accumulating in a list buffer "
                f"and joining once eliminates repeated string memory reallocations."
            ),
        )

    # 5. NAIVE_RECURSION -> Call Stack to LRU Cache
    elif pattern_id == "NAIVE_RECURSION":
        return DataStructureRecommendation(
            current_structure="call stack (unmemoized)",
            recommended_structure="functools.lru_cache (memoized dict)",
            workload_reason=(
                "Recursive branching generates redundant overlapping subproblems. "
                "An LRU cache dictionary stores computed results in O(1) hash table."
            ),
        )

    # 6. LIST_POP_FRONT -> List (FIFO) to collections.deque
    elif pattern_id == "LIST_POP_FRONT":
        return DataStructureRecommendation(
            current_structure="list (FIFO queue)",
            recommended_structure="collections.deque",
            workload_reason=(
                f"Workload drains queue from the head ({input_size} items). collections.deque "
                f"provides O(1) popleft() without shifting remaining elements in memory."
            ),
        )

    # 7. Control / Default
    return DataStructureRecommendation(
        current_structure="list",
        recommended_structure="list (unchanged)",
        workload_reason=(
            "Current data structure is optimal for linear traversal with zero conversion overhead."
        ),
    )


class CombinedRecommendation(BaseModel):
    """Complete recommendation combining algorithm, data structure, and complexity."""

    current_algorithm: str = Field(..., description="Current detected algorithm name")
    recommended_algorithm: str = Field(..., description="Recommended Contract G4 class")
    expected_complexity: str = Field(..., description="Expected asymptotic complexity change")
    confidence: float = Field(..., description="Overall confidence score 0.0 - 1.0")
    alternatives: List[str] = Field(default_factory=list, description="Alternative algorithm classes")
    reason: str = Field(..., description="Comprehensive recommendation rationale")
    source: str = Field(default="rules", description="Source of recommendation: ml or rules")
    data_structure: DataStructureRecommendation = Field(
        ..., description="Data structure recommendation"
    )
    feature_importance: Optional[Any] = Field(
        default=None, description="Per-feature importance dictionary or list"
    )
    class_probabilities: Dict[str, float] = Field(
        default_factory=dict, description="Class probability distribution"
    )


class RecommendationEngine:
    """Unified Recommendation Engine combining Algorithm and Data Structure recommendations."""

    @classmethod
    def recommend(
        cls,
        bottleneck: Bottleneck,
        features: Optional[FeatureVector] = None,
        function: Optional[Function] = None,
    ) -> CombinedRecommendation:
        """Produce unified recommendation for a bottleneck."""
        if features is None:
            features = build_feature_vector(bottleneck, function=function)

        # 1. Algorithm recommendation (ML with rule fallback)
        algo_rec = predict_recommendation(
            bottleneck=bottleneck, features=features, function=function
        )

        # 2. Data structure recommendation
        ds_rec = recommend_data_structure(
            bottleneck=bottleneck, features=features, function=function
        )

        # 3. Per-prediction feature importance & plain-English explanation
        artifact, metadata = load_model_and_metadata()
        ranked_importances, reason_sentence = explain_prediction(
            features=features,
            recommended_class=algo_rec.recommended_algorithm,
            model_artifact=artifact,
            metadata=metadata,
        )

        # 4. Combine explanations
        combined_reason = f"{reason_sentence} Recommended structure: {ds_rec.recommended_structure} ({ds_rec.workload_reason})"

        return CombinedRecommendation(
            current_algorithm=algo_rec.current_algorithm,
            recommended_algorithm=algo_rec.recommended_algorithm,
            expected_complexity=algo_rec.expected_complexity,
            confidence=algo_rec.confidence,
            alternatives=algo_rec.alternatives,
            reason=combined_reason,
            source=algo_rec.source,
            data_structure=ds_rec,
            feature_importance=ranked_importances,
            class_probabilities=algo_rec.class_probabilities,
        )
