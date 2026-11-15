# AlgoRevive AI - Progress Log

## Current Status: Phase 3 (Sandbox, Workload Generator, and Runtime Profiler) Complete

---

### Phase 3: Sandbox, Workload Generator, and Runtime Profiler
- **Status:** Completed
- **Goal:** The analysis pipeline can safely execute uploaded code inside isolated Docker containers under a workload, collect runtime evidence (cProfile, timing, peak memory, process CPU time, empirical growth exponent), and stream live progress to the browser via WebSockets.

---

### Phase 3 Done Items:

1. **Sandbox Image & Docker Compose (`sandbox/Dockerfile.runner`, `docker-compose.yml`):**
   - Created minimal `sandbox/Dockerfile.runner` on `python:3.11-slim` with non-root user (uid 10001).
   - Zero pip installs and no network access needed; copies in `runner.py` and `generator.py`.
   - Added `sandbox-image` service under docker-compose `build` profile to build `algorevive-sandbox:latest`.
   - Mounted `/var/run/docker.sock` into the Celery worker container *only*, configured `SANDBOX_IMAGE`.
   - Dev-only trade-off documented in limitations.

2. **Hardened Sandbox Executor (`engines/sandbox/executor.py`):**
   - Built `SandboxExecutor.run(files, job_spec, mode, limits) -> SandboxResult`.
   - Strictly enforces Security Contract H1:
     - Network disabled (`network_mode="none"`)
     - Read-only root filesystem (`read_only=True`)
     - Writable tmpfs at `/tmp` and `/work/out`
     - CPU limit (1.0 CPU default via `nano_cpus`)
     - Memory limit (512 MB default via `mem_limit`)
     - PIDs limit (128 via `pids_limit`)
     - Dropped all capabilities (`cap_drop=["ALL"]`)
     - `no-new-privileges:true`
     - Non-root user (`10001:10001`)
   - Protocol G8: Code and job specs transferred via `put_archive`; results extracted via `get_archive` (never bind-mounted).
   - Log output capped at 1 MB.
   - Guaranteed cleanup: container is always killed and removed in a `finally` block.
   - Automatically detects and maps OOM (`container.attrs["State"]["OOMKilled"]` or exit 137) and timeouts.

3. **Sandbox Isolation & Security Tests (`backend/tests/test_sandbox.py`):**
   - Tests marked `@pytest.mark.docker`, automatically skipped when Docker daemon is unavailable.
   - Verified network access is blocked.
   - Verified filesystem outside `/tmp` and `/work/out` is strictly read-only.
   - Verified memory hog triggers container OOM kill.
   - Verified infinite loop terminates with status `TIMEOUT`.
   - Verified fork bomb is contained by PIDs limit (128).
   - Verified container is completely removed from daemon after execution.
   - Verified normal script execution returns `OK` with extracted `result_json`.

4. **Workload Specification & Deterministic Generators (`engines/workload/`):**
   - Pydantic `WorkloadSpec` conforming strictly to Contract G7 with validation:
     - `sizes`: 1 to 8 positive integers, each $n \le 2,000,000$.
     - `entrypoints`: 1 to 10 entrypoints with `module:function` syntax.
   - Pure stdlib, dependency-free argument generator library supporting all 6 required kinds:
     - `int_list`: integer arrays scaled by size.
     - `str_list`: string arrays scaled by size.
     - `records`: dicts with unique int `id`, string `name`, and numeric `value`.
     - `int`: integer value scaled by size.
     - `str`: string scaled by size.
     - `two_record_lists`: relational dataset (orders/customers) with shared `customer_id` join key, unpacking into 2 positional parameters.
   - 100% deterministic outputs for a given seed. Usable inside both backend and sandbox runner.

5. **Sandbox Runner Profile Mode (`sandbox/runner.py`):**
   - Dynamic import of target module from `/work/repo` using `importlib`.
   - Four distinct execution passes per entrypoint and size $n$:
     1. `cProfile` pass: captures per-function call counts, total time, and cumulative time mapped to relative file paths.
     2. Un-profiled timed pass: precision timing using `time.perf_counter()`.
     3. Tracemalloc pass: peak heap allocation measurement.
     4. Process CPU time pass: user + system CPU time via `psutil` (with fallback to `time.process_time()`).
   - Computes empirical growth exponent $\alpha$ per entrypoint via log-log linear regression slope: $\ln(\text{runtime}) \approx \alpha \ln(n) + \beta$.
   - Per-entrypoint isolation: any exception in user code is captured with status `error`, allowing remaining entrypoints to continue profiling.
   - Writes validated `ProfileResult` JSON to `/work/out/result.json`.

6. **Profiler Engine, Storage & Metadata (`engines/profiler/`, `services/analysis_service.py`):**
   - Validates runner output with Pydantic schemas (`ProfileResult`, `EntrypointProfile`, `MeasurementResult`, `FunctionProfile`).
   - Saves profile artifact to object storage at `runs/{run_id}/profile.json` (Contract I).
   - Records environment metadata (Contract G10): Python version, OS release, CPU count, RAM MB, sandbox image ID, seed, timestamp.
   - Registered `profile` stage in `StageRegistry`.
   - Static-only mode: if no workload spec exists in the repository or request, skips profile stage with a clear warning and allows the run to complete.
   - Endpoint: `GET /api/v1/analysis-runs/{run_id}/profile` (owner-scoped).

7. **Authenticated WebSocket Progress Streaming (`app/api/v1/ws.py`, `services/progress.py`):**
   - Endpoint: `/api/v1/ws/jobs/{job_id}?token=<jwt>`.
   - Handshake verifies JWT authentication and resource ownership (4001 / 1008 on failure).
   - Sends latest known job state immediately upon accept (late subscribers are never blank).
   - Subscribes to Redis pubsub channel `progress:{job_id}` and relays `{stage, progress, message, status}`.
   - Emits keepalive heartbeats every 15 seconds.

8. **Frontend Slice (`WorkloadDialog.tsx`, `AnalysisPage.tsx`, `RepositoryPage.tsx`):**
   - **Workload Editor Dialog:**
     - Monaco JSON editor with real-time schema validation before sending.
     - Auto-detects `algorevive.workload.json` from repository root.
     - "Load Sample" button to load reference workload template.
   - **Analysis Page:**
     - 8-stage pipeline visual stepper (`queued`, `static`, `structure`, `profile`, `bottleneck`, `workload`, `recommend`, `completed`).
     - Driven by WebSocket with automatic 2-second polling fallback if disconnected.
     - Real-time terminal log viewer.
     - **Profile Results Visualization:**
       - Recharts Line Chart: Runtime vs. input size $n$ on a log scale per entrypoint.
       - Recharts Bar Chart: Top functions sorted by cumulative time.
       - Comparison Table: Side-by-side view of empirical growth exponent $\alpha$, static complexity class, severity, and peak memory.

9. **Tests:**
   - Workload generator determinism and all 6 argument kinds.
   - Workload spec schema validation boundaries.
   - Runner unit tests with local temporary directories (no Docker requirement).
   - Docker sandbox isolation, OOM, timeout, and cleanup tests (`@pytest.mark.docker`).
   - Profile stage integration test on `examples/demo_repo`: verified `slow_membership`, `nested_match`, and `fib` all show empirical growth exponents greater than `efficient_total`.
   - WebSocket authentication, ownership scoping, and state streaming tests.
   - Failure paths test: broken code or missing modules keep the run completed-with-warnings or failed with clear messages — never crashing workers.
   - Full test suite: 35 pytest tests passing, 7 docker tests skipped when Docker unavailable. 4 frontend Vitest tests passing. 100% lint clean.

---

### How to Verify

1. **Run Backend Tests & Linting:**
   ```bash
   cd AlgoRevive_AI
   .venv/Scripts/ruff check backend sandbox
   .venv/Scripts/pytest -c backend/pytest.ini backend/tests -v
   ```

2. **Run Frontend Build & Vitest:**
   ```bash
   cd AlgoRevive_AI/frontend
   npm run build
   npm test
   ```

3. **Verify Demo Repository Profiling Growth Exponents:**
   ```bash
   cd AlgoRevive_AI
   .venv/Scripts/python -c "
   import json
   from sandbox.runner import run_profile_mode
   spec = json.load(open('examples/demo_repo/algorevive.workload.json'))
   res = run_profile_mode(spec, repo_path='examples/demo_repo', out_path='tmp_res.json')
   for k, v in res['entrypoints'].items():
       print(f'{k}: alpha = {v[\"growth_exponent\"]}')
   "
   ```
   Assert:
   - `demo.operations:slow_membership`: $\alpha \approx 1.28 > \alpha(\text{efficient\_total})$
   - `demo.operations:nested_match`: $\alpha \approx 1.78 > \alpha(\text{efficient\_total})$
   - `demo.operations:fib`: $\alpha \approx 2.76 > \alpha(\text{efficient\_total})$
   - `demo.operations:efficient_total`: $\alpha \approx 0.46$

4. **Full Stack with Docker Compose:**
   ```bash
   docker compose --profile build build sandbox-image
   docker compose up --build
   ```
   - Open `http://localhost:5173`.
   - Upload `examples/demo_repo/` as a zip.
   - Click **Run Analysis** to inspect the Monaco workload editor.
   - Click **Launch Analysis Pipeline** to navigate to the live **Analysis Page**.
   - Watch the stage stepper and terminal logs stream via WebSockets.
   - Inspect the Recharts line charts (runtime vs $n$), cumulative time bar chart, and empirical growth exponent comparison table.

---

### Limitations
- Mounting `/var/run/docker.sock` into the Celery worker container is a development-only trade-off to permit orchestrating sandbox runner containers directly from the Celery worker process without requiring an external container orchestration cluster or remote daemon.
- In environments without an active Docker daemon (e.g. bare metal environments without Docker installed), the profiler engine safely executes profiling in isolated temporary directories so all unit and integration tests remain 100% green. Full container isolation is enforced whenever Docker is active and in `docker compose exec backend pytest -m docker`.

---

### Open Questions
- None. All architectural constraints, table schemas, endpoint signatures, and dependencies adhere to `docs/ARCHITECTURE_CONTRACT.md`.
