"""T1_SET_MEMBERSHIP deterministic template (Contract G3).

Pattern: LINEAR_MEMBERSHIP_IN_LOOP
Preconditions:
- A sequence variable is tested with `in` or `not in` inside a loop (for or while).
- The collection variable is ONLY read inside the function (no append/remove/extend/insert/pop/clear or reassignment).
- Elements must be hashable.

Transformation:
- Build a set once before the loop: `<name>_set = set(<name>)`
- Test against `<name>_set` inside the loop.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Optional, Set, Tuple

import libcst as cst

from app.engines.optimizer.templates.base import (
    Template,
    TemplateResult,
    find_target_function_cst,
    run_shared_guards,
)

MUTATING_METHODS: Set[str] = {
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "clear",
}


def _is_name_mutated(fn_ast: ast.FunctionDef | ast.AsyncFunctionDef, var_name: str) -> bool:
    """Check if var_name is reassigned or has mutating methods called on it."""
    for node in ast.walk(fn_ast):
        # Check reassignments (Assign, AugAssign, AnnAssign)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for target_node in ast.walk(target):
                    if isinstance(target_node, ast.Name) and target_node.id == var_name:
                        return True
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            target = getattr(node, "target", None)
            if target and isinstance(target, ast.Name) and target.id == var_name:
                return True
        # Check mutating method calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == var_name:
                    if node.func.attr in MUTATING_METHODS:
                        return True
    return False


def _find_membership_collection_in_loop(
    fn_ast: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Optional[Tuple[str, ast.stmt]]:
    """Find a variable tested with in/not in inside a loop, returning (var_name, loop_stmt)."""
    for loop_node in ast.walk(fn_ast):
        if not isinstance(loop_node, (ast.For, ast.While, ast.AsyncFor)):
            continue

        # Look for Compare nodes inside this loop (but not inside nested inner loops)
        for child in ast.walk(loop_node):
            if child is loop_node:
                continue
            if isinstance(child, ast.Compare):
                for op, comp in zip(child.ops, child.comparators):
                    if isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, ast.Name):
                        col_name = comp.id
                        if not _is_name_mutated(fn_ast, col_name):
                            return col_name, loop_node
    return None


class CSTMembershipTransformer(cst.CSTTransformer):
    """Rewrite CST to insert set conversion before the target loop and update membership checks."""

    def __init__(self, target_var: str, set_var_name: str) -> None:
        self.target_var = target_var
        self.set_var_name = set_var_name
        self.transformed_loop = False
        self.inside_target_loop = False

    def visit_For(self, node: cst.For) -> Optional[bool]:
        # Check if this loop contains the membership test
        for child in ast.walk(ast.parse(cst.Module(body=[node]).code)):
            if isinstance(child, ast.Compare):
                for op, comp in zip(child.ops, child.comparators):
                    if isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, ast.Name) and comp.id == self.target_var:
                        self.inside_target_loop = True
                        return True
        return True

    def leave_For(
        self, orig_node: cst.For, updated_node: cst.For
    ) -> cst.For | cst.FlattenSentinel[cst.BaseStatement]:
        if self.inside_target_loop and not self.transformed_loop:
            self.inside_target_loop = False
            self.transformed_loop = True
            set_stmt = cst.parse_statement(f"{self.set_var_name} = set({self.target_var})\n")
            return cst.FlattenSentinel([set_stmt, updated_node])
        return updated_node

    def visit_While(self, node: cst.While) -> Optional[bool]:
        for child in ast.walk(ast.parse(cst.Module(body=[node]).code)):
            if isinstance(child, ast.Compare):
                for op, comp in zip(child.ops, child.comparators):
                    if isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, ast.Name) and comp.id == self.target_var:
                        self.inside_target_loop = True
                        return True
        return True

    def leave_While(
        self, orig_node: cst.While, updated_node: cst.While
    ) -> cst.While | cst.FlattenSentinel[cst.BaseStatement]:
        if self.inside_target_loop and not self.transformed_loop:
            self.inside_target_loop = False
            self.transformed_loop = True
            set_stmt = cst.parse_statement(f"{self.set_var_name} = set({self.target_var})\n")
            return cst.FlattenSentinel([set_stmt, updated_node])
        return updated_node

    def leave_ComparisonTarget(
        self, orig_node: cst.ComparisonTarget, updated_node: cst.ComparisonTarget
    ) -> cst.ComparisonTarget:
        if (
            isinstance(orig_node.operator, (cst.In, cst.NotIn))
            and isinstance(orig_node.comparator, cst.Name)
            and orig_node.comparator.value == self.target_var
        ):
            return updated_node.with_changes(comparator=cst.Name(self.set_var_name))
        return updated_node


class FunctionScopedTransformer(cst.CSTTransformer):
    """Applies CSTMembershipTransformer only inside the target function."""

    def __init__(self, target_function_name: str, target_var: str, set_var_name: str) -> None:
        self.target_function_name = target_function_name
        self.target_var = target_var
        self.set_var_name = set_var_name

    def leave_FunctionDef(
        self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        if orig_node.name.value == self.target_function_name:
            inner_transformer = CSTMembershipTransformer(self.target_var, self.set_var_name)
            return updated_node.visit(inner_transformer)
        return updated_node


class T1SetMembershipTemplate(Template):
    """T1_SET_MEMBERSHIP: Converts list membership in loop to set lookup."""

    template_id = "T1_SET_MEMBERSHIP"

    def applies(
        self,
        function_node: cst.FunctionDef,
        pattern_match: Optional[Dict[str, Any]] = None,
    ) -> bool:
        fn_code = cst.Module(body=[function_node]).code
        try:
            tree = ast.parse(fn_code)
            fn_ast = tree.body[0]
            if not isinstance(fn_ast, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
        except Exception:
            return False

        found = _find_membership_collection_in_loop(fn_ast)
        return found is not None

    def apply(
        self,
        source: str,
        function_range: Tuple[int, int],
        function_name: Optional[str] = None,
    ) -> Optional[TemplateResult]:
        try:
            mod_cst = cst.parse_module(source)
        except Exception:
            return None

        fn_cst, _ = find_target_function_cst(
            mod_cst, function_name=function_name, function_range=function_range
        )
        if not fn_cst:
            return None

        fn_name = fn_cst.name.value

        try:
            full_ast = ast.parse(source)
        except Exception:
            return None

        fn_ast: Optional[ast.FunctionDef | ast.AsyncFunctionDef] = None
        for stmt in full_ast.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == fn_name:
                fn_ast = stmt
                break

        if not fn_ast:
            return None

        found = _find_membership_collection_in_loop(fn_ast)
        if not found:
            return None

        col_var, _ = found
        set_var_name = f"{col_var}_set"

        # Apply transformation with CST
        transformer = FunctionScopedTransformer(
            target_function_name=fn_name,
            target_var=col_var,
            set_var_name=set_var_name,
        )
        new_mod = mod_cst.visit(transformer)
        candidate_code = new_mod.code

        # Run shared candidate guards
        guard = run_shared_guards(
            original_source=source,
            candidate_source=candidate_code,
            target_function_name=fn_name,
        )
        if not guard.valid:
            return None

        rationale = (
            f"Pre-converting collection '{col_var}' into a hash set ('{set_var_name}') "
            f"before the loop replaces O(n) linear scans with O(1) average hash lookups, "
            f"reducing overall complexity from O(n * m) to O(n + m)."
        )
        safety_notes = (
            f"Elements in '{col_var}' must be hashable. If elements are unhashable "
            f"(such as dicts or lists), set conversion will raise TypeError."
        )

        return TemplateResult(
            candidate_source=candidate_code,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
