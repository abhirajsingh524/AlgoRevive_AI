"""Deterministic Optimization Templates (Contract G3)."""

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

__all__ = [
    "ALLOWED_MODULES",
    "GuardResult",
    "Template",
    "TemplateResult",
    "T1SetMembershipTemplate",
    "T2DictIndexJoinTemplate",
    "check_only_target_changed",
    "compute_changed_lines",
    "find_target_function_cst",
    "generate_unified_diff",
    "run_shared_guards",
    "signatures_equal",
]
