"""Deterministic Optimization Templates (Contract G3)."""

from app.engines.optimizer.templates.base import (
    ALLOWED_MODULES,
    GuardResult,
    Template,
    TemplateResult,
    check_only_target_changed,
    compute_changed_lines,
    generate_unified_diff,
    run_shared_guards,
    signatures_equal,
)

__all__ = [
    "ALLOWED_MODULES",
    "GuardResult",
    "Template",
    "TemplateResult",
    "check_only_target_changed",
    "compute_changed_lines",
    "generate_unified_diff",
    "run_shared_guards",
    "signatures_equal",
]
