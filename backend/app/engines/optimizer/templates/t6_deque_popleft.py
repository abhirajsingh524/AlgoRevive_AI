"""T6_DEQUE_POPLEFT deterministic template (Contract G3).

Pattern: LIST_POP_FRONT
Preconditions:
- A LOCAL list (created inside the function, NOT a parameter) consumed with `pop(0)` in a loop.
- Modifying pop(0) on function parameters is strictly disallowed.
- Index must be exactly 0.

Transformation:
- Ensure `from collections import deque` at top level.
- Local creation: `queue = deque(items)` or `queue = deque([...])`.
- Loop: `queue.popleft()`.
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


def _detect_local_deque_popleft(
    fn_ast: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Optional[Dict[str, Any]]:
    """Detect local list consumed with pop(0) in a loop."""
    # 1. Parameter names cannot be the target
    param_names: Set[str] = {
        a.arg for a in (fn_ast.args.posonlyargs + fn_ast.args.args + fn_ast.args.kwonlyargs)
    }

    # 2. Find local assignments creating a list
    local_lists: Dict[str, ast.Assign] = {}
    for stmt in fn_ast.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            t = stmt.targets[0]
            if isinstance(t, ast.Name) and t.id not in param_names:
                # Check value: list(...) or [...]
                val = stmt.value
                if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) and val.func.id == "list":
                    local_lists[t.id] = stmt
                elif isinstance(val, ast.List):
                    local_lists[t.id] = stmt

    if not local_lists:
        return None

    # Disallow lists that are modified with methods unsupported by deque (e.g. .sort())
    unsupported_deque_methods = {"sort", "reverse"}
    disqualified: Set[str] = set()
    for child in ast.walk(fn_ast):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if isinstance(child.func.value, ast.Name) and child.func.value.id in local_lists:
                if child.func.attr in unsupported_deque_methods:
                    disqualified.add(child.func.value.id)

    for dis in disqualified:
        local_lists.pop(dis, None)

    if not local_lists:
        return None

    # 3. Check loops for var.pop(0)
    for loop_node in ast.walk(fn_ast):
        if not isinstance(loop_node, (ast.For, ast.While)):
            continue

        for child in ast.walk(loop_node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "pop":
                    obj = child.func.value
                    if isinstance(obj, ast.Name) and obj.id in local_lists:
                        # Check index is exactly 0
                        if len(child.args) == 1:
                            arg0 = child.args[0]
                            if isinstance(arg0, ast.Constant) and arg0.value == 0:
                                return {
                                    "var_name": obj.id,
                                    "assign_stmt": local_lists[obj.id],
                                    "loop_node": loop_node,
                                }

    return None


class CSTDequePopleftTransformer(cst.CSTTransformer):
    """Rewrites local list creation to deque() and pop(0) to popleft()."""

    def __init__(self, var_name: str) -> None:
        self.var_name = var_name
        self.transformed_assign = False
        self.transformed_pop = False

    def leave_Assign(
        self, orig_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.Assign:
        if not self.transformed_assign and len(orig_node.targets) == 1:
            t = orig_node.targets[0].target
            if isinstance(t, cst.Name) and t.value == self.var_name:
                self.transformed_assign = True
                val = orig_node.value
                # If list(items) -> deque(items)
                if isinstance(val, cst.Call) and isinstance(val.func, cst.Name) and val.func.value == "list":
                    new_val = val.with_changes(func=cst.Name("deque"))
                    return updated_node.with_changes(value=new_val)
                # If [x, y] -> deque([x, y])
                elif isinstance(val, cst.List):
                    new_val = cst.Call(func=cst.Name("deque"), args=[cst.Arg(value=val)])
                    return updated_node.with_changes(value=new_val)

        return updated_node

    def leave_Call(
        self, orig_node: cst.Call, updated_node: cst.Call
    ) -> cst.Call:
        if isinstance(orig_node.func, cst.Attribute):
            attr = orig_node.func
            if (
                isinstance(attr.value, cst.Name)
                and attr.value.value == self.var_name
                and attr.attr.value == "pop"
            ):
                # Check arg is 0
                if len(orig_node.args) == 1:
                    arg_val = orig_node.args[0].value
                    if isinstance(arg_val, cst.Integer) and arg_val.value == "0":
                        self.transformed_pop = True
                        new_func = attr.with_changes(attr=cst.Name("popleft"))
                        return updated_node.with_changes(func=new_func, args=[])

        return updated_node


def _has_deque_import(tree: ast.AST) -> bool:
    """Check if deque is imported."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "collections":
            for a in node.names:
                if a.name == "deque":
                    return True
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "collections":
                    return True
    return False


class T6DequePopleftTemplate(Template):
    """T6_DEQUE_POPLEFT: Replaces local list pop(0) with collections.deque.popleft()."""

    template_id = "T6_DEQUE_POPLEFT"

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

        detected = _detect_local_deque_popleft(fn_ast)
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

        detected = _detect_local_deque_popleft(fn_ast)
        if not detected:
            return None

        var_name = detected["var_name"]
        transformer = CSTDequePopleftTransformer(var_name=var_name)

        class ScopeTransformer(cst.CSTTransformer):
            def leave_FunctionDef(
                self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
            ) -> cst.FunctionDef:
                if orig_node.name.value == fn_name:
                    return updated_node.visit(transformer)
                return updated_node

        transformed_mod = mod_cst.visit(ScopeTransformer())
        if not transformer.transformed_pop:
            return None

        # Ensure from collections import deque at top level
        if not _has_deque_import(full_ast):
            import_stmt = cst.parse_statement("from collections import deque\n")
            transformed_mod = transformed_mod.with_changes(
                body=[import_stmt] + list(transformed_mod.body)
            )

        candidate_code = transformed_mod.code

        guard = run_shared_guards(
            original_source=source,
            candidate_source=candidate_code,
            target_function_name=fn_name,
        )
        if not guard.valid:
            return None

        rationale = (
            f"Replacing list.pop(0) on '{var_name}', which incurs an O(n) element shift per call, "
            f"with collections.deque.popleft() provides O(1) removals, reducing overall complexity from O(n^2) to O(n)."
        )
        safety_notes = (
            f"collections.deque does not support fast random indexed access (O(n) vs list O(1)). "
            f"Modifying '{var_name}' to deque with popleft() is safe because elements are consumed sequentially."
        )

        return TemplateResult(
            candidate_source=candidate_code,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
