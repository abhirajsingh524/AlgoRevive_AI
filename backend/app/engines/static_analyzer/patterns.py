"""Performance pattern detector for Python ASTs.

Detects exactly the six pattern ids specified in Contract G3:
1. LINEAR_MEMBERSHIP_IN_LOOP
2. NESTED_LOOP_LOOKUP
3. REPEATED_SORT_FOR_EXTREME
4. STRING_CONCAT_IN_LOOP
5. NAIVE_RECURSION
6. LIST_POP_FRONT

Ensures zero false positives on the control function (efficient_total).
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Set

from app.engines.static_analyzer.analyzer import FunctionInfo


@dataclass
class DetectedPattern:
    pattern_id: str
    line_number: int
    matched_snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


VALID_PATTERN_IDS = {
    "LINEAR_MEMBERSHIP_IN_LOOP",
    "NESTED_LOOP_LOOKUP",
    "REPEATED_SORT_FOR_EXTREME",
    "STRING_CONCAT_IN_LOOP",
    "NAIVE_RECURSION",
    "LIST_POP_FRONT",
}


def _walk_non_nested(node: ast.AST):
    """Walk child AST nodes without descending into nested functions or classes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield child
        yield from _walk_non_nested(child)


def _safe_unparse(node: ast.AST) -> str:
    """Unparse an AST node into clean source snippet with fallback."""
    try:
        return ast.unparse(node)
    except Exception:
        return "<source unavailable>"


def _get_variable_types(fn_node: ast.AST) -> Dict[str, str]:
    """Infer basic types (str, int, float, list, set, dict) for variables in scope."""
    var_types: Dict[str, str] = {}

    for node in _walk_non_nested(fn_node):
        if isinstance(node, ast.Assign):
            val_type = None
            if isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    val_type = "str"
                elif isinstance(node.value.value, (int, float)):
                    val_type = "numeric"
            elif isinstance(node.value, (ast.List, ast.ListComp)):
                val_type = "list"
            elif isinstance(node.value, (ast.Set, ast.SetComp)):
                val_type = "set"
            elif isinstance(node.value, (ast.Dict, ast.DictComp)):
                val_type = "dict"
            elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                func_id = node.value.func.id
                if func_id in ("list", "set", "dict", "str", "int", "float"):
                    val_type = "numeric" if func_id in ("int", "float") else func_id

            if val_type:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_types[target.id] = val_type

    return var_types


def _extract_loop_vars(loop_node: ast.AST) -> Set[str]:
    """Extract iteration variable names from a loop header."""
    names: Set[str] = set()
    if isinstance(loop_node, (ast.For, ast.AsyncFor)):
        for node in ast.walk(loop_node.target):
            if isinstance(node, ast.Name):
                names.add(node.id)
    return names


class PatternDetector:
    """Detects performance anti-patterns in function ASTs."""

    def detect_patterns(self, fn_info: FunctionInfo) -> List[DetectedPattern]:
        """Detect all contract G3 patterns within a function."""
        if not fn_info.ast_node:
            return []

        fn_node = fn_info.ast_node
        patterns: List[DetectedPattern] = []

        var_types = _get_variable_types(fn_node)
        decorators = fn_info.metrics.get("decorators", [])
        is_memoized = any(
            d in ("lru_cache", "cache", "functools.lru_cache", "functools.cache")
            for d in decorators
        )

        # 1. NAIVE_RECURSION detector
        if fn_info.has_recursion and not is_memoized:
            rec_count = fn_info.metrics.get("recursive_calls_count", 0)
            if rec_count >= 2:
                # Find the return node or call node representing naive recursion
                matched_snippet = None
                lineno = fn_info.lineno
                for node in _walk_non_nested(fn_node):
                    if isinstance(node, ast.Return) and node.value:
                        # Check if return contains self calls
                        call_names = [
                            c.func.id
                            for c in ast.walk(node.value)
                            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                        ]
                        if call_names.count(fn_info.name) >= 2:
                            matched_snippet = _safe_unparse(node)
                            lineno = node.lineno
                            break

                if not matched_snippet:
                    matched_snippet = f"Multiple recursive calls to {fn_info.name}() without memoization"

                patterns.append(
                    DetectedPattern(
                        pattern_id="NAIVE_RECURSION",
                        line_number=lineno,
                        matched_snippet=matched_snippet,
                    )
                )

        # Walk loops for loop-based anti-patterns
        self._detect_loop_patterns(fn_node, fn_info, var_types, patterns)

        # 6. LIST_POP_FRONT detector (inside loops or general function body)
        self._detect_pop_front(fn_node, var_types, patterns)

        return patterns

    def _detect_loop_patterns(
        self,
        fn_node: ast.AST,
        fn_info: FunctionInfo,
        var_types: Dict[str, str],
        patterns: List[DetectedPattern],
    ) -> None:
        """Inspect loops for membership, sort, string concatenation, and nested lookup patterns."""
        active_loops: List[ast.AST] = []

        def traverse(node: ast.AST):
            is_loop = isinstance(node, (ast.For, ast.AsyncFor, ast.While))
            if is_loop:
                active_loops.append(node)

            # Check loop-specific patterns when inside at least one loop
            if active_loops:
                # 1. LINEAR_MEMBERSHIP_IN_LOOP
                if isinstance(node, ast.Compare):
                    for op, comp in zip(node.ops, node.comparators):
                        if isinstance(op, (ast.In, ast.NotIn)):
                            is_list = False
                            if isinstance(comp, (ast.List, ast.ListComp)):
                                is_list = True
                            elif isinstance(comp, ast.Name):
                                # Check type or name or params
                                if var_types.get(comp.id) == "list":
                                    is_list = True
                                elif var_types.get(comp.id) in ("set", "dict"):
                                    is_list = False
                                else:
                                    # Check function parameter annotations or conventional name
                                    for p in fn_info.params:
                                        if p.get("name") == comp.id:
                                            ann = (p.get("annotation") or "").lower()
                                            if "set" in ann or "dict" in ann:
                                                is_list = False
                                            else:
                                                is_list = True
                                            break
                                    else:
                                        if comp.id.endswith("s") or comp.id in ("ids", "items", "values"):
                                            is_list = True
                            elif isinstance(comp, ast.Call) and isinstance(comp.func, ast.Name):
                                if comp.func.id == "list":
                                    is_list = True

                            if is_list:
                                patterns.append(
                                    DetectedPattern(
                                        pattern_id="LINEAR_MEMBERSHIP_IN_LOOP",
                                        line_number=node.lineno,
                                        matched_snippet=_safe_unparse(node),
                                    )
                                )

                # 2. NESTED_LOOP_LOOKUP
                if len(active_loops) >= 2 and isinstance(node, ast.Compare):
                    # Check if equality compare between outer loop var and inner loop var
                    outer_vars: Set[str] = set()
                    for loop_item in active_loops[:-1]:
                        outer_vars.update(_extract_loop_vars(loop_item))
                    inner_vars = _extract_loop_vars(active_loops[-1])

                    if any(isinstance(op, ast.Eq) for op in node.ops):
                        left_names = {n.id for n in ast.walk(node.left) if isinstance(n, ast.Name)}
                        comp_names: Set[str] = set()
                        for c in node.comparators:
                            comp_names.update(n.id for n in ast.walk(c) if isinstance(n, ast.Name))

                        # Check if one side references outer and other references inner
                        cross_join = (
                            (bool(left_names & outer_vars) and bool(comp_names & inner_vars))
                            or (bool(left_names & inner_vars) and bool(comp_names & outer_vars))
                        )
                        if cross_join:
                            patterns.append(
                                DetectedPattern(
                                    pattern_id="NESTED_LOOP_LOOKUP",
                                    line_number=node.lineno,
                                    matched_snippet=_safe_unparse(node),
                                )
                            )

                # 3. REPEATED_SORT_FOR_EXTREME
                if isinstance(node, ast.Call):
                    is_sort = False
                    if isinstance(node.func, ast.Name) and node.func.id == "sorted":
                        is_sort = True
                    elif isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
                        is_sort = True

                    if is_sort:
                        patterns.append(
                            DetectedPattern(
                                pattern_id="REPEATED_SORT_FOR_EXTREME",
                                line_number=node.lineno,
                                matched_snippet=_safe_unparse(node),
                            )
                        )

                # 4. STRING_CONCAT_IN_LOOP
                # Precondition: must be a string variable, never numeric!
                if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
                    if isinstance(node.target, ast.Name):
                        target_name = node.target.id
                        target_type = var_types.get(target_name)

                        is_string = False
                        if target_type == "str":
                            is_string = True
                        elif target_type == "numeric":
                            is_string = False  # Explicitly numeric, e.g. total += val
                        else:
                            # Check RHS
                            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                is_string = True
                            elif isinstance(node.value, ast.JoinedStr):
                                is_string = True
                            elif target_name in ("s", "str", "text", "report", "msg", "message", "buffer"):
                                is_string = True

                        if is_string:
                            patterns.append(
                                DetectedPattern(
                                    pattern_id="STRING_CONCAT_IN_LOOP",
                                    line_number=node.lineno,
                                    matched_snippet=_safe_unparse(node),
                                )
                            )

            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                traverse(child)

            if is_loop:
                active_loops.pop()

        traverse(fn_node)

    def _detect_pop_front(
        self,
        fn_node: ast.AST,
        var_types: Dict[str, str],
        patterns: List[DetectedPattern],
    ) -> None:
        """Detect .pop(0) operations on list objects."""
        for node in _walk_non_nested(fn_node):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "pop":
                    # Check if argument is 0
                    is_zero = False
                    if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == 0:
                        is_zero = True
                    for kw in node.keywords:
                        if kw.arg == "index" and isinstance(kw.value, ast.Constant) and kw.value.value == 0:
                            is_zero = True

                    if is_zero:
                        target = node.func.value
                        is_list = True
                        if isinstance(target, ast.Name):
                            if var_types.get(target.id) in ("dict", "set"):
                                is_list = False

                        if is_list:
                            patterns.append(
                                DetectedPattern(
                                    pattern_id="LIST_POP_FRONT",
                                    line_number=node.lineno,
                                    matched_snippet=_safe_unparse(node),
                                )
                            )
