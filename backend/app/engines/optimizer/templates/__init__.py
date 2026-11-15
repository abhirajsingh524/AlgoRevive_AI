"""Deterministic Optimization Templates (Contract G3)."""

from typing import Dict, Optional, Type

from app.engines.optimizer.templates.base import (
    ALLOWED_MODULES,
    GuardResult,
    Template,
    TemplateResult,
    check_only_target_changed,
    compute_changed_lines,
    find_target_function_cst,
    generate_unified_diff,
    run_shared_guards,
    signatures_equal,
)
from app.engines.optimizer.templates.t1_set_membership import T1SetMembershipTemplate
from app.engines.optimizer.templates.t2_dict_index_join import T2DictIndexJoinTemplate
from app.engines.optimizer.templates.t3_min_max_heap import T3MinMaxHeapTemplate
from app.engines.optimizer.templates.t4_join_strings import T4JoinStringsTemplate
from app.engines.optimizer.templates.t5_lru_cache import T5LruCacheTemplate
from app.engines.optimizer.templates.t6_deque_popleft import T6DequePopleftTemplate

# 1:1 Mapping according to Contract G3
TEMPLATES: Dict[str, Type[Template]] = {
    "T1_SET_MEMBERSHIP": T1SetMembershipTemplate,
    "T2_DICT_INDEX_JOIN": T2DictIndexJoinTemplate,
    "T3_MIN_MAX_HEAP": T3MinMaxHeapTemplate,
    "T4_JOIN_STRINGS": T4JoinStringsTemplate,
    "T5_LRU_CACHE": T5LruCacheTemplate,
    "T6_DEQUE_POPLEFT": T6DequePopleftTemplate,
}

# Mapping from Contract G4 recommendation class to Contract G3 template ID
CLASS_TO_TEMPLATE: Dict[str, str] = {
    "hash_set": "T1_SET_MEMBERSHIP",
    "hash_map_index": "T2_DICT_INDEX_JOIN",
    "min_max_builtin_or_heap": "T3_MIN_MAX_HEAP",
    "list_join": "T4_JOIN_STRINGS",
    "memoization_lru": "T5_LRU_CACHE",
    "deque": "T6_DEQUE_POPLEFT",
}

# Mapping from Contract G3 pattern ID to template ID
PATTERN_TO_TEMPLATE: Dict[str, str] = {
    "LINEAR_MEMBERSHIP_IN_LOOP": "T1_SET_MEMBERSHIP",
    "NESTED_LOOP_LOOKUP": "T2_DICT_INDEX_JOIN",
    "REPEATED_SORT_FOR_EXTREME": "T3_MIN_MAX_HEAP",
    "STRING_CONCAT_IN_LOOP": "T4_JOIN_STRINGS",
    "NAIVE_RECURSION": "T5_LRU_CACHE",
    "LIST_POP_FRONT": "T6_DEQUE_POPLEFT",
}


def get_template(template_id: str) -> Optional[Template]:
    """Retrieve an instantiated Template by its Contract G3 ID."""
    cls = TEMPLATES.get(template_id)
    if cls:
        return cls()
    return None


__all__ = [
    "ALLOWED_MODULES",
    "CLASS_TO_TEMPLATE",
    "GuardResult",
    "PATTERN_TO_TEMPLATE",
    "TEMPLATES",
    "Template",
    "TemplateResult",
    "T1SetMembershipTemplate",
    "T2DictIndexJoinTemplate",
    "T3MinMaxHeapTemplate",
    "T4JoinStringsTemplate",
    "T5LruCacheTemplate",
    "T6DequePopleftTemplate",
    "check_only_target_changed",
    "compute_changed_lines",
    "find_target_function_cst",
    "generate_unified_diff",
    "get_template",
    "run_shared_guards",
    "signatures_equal",
]
