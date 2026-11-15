"""Comprehensive tests for Phase 6 Optimization Generation.

Covers:
1. Golden before/after tests for every deterministic template (T1 through T6)
2. At least three negative precondition cases per template (returns None)
3. Shared candidate guards: compile, AST equality outside target function, signature preservation, import allowlist
4. Configurable LLM provider with mocked httpx transport: good output, garbage, multiple functions, forbidden calls, timeout
5. Demo repository slow functions verification and efficient_total rejection
6. Optimization pipeline service and API endpoints
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Tuple
import uuid
import pytest
import httpx
import libcst as cst

from app.core.security import create_access_token
from app.engines.optimizer.llm import (
    LLMDisabledError,
    LLMValidationError,
    NullProvider,
    OpenAICompatibleProvider,
)
from app.engines.optimizer.templates import (
    T1SetMembershipTemplate,
    T2DictIndexJoinTemplate,
    T3MinMaxHeapTemplate,
    T4JoinStringsTemplate,
    T5LruCacheTemplate,
    T6DequePopleftTemplate,
    find_target_function_cst,
    get_template,
    run_shared_guards,
)
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.repository import Repository
from app.models.user import User
from app.services.storage import get_storage_service


def _get_func_range(source: str, func_name: str) -> Tuple[int, int]:
    """Helper to locate start and end line of a function in source."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return (node.lineno, node.end_lineno or node.lineno)
    raise ValueError(f"Function {func_name} not found in source")


def _check_applies(template, source: str, fr: Tuple[int, int]) -> bool:
    """Helper to verify template.applies(function_node) using CST."""
    fn_cst, _ = find_target_function_cst(cst.parse_module(source), function_range=fr)
    if not fn_cst:
        return False
    return template.applies(fn_cst)


# ==============================================================================
# 1. TEMPLATE T1_SET_MEMBERSHIP TESTS
# ==============================================================================

class TestT1SetMembership:
    template = T1SetMembershipTemplate()

    def test_golden_before_after(self):
        source = """def find_matches(items, queries):
    res = []
    for q in queries:
        if q in items:
            res.append(q)
    return res
"""
        fr = _get_func_range(source, "find_matches")
        assert _check_applies(self.template, source, fr) is True
        res = self.template.apply(source, fr)
        assert res is not None
        assert "items_set = set(items)" in res.candidate_source
        assert "if q in items_set:" in res.candidate_source
        assert res.patch != ""
        assert "hashable" in res.safety_notes.lower()
        # Ensure candidate passes shared guards
        g = run_shared_guards(source, res.candidate_source, "find_matches")
        assert g.valid is True

    def test_negative_1_variable_mutated_in_loop(self):
        # Items is mutated inside loop -> unsafe to pre-convert
        source = """def find_matches(items, queries):
    res = []
    for q in queries:
        if q in items:
            res.append(q)
        items.append(q)
    return res
"""
        fr = _get_func_range(source, "find_matches")
        assert self.template.apply(source, fr) is None

    def test_negative_2_variable_reassigned_in_function(self):
        # Items is reassigned in body -> unsafe
        source = """def find_matches(items, queries):
    items = [x for x in items if x > 0]
    res = []
    for q in queries:
        if q in items:
            res.append(q)
    return res
"""
        fr = _get_func_range(source, "find_matches")
        assert self.template.apply(source, fr) is None

    def test_negative_3_not_tested_inside_loop(self):
        # Membership test is outside any loop
        source = """def check_single(items, target):
    if target in items:
        return True
    return False
"""
        fr = _get_func_range(source, "check_single")
        assert self.template.apply(source, fr) is None


# ==============================================================================
# 2. TEMPLATE T2_DICT_INDEX_JOIN TESTS
# ==============================================================================

class TestT2DictIndexJoin:
    template = T2DictIndexJoinTemplate()

    def test_golden_before_after(self):
        source = """def match_records(left, right):
    results = []
    for l in left:
        for r in right:
            if l['id'] == r['left_id']:
                results.append((l, r))
    return results
"""
        fr = _get_func_range(source, "match_records")
        assert _check_applies(self.template, source, fr) is True
        res = self.template.apply(source, fr)
        assert res is not None
        assert "defaultdict(list)" in res.candidate_source
        assert "right_by_key" in res.candidate_source
        assert "from collections import defaultdict" in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "match_records")
        assert g.valid is True

    def test_negative_1_statements_between_loops(self):
        # Statements between outer loop and inner loop break exact join shape
        source = """def match_records(left, right):
    results = []
    for l in left:
        val = l['id']
        for r in right:
            if val == r['left_id']:
                results.append((l, r))
    return results
"""
        fr = _get_func_range(source, "match_records")
        assert self.template.apply(source, fr) is None

    def test_negative_2_non_equality_condition(self):
        # Comparison is inequality (>), not equality (==)
        source = """def match_records(left, right):
    results = []
    for l in left:
        for r in right:
            if l['id'] > r['left_id']:
                results.append((l, r))
    return results
"""
        fr = _get_func_range(source, "match_records")
        assert self.template.apply(source, fr) is None

    def test_negative_3_no_if_condition_in_inner_loop(self):
        # Inner loop does cross-product without if condition
        source = """def cartesian(left, right):
    results = []
    for l in left:
        for r in right:
            results.append((l, r))
    return results
"""
        fr = _get_func_range(source, "cartesian")
        assert self.template.apply(source, fr) is None


# ==============================================================================
# 3. TEMPLATE T3_MIN_MAX_HEAP TESTS
# ==============================================================================

class TestT3MinMaxHeap:
    template = T3MinMaxHeapTemplate()

    def test_golden_before_after_min(self):
        source = """def get_lowest(values):
    return sorted(values)[0]
"""
        fr = _get_func_range(source, "get_lowest")
        assert _check_applies(self.template, source, fr) is True
        res = self.template.apply(source, fr)
        assert res is not None
        assert "min(values)" in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "get_lowest")
        assert g.valid is True

    def test_golden_before_after_max(self):
        source = """def get_highest(values):
    return sorted(values, reverse=True)[0]
"""
        fr = _get_func_range(source, "get_highest")
        res = self.template.apply(source, fr)
        assert res is not None
        assert "max(values)" in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "get_highest")
        assert g.valid is True

    def test_golden_before_after_top_k(self):
        source = """def get_top_k(values, k):
    return sorted(values)[:k]
"""
        fr = _get_func_range(source, "get_top_k")
        res = self.template.apply(source, fr)
        assert res is not None
        assert "heapq.nsmallest(k, values)" in res.candidate_source
        assert "import heapq" in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "get_top_k")
        assert g.valid is True

    def test_negative_1_full_slice(self):
        # Non-k prefix slice (e.g. from index 1 to end) -> cannot turn into min/max/heap
        source = """def get_rest(values):
    return sorted(values)[1:]
"""
        fr = _get_func_range(source, "get_rest")
        assert self.template.apply(source, fr) is None

    def test_negative_2_unindexed_sort(self):
        # Full sorted list returned without indexing or slicing
        source = """def full_sort(values):
    return sorted(values)
"""
        fr = _get_func_range(source, "full_sort")
        assert self.template.apply(source, fr) is None

    def test_negative_3_middle_index(self):
        # Arbitrary middle element (index 5)
        source = """def get_median_guess(values):
    return sorted(values)[5]
"""
        fr = _get_func_range(source, "get_median_guess")
        assert self.template.apply(source, fr) is None


# ==============================================================================
# 4. TEMPLATE T4_JOIN_STRINGS TESTS
# ==============================================================================

class TestT4JoinStrings:
    template = T4JoinStringsTemplate()

    def test_golden_before_after(self):
        source = """def format_items(items):
    out = ""
    for item in items:
        out += str(item) + "\\n"
    return out
"""
        fr = _get_func_range(source, "format_items")
        assert _check_applies(self.template, source, fr) is True
        res = self.template.apply(source, fr)
        assert res is not None
        assert "out_parts = []" in res.candidate_source
        assert "out_parts.append(" in res.candidate_source
        assert 'out = "".join(out_parts)' in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "format_items")
        assert g.valid is True

    def test_negative_1_initialized_from_non_literal(self):
        # Target string initialized from function call, not string literal
        source = """def format_items(header_func, items):
    out = header_func()
    for item in items:
        out += str(item)
    return out
"""
        fr = _get_func_range(source, "format_items")
        assert self.template.apply(source, fr) is None

    def test_negative_2_reassigned_with_non_concat_inside_loop(self):
        # Variable overwritten with something other than concat
        source = """def format_items(items):
    out = ""
    for item in items:
        out = "reset"
    return out
"""
        fr = _get_func_range(source, "format_items")
        assert self.template.apply(source, fr) is None

    def test_negative_3_concatenated_outside_loop(self):
        # Only simple concat outside any loop
        source = """def greet(first, last):
    msg = ""
    msg += first
    msg += " "
    msg += last
    return msg
"""
        fr = _get_func_range(source, "greet")
        assert self.template.apply(source, fr) is None


# ==============================================================================
# 5. TEMPLATE T5_LRU_CACHE TESTS
# ==============================================================================

class TestT5LruCache:
    template = T5LruCacheTemplate()

    def test_golden_before_after(self):
        source = """def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
"""
        fr = _get_func_range(source, "fib")
        assert _check_applies(self.template, source, fr) is True
        res = self.template.apply(source, fr)
        assert res is not None
        assert "@functools.lru_cache(maxsize=None)" in res.candidate_source
        assert "import functools" in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "fib")
        assert g.valid is True

    def test_negative_1_single_self_call_linear_recursion(self):
        # Only 1 self call (linear recursion) -> LRU cache not needed
        source = """def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
        fr = _get_func_range(source, "factorial")
        assert self.template.apply(source, fr) is None

    def test_negative_2_global_or_nonlocal_mutation(self):
        # Function modifies global state
        source = """call_count = 0

def fib(n):
    global call_count
    call_count += 1
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
"""
        fr = _get_func_range(source, "fib")
        assert self.template.apply(source, fr) is None

    def test_negative_3_io_or_randomness(self):
        # Function calls print or random
        source = """import random

def fib(n):
    print("computing", n)
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
"""
        fr = _get_func_range(source, "fib")
        assert self.template.apply(source, fr) is None


# ==============================================================================
# 6. TEMPLATE T6_DEQUE_POPLEFT TESTS
# ==============================================================================

class TestT6DequePopleft:
    template = T6DequePopleftTemplate()

    def test_golden_before_after(self):
        source = """def process_items(raw_data):
    queue = list(raw_data)
    processed = []
    while queue:
        item = queue.pop(0)
        processed.append(item * 2)
    return processed
"""
        fr = _get_func_range(source, "process_items")
        assert _check_applies(self.template, source, fr) is True
        res = self.template.apply(source, fr)
        assert res is not None
        assert "deque(raw_data)" in res.candidate_source
        assert "queue.popleft()" in res.candidate_source
        assert "from collections import deque" in res.candidate_source
        g = run_shared_guards(source, res.candidate_source, "process_items")
        assert g.valid is True

    def test_negative_1_parameter_list_popped(self):
        # List popped is a parameter, not locally created
        source = """def drain_external_queue(queue):
    out = []
    while queue:
        out.append(queue.pop(0))
    return out
"""
        fr = _get_func_range(source, "drain_external_queue")
        # Preconditions strictly forbid modifying function parameters
        assert self.template.apply(source, fr) is None

    def test_negative_2_pop_nonzero_index(self):
        # pop() from end or arbitrary index
        source = """def pop_middle(items):
    q = list(items)
    out = []
    while q:
        out.append(q.pop(1))
    return out
"""
        fr = _get_func_range(source, "pop_middle")
        assert self.template.apply(source, fr) is None

    def test_negative_3_list_mutated_with_nonqueue_methods(self):
        # List mutated with unsupported methods like reverse() or sort()
        source = """def process_sorted_queue(items):
    q = list(items)
    out = []
    while q:
        q.sort()
        out.append(q.pop(0))
    return out
"""
        fr = _get_func_range(source, "process_sorted_queue")
        assert self.template.apply(source, fr) is None


# ==============================================================================
# 7. SHARED GUARDS TESTS
# ==============================================================================

class TestSharedCandidateGuards:
    def test_compile_guard_rejection(self):
        original = "def sample():\n    return 42\n"
        invalid_candidate = "def sample():\n    return 42 syntax error :::"
        res = run_shared_guards(original, invalid_candidate, "sample")
        assert res.valid is False
        assert "compile" in res.error.lower() or "syntax" in res.error.lower()

    def test_signature_preservation_guard_name_change(self):
        original = "def sample(x, y=10):\n    return x + y\n"
        altered = "def different_name(x, y=10):\n    return x + y\n"
        res = run_shared_guards(original, altered, "sample")
        assert res.valid is False
        assert "not found" in res.error.lower() or "signature" in res.error.lower() or "name" in res.error.lower()

    def test_signature_preservation_guard_args_change(self):
        original = "def sample(x, y=10):\n    return x + y\n"
        altered = "def sample(x, z=10):\n    return x + z\n"
        res = run_shared_guards(original, altered, "sample")
        assert res.valid is False
        assert "signature" in res.error.lower() or "parameter" in res.error.lower()

    def test_only_target_function_changed_guard_rejection(self):
        original = """def helper():
    return 1

def target():
    return 2
"""
        # Candidate changes helper() as well as target()
        altered = """def helper():
    return 999

def target():
    return 42
"""
        res = run_shared_guards(original, altered, "target")
        assert res.valid is False
        assert "outside" in res.error.lower()

    def test_import_allowlist_guard_rejection(self):
        original = "def target():\n    return 1\n"
        # Candidate adds an import outside the allowlist (e.g. requests or os)
        disallowed = "import requests\n\ndef target():\n    return 1\n"
        res = run_shared_guards(original, disallowed, "target")
        assert res.valid is False
        assert "disallowed import" in res.error.lower() or "requests" in res.error.lower()

    def test_import_allowlist_guard_allowed_imports(self):
        original = "def target():\n    return 1\n"
        allowed = "import heapq\nfrom collections import defaultdict\n\ndef target():\n    return 1\n"
        res = run_shared_guards(original, allowed, "target")
        assert res.valid is True


# ==============================================================================
# 8. LLM PROVIDER TESTS (WITH MOCKED HTTPX TRANSPORT)
# ==============================================================================

class TestLLMProvider:
    def test_null_provider_raises_disabled_error(self):
        provider = NullProvider()
        with pytest.raises(LLMDisabledError) as exc_info:
            provider.generate(
                source="def f(): pass",
                function_name="f",
                function_range=(1, 1),
                evidence={},
                recommendation={},
            )
        assert "LLM generation is disabled" in str(exc_info.value)

    def test_mocked_llm_good_output(self):
        def handler(request: httpx.Request) -> httpx.Response:
            content = {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Here is the optimized function:\n```python\n"
                                "import heapq\n\n"
                                "def find_k_smallest(items, k):\n"
                                "    return heapq.nsmallest(k, items)\n"
                                "```"
                            )
                        }
                    }
                ]
            }
            return httpx.Response(200, json=content)

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-4o-mini",
            transport=transport,
        )

        original_source = """def find_k_smallest(items, k):
    return sorted(items)[:k]
"""
        fr = _get_func_range(original_source, "find_k_smallest")
        res = provider.generate(
            source=original_source,
            function_name="find_k_smallest",
            function_range=fr,
            evidence={"runtime_pct": 0.4},
            recommendation={"recommended_algorithm": "min_max_builtin_or_heap"},
        )
        assert res is not None
        assert "heapq.nsmallest" in res.candidate_source
        assert res.patch != ""
        g = run_shared_guards(original_source, res.candidate_source, "find_k_smallest")
        assert g.valid is True

    def test_mocked_llm_garbage_output_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "Sorry, I am an AI and cannot help with that code!"}}]})

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            transport=transport,
        )

        with pytest.raises(LLMValidationError) as exc_info:
            provider.generate(
                source="def foo(): return 1",
                function_name="foo",
                function_range=(1, 1),
                evidence={},
                recommendation={},
            )
        err = str(exc_info.value).lower()
        assert "syntax" in err or "did not contain" in err

    def test_mocked_llm_multiple_functions_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            content = {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "```python\n"
                                "def helper(x): return x * 2\n\n"
                                "def foo(x): return helper(x)\n"
                                "```"
                            )
                        }
                    }
                ]
            }
            return httpx.Response(200, json=content)

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            transport=transport,
        )

        with pytest.raises(LLMValidationError) as exc_info:
            provider.generate(
                source="def foo(x): return x * 2",
                function_name="foo",
                function_range=(1, 1),
                evidence={},
                recommendation={},
            )
        assert "multiple" in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "forbidden_snippet",
        [
            "exec('print(1)')",
            "eval('2+2')",
            "open('/etc/passwd')",
            "import os; os.system('ls')",
            "import subprocess; subprocess.run(['ls'])",
            "__import__('sys')",
        ],
    )
    def test_mocked_llm_forbidden_symbols_rejected(self, forbidden_snippet):
        def handler(request: httpx.Request) -> httpx.Response:
            content = {
                "choices": [
                    {
                        "message": {
                            "content": f"```python\ndef dangerous():\n    {forbidden_snippet}\n    return 42\n```"
                        }
                    }
                ]
            }
            return httpx.Response(200, json=content)

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            transport=transport,
        )

        with pytest.raises(LLMValidationError) as exc_info:
            provider.generate(
                source="def dangerous(): return 42",
                function_name="dangerous",
                function_range=(1, 1),
                evidence={},
                recommendation={},
            )
        err = str(exc_info.value).lower()
        assert "forbidden" in err or "disallowed" in err

    def test_mocked_llm_timeout_and_retry(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.ReadTimeout("Request timed out")

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            transport=transport,
        )

        with pytest.raises(RuntimeError) as exc_info:
            provider.generate(
                source="def foo(): return 1",
                function_name="foo",
                function_range=(1, 1),
                evidence={},
                recommendation={},
            )
        # Should have attempted 2 times (initial + 1 retry)
        assert call_count == 2
        err = str(exc_info.value).lower()
        assert "timed out" in err or "timeout" in err or "retry" in err


# ==============================================================================
# 9. DEMO REPOSITORY CANDIDATES & EFFICIENT_TOTAL VERIFICATION
# ==============================================================================

class TestDemoRepoCandidates:
    @pytest.fixture(scope="class")
    def demo_code(self) -> str:
        demo_path = Path("examples/demo_repo/demo/operations.py")
        if not demo_path.exists():
            demo_path = Path("../examples/demo_repo/demo/operations.py")
        assert demo_path.exists(), f"Could not find demo repository at {demo_path}"
        return demo_path.read_text(encoding="utf-8")

    def test_all_six_slow_functions_produce_valid_candidates(self, demo_code):
        test_cases = [
            ("slow_membership", "T1_SET_MEMBERSHIP"),
            ("nested_match", "T2_DICT_INDEX_JOIN"),
            ("repeated_sort", "T3_MIN_MAX_HEAP"),
            ("concat_report", "T4_JOIN_STRINGS"),
            ("fib", "T5_LRU_CACHE"),
            ("drain_queue", "T6_DEQUE_POPLEFT"),
        ]

        for fn_name, t_id in test_cases:
            template = get_template(t_id)
            assert template is not None, f"Template {t_id} not registered"
            fr = _get_func_range(demo_code, fn_name)

            assert _check_applies(template, demo_code, fr) is True, f"Template {t_id} should apply to {fn_name}"
            result = template.apply(demo_code, fr)
            assert result is not None, f"Template {t_id} returned None for {fn_name}"
            assert result.candidate_source != demo_code
            assert len(result.patch) > 0
            assert len(result.changed_lines) > 0

            # Must pass shared candidate guards
            guard_result = run_shared_guards(demo_code, result.candidate_source, fn_name)
            assert guard_result.valid is True, f"{fn_name} failed guards: {guard_result.error}"

    def test_efficient_total_produces_no_candidate(self, demo_code):
        fr = _get_func_range(demo_code, "efficient_total")
        # Ensure none of the 6 templates apply to the already-optimal control function
        all_template_ids = [
            "T1_SET_MEMBERSHIP",
            "T2_DICT_INDEX_JOIN",
            "T3_MIN_MAX_HEAP",
            "T4_JOIN_STRINGS",
            "T5_LRU_CACHE",
            "T6_DEQUE_POPLEFT",
        ]
        for tid in all_template_ids:
            t = get_template(tid)
            assert t is not None
            assert t.apply(demo_code, fr) is None, f"Template {tid} should not apply to efficient_total"


# ==============================================================================
# 10. OPTIMIZATION PIPELINE SERVICE & API TESTS
# ==============================================================================

class TestOptimizationEndpoints:
    @pytest.fixture
    def setup_data(self, db_session):
        user = User(
            id=str(uuid.uuid4()),
            email=f"opt_user_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
            role="developer",
            is_active=True,
        )
        db_session.add(user)
        project = Project(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            name="Opt Project",
        )
        db_session.add(project)
        repo = Repository(
            id=str(uuid.uuid4()),
            project_id=project.id,
            source_type="zip",
            storage_key="repos/test/original.zip",
            status="ready",
        )
        db_session.add(repo)

        storage = get_storage_service()
        demo_path = Path("examples/demo_repo/demo/operations.py")
        if not demo_path.exists():
            demo_path = Path("../examples/demo_repo/demo/operations.py")
        demo_code = demo_path.read_text(encoding="utf-8")
        file_key = f"repos/{repo.id}/files/demo/operations.py"
        storage.put_file(file_key, demo_code.encode("utf-8"))

        file_rec = File(
            id=str(uuid.uuid4()),
            repository_id=repo.id,
            path="demo/operations.py",
            language="python",
            loc=len(demo_code.splitlines()),
            sha256="fake_sha",
            storage_key=file_key,
        )
        db_session.add(file_rec)

        fn_fr = _get_func_range(demo_code, "slow_membership")
        fn = Function(
            id=str(uuid.uuid4()),
            file_id=file_rec.id,
            repository_id=repo.id,
            qualified_name="demo.operations.slow_membership",
            name="slow_membership",
            lineno=fn_fr[0],
            end_lineno=fn_fr[1],
            severity="HIGH",
        )
        db_session.add(fn)

        run = AnalysisRun(
            id=str(uuid.uuid4()),
            repository_id=repo.id,
            requested_by=user.id,
            status="completed",
            stage="completed",
            progress=100,
        )
        db_session.add(run)

        bn = Bottleneck(
            id=str(uuid.uuid4()),
            analysis_run_id=run.id,
            function_id=fn.id,
            severity="HIGH",
            impact_score=0.8,
            evidence={"runtime_pct": 0.45},
        )
        db_session.add(bn)

        rec = Recommendation(
            id=str(uuid.uuid4()),
            bottleneck_id=bn.id,
            current_algorithm="linear_scan",
            recommended_algorithm="hash_set",
            confidence=0.92,
            reason="Linear scan in loop",
            source="rules",
        )
        db_session.add(rec)
        db_session.commit()

        token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}

        return {
            "user": user,
            "project": project,
            "repo": repo,
            "file": file_rec,
            "function": fn,
            "bottleneck": bn,
            "recommendation": rec,
            "headers": headers,
        }

    def test_create_and_get_optimization_template_mode(self, client, db_session, setup_data):
        bn_id = setup_data["bottleneck"].id
        headers = setup_data["headers"]

        # POST /bottlenecks/{id}/optimizations
        resp = client.post(
            f"/api/v1/bottlenecks/{bn_id}/optimizations?sync=true",
            json={"mode": "template"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "generated"
        assert data["mode"] == "template"
        assert data["template_id"] == "T1_SET_MEMBERSHIP"
        assert "ids_set = set(ids)" in data["candidate_code"]
        assert len(data["patch"]) > 0
        opt_id = data["id"]

        # GET /optimizations/{id}
        get_resp = client.get(f"/api/v1/optimizations/{opt_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == opt_id

        # GET /bottlenecks/{id}/optimizations
        list_resp = client.get(f"/api/v1/bottlenecks/{bn_id}/optimizations", headers=headers)
        assert list_resp.status_code == 200
        opts = list_resp.json()
        assert len(opts) >= 1
        assert opts[0]["id"] == opt_id

    def test_create_optimization_llm_mode_disabled(self, client, db_session, setup_data):
        bn_id = setup_data["bottleneck"].id
        headers = setup_data["headers"]

        # With default LLM_PROVIDER=none, should gracefully set status="failed" with clear error
        resp = client.post(
            f"/api/v1/bottlenecks/{bn_id}/optimizations?sync=true",
            json={"mode": "llm"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "failed"
        assert "LLM generation is disabled" in data["error"]

    def test_get_optimizations_config(self, client, setup_data):
        headers = setup_data["headers"]
        resp = client.get("/api/v1/optimizations/config", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_provider" in data
        assert "llm_enabled" in data
        assert "templates" in data
        assert "T1_SET_MEMBERSHIP" in data["templates"]

    def test_owner_scoped_isolation_404(self, client, db_session, setup_data):
        # Other user cannot access optimization (Contract H4)
        other_user = User(
            id=str(uuid.uuid4()),
            email="other_dev@example.com",
            hashed_password="pw",
            role="developer",
            is_active=True,
        )
        db_session.add(other_user)
        db_session.commit()
        other_token = create_access_token(data={"sub": other_user.id, "email": other_user.email, "role": other_user.role})
        other_headers = {"Authorization": f"Bearer {other_token}"}

        bn_id = setup_data["bottleneck"].id
        resp = client.get(f"/api/v1/bottlenecks/{bn_id}/optimizations", headers=other_headers)
        assert resp.status_code == 404
