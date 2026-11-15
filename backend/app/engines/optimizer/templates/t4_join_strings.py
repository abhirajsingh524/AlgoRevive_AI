"""T4_JOIN_STRINGS deterministic template (Contract G3).

Pattern: STRING_CONCAT_IN_LOOP
Preconditions:
- A string variable initialised with a string literal before a loop.
- The string variable is only grown with `+=` or `s = s + x` inside the loop.
- No other complex reads or mutations to the string variable inside the loop.
- All concatenated items must be strings.

Transformation:
- Initialize a list: `_parts = []` (or `["initial"]` if literal was non-empty).
- In loop: `_parts.append(x)`.
- After loop: `s = "".join(_parts)`.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple

import libcst as cst

from app.engines.optimizer.templates.base import (
    Template,
    TemplateResult,
    find_target_function_cst,
    run_shared_guards,
)


def _detect_string_concat_pattern(
    fn_ast: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Optional[Dict[str, Any]]:
    """Detect string variable initialised before a loop and only grown inside it."""
    # Find loops in function body
    for stmt_idx, stmt in enumerate(fn_ast.body):
        if not isinstance(stmt, (ast.For, ast.While)):
            continue

        loop_node = stmt
        # Look at statements before this loop to find string initialization
        for prev_idx in range(stmt_idx - 1, -1, -1):
            prev_stmt = fn_ast.body[prev_idx]
            if not isinstance(prev_stmt, ast.Assign) or len(prev_stmt.targets) != 1:
                continue
            target = prev_stmt.targets[0]
            if not isinstance(target, ast.Name):
                continue
            str_var = target.id

            # Must be initialized with a string literal
            if not isinstance(prev_stmt.value, ast.Constant) or not isinstance(prev_stmt.value.value, str):
                continue

            init_val = prev_stmt.value.value

            # Check inside loop: only grown with += or s = s + x
            concat_count = 0
            invalid_usage = False

            for inner in ast.walk(loop_node):
                if isinstance(inner, ast.AugAssign):
                    if isinstance(inner.target, ast.Name) and inner.target.id == str_var:
                        if isinstance(inner.op, ast.Add):
                            concat_count += 1
                        else:
                            invalid_usage = True
                elif isinstance(inner, ast.Assign):
                    for t in inner.targets:
                        if isinstance(t, ast.Name) and t.id == str_var:
                            # Must be s = s + x
                            val = inner.value
                            if isinstance(val, ast.BinOp) and isinstance(val.op, ast.Add):
                                if isinstance(val.left, ast.Name) and val.left.id == str_var:
                                    concat_count += 1
                                    continue
                            invalid_usage = True
                # Check for other reads of str_var inside the loop
                elif isinstance(inner, ast.Name) and inner.id == str_var:
                    # Parent must be the target of AugAssign or left of BinOp in concat
                    pass

            if concat_count > 0 and not invalid_usage:
                return {
                    "var_name": str_var,
                    "init_val": init_val,
                    "loop_idx": stmt_idx,
                    "init_idx": prev_idx,
                    "loop_stmt": loop_node,
                }

    return None


class CSTJoinStringsTransformer(cst.CSTTransformer):
    """Rewrites string concatenation in a loop to list append and str.join."""

    def __init__(self, var_name: str, parts_var_name: str, init_val: str) -> None:
        self.var_name = var_name
        self.parts_var_name = parts_var_name
        self.init_val = init_val
        self.applied = False

    def leave_FunctionDef(
        self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        if self.applied:
            return updated_node

        new_body: List[cst.BaseStatement] = []
        for stmt in orig_node.body.body:
            # 1. Replace initialization: s = "" -> s_parts = []
            if isinstance(stmt, cst.SimpleStatementLine):
                small_stmt = stmt.body[0]
                if isinstance(small_stmt, cst.Assign) and len(small_stmt.targets) == 1:
                    t = small_stmt.targets[0].target
                    if isinstance(t, cst.Name) and t.value == self.var_name:
                        if isinstance(small_stmt.value, cst.SimpleString):
                            val_str = small_stmt.value.evaluated_value
                            if val_str:
                                init_parts = f'["{val_str}"]'
                            else:
                                init_parts = "[]"
                            new_assign = cst.parse_statement(f"{self.parts_var_name} = {init_parts}\n")
                            new_body.append(new_assign)
                            continue

            # 2. Rewrite loop body and append join after loop
            if isinstance(stmt, (cst.For, cst.While)):
                loop_transformer = CSTLoopBodyTransformer(self.var_name, self.parts_var_name)
                new_loop = stmt.visit(loop_transformer)
                new_body.append(new_loop)

                join_stmt = cst.parse_statement(f'{self.var_name} = "".join({self.parts_var_name})\n')
                new_body.append(join_stmt)
                self.applied = True
                continue

            new_body.append(stmt)

        return updated_node.with_changes(body=cst.IndentedBlock(body=new_body))


class CSTLoopBodyTransformer(cst.CSTTransformer):
    """Replaces s += x or s = s + x with s_parts.append(x) inside loop body."""

    def __init__(self, var_name: str, parts_var_name: str) -> None:
        self.var_name = var_name
        self.parts_var_name = parts_var_name

    def leave_AugAssign(
        self, orig_node: cst.AugAssign, updated_node: cst.AugAssign
    ) -> cst.BaseSmallStatement:
        if isinstance(orig_node.target, cst.Name) and orig_node.target.value == self.var_name:
            if isinstance(orig_node.operator, cst.Plus):
                val_code = cst.Module(body=[]).code_for_node(orig_node.value)
                return cst.parse_statement(f"{self.parts_var_name}.append({val_code})\n").body[0]
        return updated_node

    def leave_Assign(
        self, orig_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.BaseSmallStatement:
        if len(orig_node.targets) == 1:
            t = orig_node.targets[0].target
            if isinstance(t, cst.Name) and t.value == self.var_name:
                val = orig_node.value
                if isinstance(val, cst.BinaryOperation) and isinstance(val.operator, cst.Add):
                    if isinstance(val.left, cst.Name) and val.left.value == self.var_name:
                        val_code = cst.Module(body=[]).code_for_node(val.right)
                        return cst.parse_statement(f"{self.parts_var_name}.append({val_code})\n").body[0]
        return updated_node


class T4JoinStringsTemplate(Template):
    """T4_JOIN_STRINGS: Replaces repeated string += in a loop with list.append and str.join()."""

    template_id = "T4_JOIN_STRINGS"

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

        detected = _detect_string_concat_pattern(fn_ast)
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

        detected = _detect_string_concat_pattern(fn_ast)
        if not detected:
            return None

        var_name = detected["var_name"]
        init_val = detected["init_val"]
        parts_var_name = f"{var_name}_parts"

        transformer = CSTJoinStringsTransformer(
            var_name=var_name,
            parts_var_name=parts_var_name,
            init_val=init_val,
        )

        class ScopeTransformer(cst.CSTTransformer):
            def leave_FunctionDef(
                self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
            ) -> cst.FunctionDef:
                if orig_node.name.value == fn_name:
                    return updated_node.visit(transformer)
                return updated_node

        transformed_mod = mod_cst.visit(ScopeTransformer())
        candidate_code = transformed_mod.code

        guard = run_shared_guards(
            original_source=source,
            candidate_source=candidate_code,
            target_function_name=fn_name,
        )
        if not guard.valid:
            return None

        rationale = (
            f"Accumulating string parts in a list ('{parts_var_name}') and joining with str.join() "
            f"eliminates repeated string buffer reallocations, reducing complexity from O(n^2) to O(n)."
        )
        safety_notes = (
            f"All items appended to '{parts_var_name}' must be of type str. "
            f"Non-string items concatenated without conversion will raise TypeError on str.join()."
        )

        return TemplateResult(
            candidate_source=candidate_code,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
