import os
from app.engines.complexity import ComplexityEstimator
from app.engines.static_analyzer import PatternDetector, StaticAnalyzer
from app.engines.structure import CallGraphBuilder


def test_syntax_error_resilience():
    analyzer = StaticAnalyzer()
    bad_code = "def broken(x\n    return x + 1"
    result = analyzer.analyze_source(bad_code, file_path="broken.py")

    assert len(result.warnings) == 1
    assert "Syntax error" in result.warnings[0]
    assert len(result.functions) == 0


def test_complexity_table_rules():
    analyzer = StaticAnalyzer()
    estimator = ComplexityEstimator()

    # Rank 0: O(1)
    res_o1 = analyzer.analyze_source("def f(x):\n    return x * 2 + 1", "test.py")
    est_o1 = estimator.estimate(res_o1.functions[0])
    assert est_o1.complexity_class == "O(1)"
    assert est_o1.complexity_rank == 0
    assert est_o1.severity == "LOW"

    # Rank 2: O(n) - Single loop
    res_on = analyzer.analyze_source("def f(vals):\n    s = 0\n    for v in vals:\n        s += v\n    return s", "test.py")
    est_on = estimator.estimate(res_on.functions[0])
    assert est_on.complexity_class == "O(n)"
    assert est_on.complexity_rank == 2
    assert est_on.severity == "LOW"

    # Rank 2: O(n) - Single recursion
    res_rec1 = analyzer.analyze_source("def f(n):\n    if n <= 1: return 1\n    return n * f(n - 1)", "test.py")
    est_rec1 = estimator.estimate(res_rec1.functions[0])
    assert est_rec1.complexity_class == "O(n)"
    assert est_rec1.complexity_rank == 2
    assert est_rec1.severity == "LOW"

    # Rank 3: O(n log n) - Sort outside loop
    res_sort = analyzer.analyze_source("def f(vals):\n    return sorted(vals)", "test.py")
    est_sort = estimator.estimate(res_sort.functions[0])
    assert est_sort.complexity_class == "O(n log n)"
    assert est_sort.complexity_rank == 3
    assert est_sort.severity == "MEDIUM"

    # Rank 4: O(n^2) - Nested loops (depth 2)
    res_on2 = analyzer.analyze_source("def f(a, b):\n    for x in a:\n        for y in b:\n            pass", "test.py")
    est_on2 = estimator.estimate(res_on2.functions[0])
    assert est_on2.complexity_class == "O(n^2)"
    assert est_on2.complexity_rank == 4
    assert est_on2.severity == "HIGH"

    # Rank 5: O(n^3) - Depth 3
    res_on3 = analyzer.analyze_source("def f(a, b, c):\n    for x in a:\n        for y in b:\n            for z in c:\n                pass", "test.py")
    est_on3 = estimator.estimate(res_on3.functions[0])
    assert est_on3.complexity_class == "O(n^3)"
    assert est_on3.complexity_rank == 5
    assert est_on3.severity == "CRITICAL"

    # Rank 6: O(2^n) - Two recursive self-calls without memoization
    res_exp = analyzer.analyze_source("def f(n):\n    if n <= 1: return 1\n    return f(n - 1) + f(n - 2)", "test.py")
    est_exp = estimator.estimate(res_exp.functions[0])
    assert est_exp.complexity_class == "O(2^n)"
    assert est_exp.complexity_rank == 6
    assert est_exp.severity == "CRITICAL"

    # Memoized recursion reduces exponential to O(n)
    res_memo = analyzer.analyze_source("@lru_cache\ndef f(n):\n    if n <= 1: return 1\n    return f(n - 1) + f(n - 2)", "test.py")
    est_memo = estimator.estimate(res_memo.functions[0])
    assert est_memo.complexity_class == "O(n)"
    assert est_memo.complexity_rank == 2
    assert est_memo.severity == "LOW"


def test_golden_patterns_positive_and_negative():
    analyzer = StaticAnalyzer()
    detector = PatternDetector()

    # 1. LINEAR_MEMBERSHIP_IN_LOOP
    pos_code = "def f(users, ids: list):\n    for u in users:\n        if u['id'] in ids:\n            pass"
    neg_code = "def f(users, ids: set):\n    for u in users:\n        if u['id'] in ids:\n            pass"
    p_pos = detector.detect_patterns(analyzer.analyze_source(pos_code).functions[0])
    p_neg = detector.detect_patterns(analyzer.analyze_source(neg_code).functions[0])
    assert any(p.pattern_id == "LINEAR_MEMBERSHIP_IN_LOOP" for p in p_pos)
    assert not any(p.pattern_id == "LINEAR_MEMBERSHIP_IN_LOOP" for p in p_neg)

    # 2. NESTED_LOOP_LOOKUP
    pos_nested = "def f(orders, customers):\n    for o in orders:\n        for c in customers:\n            if o['customer_id'] == c['id']:\n                pass"
    neg_nested = "def f(orders, customers):\n    for o in orders:\n        pass\n    for c in customers:\n        pass"
    p_pos = detector.detect_patterns(analyzer.analyze_source(pos_nested).functions[0])
    p_neg = detector.detect_patterns(analyzer.analyze_source(neg_nested).functions[0])
    assert any(p.pattern_id == "NESTED_LOOP_LOOKUP" for p in p_pos)
    assert not any(p.pattern_id == "NESTED_LOOP_LOOKUP" for p in p_neg)

    # 3. REPEATED_SORT_FOR_EXTREME
    pos_sort = "def f(vals, queries):\n    for q in queries:\n        m = sorted(vals)[0]"
    neg_sort = "def f(vals, queries):\n    m = sorted(vals)[0]\n    for q in queries:\n        pass"
    p_pos = detector.detect_patterns(analyzer.analyze_source(pos_sort).functions[0])
    p_neg = detector.detect_patterns(analyzer.analyze_source(neg_sort).functions[0])
    assert any(p.pattern_id == "REPEATED_SORT_FOR_EXTREME" for p in p_pos)
    assert not any(p.pattern_id == "REPEATED_SORT_FOR_EXTREME" for p in p_neg)

    # 4. STRING_CONCAT_IN_LOOP
    pos_concat = "def f(parts):\n    s = ''\n    for p in parts:\n        s += p\n    return s"
    neg_concat = "def f(vals):\n    total = 0\n    for v in vals:\n        total += v\n    return total"
    p_pos = detector.detect_patterns(analyzer.analyze_source(pos_concat).functions[0])
    p_neg = detector.detect_patterns(analyzer.analyze_source(neg_concat).functions[0])
    assert any(p.pattern_id == "STRING_CONCAT_IN_LOOP" for p in p_pos)
    assert not any(p.pattern_id == "STRING_CONCAT_IN_LOOP" for p in p_neg)

    # 5. NAIVE_RECURSION
    pos_rec = "def fib(n):\n    if n <= 1: return n\n    return fib(n - 1) + fib(n - 2)"
    neg_rec = "@lru_cache\ndef fib(n):\n    if n <= 1: return n\n    return fib(n - 1) + fib(n - 2)"
    p_pos = detector.detect_patterns(analyzer.analyze_source(pos_rec).functions[0])
    p_neg = detector.detect_patterns(analyzer.analyze_source(neg_rec).functions[0])
    assert any(p.pattern_id == "NAIVE_RECURSION" for p in p_pos)
    assert not any(p.pattern_id == "NAIVE_RECURSION" for p in p_neg)

    # 6. LIST_POP_FRONT
    pos_pop = "def f(items):\n    q = list(items)\n    while q:\n        x = q.pop(0)"
    neg_pop = "def f(items):\n    q = list(items)\n    while q:\n        x = q.pop()"
    p_pos = detector.detect_patterns(analyzer.analyze_source(pos_pop).functions[0])
    p_neg = detector.detect_patterns(analyzer.analyze_source(neg_pop).functions[0])
    assert any(p.pattern_id == "LIST_POP_FRONT" for p in p_pos)
    assert not any(p.pattern_id == "LIST_POP_FRONT" for p in p_neg)


def test_call_graph_cross_file_resolution():
    builder = CallGraphBuilder()
    functions_data = [
        {
            "id": "fn-1",
            "name": "service_entry",
            "qualified_name": "app.service.service_entry",
            "file_id": "file-1",
            "file_path": "app/service.py",
            "lineno": 10,
            "end_lineno": 15,
            "severity": "LOW",
            "complexity_class": "O(n)",
            "complexity_rank": 2,
            "calls": ["database_query"],
        },
        {
            "id": "fn-2",
            "name": "database_query",
            "qualified_name": "app.db.database_query",
            "file_id": "file-2",
            "file_path": "app/db.py",
            "lineno": 5,
            "end_lineno": 12,
            "severity": "HIGH",
            "complexity_class": "O(n^2)",
            "complexity_rank": 4,
            "calls": [],
        },
    ]

    file_imports = {
        "app/service.py": [
            {"module": "app.db", "name": "database_query", "alias": "database_query"}
        ]
    }

    graph_res = builder.build_graph("repo-test", functions_data, file_imports)

    assert graph_res.node_count == 2
    assert graph_res.edge_count == 1
    edge = graph_res.edges[0]
    assert edge["source"] == "fn-1"
    assert edge["target"] == "fn-2"

    caller_node = next(n for n in graph_res.nodes if n["id"] == "fn-1")
    callee_node = next(n for n in graph_res.nodes if n["id"] == "fn-2")
    assert caller_node["fan_out"] == 1
    assert caller_node["fan_in"] == 0
    assert callee_node["fan_in"] == 1
    assert callee_node["fan_out"] == 0


def test_demo_repo_contract_expectations():
    """Assert contract requirements for demo repository functions:

    slow_membership and nested_match HIGH or above
    repeated_sort HIGH or above
    fib CRITICAL
    efficient_total LOW
    """
    demo_file = os.path.abspath("examples/demo_repo/demo/operations.py")
    with open(demo_file, "r") as f:
        code = f.read()

    analyzer = StaticAnalyzer()
    estimator = ComplexityEstimator()
    detector = PatternDetector()

    res = analyzer.analyze_source(code, "operations.py")
    fn_map = {fn.name: fn for fn in res.functions}

    assert len(fn_map) == 7

    # 1. slow_membership: HIGH or above
    est_slow = estimator.estimate(fn_map["slow_membership"])
    assert est_slow.severity in ("HIGH", "CRITICAL")
    assert est_slow.complexity_rank >= 4
    p_slow = detector.detect_patterns(fn_map["slow_membership"])
    assert any(p.pattern_id == "LINEAR_MEMBERSHIP_IN_LOOP" for p in p_slow)

    # 2. nested_match: HIGH or above
    est_nested = estimator.estimate(fn_map["nested_match"])
    assert est_nested.severity in ("HIGH", "CRITICAL")
    assert est_nested.complexity_rank >= 4
    p_nested = detector.detect_patterns(fn_map["nested_match"])
    assert any(p.pattern_id == "NESTED_LOOP_LOOKUP" for p in p_nested)

    # 3. repeated_sort: HIGH or above
    est_sort = estimator.estimate(fn_map["repeated_sort"])
    assert est_sort.severity in ("HIGH", "CRITICAL")
    assert est_sort.complexity_rank >= 4
    p_sort = detector.detect_patterns(fn_map["repeated_sort"])
    assert any(p.pattern_id == "REPEATED_SORT_FOR_EXTREME" for p in p_sort)

    # 4. fib: CRITICAL
    est_fib = estimator.estimate(fn_map["fib"])
    assert est_fib.severity == "CRITICAL"
    assert est_fib.complexity_rank == 6
    p_fib = detector.detect_patterns(fn_map["fib"])
    assert any(p.pattern_id == "NAIVE_RECURSION" for p in p_fib)

    # 5. concat_report
    p_concat = detector.detect_patterns(fn_map["concat_report"])
    assert any(p.pattern_id == "STRING_CONCAT_IN_LOOP" for p in p_concat)

    # 6. drain_queue
    p_drain = detector.detect_patterns(fn_map["drain_queue"])
    assert any(p.pattern_id == "LIST_POP_FRONT" for p in p_drain)

    # 7. efficient_total: LOW (must never be flagged HIGH or CRITICAL)
    est_total = estimator.estimate(fn_map["efficient_total"])
    assert est_total.severity == "LOW"
    assert est_total.complexity_rank <= 2
    p_total = detector.detect_patterns(fn_map["efficient_total"])
    assert len(p_total) == 0
