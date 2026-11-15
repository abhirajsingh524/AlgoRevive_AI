"""Heuristic Complexity Estimator using Contract G5.

Rules and Heuristics:
1. No loop and no recursion -> O(1) [rank 0, LOW]
2. Single loop or comprehension -> O(n) [rank 2, LOW]
3. sorted() or .sort() outside a loop -> O(n log n) [rank 3, MEDIUM]
4. Loop depth k gives O(n^k):
   - depth 2 -> O(n^2) [rank 4, HIGH]
   - depth >= 3 -> O(n^3) [rank 5, CRITICAL]
5. Sort inside a loop -> O(n^2) at least [rank 4, HIGH], or O(n^(k+1)) if deeper
6. Membership test (`in` / `not in`) against a list-typed name inside a loop adds
   one factor of n (e.g., depth 1 + membership in list -> O(n^2) [rank 4, HIGH]).
   List-like names include variables assigned from list literals, list(), list comprehensions,
   or parameters annotated as List/list or used with list methods/indexing.
7. Recursion:
   - Single recursive self-call -> O(n) [rank 2, LOW]
   - Two or more self-calls without memoization -> O(2^n) [rank 6, CRITICAL]
   - lru_cache or cache decorator removes exponential recursion -> O(n) [rank 2, LOW]

DISCLAIMER:
All results produced by this engine are static heuristic estimates. They represent worst-case
or typical algorithmic complexity bounds inferred through AST pattern matching, not formal proofs
or dynamic execution profiles.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Set

from app.engines.static_analyzer.analyzer import FunctionInfo


@dataclass
class ComplexityEstimate:
    complexity_class: str
    complexity_rank: int
    severity: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "complexity_class": self.complexity_class,
            "complexity_rank": self.complexity_rank,
            "severity": self.severity,
            "reason": self.reason,
        }


RANK_TO_CLASS = {
    0: "O(1)",
    1: "O(log n)",
    2: "O(n)",
    3: "O(n log n)",
    4: "O(n^2)",
    5: "O(n^3)",
    6: "O(2^n)",
}


def rank_to_severity(rank: int) -> str:
    """Contract G5: rank <= 2 LOW, 3 MEDIUM, 4 HIGH, >= 5 CRITICAL."""
    if rank <= 2:
        return "LOW"
    elif rank == 3:
        return "MEDIUM"
    elif rank == 4:
        return "HIGH"
    else:
        return "CRITICAL"


def _walk_non_nested(node: ast.AST):
    """Walk child AST nodes without descending into nested functions or classes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield child
        yield from _walk_non_nested(child)


def _find_list_like_names(fn_node: ast.AST, params: List[Dict[str, Any]]) -> Set[str]:
    """Identify variable and parameter names that behave as lists."""
    list_names: Set[str] = set()

    # 1. Inspect parameters
    for p in params:
        p_name = p.get("name", "")
        ann = (p.get("annotation") or "").lower()
        if "list" in ann:
            list_names.add(p_name)
        elif p_name in ("ids", "items", "values", "elements", "lst", "records"):
            list_names.add(p_name)

    # 2. Inspect local assignments and usage
    for node in _walk_non_nested(fn_node):
        if isinstance(node, ast.Assign):
            # Check if assigned from list literal, list(), or list comp
            is_list_val = False
            if isinstance(node.value, (ast.List, ast.ListComp)):
                is_list_val = True
            elif isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "list":
                    is_list_val = True

            if is_list_val:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        list_names.add(target.id)

        # Check for list method usage (.append, .extend, .pop)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("append", "extend", "pop", "insert"):
                if isinstance(node.func.value, ast.Name):
                    list_names.add(node.func.value.id)

    return list_names


def _has_sort_call(node: ast.AST) -> bool:
    """Check if AST node contains sorted() or .sort() call."""
    for child in _walk_non_nested(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name) and child.func.id == "sorted":
                return True
            if isinstance(child.func, ast.Attribute) and child.func.attr == "sort":
                return True
    return False


def _has_sort_in_loop(fn_node: ast.AST) -> bool:
    """Check if sorted() or .sort() is invoked directly inside any loop."""
    for node in _walk_non_nested(fn_node):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            if _has_sort_call(node):
                return True
    return False


def _has_list_membership_in_loop(fn_node: ast.AST, list_names: Set[str]) -> bool:
    """Check if an `in` or `not in` membership test against a list-like collection occurs in a loop."""
    for node in _walk_non_nested(fn_node):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            for child in _walk_non_nested(node):
                if isinstance(child, ast.Compare):
                    for op, comparator in zip(child.ops, child.comparators):
                        if isinstance(op, (ast.In, ast.NotIn)):
                            # Check if comparator is a known list-like name or literal list
                            if isinstance(comparator, (ast.List, ast.ListComp)):
                                return True
                            if isinstance(comparator, ast.Name) and (
                                comparator.id in list_names or comparator.id.endswith("s")
                            ):
                                return True
                            if isinstance(comparator, ast.Call) and isinstance(comparator.func, ast.Name):
                                if comparator.func.id == "list":
                                    return True
    return False


class ComplexityEstimator:
    """Rule-based asymptotic complexity estimator."""

    def estimate(self, fn_info: FunctionInfo) -> ComplexityEstimate:
        """Estimate asymptotic time complexity for a given function."""
        ast_node = fn_info.ast_node
        metrics = fn_info.metrics
        loop_depth = fn_info.loop_depth
        comprehension_loops = metrics.get("comprehension_loops", 0)
        has_recursion = fn_info.has_recursion
        rec_count = metrics.get("recursive_calls_count", 0)
        decorators = metrics.get("decorators", [])

        # Check for memoization decorators
        is_memoized = any(
            d in ("lru_cache", "cache", "functools.lru_cache", "functools.cache")
            for d in decorators
        )

        # 1. Recursion rules
        rec_rank = 0
        rec_reason = ""
        if has_recursion:
            if rec_count >= 2:
                if is_memoized:
                    rec_rank = 2  # O(n)
                    rec_reason = "Multiple recursive self-calls with memoization decorator -> O(n)"
                else:
                    rec_rank = 6  # O(2^n)
                    rec_reason = "Multiple recursive self-calls without memoization -> O(2^n)"
            else:
                rec_rank = 2  # O(n)
                rec_reason = "Single recursive self-call -> O(n)"

        # 2. Iteration and Loop rules
        loop_rank = 0
        loop_reason = ""
        effective_depth = loop_depth

        list_names: Set[str] = set()
        if ast_node:
            list_names = _find_list_like_names(ast_node, fn_info.params)

        has_sort_inside = _has_sort_in_loop(ast_node) if ast_node else False
        has_membership_inside = (
            _has_list_membership_in_loop(ast_node, list_names) if ast_node else False
        )
        has_sort_anywhere = _has_sort_call(ast_node) if ast_node else False

        if effective_depth == 0 and comprehension_loops == 0:
            if has_sort_anywhere:
                loop_rank = 3  # O(n log n)
                loop_reason = "sorted() or .sort() outside of loops -> O(n log n)"
            else:
                loop_rank = 0  # O(1)
                loop_reason = "No loops and no recursion -> O(1)"
        elif effective_depth == 0 and comprehension_loops > 0:
            loop_rank = 2  # O(n)
            loop_reason = "Comprehension expression -> O(n)"
        else:
            # We have at least 1 loop
            power = effective_depth
            reasons = [f"Loop nesting depth {effective_depth}"]

            if has_sort_inside:
                # Sort inside a loop adds at least n, making it O(n^2) at minimum
                power = max(power + 1, 2)
                reasons.append("sort inside loop adds factor of n (at least O(n^2))")

            if has_membership_inside:
                # Linear membership check inside loop adds one factor of n
                power = power + 1
                reasons.append("linear list membership check inside loop adds factor of n")

            if power == 1:
                loop_rank = 2  # O(n)
                loop_reason = "Single loop -> O(n)"
            elif power == 2:
                loop_rank = 4  # O(n^2)
                loop_reason = "; ".join(reasons) + " -> O(n^2)"
            else:
                loop_rank = 5  # O(n^3) or higher
                loop_reason = "; ".join(reasons) + f" -> O(n^{power})"

        # Determine governing complexity between loop and recursion
        if rec_rank >= loop_rank:
            final_rank = rec_rank
            final_reason = rec_reason or loop_reason
        else:
            final_rank = loop_rank
            final_reason = loop_reason

        complexity_class = RANK_TO_CLASS.get(final_rank, "O(1)")
        severity = rank_to_severity(final_rank)

        return ComplexityEstimate(
            complexity_class=complexity_class,
            complexity_rank=final_rank,
            severity=severity,
            reason=final_reason,
        )
