# AlgoRevive AI

AlgoRevive AI is an automated algorithmic code intelligence and performance revival platform. It combines static AST analysis, sandbox-isolated runtime profiling, machine-learned algorithmic recommendations, verified automated optimizations, and comprehensive evidence cards.

## Quickstart

### Prerequisites
- Docker Compose
- Node.js 20+
- Python 3.11+

### Running with Docker Compose
```bash
docker compose up --build
```

Services will be available at:
- **Frontend:** http://localhost:5173
- **Backend API & Swagger Docs:** http://localhost:8000/docs
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379
- **MinIO Console:** http://localhost:9001 (Credentials: `minioadmin` / `minioadmin`)

---

## How to Run the Demo Repository

AlgoRevive includes a reference demo repository at `examples/demo_repo/` with standard-library-only Python code demonstrating classic algorithmic bottlenecks, anti-patterns, and a control function.

### 1. Test Demo Functions Directly
Verify the demo repository's unit tests using Python's built-in `unittest` runner:
```bash
python -m unittest discover -s examples/demo_repo/tests
```

### 2. Run Static Analysis & Runtime Profiling in the Platform
1. Start the stack with `docker compose up --build` and open `http://localhost:5173`.
2. Register an account and sign in.
3. Create a new project (e.g., *Performance Benchmark Demo*).
4. Package the demo repository into a zip:
   ```bash
   cd examples/demo_repo
   python -c "import zipfile, glob; zf = zipfile.ZipFile('demo_repo.zip', 'w'); [zf.write(f) for f in glob.glob('**/*', recursive=True) if not f.endswith('.zip')]; zf.close()"
   ```
5. In the UI, drag and drop `demo_repo.zip` into your project.
6. Open the newly created repository and click **Run Analysis**.
7. In the **Run Analysis & Workload Spec** dialog:
   - Notice the auto-detected `algorevive.workload.json` from the repository root.
   - Edit, modify, or reload sample workload specifications using the embedded Monaco JSON editor with real-time schema validation.
   - Click **Launch Analysis Pipeline**.
8. Follow live analysis progress on the **Analysis Page**:
   - Real-time stage stepper driven by WebSocket (`/api/v1/ws/jobs/{id}`) with automatic 2-second polling fallback.
   - Terminal-style live event log.
   - Upon completion, view the **Runtime Profile Results**:
     - **Recharts Line Chart:** Runtime vs. input size $n$ on a log-log scale per entrypoint demonstrating empirical growth curves.
     - **Recharts Bar Chart:** Top functions sorted by cumulative execution time.
     - **Comparison Table:** Side-by-side comparison of empirical growth exponent $\alpha$, static complexity class ($O(n^2)$, $O(2^n)$), severity, and peak memory.
    - Inspect the **Bottleneck Explorer & Recommendations**:
      - Table of detected bottlenecks ranked by composite impact score (0.40 * runtime_pct + 0.25 * static_norm + 0.20 * call_freq_norm + 0.15 * mem_norm).
      - Severity chips (CRITICAL, HIGH, MEDIUM, LOW) and visual runtime contribution bars.
      - Click any bottleneck to open the **Detail Drawer**:
        - **Recommendation**: Hybrid ML & rule-based recommendation panel with current-to-recommended algorithm arrow, confidence ring, expected complexity transition, alternative candidates, Recharts horizontal feature importance bar chart, plain-English reason sentence citing real values, data structure optimization card, and source badge (`ML` vs `RULES`).
        - **Why Flagged?**: Structured diagnostic tree showing exact weights, metrics, and evidence without invented numbers.
        - **Code Highlight**: Monaco editor highlighting the bottleneck function with exact line numbers.
        - **Workload Profile**: Characterized input size, lookup frequency, insert/delete ratios, read/write ratio, data distribution, and constraints.
        - **Call Graph**: Mini React Flow visualization showing transitive upstream callers with depth and workload coverage badges.
9. Return to the repository to explore the static analysis tabs:
   - **Files:** Browse source code in the Monaco code editor.
   - **Functions:** Inspect estimated time complexities (`O(n^2)`, `O(2^n)`), severity badges (`LOW`, `HIGH`, `CRITICAL`), loop depths, recursion flags, and detected pattern chips (`LINEAR_MEMBERSHIP_IN_LOOP`, `NAIVE_RECURSION`, etc.).
   - **Call Graph:** Explore an interactive React Flow visualization of function calls with hierarchical layered layout, node severity coloring, fan-in/fan-out metrics, minimap, and zoom controls.

---

## Candidate Optimization Generation (Phase 6)

AlgoRevive AI generates safe, minimal candidate implementations for identified bottlenecks:
- **Mode A (Deterministic Templates - Default):** Always available with zero external dependencies. Employs LibCST AST transformers to preserve original comments, formatting, and invariants for 6 Contract G3 algorithmic patterns:
  1. `T1_SET_MEMBERSHIP`: Converts read-only list membership checks inside loops into a pre-computed hash set.
  2. `T2_DICT_INDEX_JOIN`: Transforms $O(N \times M)$ nested equality loops into an indexed `defaultdict(list)` join.
  3. `T3_MIN_MAX_HEAP`: Replaces `sorted(X)[0]`, `sorted(X, reverse=True)[0]`, and `sorted(X)[:k]` with `min(X)`, `max(X)`, and `heapq.nsmallest(k, X)`.
  4. `T4_JOIN_STRINGS`: Accumulates string loop concatenations in a list joined with `"".join(...)`.
  5. `T5_LRU_CACHE`: Adds `@functools.lru_cache(maxsize=None)` to multi-recursive pure functions.
  6. `T6_DEQUE_POPLEFT`: Converts FIFO queue lists consumed via `pop(0)` into `collections.deque` and `popleft()`.

- **Mode B (Configurable LLM Synthesis - Optional):** Disabled by default (`LLM_PROVIDER=none`). Allows optional synthesis via any OpenAI-compatible server (OpenAI, Ollama, vLLM).

### Enabling an LLM Provider
To enable Mode B, configure the following environment variables in your `.env` or container environment:
```bash
# Enable OpenAI-compatible provider
LLM_PROVIDER=openai_compatible

# Server endpoint (e.g. OpenAI, Ollama, or local vLLM)
LLM_BASE_URL=https://api.openai.com/v1
# Or local Ollama: http://localhost:11434/v1
# Or local vLLM:   http://localhost:8000/v1

# Authentication key (or dummy key for local Ollama/vLLM)
LLM_API_KEY=sk-your-openai-api-key

# Model name
LLM_MODEL=gpt-4o-mini
# Or local Ollama model: qwen2.5-coder:7b
```

### Strict Candidate Safety Guards
Every candidate generated by either mode must pass rigorous AST and security checks before acceptance:
1. **Compilation & Parsing Guard:** Must cleanly pass Python `compile()` and re-parse via both `ast` and `libcst`.
2. **Signature Preservation Guard:** Function name, parameter names, argument counts, default values, and type annotations must remain identical.
3. **Target Scope Guard:** Modifies ONLY the target function's line range. AST of all code outside the function must match original AST identically.
4. **Strict Import Allowlist:** Added imports are strictly restricted to: `functools`, `collections`, `heapq`, `bisect`, `itertools`, `math`, `operator`.
5. **Forbidden Symbol Rejection (LLM):** Rejects any candidate containing `exec`, `eval`, `compile`, `open`, `__import__`, `os`, `sys`, `subprocess`, `socket`, or `ctypes`.
6. **Execution Safeguard:** Candidate code is NEVER executed or auto-applied in Phase 6; candidates are stored as diff artifacts (`optimizations/{id}/candidate.py`, `patch.diff`).

---

### Machine Learning Recommender Training
To regenerate the empirical dataset and train the recommendation models (RandomForest and XGBoost):
```bash
# Generate empirical benchmark dataset (4,000+ rows)
python -m ml.generate_dataset

# Train models, select best by Macro F1, and save artifacts
python -m ml.train
# Or inside docker:
docker compose exec backend python -m ml.train
```

---

### Sandbox Runner Image Build
To build the sandbox runner image used for isolated code execution:
```bash
docker compose --profile build build sandbox-image
```

---

### Architecture & Progress
- Contract: [docs/ARCHITECTURE_CONTRACT.md](docs/ARCHITECTURE_CONTRACT.md)
- Progress & Status: [docs/PROGRESS.md](docs/PROGRESS.md)
- API Documentation: [docs/API.md](docs/API.md)
- ML Evaluation Report: [docs/ML_REPORT.md](docs/ML_REPORT.md)
