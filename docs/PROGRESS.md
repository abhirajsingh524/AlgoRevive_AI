# AlgoRevive AI - Progress Log

## Current Status: Phase 2 (Static Analysis, Complexity, and Call Graph) Complete

### Phase 2: Static Analysis, Complexity, and Call Graph
- **Status:** Completed
- **Goal:** After uploading a repository, the user can run static analysis and view every function with estimated complexity, detected performance patterns, severity, and an interactive call graph.

---

### Done

1. **Demo Repository (`examples/demo_repo/`):**
   - Created pure stdlib Python package `demo` with all 7 required functions and control function:
     - `slow_membership(users, ids)`: loops over users and checks `u["id"] in ids` where `ids` is a list.
     - `nested_match(orders, customers)`: nested for loops joining on `customer_id == id`.
     - `repeated_sort(values, queries)`: returns `sorted(values)[0]` inside query loop.
     - `concat_report(parts)`: string accumulation with `s += part` in loop.
     - `fib(n)`: naive recursion with two self-calls without memoization.
     - `drain_queue(items)`: while loop calling `pop(0)`.
     - `efficient_total(values)`: control sum loop (guaranteed LOW severity, never flagged HIGH or CRITICAL).
   - Created `algorevive.workload.json` conforming to Contract G7 with all 7 functions.
   - Created `examples/demo_repo/tests/test_demo.py` using standard `unittest`.

2. **AST Static Analyzer Engine (`engines/static_analyzer/`):**
   - Built robust Python AST parser with resilient error handling: `SyntaxError` and `IndentationError` are recorded as warnings in `result.warnings` and never abort execution.
   - Extracts top-level functions, class definitions, methods, and nested functions with accurate lexical qualified names (`Class.method`, `outer.inner`).
   - Extracts parameters (names, annotations, defaults, kinds), imports, and call signatures.
   - Computes loop nesting depth (maximum nested `For`/`While`), comprehension loop counts, direct recursive calls, McCabe cyclomatic complexity, and line ranges into `functions.metrics`.

3. **Rule-Based Complexity Estimator (`engines/complexity/`):**
   - Implemented asymptotic complexity estimator strictly following Contract G5:
     - No loops, no recursion: $O(1)$ [rank 0, LOW]
     - Single loop or comprehension: $O(n)$ [rank 2, LOW]
     - `sorted()` or `.sort()` outside loop: $O(n \log n)$ [rank 3, MEDIUM]
     - Loop depth $k \ge 2$: $O(n^k)$ (depth 2 $\to O(n^2)$ [rank 4, HIGH]; depth 3 $\to O(n^3)$ [rank 5, CRITICAL])
     - Sort inside loop: at least $O(n^2)$ [rank 4, HIGH]
     - Linear membership check (`in`/`not in` on list-like collections) inside loop: adds $+1$ factor of $n$ ($O(n^2)$ [rank 4, HIGH])
     - Single recursive call: $O(n)$ [rank 2, LOW]
     - $\ge 2$ recursive self-calls without memoization: $O(2^n)$ [rank 6, CRITICAL]
     - `@lru_cache` or `@cache` decorator eliminates exponential recursion to $O(n)$ [rank 2, LOW]
   - Fully documented heuristics in module docstring with clear static estimate disclaimer.

4. **Pattern Detector (`engines/static_analyzer/patterns.py`):**
   - Detects exactly the six performance anti-pattern IDs from Contract G3:
     1. `LINEAR_MEMBERSHIP_IN_LOOP`
     2. `NESTED_LOOP_LOOKUP`
     3. `REPEATED_SORT_FOR_EXTREME`
     4. `STRING_CONCAT_IN_LOOP`
     5. `NAIVE_RECURSION`
     6. `LIST_POP_FRONT`
   - Stores line numbers and matched AST node source snippets in `functions.patterns`.
   - Strict preconditions ensure zero false positives on `efficient_total` or other control functions.

5. **Call Graph Builder & Storage (`engines/structure/`):**
   - Constructs a directed graph of function invocations using NetworkX `DiGraph`.
   - Cross-file call resolution: resolves calls through file imports (`from ... import ...`, `import ... as ...`), same-file declarations, self-recursion, and unambiguous symbols.
   - Calculates `fan_in`, `fan_out`, `callers`, and `callees` for every function.
   - Serializes call graph to `repos/{repository_id}/call_graph.json` in object storage.

6. **Orchestrator, Celery Task & REST Endpoints:**
   - Implemented pipeline stage registry in `services/analysis_service.py` adhering to Contract G1; registered `static` and `structure` stages.
   - Background execution via Celery task `run_analysis(run_id)` in `workers/tasks.py`.
   - Idempotent re-run: re-analyzing a repository safely replaces existing function rows without duplicate keys or orphan records.
   - Endpoints implemented:
     - `POST /repositories/{id}/analysis-runs`
     - `GET /repositories/{id}/analysis-runs`
     - `GET /analysis-runs/{id}`
     - `GET /repositories/{id}/functions` (with `file_id`, `severity`, `min_rank`, `pattern` filters; sorted by rank descending)
     - `GET /repositories/{id}/call-graph`
   - Strict owner-scoping: non-owners receive 404 for all analysis endpoints.

7. **Frontend Slice:**
   - Repository page tabs: **Files** | **Functions** | **Call Graph**.
   - Header **Run Analysis** button with live progress tracking, stage status, and automatic refresh.
   - **Functions Tab:** Sortable table displaying function name, qualified name, complexity badge, severity pill, loop depth, recursion status, and pattern chips with hover tooltips. Clicking a row navigates to the file in Monaco, scrolls to the function, and highlights its exact line span.
   - **Call Graph Tab:** Interactive graph rendering using React Flow with custom layered topological layout algorithm (zero external layout dependencies), node coloring by severity, fan-in/fan-out metrics, minimap, and zoom controls.

8. **Testing & Verification:**
   - Golden tests covering positive and negative cases for all 6 patterns.
   - Complexity table unit tests covering ranks 0 through 6 and decorator effects.
   - Syntax-error resilience test.
   - Cross-file call graph resolution test.
   - Demo repository verification test: asserts `slow_membership` and `nested_match` $\ge$ HIGH, `repeated_sort` $\ge$ HIGH, `fib` CRITICAL, and `efficient_total` LOW.
   - API integration tests: run lifecycle, filters, idempotent re-run, and owner isolation.
   - Total backend test suite: 19 pytest tests passing.
   - Total frontend test suite: 4 Vitest tests passing.
   - Linting: 100% green on `ruff check backend` and `npm run build`.

---

### How to Verify

1. **Backend Tests & Linting:**
   ```bash
   cd AlgoRevive_AI
   .venv/Scripts/ruff check backend
   .venv/Scripts/pytest -c backend/pytest.ini backend/tests -v
   ```

2. **Frontend Build & Tests:**
   ```bash
   cd AlgoRevive_AI/frontend
   npm run build
   npm test
   ```

3. **Demo Repository Unit Tests:**
   ```bash
   cd AlgoRevive_AI
   python -m unittest discover -s examples/demo_repo/tests
   ```

4. **Full Stack with Docker Compose:**
   ```bash
   docker compose up --build
   ```
   - Open `http://localhost:5173`
   - Upload `examples/demo_repo` as a zip archive
   - Click **Run Analysis**
   - Verify all 7 demo functions show expected complexity, severities, and detected pattern chips
   - Inspect the interactive call graph in the **Call Graph** tab

---

### Limitations
- Static analysis infers complexity and patterns statically using AST heuristics. Dynamic profiling (cProfile, line_profiler, tracemalloc) and runtime validation in sandbox containers will be introduced in Phase 3.

---

### Open Questions
- None. All architectural constraints, table schemas, endpoint signatures, and dependencies adhere to `docs/ARCHITECTURE_CONTRACT.md`.
