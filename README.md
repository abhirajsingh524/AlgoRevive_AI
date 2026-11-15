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
9. Return to the repository to explore the static analysis tabs:
   - **Files:** Browse source code in the Monaco code editor.
   - **Functions:** Inspect estimated time complexities (`O(n^2)`, `O(2^n)`), severity badges (`LOW`, `HIGH`, `CRITICAL`), loop depths, recursion flags, and detected pattern chips (`LINEAR_MEMBERSHIP_IN_LOOP`, `NAIVE_RECURSION`, etc.).
   - **Call Graph:** Explore an interactive React Flow visualization of function calls with hierarchical layered layout, node severity coloring, fan-in/fan-out metrics, minimap, and zoom controls.

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
