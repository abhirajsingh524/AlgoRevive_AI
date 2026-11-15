# AlgoRevive AI - Progress Log

## Current Status: Phase 4 (Bottlenecks, Workload Characterization and Explainability) Complete

---

### Phase 4: Bottlenecks, Workload Characterization and Explainability
- **Status:** Completed
- **Goal:** Combine static AST analysis and runtime profiling evidence into a ranked, explained list of bottlenecks, and turn the workload into the exact 12-dimensional feature vector the ML model will use in Phase 5.

---

### Phase 4 Done Items:

1. **Impact Scoring Engine & Severity Evaluation (`engines/bottleneck/scorer.py`, `engines/bottleneck/detector.py`):**
   - Implemented exact Contract G6 formula:
     $$\text{impact\_score} = 0.40 \cdot \text{runtime\_pct} + 0.25 \cdot \text{static\_norm} + 0.20 \cdot \text{call\_freq\_norm} + 0.15 \cdot \text{mem\_norm}$$
   - Normalizations:
     - $\text{static\_norm} = \text{complexity\_rank} / 6.0$
     - $\text{call\_freq\_norm} = \log_{10}(1 + \text{calls}) / \log_{10}(1 + \text{max\_calls})$ (0.0 if max_calls is 0)
     - $\text{mem\_norm} = \text{peak\_mem\_kb} / \text{max\_peak\_mem\_kb}$ (0.0 if max_peak_mem is 0)
     - $\text{runtime\_pct} = \text{function's cumulative profile time} / \text{total entrypoint time}$
   - Severity thresholds (Contract G6):
     - $\ge 0.75$: `CRITICAL`
     - $\ge 0.50$: `HIGH`
     - $\ge 0.25$: `MEDIUM`
     - $< 0.25$: `LOW`
   - Static-only fallback (when no runtime profile is present):
     $$\text{impact\_score} = 0.60 \cdot \text{static\_norm}, \quad \text{evidence.source} = \text{"static-only"}$$
   - Filters candidate bottlenecks by $\text{impact\_score} \ge 0.10$.
   - Control function `efficient_total` comes out `LOW` ($\text{static\_norm} = 2/6$, impact $\approx 0.15 - 0.20 < 0.25$).
   - Registered `bottleneck` stage in `services/analysis_service.py`.

2. **Workload Characterization Profile (`engines/workload/profiler.py`):**
   - Derived `WorkloadProfile` stored in `bottlenecks.evidence["workload"]`:
     - `input_size`: largest $n$ from workload spec sizes
     - `lookup_frequency`: `LOW` / `MEDIUM` / `HIGH` / `VERY_HIGH` derived from `operation_mix.lookup` thresholds ($0.2 / 0.5 / 0.8$), or inferred from detected patterns (`LINEAR_MEMBERSHIP_IN_LOOP` $\to$ `HIGH`, `NESTED_LOOP_LOOKUP` $\to$ `HIGH`)
     - `insert_ratio`: float from `operation_mix.insert`
     - `delete_ratio`: float from `operation_mix.delete`
     - `read_write_ratio`: ratio of read/lookup operations to write operations
     - `data_distribution`: `uniform` / `sorted` / `skewed` from generator options (default `uniform`)
     - `memory_constraint`: `LOW` / `MEDIUM` / `HIGH` from `spec.memory_constraint`
     - `latency_requirement`: `LOW` / `MEDIUM` / `HIGH` / `VERY_HIGH` from `latency_target_ms` (default `MEDIUM`)
   - Registered `workload` stage in `services/analysis_service.py`.

3. **Fixed ML Feature Vector Contract (`engines/workload/features.py`):**
   - **IMMUTABLE CONTRACT FOR PHASE 5:** Fixed 12-dimensional vector in exact order:
     1. `input_size_log10` (float): $\log_{10}(\max(1, \text{input\_size}))$
     2. `current_algorithm_code` (int): integer index of primary pattern ID from Contract G3 (-1 if none)
     3. `current_complexity_rank` (int): asymptotic complexity rank $0..6$ (Contract G5)
     4. `lookup_freq_level` (int): $\text{LOW}=0, \text{MEDIUM}=1, \text{HIGH}=2, \text{VERY\_HIGH}=3$
     5. `insert_ratio` (float): insert operation ratio ($0..1$)
     6. `delete_ratio` (float): delete operation ratio ($0..1$)
     7. `read_write_ratio` (float): ratio of read/lookup to write operations
     8. `data_distribution_code` (int): $\text{uniform}=0, \text{sorted}=1, \text{skewed}=2$
     9. `memory_constraint_level` (int): $\text{LOW}=0, \text{MEDIUM}=1, \text{HIGH}=2$
     10. `latency_requirement_level` (int): $\text{LOW}=0, \text{MEDIUM}=1, \text{HIGH}=2, \text{VERY\_HIGH}=3$
     11. `call_count_log10` (float): $\log_{10}(1 + \text{call\_count})$
     12. `runtime_pct` (float): runtime contribution percentage ($0..1$)
   - Provided `to_array()` returning the ordered list of 12 numerical features.
   - Saved in `bottlenecks.evidence["features"]` and `bottlenecks.evidence["features_array"]`.

4. **Affected Dependency Analysis (`engines/structure/dependencies.py`):**
   - Analyzes transitive callers using NetworkX directed call graph stored in `repos/{repository_id}/call_graph.json`.
   - Computes shortest topological call distance/depth from target bottleneck function.
   - Flags callers covered by workload spec entrypoints (`covered_by_workload: bool`).
   - Saved in `bottlenecks.evidence["affected_functions"]`.

5. **Explainability Engine & "WHY FLAGGED?" Tree (`engines/explain/why_flagged.py`):**
   - Builds structured hierarchical tree (`reason`, `metric`, `value`, `weight`, `children`) mirroring the SRS specification.
   - Zero invented numbers: every value is extracted directly from stored bottleneck, function, and workload evidence.
   - Saved in `bottlenecks.evidence["why_flagged"]`.

6. **Bottlenecks API Endpoints (`backend/app/api/v1/bottlenecks.py`):**
   - `GET /api/v1/analysis-runs/{id}/bottlenecks`: lists ranked bottlenecks sorted by `impact_score desc`, with optional filters (`severity`, `min_impact`, `pattern`).
   - `GET /api/v1/bottlenecks/{id}`: retrieves full bottleneck detail with complete evidence payload.
   - `GET /api/v1/bottlenecks/{id}/recommendation`: returns `404 Not Found` with error code `NOT_READY` until Phase 5.
   - Strict owner scoping across all endpoints (returns 404 for unauthorized users).

7. **Frontend Slice (`BottleneckExplorer.tsx`, `BottleneckDetailDrawer.tsx`, `WhyFlaggedTree.tsx`, `MiniCallGraph.tsx`, `BottleneckExplorerPage.tsx`):**
   - **Bottleneck Explorer:** Table sorted by impact score with severity chips, visual runtime contribution progress bars, and search/severity filters.
   - **Static-Only Badge:** Prominently highlights when an analysis run was executed without runtime profiling.
   - **Detail Drawer:**
     - **Why Flagged?:** Interactive hierarchical tree visualizing exact formula weights and metrics.
     - **Code Highlight:** Monaco editor focusing on the bottleneck function with line range selection.
     - **Workload Profile:** Diagnostic cards showing input size, operation ratios, distribution, and constraints.
     - **Call Graph:** React Flow interactive canvas displaying upstream callers, depths, and workload coverage badges.

8. **Tests (`backend/tests/test_bottlenecks.py`):**
   - Formula unit tests with hand-calculated numbers.
   - Severity boundary tests (0.25, 0.50, 0.75 exact edge cases).
   - Static-only fallback validation.
   - FeatureVector order, field definitions, and range tests.
   - Explanation tree validation verifying all numbers match stored evidence.
   - Integration test on `examples/demo_repo`: verified `slow_membership`, `nested_match`, and `fib` rank at the top with plausible runtime percentages, and `efficient_total` comes out `LOW` ($\text{impact} < 0.25$).
   - Ownership isolation tests verifying 404 on unowned runs/bottlenecks and 404 `NOT_READY` for recommendations.

---

### Feature Mapping Table (Phase 5 ML Contract)

| Dimension # | Feature Name | Type | Allowed Values / Encoding | Description |
|---|---|---|---|---|
| 1 | `input_size_log10` | `float` | $[0.0, 7.0]$ | $\log_{10}(\max(1, \text{input\_size}))$ |
| 2 | `current_algorithm_code` | `int` | $0$: `LINEAR_MEMBERSHIP_IN_LOOP`<br>$1$: `NESTED_LOOP_LOOKUP`<br>$2$: `REPEATED_SORT_FOR_EXTREME`<br>$3$: `STRING_CONCAT_IN_LOOP`<br>$4$: `NAIVE_RECURSION`<br>$5$: `LIST_POP_FRONT`<br>$-1$: None / Other | Integer index of primary detected pattern (Contract G3) |
| 3 | `current_complexity_rank` | `int` | $0$: $O(1)$<br>$1$: $O(\log n)$<br>$2$: $O(n)$<br>$3$: $O(n \log n)$<br>$4$: $O(n^2)$<br>$5$: $O(n^3)$<br>$6$: $O(2^n)$ | Asymptotic time complexity rank (Contract G5) |
| 4 | `lookup_freq_level` | `int` | $0$: `LOW` ($< 0.2$)<br>$1$: `MEDIUM` ($0.2 \le x < 0.5$)<br>$2$: `HIGH` ($0.5 \le x < 0.8$)<br>$3$: `VERY_HIGH` ($\ge 0.8$) | Workload lookup frequency level |
| 5 | `insert_ratio` | `float` | $[0.0, 1.0]$ | Insert operation ratio in workload mix |
| 6 | `delete_ratio` | `float` | $[0.0, 1.0]$ | Delete operation ratio in workload mix |
| 7 | `read_write_ratio` | `float` | $[0.0, 100.0]$ | Ratio of read operations to write operations |
| 8 | `data_distribution_code` | `int` | $0$: `uniform`<br>$1$: `sorted`<br>$2$: `skewed` | Input dataset value distribution |
| 9 | `memory_constraint_level` | `int` | $0$: `LOW`<br>$1$: `MEDIUM`<br>$2$: `HIGH` | Memory budget constraint tier |
| 10 | `latency_requirement_level` | `int` | $0$: `LOW` ($> 200\text{ ms}$)<br>$1$: `MEDIUM` ($50\text{ ms} < x \le 200\text{ ms}$)<br>$2$: `HIGH` ($10\text{ ms} < x \le 50\text{ ms}$)<br>$3$: `VERY_HIGH` ($\le 10\text{ ms}$) | Latency target requirement tier |
| 11 | `call_count_log10` | `float` | $[0.0, 8.0]$ | $\log_{10}(1 + \text{call\_count})$ |
| 12 | `runtime_pct` | `float` | $[0.0, 1.0]$ | Cumulative function runtime / total entrypoint runtime |

---

### How to Verify

1. **Run Backend Test Suite:**
   ```bash
   cd AlgoRevive_AI
   .venv/Scripts/ruff check backend sandbox
   .venv/Scripts/pytest -c backend/pytest.ini backend/tests -v
   ```
   Assert: 42 passed, 7 skipped (docker isolation tests cleanly skipped when Docker unavailable).

2. **Run Frontend Build & Vitest:**
   ```bash
   cd AlgoRevive_AI/frontend
   npm run build
   npm test
   ```
   Assert: TypeScript strict check, Vite bundle generation, and 4/4 Vitest tests passing.

3. **Verify Demo Repository Bottleneck Ranks & Control Function:**
   ```bash
   cd AlgoRevive_AI
   $env:PYTHONPATH='backend'
   .venv/Scripts/python -c "
   import json
   from app.engines.bottleneck.scorer import calculate_impact
   # slow_membership: rank 4, runtime_pct ~0.95 -> impact >= 0.70 (HIGH/CRITICAL)
   sm = calculate_impact(complexity_rank=4, runtime_pct=0.95, call_count=100, max_calls=100, memory_peak_kb=100, max_peak_mem_kb=100)
   print('slow_membership:', sm.impact_score, sm.severity)
   # efficient_total: rank 2, runtime_pct ~0.02 -> impact < 0.25 (LOW)
   eff = calculate_impact(complexity_rank=2, runtime_pct=0.02, call_count=1, max_calls=100, memory_peak_kb=10, max_peak_mem_kb=100)
   print('efficient_total:', eff.impact_score, eff.severity)
   assert eff.severity == 'LOW'
   assert sm.impact_score > eff.impact_score
   "
   ```

4. **Verify Live Bottleneck Explorer in Browser:**
   - Run stack: `docker compose up --build`.
   - Open `http://localhost:5173`, upload `examples/demo_repo/demo_repo.zip`.
   - Run analysis with `algorevive.workload.json`.
   - Inspect the **Ranked Bottlenecks** table: `slow_membership`, `nested_match`, and `fib` appear at the top.
   - Click any bottleneck to open the **Detail Drawer** and inspect the **Why Flagged?** tree, Monaco highlighted code, workload profile, and React Flow caller graph.

---

### Limitations
- Recommendations endpoint (`GET /bottlenecks/{id}/recommendation`) returns `404 Not Found` with `code: "NOT_READY"` until Phase 5 (Rule & ML-based Recommender).
- In environments without an active Docker daemon, profiling is executed in temporary directories with Python standard library hooks; full container isolation is enforced whenever Docker is active.

---

### Open Questions
- None. All architectural constraints, table schemas, endpoint signatures, and dependencies adhere to `docs/ARCHITECTURE_CONTRACT.md`.
