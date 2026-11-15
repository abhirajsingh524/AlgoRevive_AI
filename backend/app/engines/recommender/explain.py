"""Explainability Engine for ML & Rule Recommendations.

Computes per-prediction feature importance using SHAP TreeExplainer when available,
falling back to global feature importances scaled by feature deviation from training mean.
Produces a ranked, normalized list (summing to ~1.0) and generates a plain-English
reason sentence citing top factors with their real, human-readable values.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.engines.recommender.rules import CODE_TO_PATTERN
from app.engines.workload.features import FeatureVector

FEATURE_COLUMNS = list(FeatureVector.model_fields.keys())

logger = logging.getLogger("recommender.explain")

FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    "input_size_log10": "Input Size (N)",
    "current_algorithm_code": "Detected Pattern",
    "current_complexity_rank": "Asymptotic Complexity",
    "lookup_freq_level": "Lookup Frequency",
    "insert_ratio": "Insert Ratio",
    "delete_ratio": "Delete Ratio",
    "read_write_ratio": "Read/Write Ratio",
    "data_distribution_code": "Data Distribution",
    "memory_constraint_level": "Memory Constraint",
    "latency_requirement_level": "Latency Requirement",
    "call_count_log10": "Call Count",
    "runtime_pct": "Runtime Contribution",
}

LOOKUP_LEVEL_NAMES = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "VERY_HIGH"}
DISTRIBUTION_NAMES = {0: "uniform", 1: "sorted", 2: "skewed"}
MEMORY_LEVEL_NAMES = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}
LATENCY_LEVEL_NAMES = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "VERY_HIGH"}
COMPLEXITY_RANK_NAMES = {
    0: "O(1)",
    1: "O(log n)",
    2: "O(n)",
    3: "O(n log n)",
    4: "O(n^2)",
    5: "O(n^3)",
    6: "O(2^n)",
}


def format_feature_real_value(feature_name: str, value: float) -> str:
    """Format raw feature value into human-readable real value."""
    if feature_name == "input_size_log10":
        n = int(round(10.0 ** value))
        return f"{n:,} items" if n >= 1000 else f"{n} items"
    elif feature_name == "current_algorithm_code":
        code = int(round(value))
        return CODE_TO_PATTERN.get(code, "None/Control")
    elif feature_name == "current_complexity_rank":
        rank = int(round(value))
        return COMPLEXITY_RANK_NAMES.get(rank, f"Rank {rank}")
    elif feature_name == "lookup_freq_level":
        lvl = int(round(value))
        return f"{LOOKUP_LEVEL_NAMES.get(lvl, 'MEDIUM')}"
    elif feature_name in ("insert_ratio", "delete_ratio"):
        return f"{value * 100:.1f}%"
    elif feature_name == "read_write_ratio":
        return f"{value:.1f}:1"
    elif feature_name == "data_distribution_code":
        dist = int(round(value))
        return DISTRIBUTION_NAMES.get(dist, "uniform")
    elif feature_name == "memory_constraint_level":
        lvl = int(round(value))
        return MEMORY_LEVEL_NAMES.get(lvl, "MEDIUM")
    elif feature_name == "latency_requirement_level":
        lvl = int(round(value))
        return LATENCY_LEVEL_NAMES.get(lvl, "MEDIUM")
    elif feature_name == "call_count_log10":
        calls = int(round(10.0 ** value - 1.0))
        return f"{calls:,} calls" if calls >= 1000 else f"{calls} calls"
    elif feature_name == "runtime_pct":
        return f"{value * 100:.1f}% of total runtime"
    return f"{value:.3f}"


def generate_reason_sentence(
    ranked_importances: List[Dict[str, Any]],
    recommended_algorithm: str,
) -> str:
    """Generate plain-English reason sentence citing top factors with real values."""
    if not ranked_importances:
        return f"Recommended {recommended_algorithm} based on workload analysis."

    top_factors = ranked_importances[:3]
    parts: List[str] = []
    for f in top_factors:
        dname = f["display_name"]
        fval = f["formatted_value"]
        imp_pct = round(f["importance"] * 100, 1)
        parts.append(f"{dname} ({fval}, {imp_pct}%)")

    top_phrase = ", ".join(parts[:-1]) + f", and {parts[-1]}" if len(parts) > 1 else parts[0]
    return f"Recommendation of {recommended_algorithm} is driven primarily by: {top_phrase}."


def explain_prediction(
    features: FeatureVector,
    recommended_class: str,
    model_artifact: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Compute normalized per-prediction feature importance and plain-English reason."""
    row_dict = {col: getattr(features, col) for col in FEATURE_COLUMNS}
    X_df = pd.DataFrame([row_dict], columns=FEATURE_COLUMNS)

    importances_raw: Optional[np.ndarray] = None

    # 1. Try SHAP TreeExplainer
    if model_artifact is not None:
        try:
            import shap
            estimator = model_artifact.get("model") if isinstance(model_artifact, dict) else model_artifact
            classes = model_artifact.get("classes", []) if isinstance(model_artifact, dict) else list(getattr(model_artifact, "classes_", []))
            if not classes and metadata and "classes" in metadata:
                classes = metadata["classes"]

            explainer = shap.TreeExplainer(estimator)
            sv = explainer(X_df)

            # sv.values has shape (1, n_features, n_classes) or (1, n_features)
            if hasattr(sv, "values") and len(sv.values.shape) == 3:
                if recommended_class in classes:
                    c_idx = classes.index(recommended_class)
                    importances_raw = np.abs(sv.values[0, :, c_idx])
                else:
                    importances_raw = np.mean(np.abs(sv.values[0, :, :]), axis=1)
            elif hasattr(sv, "values") and len(sv.values.shape) == 2:
                importances_raw = np.abs(sv.values[0, :])
        except Exception as e:
            logger.debug(f"SHAP TreeExplainer unavailable or raised: {e}. Using deviation fallback.")

    # 2. Fallback: Global feature importances scaled by feature deviation from training mean
    if importances_raw is None or np.sum(importances_raw) < 1e-9:
        global_imps: Dict[str, float] = {}
        means: Dict[str, float] = {}
        stds: Dict[str, float] = {}

        if metadata:
            global_imps = metadata.get("feature_importances", {})
            means = metadata.get("feature_means", {})
            stds = metadata.get("feature_stds", {})

        scaled_values: List[float] = []
        for col in FEATURE_COLUMNS:
            g_imp = global_imps.get(col, 1.0 / len(FEATURE_COLUMNS))
            mean_val = means.get(col, 0.0)
            std_val = max(1e-5, stds.get(col, 1.0))
            cur_val = float(row_dict[col])
            z_score = abs(cur_val - mean_val) / std_val
            # Weight global importance by deviation from typical distribution
            scaled_values.append(g_imp * (1.0 + z_score))

        importances_raw = np.array(scaled_values)

    # 3. Normalize importances so sum is ~1.0
    total = float(np.sum(importances_raw))
    if total > 1e-9:
        normalized = importances_raw / total
    else:
        normalized = np.ones(len(FEATURE_COLUMNS)) / len(FEATURE_COLUMNS)

    # 4. Build ranked feature list
    ranked_items: List[Dict[str, Any]] = []
    for i, col in enumerate(FEATURE_COLUMNS):
        imp = float(round(normalized[i], 4))
        raw_val = float(row_dict[col])
        ranked_items.append(
            {
                "feature": col,
                "display_name": FEATURE_DISPLAY_NAMES.get(col, col),
                "importance": imp,
                "value": raw_val,
                "formatted_value": format_feature_real_value(col, raw_val),
            }
        )

    # Sort descending by importance
    ranked_items.sort(key=lambda x: x["importance"], reverse=True)

    # Ensure sum is strictly ~1.0
    sum_imps = sum(item["importance"] for item in ranked_items)
    if abs(sum_imps - 1.0) > 0.01 and sum_imps > 0:
        for item in ranked_items:
            item["importance"] = round(item["importance"] / sum_imps, 4)

    # 5. Generate plain-English reason sentence citing top factors with real values
    reason_sentence = generate_reason_sentence(ranked_items, recommended_class)

    return ranked_items, reason_sentence
