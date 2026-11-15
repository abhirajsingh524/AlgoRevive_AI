ARCHITECTURE CONTRACT - AlgoRevive AI (v1, IMMUTABLE)

A. RULES FOR THE AI AGENT
A1. This contract is law. Never rename, move, replace, or add a framework, service, table, endpoint, folder or dependency that is not listed here. If a task seems to need one, solve it inside the contract and write the question in docs/PROGRESS.md under "Open questions".
A2. Do only the current phase. Do not implement later phases early.
A3. Commit after each logical step with Conventional Commits (feat, fix, test, docs, chore, refactor). Before every commit run lint and tests for what you touched. Never commit failing code, secrets, .env, node_modules, __pycache__ or virtualenvs.
A4. If an install or build fails, fix it by choosing a compatible version of the SAME library. Never swap libraries, never delete or weaken tests to get green, never silence errors.
A5. No fake logic. Everything a phase lists must really work and be tested. No leftover TODO / pass / NotImplementedError in code paths used by tests.
A6. Must run on Windows, macOS and Linux: use pathlib, LF line endings (.gitattributes), and only these required commands: docker compose, pytest, npm, alembic.
A7. At the end of each phase update docs/PROGRESS.md (done, how to verify, limitations, open questions) and print a verification report.

B. STACK (fixed)
Backend: Python 3.11, FastAPI, Pydantic v2 + pydantic-settings, email-validator, SQLAlchemy 2.0 (SYNC) + psycopg2-binary, Alembic, Celery 5 (Redis broker and result backend), redis-py, PyJWT, bcrypt (use the bcrypt package directly, NOT passlib), python-multipart, boto3, docker (Docker SDK), libcst, networkx, psutil, numpy, pandas, scikit-learn, xgboost, joblib, shap (optional import with fallback), jinja2, pyyaml, httpx, pytest, ruff.
Frontend: Node 20, Vite, React 18, TypeScript (strict), Tailwind CSS 3.4 (NOT v4), react-router-dom 6, axios, @monaco-editor/react, recharts, reactflow (v11 package name), lucide-react, vitest, @testing-library/react.
Infra: PostgreSQL 16, Redis 7, MinIO (S3-compatible), Docker Compose, GitHub Actions.

C. REPOSITORY LAYOUT (fixed)
algorevive/
  README.md  docker-compose.yml  .env.example  .gitignore  .gitattributes
  docs/  ARCHITECTURE_CONTRACT.md  PROGRESS.md  API.md  (later: SECURITY.md, ML_REPORT.md)
  scripts/  (e2e_smoke.py, seed_demo.py, check_contract.py, algorevive_ci.py)
  examples/demo_repo/  (sample slow Python code + algorevive.workload.json)
  sandbox/  Dockerfile.runner  runner.py
  .github/workflows/  ci.yml  algorevive-perf.yml
  backend/
    requirements.txt  Dockerfile  entrypoint.sh  alembic.ini  alembic/versions/
    app/
      main.py
      core/  config.py  security.py  logging.py  deps.py  errors.py
      db/  base.py  session.py
      models/  user.py project.py repository.py file.py function.py analysis_run.py bottleneck.py recommendation.py optimization.py benchmark.py test_result.py audit_log.py
      schemas/  (one module per model group)
      api/v1/  router.py auth.py projects.py repositories.py analysis.py bottlenecks.py optimizations.py dashboard.py audit.py health.py ws.py
      services/  storage.py  repository_service.py  analysis_service.py  optimization_service.py  regression_service.py  report_service.py  progress.py
      engines/
        static_analyzer/  complexity/  structure/  profiler/  workload/  bottleneck/
        recommender/ (rules.py ml.py features.py explain.py datastructures.py)
        optimizer/ (templates/  llm/)
        sandbox/  validator/  benchmark/  decision/ (policy.yaml)  explain/
      workers/  celery_app.py  tasks.py
    ml/  generate_dataset.py  train.py  data/  models/
    tests/
  frontend/
    package.json  vite.config.ts  tailwind.config.js  tsconfig.json  Dockerfile
    src/  api/  components/  pages/  hooks/  context/  types/  lib/

D. SERVICES (docker-compose, fixed names and ports)
postgres:5432, redis:6379, minio:9000 (console 9001), backend:8000 (uvicorn), worker (celery, same image as backend), frontend:5173 (Vite dev server, polling file watch enabled so it works on Windows/Docker Desktop). One network: algorevive-net. Sandbox image tag: algorevive-sandbox:latest (built from sandbox/Dockerfile.runner). Environment variables (fixed names): DATABASE_URL, TEST_DATABASE_URL, REDIS_URL, STORAGE_BACKEND (s3|local), S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, LOCAL_STORAGE_DIR, JWT_SECRET, JWT_EXPIRE_MINUTES, CORS_ORIGINS, MAX_UPLOAD_MB, SANDBOX_IMAGE, SANDBOX_TIMEOUT_S, SANDBOX_MEMORY_MB, SANDBOX_CPUS, LLM_PROVIDER (none|openai_compatible), LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, SENTRY_DSN (optional), VITE_API_URL.

E. DATABASE (fixed tables; UUID primary keys; created_at/updated_at timezone-aware UTC)
users(email unique, hashed_password, full_name, is_active, role user|admin)
projects(owner_id, name, description)
repositories(project_id, version_label, source_type zip|files, storage_key, status uploaded|ingested|failed, file_count, total_loc)
files(repository_id, path, language, loc, sha256, storage_key)
functions(file_id, repository_id, qualified_name, name, lineno, end_lineno, params json, complexity_class, complexity_rank int, loop_depth, has_recursion, patterns json, severity, metrics json)
analysis_runs(repository_id, requested_by, status queued|running|completed|failed, stage, progress int, config json, workload_spec json, workload_hash, environment json, error, started_at, finished_at)
bottlenecks(analysis_run_id, function_id, static_score, runtime_score, call_count, runtime_pct, memory_peak_kb, impact_score, severity LOW|MEDIUM|HIGH|CRITICAL, evidence json)
recommendations(bottleneck_id, current_algorithm, recommended_algorithm, alternatives json, expected_complexity, confidence, reason, feature_importance json, source rules|ml)
optimizations(recommendation_id, mode template|llm, template_id, candidate_code, patch, status generated|validating|benchmarking|completed|failed, decision ACCEPT|REVIEW|REJECT|null, decision_reason json, human_review json, error)
benchmark_runs(optimization_id, repetitions, workload json, environment json, status)
benchmark_results(benchmark_run_id, variant original|candidate, size_n, metrics json)
test_results(benchmark_run_id, name, passed, details json)
audit_logs(user_id, action, entity, entity_id, meta json)
All tables are created in the Phase 1 migration. Later phases may add an Alembic revision ONLY for additive columns or indexes their prompt names explicitly.

F. API (prefix /api/v1, JWT bearer, errors are {"detail": str, "code": str})
Auth: POST /auth/register  POST /auth/login  GET /auth/me
Projects: POST /projects  GET /projects  GET|PATCH|DELETE /projects/{project_id}
Repositories: POST|GET /projects/{project_id}/repositories  GET /repositories/{repository_id}  GET /repositories/{repository_id}/files  GET /repositories/{repository_id}/files/{file_id}/content  GET /repositories/{repository_id}/functions  GET /repositories/{repository_id}/call-graph  GET /repositories/{repository_id}/regressions
Analysis: POST|GET /repositories/{repository_id}/analysis-runs  GET /analysis-runs/{run_id}  GET /analysis-runs/{run_id}/profile  GET /analysis-runs/{run_id}/bottlenecks  GET /analysis-runs/{run_id}/report
Bottlenecks: GET /bottlenecks/{bottleneck_id}  GET /bottlenecks/{bottleneck_id}/recommendation  POST|GET /bottlenecks/{bottleneck_id}/optimizations
Optimizations: GET /optimizations/{optimization_id}  GET /optimizations/{optimization_id}/benchmark  GET /optimizations/{optimization_id}/evidence-card  POST /optimizations/{optimization_id}/review
Dashboard: GET /dashboard/summary  GET /dashboard/history
Admin: GET /audit-logs
Health: GET /health  GET /health/ready
WebSocket: /api/v1/ws/jobs/{job_id}?token=<jwt>  (job_id is an analysis_run id or an optimization id)

G. PIPELINES, FORMULAS, POLICIES (fixed)
G1. Analysis pipeline stages, in order: queued, static, structure, profile, bottleneck, workload, recommend, completed. Implemented as a stage registry in services/analysis_service.py; each phase registers its stages; progress is saved on the run and published to Redis channel progress:{id}.
G2. Optimization pipeline stages: generate, validate, benchmark, decide, completed. Registry in services/optimization_service.py. Optimizations are always triggered by a user (POST), never automatically.
G3. Pattern ids: LINEAR_MEMBERSHIP_IN_LOOP, NESTED_LOOP_LOOKUP, REPEATED_SORT_FOR_EXTREME, STRING_CONCAT_IN_LOOP, NAIVE_RECURSION, LIST_POP_FRONT. Template ids map 1:1: T1_SET_MEMBERSHIP, T2_DICT_INDEX_JOIN, T3_MIN_MAX_HEAP, T4_JOIN_STRINGS, T5_LRU_CACHE, T6_DEQUE_POPLEFT.
G4. Recommendation classes: hash_set, hash_map_index, min_max_builtin_or_heap, list_join, memoization_lru, deque, keep_current.
G5. Complexity ranks: O(1)=0, O(log n)=1, O(n)=2, O(n log n)=3, O(n^2)=4, O(n^3)=5, O(2^n)=6. Function severity: rank<=2 LOW, 3 MEDIUM, 4 HIGH, >=5 CRITICAL.
G6. Impact score = 0.40*runtime_pct + 0.25*static_norm + 0.20*call_freq_norm + 0.15*mem_norm, each normalized to 0..1 (static_norm = rank/6; call_freq_norm = log10(1+calls)/log10(1+max_calls); mem_norm = peak_mem/max_peak_mem). If no runtime profile exists: impact = 0.6*static_norm and evidence.source = "static-only". Severity: >=0.75 CRITICAL, >=0.50 HIGH, >=0.25 MEDIUM, else LOW.
G7. Workload spec file (algorevive.workload.json in repo root, or sent in the POST body): {"sizes":[n,...], "entrypoints":[{"function":"module.path:func", "args":[{"kind":"int_list|str_list|records|int|str|two_record_lists", "size_factor":1.0, "fixed":null, "options":{}}]}], "operation_mix":{"lookup":0.9,"insert":0.05,"delete":0.05}, "memory_constraint":"low|medium|high", "latency_target_ms":null, "seed":42}.
G8. Sandbox protocol: python /runner/runner.py --mode profile|validate|benchmark --spec /work/job.json ; code is copied in and results copied out with Docker put_archive/get_archive (never bind-mount host paths); result is /work/out/result.json.
G9. Decision policy (backend/app/engines/decision/policy.yaml): correctness FAIL -> REJECT. ACCEPT if median speedup >= 1.5, 95% bootstrap CI lower bound > 1.1, and memory increase <= 50% (<= 20% when memory_constraint is high). REVIEW if correct and (1.1 <= speedup < 1.5, or speedup >= 1.5 with memory increase in (50%,150%], or speedup >= 1.1 with CI including 1.0). Everything else REJECT. The decision is advice; a human review (POST /optimizations/{id}/review) is always required and nothing is ever auto-applied or auto-merged.
G10. Benchmark defaults: 2 warm-up runs, 7 repetitions, original and candidate alternated (ABAB), median is the headline statistic, gc disabled during timing, memory measured in a separate tracemalloc run, environment metadata recorded (python version, OS, CPU count, RAM, sandbox image id, seed, timestamp).

H. SECURITY INVARIANTS
H1. Uploaded or generated code runs ONLY inside sandbox containers: network disabled, memory 512 MB, 1 CPU, pids limit 128, read-only root filesystem with tmpfs /tmp and /work/out, all capabilities dropped, no-new-privileges, non-root user, 60 s wall timeout, container always removed in a finally block.
H2. Never exec/import uploaded code inside the backend or worker process. Static analysis uses ast/libcst parsing only.
H3. Zip uploads: reject path traversal (zip-slip), absolute paths, symlinks, archives over MAX_UPLOAD_MB (default 50), more than 5000 files, or any single file over 2 MB decompressed.
H4. Every resource is owner-scoped; another user's id returns 404.
H5. Failures set status=failed with an error message; a task failure never crashes the worker or the API; tasks are idempotent.

I. OBJECT STORAGE KEYS (fixed)
repos/{repository_id}/original.zip  repos/{repository_id}/files/{path}  repos/{repository_id}/call_graph.json  runs/{run_id}/profile.json  runs/{run_id}/report.html  optimizations/{optimization_id}/candidate.py  optimizations/{optimization_id}/patch.diff  optimizations/{optimization_id}/evidence_card.json

J. UNIVERSAL DEFINITION OF DONE
docker compose up --build works from a clean clone; alembic upgrade head works on an empty database; pytest, ruff, npm run build and npm test are all green; docs/PROGRESS.md is updated.
