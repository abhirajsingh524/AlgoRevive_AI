"""T2_DICT_INDEX_JOIN deterministic template (Contract G3).

Pattern: NESTED_LOOP_LOOKUP
Preconditions:
- Exact nested loop shape:
    for x in A:
        for y in B:
            if key(x) == key(y): # or key(y) == key(x)
                ...
- Neither collection A nor B is mutated or reassigned.
- Index keys must be hashable.

Transformation:
- Build a `defaultdict(list)` index of B before the outer loop:
    _b_index = defaultdict(list)
    for y in B:
        _b_index[key(y)].append(y)
- Replace inner loop with lookup:
    for y in _b_index[key(x)]:
        ...
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set, Tuple

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


def _is_var_mutated(fn_ast: ast.FunctionDef | ast.AsyncFunctionDef, var_name: str) -> bool:
    """Check if var_name is reassigned or modified via mutating methods."""
    for node in ast.walk(fn_ast):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for target_node in ast.walk(target):
                    if isinstance(target_node, ast.Name) and target_node.id == var_name:
                        return True
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            target = getattr(node, "target", None)
            if target and isinstance(target, ast.Name) and target.id == var_name:
                return True
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == var_name:
                if node.func.attr in MUTATING_METHODS:
                    return True
    return False


def _node_mentions_var(node: ast.AST, var_name: str) -> bool:
    """Check if AST node references var_name."""
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == var_name:
            return True
    return False




def _detect_nested_join_pattern(
    fn_ast: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Optional[Dict[str, Any]]:
    """Detect exact shape:

    for x in A:
        for y in B:
            if key(x) == key(y):
                ...
    """
    for outer in ast.walk(fn_ast):
        if not isinstance(outer, ast.For):
            continue
        if not isinstance(outer.target, ast.Name) or not isinstance(outer.iter, ast.Name):
            continue

        x_name = outer.target.id
        a_name = outer.iter.id

        for inner in outer.body:
            if not isinstance(inner, ast.For):
                continue
            if not isinstance(inner.target, ast.Name) or not isinstance(inner.iter, ast.Name):
                continue

            y_name = inner.target.id
            b_name = inner.iter.id

            if x_name == y_name or a_name == b_name:
                continue

            # Check that inner loop has an if statement with Eq test
            if not inner.body:
                continue
            if_stmt = inner.body[0]
            if not isinstance(if_stmt, ast.If) or if_stmt.orelse:
                continue

            test = if_stmt.test
            if not isinstance(test, ast.Compare) or len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
                continue

            left = test.left
            right = test.comparators[0]

            left_has_x = _node_mentions_var(left, x_name)
            left_has_y = _node_mentions_var(left, y_name)
            right_has_x = _node_mentions_var(right, x_name)
            right_has_y = _node_mentions_var(right, y_name)

            if left_has_x and not left_has_y and right_has_y and not right_has_x:
                x_key_ast = left
                y_key_ast = right
            elif left_has_y and not left_has_x and right_has_x and not right_has_y:
                x_key_ast = right
                y_key_ast = left
            else:
                continue

            # Verify neither A nor B is mutated
            if _is_var_mutated(fn_ast, a_name) or _is_var_mutated(fn_ast, b_name):
                continue

            return {
                "outer_target": x_name,
                "outer_iter": a_name,
                "inner_target": y_name,
                "inner_iter": b_name,
                "x_key_ast": x_key_ast,
                "y_key_ast": y_key_ast,
                "inner_if": if_stmt,
                "outer_for": outer,
                "inner_for": inner,
            }
    return None


class CSTNestedJoinTransformer(cst.CSTTransformer):
    """Rewrites the nested loop into indexed lookup via LibCST."""

    def __init__(
        self,
        outer_target: str,
        outer_iter: str,
        inner_target: str,
        inner_iter: str,
        x_key_code: str,
        y_key_code: str,
        index_var_name: str,
    ) -> None:
        self.outer_target = outer_target
        self.outer_iter = outer_iter
        self.inner_target = inner_target
        self.inner_iter = inner_iter
        self.x_key_code = x_key_code
        self.y_key_code = y_key_code
        self.index_var_name = index_var_name
        self.applied = False

    def leave_For(
        self, orig_node: cst.For, updated_node: cst.For
    ) -> cst.For | cst.FlattenSentinel[cst.BaseStatement]:
        if self.applied:
            return updated_node

        # Check if this is the outer loop
        if (
            isinstance(orig_node.target, cst.Name)
            and orig_node.target.value == self.outer_target
            and isinstance(orig_node.iter, cst.Name)
            and orig_node.iter.value == self.outer_iter
        ):
            self.applied = True

            # Index construction statements
            index_code = (
                f"{self.index_var_name} = defaultdict(list)\n"
                f"for {self.inner_target} in {self.inner_iter}:\n"
                f"    {self.index_var_name}[{self.y_key_code}].append({self.inner_target})\n"
            )
            index_stmts = list(cst.parse_module(index_code).body)

            # Find the inner if body inside inner loop
            inner_body_stmts: List[cst.BaseStatement] = []
            for stmt in orig_node.body.body:
                if isinstance(stmt, cst.For):
                    for inner_stmt in stmt.body.body:
                        if isinstance(inner_stmt, cst.If):
                            inner_body_stmts = list(inner_stmt.body.body)
                            break

            if not inner_body_stmts:
                # Fallback to empty pass
                inner_body_stmts = [cst.parse_statement("pass\n")]

            # Construct new inner for loop
            inner_loop_stmt = cst.For(
                target=cst.Name(self.inner_target),
                iter=cst.parse_expression(f"{self.index_var_name}[{self.x_key_code}]"),
                body=cst.IndentedBlock(body=inner_body_stmts),
            )

            new_outer = updated_node.with_changes(
                body=cst.IndentedBlock(body=[inner_loop_stmt])
            )
            return cst.FlattenSentinel(index_stmts + [new_outer])

        return updated_node


def _has_defaultdict_import(tree: ast.AST) -> bool:
    """Check if defaultdict is already imported."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "collections":
            for name in node.names:
                if name.name == "defaultdict":
                    return True
    return False


class T2DictIndexJoinTemplate(Template):
    """T2_DICT_INDEX_JOIN: Replaces nested loops with hash map index join."""

    template_id = "T2_DICT_INDEX_JOIN"

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

        detected = _detect_nested_join_pattern(fn_ast)
        return detected is not None

    def apply(
        self,
        source: str,
        function_range: Tuple[int, int],
        function_name: Optional[str] = None,
    ) -> Optional[TemplateResult]:
        try:
            mod_cst = cst.parse_module(source)
            full_ast = ast.parse(source)
        except Exception:
            return None

        fn_cst, _ = find_target_function_cst(
            mod_cst, function_name=function_name, function_range=function_range
        )
        if not fn_cst:
            return None

        fn_name = fn_cst.name.value
        fn_ast: Optional[ast.FunctionDef | ast.AsyncFunctionDef] = None
        for stmt in full_ast.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == fn_name:
                fn_ast = stmt
                break

        if not fn_ast:
            return None

        detected = _detect_nested_join_pattern(fn_ast)
        if not detected:
            return None

        outer_target = detected["outer_target"]
        outer_iter = detected["outer_iter"]
        inner_target = detected["inner_target"]
        inner_iter = detected["inner_iter"]
        x_key_code = ast.unparse(detected["x_key_ast"])
        y_key_code = ast.unparse(detected["y_key_ast"])

        index_var_name = f"{inner_iter}_by_key"

        # Apply transformation with CST
        transformer = CSTNestedJoinTransformer(
            outer_target=outer_target,
            outer_iter=outer_iter,
            inner_target=inner_target,
            inner_iter=inner_iter,
            x_key_code=x_key_code,
            y_key_code=y_key_code,
            index_var_name=index_var_name,
        )

        class ScopeTransformer(cst.CSTTransformer):
            def leave_FunctionDef(
                self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
            ) -> cst.FunctionDef:
                if orig_node.name.value == fn_name:
                    return updated_node.visit(transformer)
                return updated_node

        transformed_mod = mod_cst.visit(ScopeTransformer())

        # Ensure from collections import defaultdict is present at top-level
        if not _has_defaultdict_import(full_ast):
            import_stmt = cst.parse_statement("from collections import defaultdict\n")
            transformed_mod = transformed_mod.with_changes(
                body=[import_stmt] + list(transformed_mod.body)
            )

        candidate_code = transformed_mod.code

        # Run shared candidate guards
        guard = run_shared_guards(
            original_source=source,
            candidate_source=candidate_code,
            target_function_name=fn_name,
        )
        if not guard.valid:
            return None

        rationale = (
            f"Pre-indexing collection '{inner_iter}' by join key into a hash map ('{index_var_name}') "
            f"replaces the inner O(|{inner_iter}|) loop with an O(1) hash lookup, reducing overall complexity "
            f"from O(|{outer_iter}| * |{inner_iter}|) to O(|{outer_iter}| + |{inner_iter}|)."
        )
        safety_notes = (
            f"Join keys must be hashable. Pre-indexing consumes O(|{inner_iter}|) additional memory "
            f"to store referenced items in '{index_var_name}'."
        )

        return TemplateResult(
            candidate_source=candidate_code,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
