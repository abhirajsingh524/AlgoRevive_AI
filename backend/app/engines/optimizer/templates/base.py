"""Template base interface and shared candidate validation guards.

Conforms to Contract G2, G3 and Phase 6 specifications:
- Preserves comments and formatting using LibCST.
- Enforces strict candidate guards:
  1. Compiles with compile()
  2. Re-parses cleanly in both ast and libcst
  3. Preserves target function name and signature (arguments, defaults, return annotation)
  4. Changes ONLY the target function's line range (AST of all other code is identical)
  5. Adds imports strictly from the allowlist: functools, collections, heapq, bisect, itertools, math, operator
  6. Produces unified diff with difflib
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import ast
from dataclasses import dataclass, field
import difflib
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import libcst as cst
from libcst.metadata import PositionProvider

logger = logging.getLogger("optimizer.templates.base")

# Contract Phase 6 import allowlist
ALLOWED_MODULES: Set[str] = {
    "functools",
    "collections",
    "heapq",
    "bisect",
    "itertools",
    "math",
    "operator",
}


@dataclass
class TemplateResult:
    """Result of applying a template transformation."""

    candidate_source: str
    rationale: str
    safety_notes: str
    changed_lines: List[int] = field(default_factory=list)
    patch: str = ""


@dataclass
class GuardResult:
    """Result of running candidate safety guards."""

    valid: bool
    error: Optional[str] = None
    patch: str = ""
    changed_lines: List[int] = field(default_factory=list)


def generate_unified_diff(
    original_source: str, candidate_source: str, filename: str = "candidate.py"
) -> str:
    """Produce a standard unified diff between original and candidate source."""
    orig_lines = original_source.splitlines(keepends=True)
    cand_lines = candidate_source.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        cand_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff)


def compute_changed_lines(original_source: str, candidate_source: str) -> List[int]:
    """Compute 1-indexed line numbers of candidate_source that differ from original_source."""
    orig_lines = original_source.splitlines()
    cand_lines = candidate_source.splitlines()
    matcher = difflib.SequenceMatcher(None, orig_lines, cand_lines)
    changed: List[int] = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            for line_no in range(j1 + 1, j2 + 1):
                changed.append(line_no)
    return changed


def extract_all_imports(tree: ast.AST) -> Set[str]:
    """Extract set of root module names imported across the AST."""
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def find_function_ast(
    tree: ast.Module, function_name: str
) -> Optional[Union[ast.FunctionDef, ast.AsyncFunctionDef]]:
    """Find a top-level or method function in AST by name."""
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == function_name:
            return stmt
        if isinstance(stmt, ast.ClassDef):
            for item in stmt.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == function_name
                ):
                    return item
    return None


def signatures_equal(
    orig_fn: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    cand_fn: Union[ast.FunctionDef, ast.AsyncFunctionDef],
) -> Tuple[bool, Optional[str]]:
    """Check that candidate function preserves exact signature (name, arguments, defaults, return annotation)."""
    if orig_fn.name != cand_fn.name:
        return False, f"Function name changed from '{orig_fn.name}' to '{cand_fn.name}'"

    # Compare arguments AST dump
    orig_args_dump = ast.dump(orig_fn.args)
    cand_args_dump = ast.dump(cand_fn.args)
    if orig_args_dump != cand_args_dump:
        return False, f"Function signature for '{orig_fn.name}' was modified"

    # Compare return type annotation
    orig_ret_dump = ast.dump(orig_fn.returns) if orig_fn.returns else None
    cand_ret_dump = ast.dump(cand_fn.returns) if cand_fn.returns else None
    if orig_ret_dump != cand_ret_dump:
        return False, f"Function return type annotation for '{orig_fn.name}' was modified"

    return True, None


def check_only_target_changed(
    orig_tree: ast.Module,
    cand_tree: ast.Module,
    target_function_name: str,
) -> Tuple[bool, Optional[str]]:
    """Verify that all statements outside the target function are identical,

    with the only exception being newly added import statements from the allowlist.
    """
    orig_non_target: List[ast.stmt] = []
    for stmt in orig_tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == target_function_name:
            continue
        orig_non_target.append(stmt)

    cand_non_target: List[ast.stmt] = []
    for stmt in cand_tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == target_function_name:
            continue
        cand_non_target.append(stmt)

    # Separate non-import statements
    orig_other: List[ast.stmt] = [
        s for s in orig_non_target if not isinstance(s, (ast.Import, ast.ImportFrom))
    ]

    cand_other: List[ast.stmt] = [
        s for s in cand_non_target if not isinstance(s, (ast.Import, ast.ImportFrom))
    ]

    # Non-import statements outside target function must be identical
    if len(orig_other) != len(cand_other):
        return (
            False,
            f"Outside code modified: original had {len(orig_other)} non-import statements, "
            f"candidate has {len(cand_other)}",
        )

    for idx, (o_stmt, c_stmt) in enumerate(zip(orig_other, cand_other)):
        if ast.dump(o_stmt) != ast.dump(c_stmt):
            return (
                False,
                f"Outside code modified at non-import statement #{idx + 1}: "
                f"expected {ast.dump(o_stmt)[:100]}, got {ast.dump(c_stmt)[:100]}",
            )

    # Validate that any newly added imports are strictly in the allowlist
    orig_imported_modules = extract_all_imports(orig_tree)
    cand_all_imports = extract_all_imports(cand_tree)
    new_imports = cand_all_imports - orig_imported_modules

    disallowed_new = new_imports - ALLOWED_MODULES
    if disallowed_new:
        return (
            False,
            f"Candidate added disallowed imports outside allowlist: {sorted(disallowed_new)}. "
            f"Allowed modules: {sorted(ALLOWED_MODULES)}",
        )

    return True, None


def run_shared_guards(
    original_source: str,
    candidate_source: str,
    target_function_name: Union[str, Tuple[int, int]],
    filename: str = "candidate.py",
) -> GuardResult:
    """Run all mandatory shared candidate guards:

    1. compile() succeeds
    2. ast.parse() and cst.parse_module() succeed
    3. Target function name and signature are identical
    4. Only target function lines and allowlist imports are changed
    5. Imports strictly follow allowlist
    6. Generate unified diff
    """
    # 1. Must compile
    try:
        compile(candidate_source, filename, "exec")
    except Exception as e:
        return GuardResult(valid=False, error=f"Candidate code failed compile(): {e}")

    # 2. Must re-parse in ast
    try:
        cand_ast = ast.parse(candidate_source)
        orig_ast = ast.parse(original_source)
    except Exception as e:
        return GuardResult(valid=False, error=f"Candidate code failed ast.parse(): {e}")

    # Must re-parse in libcst
    try:
        cst.parse_module(candidate_source)
    except Exception as e:
        return GuardResult(valid=False, error=f"Candidate code failed libcst parsing: {e}")

    # 3. Locate target function in both
    if isinstance(target_function_name, tuple):
        found_name: Optional[str] = None
        for node in ast.walk(orig_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.lineno == target_function_name[0] or (
                    node.lineno <= target_function_name[0]
                    and (node.end_lineno or node.lineno) >= target_function_name[1]
                ):
                    found_name = node.name
                    break
        if not found_name:
            return GuardResult(
                valid=False,
                error=f"Target function at line range {target_function_name} not found in original source",
            )
        target_function_name = found_name

    orig_fn = find_function_ast(orig_ast, target_function_name)
    cand_fn = find_function_ast(cand_ast, target_function_name)

    if not orig_fn:
        return GuardResult(
            valid=False,
            error=f"Target function '{target_function_name}' not found in original source",
        )
    if not cand_fn:
        return GuardResult(
            valid=False,
            error=f"Target function '{target_function_name}' not found in candidate source (name changed or deleted)",
        )

    # 4. Same function name and signature
    sig_ok, sig_err = signatures_equal(orig_fn, cand_fn)
    if not sig_ok:
        return GuardResult(valid=False, error=sig_err)

    # 5. Change ONLY target function line range (plus allowlist imports)
    outside_ok, outside_err = check_only_target_changed(
        orig_ast, cand_ast, target_function_name
    )
    if not outside_ok:
        return GuardResult(valid=False, error=outside_err)

    # 6. Check overall imports allowlist
    orig_mods = extract_all_imports(orig_ast)
    cand_mods = extract_all_imports(cand_ast)
    new_mods = cand_mods - orig_mods
    disallowed = new_mods - ALLOWED_MODULES
    if disallowed:
        return GuardResult(
            valid=False,
            error=f"Candidate added disallowed imports: {sorted(disallowed)}. "
            f"Allowed modules: {sorted(ALLOWED_MODULES)}",
        )

    # 7. Generate diff and changed lines
    diff_text = generate_unified_diff(original_source, candidate_source, filename=filename)
    changed = compute_changed_lines(original_source, candidate_source)

    return GuardResult(
        valid=True,
        error=None,
        patch=diff_text,
        changed_lines=changed,
    )


class FunctionDefFinder(cst.CSTVisitor):
    """CST Visitor to find a function node matching line range or function name."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        function_name: Optional[str] = None,
        function_range: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.function_name = function_name
        self.function_range = function_range
        self.matched_node: Optional[cst.FunctionDef] = None
        self.matched_position: Optional[Tuple[int, int]] = None

    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        start_line = pos.start.line
        end_line = pos.end.line

        name_match = (self.function_name is None) or (node.name.value == self.function_name)
        range_match = True
        if self.function_range is not None:
            r_start, r_end = self.function_range
            # Overlap or inclusion
            range_match = not (end_line < r_start or start_line > r_end)

        if name_match and range_match:
            self.matched_node = node
            self.matched_position = (start_line, end_line)
            return False  # stop visiting children
        return True


def find_target_function_cst(
    module: cst.Module,
    function_name: Optional[str] = None,
    function_range: Optional[Tuple[int, int]] = None,
) -> Tuple[Optional[cst.FunctionDef], Optional[Tuple[int, int]]]:
    """Find a target CST function node using PositionProvider metadata."""
    wrapper = cst.MetadataWrapper(module)
    visitor = FunctionDefFinder(function_name=function_name, function_range=function_range)
    wrapper.visit(visitor)
    return visitor.matched_node, visitor.matched_position


class Template(ABC):
    """Abstract base class for deterministic optimization templates (Mode A)."""

    template_id: str

    @abstractmethod
    def applies(
        self,
        function_node: cst.FunctionDef,
        pattern_match: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if template preconditions hold for the given CST function node and pattern match."""
        pass

    @abstractmethod
    def apply(
        self,
        source: str,
        function_range: Tuple[int, int],
        function_name: Optional[str] = None,
    ) -> Optional[TemplateResult]:
        """Apply transformation. Returns TemplateResult or None when preconditions fail."""
        pass
