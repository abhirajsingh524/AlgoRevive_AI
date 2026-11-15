"""T5_LRU_CACHE deterministic template (Contract G3).

Pattern: NAIVE_RECURSION
Preconditions:
- Function with two or more direct self-calls.
- No global or nonlocal writes.
- No I/O (print, open, socket, etc.), randomness, or time calls.
- No mutable defaults in function arguments.

Transformation:
- Ensure `import functools` at module level.
- Add `@functools.lru_cache(maxsize=None)` decorator.
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

FORBIDDEN_CALL_NAMES: Set[str] = {
    "print",
    "open",
    "input",
    "socket",
    "sleep",
    "time",
    "random",
    "randint",
    "choice",
    "shuffle",
    "uniform",
}

FORBIDDEN_MODULE_CALLS: Set[str] = {
    "random",
    "time",
    "os",
    "sys",
    "socket",
    "urllib",
    "requests",
    "httpx",
}


def _check_mutable_defaults(fn_ast: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if any default argument is mutable (list, dict, set, call)."""
    all_defaults = list(fn_ast.args.defaults) + [d for d in fn_ast.args.kw_defaults if d is not None]
    for d in all_defaults:
        if isinstance(d, (ast.List, ast.Dict, ast.Set, ast.Call)):
            return True
    return False


def _check_naive_recursion_preconditions(
    fn_ast: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Verify all T5 preconditions:

    - >= 2 direct self-calls
    - no global / nonlocal
    - no I/O, randomness, or time calls
    - no mutable defaults
    """
    fn_name = fn_ast.name

    # 1. No mutable defaults
    if _check_mutable_defaults(fn_ast):
        return False

    self_calls_count = 0

    for node in ast.walk(fn_ast):
        # 2. No global or nonlocal statements
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            return False

        # 3. Check calls for self-calls and forbidden I/O/randomness
        if isinstance(node, ast.Call):
            # Direct self-call
            if isinstance(node.func, ast.Name) and node.func.id == fn_name:
                self_calls_count += 1
            # Check for forbidden function calls
            elif isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALL_NAMES:
                    return False
            # Check for module attribute calls e.g. time.sleep, random.randint
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id in FORBIDDEN_MODULE_CALLS or node.func.attr in FORBIDDEN_CALL_NAMES:
                        return False

    # Must have at least 2 direct self-calls
    return self_calls_count >= 2


def _has_functools_import(tree: ast.AST) -> bool:
    """Check if functools is already imported."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "functools":
                    return True
        elif isinstance(node, ast.ImportFrom) and node.module == "functools":
            return True
    return False


class T5LruCacheTemplate(Template):
    """T5_LRU_CACHE: Adds functools.lru_cache(maxsize=None) to naive recursive functions."""

    template_id = "T5_LRU_CACHE"

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

        return _check_naive_recursion_preconditions(fn_ast)

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

        if not fn_ast or not _check_naive_recursion_preconditions(fn_ast):
            return None

        # Build decorator node: @functools.lru_cache(maxsize=None)
        decorator_node = cst.Decorator(
            decorator=cst.Call(
                func=cst.Attribute(
                    value=cst.Name("functools"),
                    attr=cst.Name("lru_cache"),
                ),
                args=[cst.Arg(keyword=cst.Name("maxsize"), value=cst.Name("None"))],
            )
        )

        class AddDecoratorTransformer(cst.CSTTransformer):
            def leave_FunctionDef(
                self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
            ) -> cst.FunctionDef:
                if orig_node.name.value == fn_name:
                    # Check if already decorated
                    for d in orig_node.decorators:
                        d_code = cst.Module(body=[]).code_for_node(d)
                        if "lru_cache" in d_code:
                            return updated_node
                    return updated_node.with_changes(
                        decorators=[decorator_node] + list(updated_node.decorators)
                    )
                return updated_node

        transformed_mod = mod_cst.visit(AddDecoratorTransformer())

        # Ensure import functools at module level
        if not _has_functools_import(full_ast):
            import_stmt = cst.parse_statement("import functools\n")
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
            "Applying @functools.lru_cache(maxsize=None) memoizes subproblem results, "
            "eliminating exponential redundant recomputations and reducing complexity from O(2^n) to O(n)."
        )
        safety_notes = (
            "All function arguments must be hashable for lru_cache. Memory consumption grows "
            "proportional to the number of distinct argument tuples evaluated."
        )

        return TemplateResult(
            candidate_source=candidate_code,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
