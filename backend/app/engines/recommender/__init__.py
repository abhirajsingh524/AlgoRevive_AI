"""AlgoRevive AI Recommender Engine package."""

from app.engines.recommender.datastructures import (
    CombinedRecommendation,
    DataStructureRecommendation,
    RecommendationEngine,
    recommend_data_structure,
)
from app.engines.recommender.ml import MLRecommendation, predict_recommendation
from app.engines.recommender.rules import (
    RuleRecommendation,
    evaluate_rules,
    get_expected_complexity,
)

__all__ = [
    "CombinedRecommendation",
    "DataStructureRecommendation",
    "MLRecommendation",
    "RecommendationEngine",
    "RuleRecommendation",
    "evaluate_rules",
    "get_expected_complexity",
    "predict_recommendation",
    "recommend_data_structure",
]
