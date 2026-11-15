"""Static code analyzer using Python's ast module.

Extracts classes, functions, methods, nested functions, qualified names,
line ranges, parameters, imports, calls, loop nesting depth, comprehension loops,
direct recursion, cyclomatic complexity, and LOC into function metrics.
Syntax errors are recorded as warnings and never abort analysis.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParameterInfo:
    name: str
    kind: str
    annotation: Optional[str] = None
    default: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImportInfo:
    module: Optional[str]
    name: str
    alias: Optional[str] = None
    lineno: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClassInfo:
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    bases: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    params: List[Dict[str, Any]]
    loop_depth: int
    has_recursion: bool
    metrics: Dict[str, Any]
    docstring: Optional[str] = None
    ast_node: Optional[ast.AST] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "params": self.params,
            "loop_depth": self.loop_depth,
            "has_recursion": self.has_recursion,
            "metrics": self.metrics,
            "docstring": self.docstring,
        }
        return d


@dataclass
class FileAnalysisResult:
    path: str
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "classes": [c.to_dict() for c in self.classes],
            "functions": [f.to_dict() for f in self.functions],
            "imports": [i.to_dict() for i in self.imports],
            "warnings": self.warnings,
        }


def _walk_non_nested(node: ast.AST):
    """Walk child AST nodes without descending into nested functions or classes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield child
        yield from _walk_non_nested(child)


def _compute_loop_depth(fn_node: ast.AST) -> int:
    """Compute maximum loop nesting depth inside the function, ignoring nested functions."""
    max_depth = 0

    def walk_loops(node: ast.AST, current_depth: int):
        nonlocal max_depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                new_depth = current_depth + 1
                if new_depth > max_depth:
                    max_depth = new_depth
                walk_loops(child, new_depth)
            else:
                walk_loops(child, current_depth)

    walk_loops(fn_node, 0)
    return max_depth


def _compute_comprehension_loops(fn_node: ast.AST) -> int:
    """Count comprehension generators inside the function (excluding nested functions)."""
    count = 0
    for node in _walk_non_nested(fn_node):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            count += len(node.generators)
    return count


def _compute_cyclomatic_complexity(fn_node: ast.AST) -> int:
    """Compute McCabe cyclomatic complexity: 1 + decision points."""
    complexity = 1
    for node in _walk_non_nested(fn_node):
        if isinstance(node, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            complexity += 1
        elif isinstance(node, ast.ExceptHandler):
            complexity += 1
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(node, ast.Assert):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += max(0, len(node.values) - 1)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            complexity += len(node.generators)
            for gen in node.generators:
                complexity += len(gen.ifs)
    return complexity


def _get_call_name(node: ast.Call) -> Optional[str]:
    """Extract a dotted or simple identifier string from a Call node."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = []
        curr: ast.AST = node.func
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
        elif isinstance(curr, ast.Call):
            inner = _get_call_name(curr)
            if inner:
                parts.append(inner)
        parts.reverse()
        return ".".join(parts) if parts else None
    return None


def _extract_calls(fn_node: ast.AST) -> List[str]:
    """Extract all called function names/attributes within the function body."""
    calls: List[str] = []
    for node in _walk_non_nested(fn_node):
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name:
                calls.append(call_name)
    return calls


def _detect_recursion(fn_node: ast.AST, fn_name: str) -> tuple[bool, int]:
    """Detect direct recursive self-calls and count their occurrences."""
    recursive_calls = 0
    for node in _walk_non_nested(fn_node):
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name == fn_name or (call_name and call_name.endswith(f".{fn_name}")):
                recursive_calls += 1
    return recursive_calls > 0, recursive_calls


def _extract_decorators(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[str]:
    """Extract decorator names attached to a function."""
    decorators = []
    for dec in fn_node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            parts = []
            curr: ast.AST = dec
            while isinstance(curr, ast.Attribute):
                parts.append(curr.attr)
                curr = curr.value
            if isinstance(curr, ast.Name):
                parts.append(curr.id)
            parts.reverse()
            decorators.append(".".join(parts))
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                parts = []
                curr = dec.func
                while isinstance(curr, ast.Attribute):
                    parts.append(curr.attr)
                    curr = curr.value
                if isinstance(curr, ast.Name):
                    parts.append(curr.id)
                parts.reverse()
                decorators.append(".".join(parts))
    return decorators


def _extract_parameters(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[Dict[str, Any]]:
    """Extract parameters, annotations, and defaults."""
    args_obj = fn_node.args
    params: List[ParameterInfo] = []

    # Map defaults to positional args
    num_args = len(args_obj.args)
    num_defaults = len(args_obj.defaults)
    first_default_idx = num_args - num_defaults

    # Positional-only args
    for idx, arg in enumerate(args_obj.posonlyargs):
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        params.append(
            ParameterInfo(
                name=arg.arg,
                kind="POSITIONAL_ONLY",
                annotation=annotation,
                default=None,
            )
        )

    # Standard positional or keyword args
    for idx, arg in enumerate(args_obj.args):
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        default_val = None
        if idx >= first_default_idx:
            default_node = args_obj.defaults[idx - first_default_idx]
            try:
                default_val = ast.unparse(default_node)
            except Exception:
                default_val = "..."
        params.append(
            ParameterInfo(
                name=arg.arg,
                kind="POSITIONAL_OR_KEYWORD",
                annotation=annotation,
                default=default_val,
            )
        )

    # *vararg
    if args_obj.vararg:
        arg = args_obj.vararg
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        params.append(
            ParameterInfo(
                name=arg.arg,
                kind="VAR_POSITIONAL",
                annotation=annotation,
            )
        )

    # Keyword-only args
    for idx, arg in enumerate(args_obj.kwonlyargs):
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        default_val = None
        if idx < len(args_obj.kw_defaults) and args_obj.kw_defaults[idx] is not None:
            try:
                default_val = ast.unparse(args_obj.kw_defaults[idx])
            except Exception:
                default_val = "..."
        params.append(
            ParameterInfo(
                name=arg.arg,
                kind="KEYWORD_ONLY",
                annotation=annotation,
                default=default_val,
            )
        )

    # **kwargs
    if args_obj.kwarg:
        arg = args_obj.kwarg
        annotation = ast.unparse(arg.annotation) if arg.annotation else None
        params.append(
            ParameterInfo(
                name=arg.arg,
                kind="VAR_KEYWORD",
                annotation=annotation,
            )
        )

    return [p.to_dict() for p in params]


class StaticAnalyzer:
    """AST-based static analyzer for Python source files."""

    def analyze_source(self, source_code: str, file_path: str = "module.py") -> FileAnalysisResult:
        """Parse source code with ast and extract structural entities and metrics."""
        result = FileAnalysisResult(path=file_path)

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as e:
            result.warnings.append(f"Syntax error in {file_path}:{e.lineno}:{e.offset} - {e.msg}")
            return result
        except Exception as e:
            result.warnings.append(f"Failed to parse {file_path}: {e}")
            return result

        # 1. Extract file-level and all imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result.imports.append(
                        ImportInfo(
                            module=None,
                            name=alias.name,
                            alias=alias.asname,
                            lineno=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = ("." * node.level) + (node.module or "")
                for alias in node.names:
                    result.imports.append(
                        ImportInfo(
                            module=mod,
                            name=alias.name,
                            alias=alias.asname,
                            lineno=node.lineno,
                        )
                    )

        # 2. Walk AST tracking class and function hierarchy
        self._analyze_scope(tree, result, scope_prefix=[], current_class=None)

        return result

    def _analyze_scope(
        self,
        node: ast.AST,
        result: FileAnalysisResult,
        scope_prefix: List[str],
        current_class: Optional[str] = None,
    ) -> None:
        """Traverse AST nodes preserving lexical scope for accurate qualified names."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                cls_qualname = ".".join(scope_prefix + [child.name])
                bases = []
                for b in child.bases:
                    try:
                        bases.append(ast.unparse(b))
                    except Exception:
                        bases.append("...")

                class_info = ClassInfo(
                    name=child.name,
                    qualified_name=cls_qualname,
                    lineno=child.lineno,
                    end_lineno=child.end_lineno or child.lineno,
                    bases=bases,
                )
                result.classes.append(class_info)

                # Process class body with updated class context
                self._analyze_scope(
                    child,
                    result,
                    scope_prefix=scope_prefix + [child.name],
                    current_class=child.name,
                )

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_name = child.name
                fn_qualname = ".".join(scope_prefix + [fn_name])
                lineno = child.lineno
                end_lineno = child.end_lineno or lineno
                loc = max(1, end_lineno - lineno + 1)

                loop_depth = _compute_loop_depth(child)
                comprehension_loops = _compute_comprehension_loops(child)
                cyclomatic_complexity = _compute_cyclomatic_complexity(child)
                calls = _extract_calls(child)
                has_recursion, rec_count = _detect_recursion(child, fn_name)
                decorators = _extract_decorators(child)
                params = _extract_parameters(child)
                docstring = ast.get_docstring(child)

                is_method = current_class is not None
                is_nested = len(scope_prefix) > (1 if is_method else 0)

                if is_method and current_class:
                    for c in result.classes:
                        if c.name == current_class:
                            c.methods.append(fn_name)

                metrics = {
                    "loc": loc,
                    "cyclomatic_complexity": cyclomatic_complexity,
                    "loop_depth": loop_depth,
                    "comprehension_loops": comprehension_loops,
                    "has_recursion": has_recursion,
                    "recursive_calls_count": rec_count,
                    "calls": calls,
                    "decorators": decorators,
                    "is_method": is_method,
                    "is_nested": is_nested,
                    "class_name": current_class,
                }

                fn_info = FunctionInfo(
                    name=fn_name,
                    qualified_name=fn_qualname,
                    lineno=lineno,
                    end_lineno=end_lineno,
                    params=params,
                    loop_depth=loop_depth,
                    has_recursion=has_recursion,
                    metrics=metrics,
                    docstring=docstring,
                    ast_node=child,
                )
                result.functions.append(fn_info)

                # Traverse children to extract nested functions
                self._analyze_scope(
                    child,
                    result,
                    scope_prefix=scope_prefix + [fn_name],
                    current_class=current_class,
                )

            else:
                # Recurse into blocks like If, For, While, Try, With to discover nested functions
                self._analyze_scope(
                    child,
                    result,
                    scope_prefix=scope_prefix,
                    current_class=current_class,
                )
