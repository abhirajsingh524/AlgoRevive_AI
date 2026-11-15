"""T3_MIN_MAX_HEAP deterministic template (Contract G3).

Pattern: REPEATED_SORT_FOR_EXTREME
Preconditions:
- sorted(X)[0] or sorted(X, key=f)[0] -> min(X) / min(X, key=f)
- sorted(X, reverse=True)[0] -> max(X) / max(X, key=f)
- sorted(X)[:k] -> heapq.nsmallest(k, X) (with key if present)
- sorted(X, reverse=True)[:k] -> heapq.nlargest(k, X) (with key if present)
Apply ONLY to these semantically equivalent forms.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Optional, Tuple

import libcst as cst

from app.engines.optimizer.templates.base import (
    Template,
    TemplateResult,
    find_target_function_cst,
    run_shared_guards,
)


def _is_true_constant(node: ast.AST) -> bool:
    """Check if AST node is boolean True."""
    return isinstance(node, ast.Constant) and node.value is True


def _detect_sort_for_extreme(
    fn_ast: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Detect if function contains one of the supported sorted() forms."""
    for node in ast.walk(fn_ast):
        if not isinstance(node, ast.Subscript):
            continue

        call_node = node.value
        if not isinstance(call_node, ast.Call):
            continue
        func = call_node.func
        if not isinstance(func, ast.Name) or func.id != "sorted":
            continue

        # Form 1 & 2: sorted(...)[0]
        slice_node = node.slice
        if isinstance(slice_node, ast.Constant) and slice_node.value == 0:
            return True

        # Form 3 & 4: sorted(...)[:k]
        if isinstance(slice_node, ast.Slice):
            if slice_node.lower is None and slice_node.upper is not None and slice_node.step is None:
                return True

    return False


class CSTSortExtremeTransformer(cst.CSTTransformer):
    """Rewrite sorted()[0] and sorted()[:k] calls into min/max/heapq calls."""

    def __init__(self) -> None:
        self.transformed = False
        self.needs_heapq = False

    def leave_Subscript(
        self, orig_node: cst.Subscript, updated_node: cst.Subscript
    ) -> cst.BaseExpression:
        # Check if value is Call to sorted
        val = orig_node.value
        if not (isinstance(val, cst.Call) and isinstance(val.func, cst.Name) and val.func.value == "sorted"):
            return updated_node

        if not orig_node.slice:
            return updated_node

        slice_item = orig_node.slice[0].slice

        # Inspect sorted() arguments: iterable (arg 0), and optional keywords 'key', 'reverse'
        if not val.args:
            return updated_node

        iter_arg = val.args[0]
        key_arg: Optional[cst.Arg] = None
        is_reverse = False

        for arg in val.args[1:]:
            if arg.keyword and arg.keyword.value == "key":
                key_arg = arg
            elif arg.keyword and arg.keyword.value == "reverse":
                if isinstance(arg.value, cst.Name) and arg.value.value == "True":
                    is_reverse = True

        # Check for [0]
        is_zero_index = False
        if isinstance(slice_item, cst.Index) and isinstance(slice_item.value, cst.Integer) and slice_item.value.value == "0":
            is_zero_index = True
        elif isinstance(slice_item, cst.Integer) and slice_item.value == "0":
            is_zero_index = True

        if is_zero_index:
            self.transformed = True
            target_func_name = "max" if is_reverse else "min"
            clean_iter_arg = iter_arg.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            new_args = [clean_iter_arg]
            if key_arg:
                clean_key_arg = key_arg.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                clean_iter_arg = iter_arg.with_changes(comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")))
                new_args = [clean_iter_arg, clean_key_arg]
            return cst.Call(func=cst.Name(target_func_name), args=new_args)

        # Check for [:k]
        if isinstance(slice_item, cst.Slice) and slice_item.lower is None and slice_item.upper is not None and slice_item.step is None:
            self.transformed = True
            self.needs_heapq = True
            k_expr = slice_item.upper
            heap_func_name = "nlargest" if is_reverse else "nsmallest"

            k_arg = cst.Arg(value=k_expr, comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")))
            clean_iter_arg = iter_arg.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            new_args = [k_arg, clean_iter_arg]
            if key_arg:
                clean_key_arg = key_arg.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                clean_iter_arg = iter_arg.with_changes(comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")))
                new_args = [k_arg, clean_iter_arg, clean_key_arg]

            return cst.Call(
                func=cst.Attribute(value=cst.Name("heapq"), attr=cst.Name(heap_func_name)),
                args=new_args,
            )

        return updated_node


def _has_heapq_import(tree: ast.AST) -> bool:
    """Check if heapq is imported."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "heapq":
                    return True
        elif isinstance(node, ast.ImportFrom) and node.module == "heapq":
            return True
    return False


class T3MinMaxHeapTemplate(Template):
    """T3_MIN_MAX_HEAP: Replaces sorted()[0] or sorted()[:k] with min()/max() or heapq."""

    template_id = "T3_MIN_MAX_HEAP"

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

        return _detect_sort_for_extreme(fn_ast)

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

        if not fn_ast or not _detect_sort_for_extreme(fn_ast):
            return None

        transformer = CSTSortExtremeTransformer()

        class ScopeTransformer(cst.CSTTransformer):
            def leave_FunctionDef(
                self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
            ) -> cst.FunctionDef:
                if orig_node.name.value == fn_name:
                    return updated_node.visit(transformer)
                return updated_node

        transformed_mod = mod_cst.visit(ScopeTransformer())
        if not transformer.transformed:
            return None

        if transformer.needs_heapq and not _has_heapq_import(full_ast):
            import_stmt = cst.parse_statement("import heapq\n")
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
            "Replacing full O(n log n) sorting with linear min()/max() or O(n log k) heap selection "
            "eliminates unnecessary ordering overhead when only the extreme element or top k elements are required."
        )
        safety_notes = (
            "min() and max() raise ValueError if the sequence is empty, matching sorted(X)[0] IndexError "
            "behavior on empty sequences. Elements must be mutually comparable."
        )

        return TemplateResult(
            candidate_source=candidate_code,
            rationale=rationale,
            safety_notes=safety_notes,
            changed_lines=guard.changed_lines,
            patch=guard.patch,
        )
