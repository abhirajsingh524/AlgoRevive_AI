"""ML Recommendation Engine with lazy loading, pattern masking, and fallback.

Conforms to Contract G3/G4:
- Lazily loads trained ML model artifact and metadata
- Predicts class probabilities over 12-dimensional FeatureVector
- Enforces strict pattern-compatibility masking so unrelated algorithms can never be suggested
- Falls back to rule-based engine if model is missing, fails to load, or confidence < 0.50
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import joblib
import pandas as pd
from pydantic import BaseModel, Field

from app.engines.recommender.rules import (
    CODE_TO_PATTERN,
    evaluate_rules,
    get_current_algorithm_name,
    get_expected_complexity,
)
from app.engines.workload.features import FeatureVector
from app.models.bottleneck import Bottleneck
from app.models.function import Function

FEATURE_COLUMNS = list(FeatureVector.model_fields.keys())

logger = logging.getLogger("recommender.ml")

# Mapping from Contract G3 pattern ID to compatible Contract G4 recommendation classes
PATTERN_COMPATIBLE_CLASSES: Dict[str, Set[str]] = {
    "LINEAR_MEMBERSHIP_IN_LOOP": {"hash_set", "keep_current"},
    "NESTED_LOOP_LOOKUP": {"hash_map_index", "hash_set", "keep_current"},
    "REPEATED_SORT_FOR_EXTREME": {"min_max_builtin_or_heap", "keep_current"},
    "STRING_CONCAT_IN_LOOP": {"list_join", "keep_current"},
    "NAIVE_RECURSION": {"memoization_lru", "keep_current"},
    "LIST_POP_FRONT": {"deque", "keep_current"},
}

_CACHED_MODEL_ARTIFACT: Optional[Any] = None
_CACHED_METADATA: Optional[Dict[str, Any]] = None
_MODEL_LOAD_ATTEMPTED: bool = False


def reset_model_cache() -> None:
    """Reset model cache (used for testing fallback when artifact is removed)."""
    global _CACHED_MODEL_ARTIFACT, _CACHED_METADATA, _MODEL_LOAD_ATTEMPTED
    _CACHED_MODEL_ARTIFACT = None
    _CACHED_METADATA = None
    _MODEL_LOAD_ATTEMPTED = False


def locate_model_paths() -> Tuple[Optional[Path], Optional[Path]]:
    """Locate recommender.joblib and metadata.json across repo directories."""
    current_dir = Path(__file__).resolve().parent
    candidates = [
        # Standard backend layout: backend/app/engines/recommender -> backend/ml/models
        current_dir.parent.parent.parent / "ml" / "models",
        # Alternate root layout
        current_dir.parent.parent.parent.parent / "backend" / "ml" / "models",
        Path("backend/ml/models").resolve(),
        Path("ml/models").resolve(),
    ]

    for c in candidates:
        model_file = c / "recommender.joblib"
        meta_file = c / "metadata.json"
        if model_file.exists():
            return model_file, meta_file if meta_file.exists() else None

    return None, None


def load_model_and_metadata() -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """Lazily loads recommender artifact and metadata, caching them in memory."""
    global _CACHED_MODEL_ARTIFACT, _CACHED_METADATA, _MODEL_LOAD_ATTEMPTED

    if _MODEL_LOAD_ATTEMPTED:
        return _CACHED_MODEL_ARTIFACT, _CACHED_METADATA

    _MODEL_LOAD_ATTEMPTED = True
    model_path, meta_path = locate_model_paths()

    if not model_path or not model_path.exists():
        logger.warning("Recommender model file not found at candidates. Fallback to rules active.")
        return None, None

    try:
        artifact = joblib.load(model_path)
        _CACHED_MODEL_ARTIFACT = artifact
        logger.info(f"Loaded recommender model from {model_path}")
    except Exception as e:
        logger.warning(f"Failed to load recommender model from {model_path}: {e}. Fallback to rules active.")
        return None, None

    if meta_path and meta_path.exists():
        try:
            import json
            with open(meta_path, "r", encoding="utf-8") as f:
                _CACHED_METADATA = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read metadata from {meta_path}: {e}")

    return _CACHED_MODEL_ARTIFACT, _CACHED_METADATA


class MLRecommendation(BaseModel):
    """Result of ML recommendation engine."""

    current_algorithm: str = Field(..., description="Current detected algorithm name")
    recommended_algorithm: str = Field(..., description="Recommended Contract G4 class")
    expected_complexity: str = Field(..., description="Complexity transition e.g. O(n*m) -> O(n+m)")
    confidence: float = Field(..., description="Prediction confidence score 0.0 - 1.0")
    alternatives: List[str] = Field(default_factory=list, description="Ranked compatible alternative classes")
    reason: str = Field(..., description="Recommendation rationale")
    source: str = Field(default="ml", description="Source indicator: ml or rules")
    class_probabilities: Dict[str, float] = Field(
        default_factory=dict, description="Normalized probability distribution over classes"
    )


def predict_recommendation(
    bottleneck: Optional[Bottleneck] = None,
    features: Optional[FeatureVector] = None,
    function: Optional[Function] = None,
    min_confidence: float = 0.50,
) -> MLRecommendation:
    """Predict recommended algorithm using ML model with pattern masking and rule fallback."""
    # 1. Ensure FeatureVector exists
    if features is None:
        if bottleneck is not None:
            from app.engines.workload.features import build_feature_vector
            features = build_feature_vector(bottleneck, function=function)
        else:
            rule_rec = evaluate_rules(bottleneck=bottleneck, features=features, function=function)
            return MLRecommendation(
                current_algorithm=rule_rec.current_algorithm,
                recommended_algorithm=rule_rec.recommended_algorithm,
                expected_complexity=rule_rec.expected_complexity,
                confidence=rule_rec.confidence,
                alternatives=rule_rec.alternatives,
                reason=rule_rec.reason,
                source="rules",
            )

    # 2. Identify primary detected pattern and compatible classes
    p_code = features.current_algorithm_code
    pattern_id = CODE_TO_PATTERN.get(p_code)
    current_alg = get_current_algorithm_name(pattern_id)
    compatible_classes = PATTERN_COMPATIBLE_CLASSES.get(pattern_id or "", {"keep_current"})

    # 3. Attempt lazy model loading
    artifact, metadata = load_model_and_metadata()
    if artifact is None:
        logger.info("Model artifact unavailable. Falling back to rule-based engine.")
        rule_rec = evaluate_rules(bottleneck=bottleneck, features=features, function=function)
        return MLRecommendation(
            current_algorithm=rule_rec.current_algorithm,
            recommended_algorithm=rule_rec.recommended_algorithm,
            expected_complexity=rule_rec.expected_complexity,
            confidence=rule_rec.confidence,
            alternatives=rule_rec.alternatives,
            reason=rule_rec.reason,
            source="rules",
        )

    # 4. Extract model estimator and classes
    if isinstance(artifact, dict):
        estimator = artifact.get("model")
        classes = artifact.get("classes", [])
    else:
        estimator = artifact
        classes = list(getattr(artifact, "classes_", []))

    if not classes and metadata and "classes" in metadata:
        classes = metadata["classes"]

    # 5. Build input dataframe in exact FEATURE_COLUMNS order
    row_dict = {col: getattr(features, col) for col in FEATURE_COLUMNS}
    X_df = pd.DataFrame([row_dict], columns=FEATURE_COLUMNS)

    # 6. Predict raw probabilities
    try:
        raw_probs = estimator.predict_proba(X_df)[0]
    except Exception as e:
        logger.warning(f"Model predict_proba failed: {e}. Falling back to rules.")
        rule_rec = evaluate_rules(bottleneck=bottleneck, features=features, function=function)
        return MLRecommendation(
            current_algorithm=rule_rec.current_algorithm,
            recommended_algorithm=rule_rec.recommended_algorithm,
            expected_complexity=rule_rec.expected_complexity,
            confidence=rule_rec.confidence,
            alternatives=rule_rec.alternatives,
            reason=rule_rec.reason,
            source="rules",
        )

    # 7. Apply Pattern-Compatibility Mask
    # Mask out any class not compatible with detected pattern so unrelated classes are never recommended
    masked_probs: Dict[str, float] = {}
    for c_idx, c_name in enumerate(classes):
        prob = float(raw_probs[c_idx])
        if c_name in compatible_classes:
            masked_probs[c_name] = max(0.0, prob)
        else:
            masked_probs[c_name] = 0.0

    total_prob = sum(masked_probs.values())
    if total_prob > 1e-9:
        normalized_probs = {c: round(p / total_prob, 5) for c, p in masked_probs.items()}
    else:
        # Fallback to keep_current if all compatible classes had zero probability
        normalized_probs = {c: (1.0 if c == "keep_current" else 0.0) for c in compatible_classes}

    # 8. Rank compatible classes by probability
    ranked_classes = sorted(
        [(c, p) for c, p in normalized_probs.items() if c in compatible_classes],
        key=lambda x: x[1],
        reverse=True,
    )

    top_class, top_confidence = ranked_classes[0]

    # 9. Low-confidence fallback: if confidence < min_confidence (0.50), fall back to rules
    if top_confidence < min_confidence:
        logger.info(
            f"Prediction confidence {top_confidence:.3f} < {min_confidence}. Falling back to rules."
        )
        rule_rec = evaluate_rules(bottleneck=bottleneck, features=features, function=function)
        return MLRecommendation(
            current_algorithm=rule_rec.current_algorithm,
            recommended_algorithm=rule_rec.recommended_algorithm,
            expected_complexity=rule_rec.expected_complexity,
            confidence=rule_rec.confidence,
            alternatives=rule_rec.alternatives,
            reason=rule_rec.reason,
            source="rules",
            class_probabilities=normalized_probs,
        )

    # 10. Construct ML recommendation
    expected_complexity = get_expected_complexity(top_class)
    alternatives = [c for c, p in ranked_classes[1:] if p > 0.01 and c != top_class]

    # Generated plain rationale citing pattern and predicted class
    input_size_n = int(round(10.0 ** features.input_size_log10))
    if top_class == "keep_current":
        reason_text = (
            f"ML model recommends retaining current implementation for input size {input_size_n}. "
            f"Workload characteristics do not justify replacement overhead."
        )
    else:
        reason_text = (
            f"ML model recommends {top_class} for {pattern_id} with {round(top_confidence * 100, 1)}% confidence. "
            f"Expected complexity transition: {expected_complexity}."
        )

    return MLRecommendation(
        current_algorithm=current_alg,
        recommended_algorithm=top_class,
        expected_complexity=expected_complexity,
        confidence=round(top_confidence, 4),
        alternatives=alternatives,
        reason=reason_text,
        source="ml",
        class_probabilities=normalized_probs,
    )
