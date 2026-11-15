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

### 2. Run Static Analysis & Call Graph in the Platform
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
7. Explore the three tabs:
   - **Files:** Browse source code in the Monaco code editor.
   - **Functions:** Inspect estimated time complexities (`O(n^2)`, `O(2^n)`), severity badges (`LOW`, `HIGH`, `CRITICAL`), loop depths, recursion flags, and detected pattern chips (`LINEAR_MEMBERSHIP_IN_LOOP`, `NAIVE_RECURSION`, etc.). Clicking any function row opens the file in Monaco, scrolls to the function definition, and highlights its exact line span.
   - **Call Graph:** Explore an interactive React Flow visualization of function calls with hierarchical layered layout, node severity coloring, fan-in/fan-out metrics, minimap, and zoom controls.

---

### Architecture & Progress
- Contract: [docs/ARCHITECTURE_CONTRACT.md](docs/ARCHITECTURE_CONTRACT.md)
- Progress & Status: [docs/PROGRESS.md](docs/PROGRESS.md)
- API Documentation: [docs/API.md](docs/API.md)
