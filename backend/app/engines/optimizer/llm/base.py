"""LLM Provider interface, prompt builder, output parser, and safety guards.

Conforms to Contract Phase 6 specifications:
- LLMProvider interface
- NullProvider raising clear 'LLM disabled' error
- Prompt builder sending ONLY function source, evidence, and recommendation
- Strict parser requiring exactly one function definition
- Strict security guards rejecting forbidden calls: exec, eval, compile, open, __import__, os, sys, subprocess, socket, ctypes
- Shared guards enforcement (AST equality outside target, imports allowlist, compile, signature matching)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import ast
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import libcst as cst

from app.engines.optimizer.templates.base import (
    ALLOWED_MODULES,
    TemplateResult,
)

FORBIDDEN_SYMBOLS: Set[str] = {
    "exec",
    "eval",
    "compile",
    "open",
    "__import__",
    "os",
    "sys",
    "subprocess",
    "socket",
    "ctypes",
}


class LLMDisabledError(RuntimeError):
    """Raised when LLM generation is requested but LLM_PROVIDER is none."""

    pass


class LLMValidationError(ValueError):
    """Raised when LLM output fails security guards, parsing, or signature validation."""

    pass


def check_forbidden_symbols(tree: ast.AST) -> Optional[str]:
    """Inspect AST for forbidden calls or references:

    exec, eval, compile, open, __import__, os, sys, subprocess, socket, ctypes
    """
    for node in ast.walk(tree):
        # 1. Names
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_SYMBOLS:
            return f"Candidate contains forbidden symbol '{node.id}'"

        # 2. Attributes (e.g. os.system, sys.exit)
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_SYMBOLS:
                return f"Candidate accesses forbidden attribute '{node.attr}'"
            if isinstance(node.value, ast.Name) and node.value.id in FORBIDDEN_SYMBOLS:
                return f"Candidate accesses forbidden module or object '{node.value.id}'"

        # 3. Imports
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod_root = alias.name.split(".")[0]
                if mod_root in FORBIDDEN_SYMBOLS:
                    return f"Candidate imports forbidden module '{mod_root}'"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod_root = node.module.split(".")[0]
                if mod_root in FORBIDDEN_SYMBOLS:
                    return f"Candidate imports from forbidden module '{mod_root}'"

    return None


class PromptBuilder:
    """Builds minimal prompt sending ONLY target function, evidence, and recommendation."""

    @staticmethod
    def build(
        function_source: str,
        evidence: Dict[str, Any],
        recommendation: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        system_content = (
            "You are a performance optimization expert for Python code. "
            "Your task is to optimize the provided target function according to the recommendation and evidence. "
            "CRITICAL CONSTRAINTS:\n"
            "1. Output ONLY valid Python code containing EXACTLY ONE function definition.\n"
            "2. Preserve the exact function name, parameter names, default arguments, and return annotations.\n"
            "3. You may ONLY import from the standard allowlist: functools, collections, heapq, bisect, itertools, math, operator.\n"
            "4. NEVER use exec, eval, compile, open, __import__, os, sys, subprocess, socket, ctypes.\n"
            "5. Do NOT include any explanations, markdown commentary, or introductory text."
        )

        user_content = (
            f"TARGET FUNCTION SOURCE:\n```python\n{function_source}\n```\n\n"
            f"RECOMMENDATION:\n"
            f"- Recommended Algorithm / Structure: {recommendation.get('recommended_algorithm')}\n"
            f"- Expected Complexity: {recommendation.get('expected_complexity')}\n"
            f"- Rationale: {recommendation.get('reason')}\n\n"
            f"WORKLOAD EVIDENCE:\n"
            f"- Runtime contribution: {evidence.get('runtime_pct', 0.0)}\n"
            f"- Call count: {evidence.get('call_count', 0)}\n"
            f"- Complexity rank: {evidence.get('static_score', 0)}\n"
            f"- Workload characteristics: {evidence.get('workload', {})}\n\n"
            f"Please output the optimized replacement function definition now:"
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]


class OutputParser:
    """Strictly parses LLM output into a single validated function and required imports."""

    @staticmethod
    def parse(llm_output: str) -> Tuple[str, List[str]]:
        """Extract exactly one function definition and any allowed top-level imports.

        Returns (function_code, list_of_import_statements).
        Raises LLMValidationError if output contains 0 or >1 functions, or syntax errors.
        """
        cleaned = llm_output.strip()

        # Extract code from markdown fences if present
        fence_match = re.search(r"```(?:python)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        elif cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()

        # Parse AST
        try:
            tree = ast.parse(cleaned)
        except Exception as e:
            raise LLMValidationError(f"LLM output failed Python syntax parse: {e}")

        # Check forbidden symbols across entire output
        forbidden_err = check_forbidden_symbols(tree)
        if forbidden_err:
            raise LLMValidationError(forbidden_err)

        functions: List[ast.FunctionDef | ast.AsyncFunctionDef] = []
        imports: List[str] = []

        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(stmt)
            elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                # Verify import against allowlist
                if isinstance(stmt, ast.Import):
                    for a in stmt.names:
                        root = a.name.split(".")[0]
                        if root not in ALLOWED_MODULES:
                            raise LLMValidationError(
                                f"LLM added disallowed import '{root}'. Allowed: {sorted(ALLOWED_MODULES)}"
                            )
                elif isinstance(stmt, ast.ImportFrom):
                    if stmt.module:
                        root = stmt.module.split(".")[0]
                        if root not in ALLOWED_MODULES:
                            raise LLMValidationError(
                                f"LLM added disallowed import '{root}'. Allowed: {sorted(ALLOWED_MODULES)}"
                            )
                imports.append(ast.unparse(stmt))
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                # Allow module docstring
                continue
            else:
                raise LLMValidationError(
                    f"LLM output contained unexpected top-level statement: {type(stmt).__name__}. "
                    f"Only function definitions and allowed imports are permitted."
                )

        if len(functions) == 0:
            raise LLMValidationError("LLM output did not contain any function definition")
        if len(functions) > 1:
            fn_names = [f.name for f in functions]
            raise LLMValidationError(
                f"LLM output contained multiple ({len(functions)}) function definitions {fn_names}, "
                f"expected exactly one"
            )

        target_fn_code = ast.unparse(functions[0])
        return target_fn_code, imports


class LLMProvider(ABC):
    """Abstract interface for LLM candidate generators."""

    @abstractmethod
    def generate(
        self,
        source: str,
        function_name: str,
        function_range: Tuple[int, int],
        evidence: Dict[str, Any],
        recommendation: Dict[str, Any],
    ) -> TemplateResult:
        """Generate optimized candidate implementation using LLM synthesis."""
        pass


class NullProvider(LLMProvider):
    """Default provider when LLM_PROVIDER=none."""

    def generate(
        self,
        source: str,
        function_name: str,
        function_range: Tuple[int, int],
        evidence: Dict[str, Any],
        recommendation: Dict[str, Any],
    ) -> TemplateResult:
        raise LLMDisabledError(
            "LLM generation is disabled (LLM_PROVIDER=none). "
            "To enable LLM synthesis, configure LLM_PROVIDER=openai_compatible with "
            "LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL in environment or settings."
        )


def splice_candidate_function(
    original_source: str,
    target_function_name: str,
    target_function_code: str,
    new_imports: List[str],
) -> str:
    """Replace target function in original CST and prepend any new allowlist imports."""
    mod_cst = cst.parse_module(original_source)
    new_fn_cst = cst.parse_module(target_function_code).body[0]

    class Replacer(cst.CSTTransformer):
        def __init__(self) -> None:
            self.replaced = False

        def leave_FunctionDef(
            self, orig_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.FunctionDef:
            if orig_node.name.value == target_function_name and not self.replaced:
                self.replaced = True
                return new_fn_cst  # type: ignore[return-value]
            return updated_node

    transformed = mod_cst.visit(Replacer())

    # Prepend new imports
    if new_imports:
        import_stmts = [cst.parse_statement(f"{imp}\n") for imp in new_imports]
        transformed = transformed.with_changes(body=import_stmts + list(transformed.body))

    return transformed.code
