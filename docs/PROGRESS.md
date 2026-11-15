# AlgoRevive AI - Progress Log

## Current Status: Phase 5 (ML Recommendation Engine) Complete

---

### Phase 5: Machine Learning Recommendation Engine
- **Status:** Completed
- **Goal:** A hybrid recommender (rules + Random Forest / XGBoost) that returns a recommended algorithm or data structure, alternatives, confidence, expected complexity, reasons, and per-feature importance - with graceful fallback to deterministic rules if the model file is missing or low-confidence (< 0.50).

---

### Phase 5 Done Items:

1. **Empirical Dataset Generator (`backend/ml/generate_dataset.py`, `backend/ml/data/dataset.csv`):**
   - Generated a reproducible dataset (4,032 rows) by timing small, trusted reference implementations (original vs. optimized alternative) for each of the 6 Contract G3 patterns across problem sizes ($n \in [100, 200,000]$), operation mixes, data distributions, and memory constraints.
   - Ground-truth labels derive from empirical speedup and memory measurements: alternative assigned if $\text{speedup} \ge 1.2$ and memory growth is acceptable, otherwise `keep_current` (incorporating small-$n$, low-lookup, and single-call cases so the model learns when *not* to optimize).
   - Fixed random seed and deterministic row ordering.
   - Provides `--quick` mode (~672 rows, < 2 minutes) and full mode (4,032 rows, 514 KB CSV, under 3 MB contract limit).
   - Saved in `backend/ml/data/dataset.csv`.

2. **Model Training & Artifacts (`backend/ml/train.py`, `backend/ml/models/recommender.joblib`, `backend/ml/models/metadata.json`, `docs/ML_REPORT.md`):**
   - Implemented stratified 80/20 train/test split with fixed seed (`42`).
   - Trained and evaluated `RandomForestClassifier` and `XGBClassifier`.
   - Tracked all contract metrics: Accuracy, Macro Precision, Macro Recall, Macro F1, Top-3 Accuracy, and Mean Reciprocal Rank (MRR).
   - Both models scored Macro F1 = 1.0000 on held-out test data; Random Forest selected as primary model for explainability and dependency simplicity.
   - Serialized model artifact to `backend/ml/models/recommender.joblib` and comprehensive metadata (feature ordering, classes, metrics, library versions, seed, date) to `backend/ml/models/metadata.json`.
   - Command repeatable via `python -m ml.train` or `docker compose exec backend python -m ml.train`.

3. **Rule-Based Fallback Engine (`backend/app/engines/recommender/rules.py`):**
   - Workload-gated deterministic fallback mapping detected pattern $\to$ candidate class.
   - Enforces workload gating: preserves current implementation (`keep_current`) if input size is low ($n < 50$), lookup frequency is low, call count is 1, or runtime percentage is negligible.
   - Provides expected complexity transitions for each class (e.g., $O(n \cdot m) \to O(n + m)$, $O(2^n) \to O(n)$, $O(n \log n) \to O(1)$).

4. **ML Inference Engine with Pattern Masking & Fallback (`backend/app/engines/recommender/ml.py`):**
   - Thread-safe lazy singleton model loading.
   - Strict pattern compatibility masking (Contract G3/G4 mapping matrix): masks probabilities to only pattern-compatible candidate classes so the model cannot recommend an unrelated algorithm.
   - Automatic fallback to `rules` (`source="rules"`) when:
     - Model artifact (`recommender.joblib`) is missing or fails to load.
     - Top model confidence is below the $0.50$ threshold.
     - Bottleneck has no detected pattern and model confidence is weak.

5. **Data Structure Recommendation & Combined Engine (`backend/app/engines/recommender/datastructures.py`, `backend/app/engines/recommender/__init__.py`):**
   - Workload-aware data structure mapping:
     - List $\to$ Set/Hash for repeated membership queries.
     - Repeated linear lookup $\to$ indexed dict.
     - Priority operations $\to$ min-heap.
     - FIFO queue $\to$ collections.deque.
     - LIFO queue $\to$ list stack.
   - Unified `RecommendationEngine.recommend(bottleneck, features)` coordinating algorithm and data structure proposals into a unified recommendation.

6. **Explainability Engine & Reason Synthesis (`backend/app/engines/recommender/explain.py`):**
   - Per-prediction feature importance extraction: uses SHAP `TreeExplainer` when available, falling back to global Gini importances scaled by per-feature deviations from the training mean.
   - Generates plain-English reason sentences citing top factors with exact real values and percentages (e.g., `"Detected Pattern (LINEAR_MEMBERSHIP_IN_LOOP, 43.3%), Input Size (100 items, 14.9%)..."`).
   - Registered `recommend` analysis pipeline stage in `backend/app/services/analysis_service.py` and persisted results in the `recommendations` table.
   - Implemented `GET /api/v1/bottlenecks/{id}/recommendation` returning the complete recommendation payload.

7. **Frontend Recommendation Panel (`frontend/src/components/RecommendationPanel.tsx`, `BottleneckDetailDrawer.tsx`):**
   - Current $\to$ Recommended visual arrow with source badge (`ML Model` vs `Rule-based Fallback`).
   - Confidence percentage badge / ring.
   - Expected complexity transition card (e.g., $O(n \cdot m) \to O(n + m)$).
   - Alternatives list with individual confidence scores.
   - Horizontal Recharts bar chart displaying ranked feature importance factors.
   - Plain-English reason explanation alert citing real workload metrics.
   - Data structure optimization card displaying current vs. recommended structure and workload reason.

8. **Comprehensive Test Suite (`backend/tests/test_recommender.py`):**
   - 8 comprehensive tests covering:
     - Dataset generator determinism with `--quick`.
     - Model artifact loading and validation of Macro F1 $\ge 0.75$ on held-out split.
     - Pattern masking compatibility ensuring valid candidate recommendations.
     - Graceful fallback to rules when `recommender.joblib` is deleted/missing.
     - Fallback to rules when model prediction confidence is low ($< 0.50$).
     - Feature importance normalization ($\sum \approx 1.0$).
     - Plain-English reason sentence verification citing real workload values.
     - End-to-end integration test on `examples/demo_repo`:
       - `slow_membership` $\to$ `hash_set`
       - `nested_match` $\to$ `hash_map_index`
       - `repeated_sort` $\to$ `min_max_builtin_or_heap`
       - `concat_report` $\to$ `list_join`
       - `fib` $\to$ `memoization_lru`
       - `drain_queue` $\to$ `deque`
       - `efficient_total` $\to$ `keep_current`

---

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
   Assert: 50 passed, 7 skipped (all 8 recommender tests passed; docker isolation tests cleanly skipped when Docker unavailable).

2. **Run Frontend Build & Vitest:**
   ```bash
   cd AlgoRevive_AI/frontend
   npm run build
   npm test
   ```
   Assert: TypeScript strict check, Vite bundle generation, and 7/7 Vitest tests passing.

3. **Verify Demo Repository Recommendations & Control Function:**
   ```bash
   cd AlgoRevive_AI
   $env:PYTHONPATH='backend'
   .venv/Scripts/python -c "
   from app.engines.recommender.ml import MLRecommender
   from app.engines.recommender.rules import RuleBasedRecommender
   from app.models.analysis import FeatureVector
   ml = MLRecommender()
   assert ml.is_available()
   # slow_membership
   fv = FeatureVector(input_size_log10=2.0, current_algorithm_code=0, current_complexity_rank=4, lookup_freq_level=2, insert_ratio=0.0, delete_ratio=0.0, read_write_ratio=10.0, data_distribution_code=0, memory_constraint_level=0, latency_requirement_level=1, call_count_log10=2.0, runtime_pct=0.95)
   pred = ml.predict(fv, allowed_classes=['hash_set', 'keep_current'])
   print('slow_membership:', pred.recommended_class, pred.confidence)
   assert pred.recommended_class == 'hash_set'
   # efficient_total
   fv_eff = FeatureVector(input_size_log10=2.0, current_algorithm_code=-1, current_complexity_rank=2, lookup_freq_level=0, insert_ratio=0.0, delete_ratio=0.0, read_write_ratio=1.0, data_distribution_code=0, memory_constraint_level=0, latency_requirement_level=0, call_count_log10=0.0, runtime_pct=0.01)
   pred_eff = ml.predict(fv_eff, allowed_classes=None)
   print('efficient_total:', pred_eff.recommended_class, pred_eff.confidence)
   assert pred_eff.recommended_class == 'keep_current'
   print('Verification succeeded!')
   "
   ```

4. **Verify Live Bottleneck Explorer & Recommendation Panel in Browser:**
   - Run stack: `docker compose up --build`.
   - Open `http://localhost:5173`, upload `examples/demo_repo/demo_repo.zip`.
   - Run analysis with `algorevive.workload.json`.
   - Inspect the **Ranked Bottlenecks** table: `slow_membership`, `nested_match`, and `fib` appear at the top.
   - Click any bottleneck to open the **Detail Drawer** and inspect the **Recommendation Panel**:
     - Visual arrow (`linear_scan_membership` $\to$ `hash_set`).
     - Confidence ring and expected complexity transition ($O(n \cdot m) \to O(n + m)$).
     - Alternatives list with scores.
     - Horizontal Recharts bar chart showing feature importances.
     - Plain-English reason sentence citing exact runtime metrics.
     - Source badge indicating `ML Model` (or `Rule-based Fallback` when model is omitted).

---

### Limitations
- Phase 6 (Code Transformation Engine) will introduce AST rewriting and candidate code synthesis. In Phase 5, recommendation output is purely algorithmic and data-structure focused without generating executable replacement code.
- In environments without an active Docker daemon, profiling is executed in temporary directories with Python standard library hooks; full container isolation is enforced whenever Docker is active.

---

### Open Questions
- None. All architectural constraints, table schemas, endpoint signatures, and dependencies adhere to `docs/ARCHITECTURE_CONTRACT.md`.
