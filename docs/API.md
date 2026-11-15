# AlgoRevive AI - API Reference (Phase 6: Candidate Optimization Generation)

All endpoints are prefixed with `/api/v1`. Authentication uses standard HTTP Bearer tokens with JWT: `Authorization: Bearer <access_token>`.

Standard Error Response format:
```json
{
  "detail": "Error description message",
  "code": "ERROR_CODE_STRING"
}
```

---

## 1. System Health

### GET `/api/v1/health`
Returns system liveness and basic service configuration.

- **Auth Required:** No
- **Response 200 OK:**
```json
{
  "status": "healthy",
  "app_name": "AlgoRevive AI",
  "version": "1.0.0"
}
```

### GET `/api/v1/health/ready`
Verifies database, Redis broker, and object storage connectivity.

- **Auth Required:** No
- **Response 200 OK:**
```json
{
  "status": "ready",
  "database": "connected",
  "redis": "connected",
  "storage": "connected"
}
```
- **Response 503 Service Unavailable:** If any critical subsystem check fails.

---

## 2. Authentication

### POST `/api/v1/auth/register`
Registers a new user account. Passwords must be at least 8 characters (max 72 bytes). Hashes password using `bcrypt` directly. Logs audit event `user.registered`.

- **Auth Required:** No
- **Request Body (`application/json`):**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "Jane Developer"
}
```
- **Response 201 Created:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@example.com",
  "full_name": "Jane Developer",
  "is_active": true,
  "role": "user",
  "created_at": "2026-11-15T12:00:00Z",
  "updated_at": "2026-11-15T12:00:00Z"
}
```
- **Errors:**
  - `400 Bad Request` (`PASSWORD_TOO_SHORT`): Password must be at least 8 characters.
  - `400 Bad Request` (`PASSWORD_TOO_LONG`): Password exceeds maximum length of 72 bytes.
  - `409 Conflict` (`EMAIL_ALREADY_REGISTERED`): Email is already registered.

---

### POST `/api/v1/auth/login`
Authenticates user credentials and issues a JWT access token. Logs audit event `user.login`.

- **Auth Required:** No
- **Request Body (`application/json`):**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```
- **Response 200 OK:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "user@example.com",
    "full_name": "Jane Developer",
    "is_active": true,
    "role": "user",
    "created_at": "2026-11-15T12:00:00Z",
    "updated_at": "2026-11-15T12:00:00Z"
  }
}
```
- **Errors:**
  - `401 Unauthorized` (`INVALID_CREDENTIALS`): Incorrect email or password.
  - `403 Forbidden` (`INACTIVE_USER`): Account has been deactivated.

---

### GET `/api/v1/auth/me`
Fetches current authenticated user profile.

- **Auth Required:** Yes (`Bearer <token>`)
- **Response 200 OK:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@example.com",
  "full_name": "Jane Developer",
  "is_active": true,
  "role": "user",
  "created_at": "2026-11-15T12:00:00Z",
  "updated_at": "2026-11-15T12:00:00Z"
}
```
- **Errors:**
  - `401 Unauthorized` (`UNAUTHORIZED`): Missing, invalid, or expired bearer token.

---

## 3. Projects

Projects are strictly owner-scoped. Users can only read and mutate their own projects. Access to other users' projects returns `404 Not Found`.

### POST `/api/v1/projects`
Create a new project. Logs audit event `project.created`.

- **Auth Required:** Yes
- **Request Body (`application/json`):**
```json
{
  "name": "Backend Optimization Suite",
  "description": "Core algorithm benchmarking and optimization workspace"
}
```
- **Response 201 Created:**
```json
{
  "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "owner_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Backend Optimization Suite",
  "description": "Core algorithm benchmarking and optimization workspace",
  "created_at": "2026-11-15T12:00:00Z",
  "updated_at": "2026-11-15T12:00:00Z"
}
```

---

### GET `/api/v1/projects`
List all projects owned by the authenticated user.

- **Auth Required:** Yes
- **Response 200 OK:**
```json
[
  {
    "id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "owner_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "name": "Backend Optimization Suite",
    "description": "Core algorithm benchmarking and optimization workspace",
    "created_at": "2026-11-15T12:00:00Z",
    "updated_at": "2026-11-15T12:00:00Z"
  }
]
```

---

### GET `/api/v1/projects/{project_id}`
Retrieve a specific project by UUID. Returns 404 if the project does not exist or belongs to another user.

- **Auth Required:** Yes
- **Response 200 OK:** Project JSON schema as above.
- **Errors:**
  - `404 Not Found` (`PROJECT_NOT_FOUND`): Project not found.

---

### PATCH `/api/v1/projects/{project_id}`
Update project details (`name` or `description`). Logs audit event `project.updated`.

- **Auth Required:** Yes
- **Request Body (`application/json`):**
```json
{
  "name": "Renamed Suite",
  "description": "Updated project description"
}
```
- **Response 200 OK:** Updated Project JSON schema.

---

### DELETE `/api/v1/projects/{project_id}`
Delete a project and cascade delete associated repositories. Logs audit event `project.deleted`.

- **Auth Required:** Yes
- **Response 204 No Content**

---

## 4. Repositories & Ingestion

### POST `/api/v1/projects/{project_id}/repositories`
Uploads code to ingest. Accepts either a single `.zip` archive or multiple `.py` files using `multipart/form-data`.
Enforces Security Invariant H3:
- Rejects zip-slip paths (`..`)
- Rejects absolute paths (`/` or `C:\`)
- Rejects symbolic links
- Archive max size: 50MB (decompressed file max: 2MB)
- Max file count: 5,000 files
- Ignores `.git`, `__pycache__`, `venv`, `.venv`, `node_modules`

Files are saved into storage under `repos/{repo_id}/original.zip` and `repos/{repo_id}/files/{path}`.
Lines of code (LOC) and SHA-256 hashes are computed for each indexed file.

- **Auth Required:** Yes
- **Request Form Data (`multipart/form-data`):**
  - `version_label` (string, optional, defaults to "v1.0.0")
  - `file` (UploadFile, optional if uploading zip)
  - `files` (List of UploadFiles, optional if uploading multiple `.py` files)
- **Response 201 Created:**
```json
{
  "id": "e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
  "project_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "version_label": "v1.0.0",
  "source_type": "zip",
  "storage_key": "repos/e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e/original.zip",
  "status": "ingested",
  "file_count": 5,
  "total_loc": 450,
  "created_at": "2026-11-15T12:00:00Z",
  "updated_at": "2026-11-15T12:00:00Z"
}
```
- **Errors:**
  - `400 Bad Request` (`SECURITY_VIOLATION`): Zip-slip, absolute path, or symlink detected.
  - `400 Bad Request` (`FILE_TOO_LARGE`): Single file exceeds 2MB limit.
  - `400 Bad Request` (`ARCHIVE_TOO_LARGE`): Zip exceeds 50MB.
  - `400 Bad Request` (`TOO_MANY_FILES`): File count exceeds 5,000 files.
  - `400 Bad Request` (`EMPTY_REPOSITORY`): No valid Python files found.

---

### GET `/api/v1/projects/{project_id}/repositories`
List all repositories under a specific project.

- **Auth Required:** Yes
- **Response 200 OK:** Array of Repository objects.

---

### GET `/api/v1/repositories/{repository_id}`
Retrieve a repository record by ID.

- **Auth Required:** Yes
- **Response 200 OK:** Repository JSON schema.
- **Errors:**
  - `404 Not Found` (`REPOSITORY_NOT_FOUND`)

---

### GET `/api/v1/repositories/{repository_id}/files`
List all indexed source files in the repository.

- **Auth Required:** Yes
- **Response 200 OK:**
```json
[
  {
    "id": "f8a7b6c5-d4e3-2f1a-0b9c-8d7e6f5a4b3c",
    "repository_id": "e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
    "path": "app/main.py",
    "language": "python",
    "loc": 120,
    "sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "storage_key": "repos/e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e/files/app/main.py",
    "created_at": "2026-11-15T12:00:00Z",
    "updated_at": "2026-11-15T12:00:00Z"
  }
]
```

---

### GET `/api/v1/repositories/{repository_id}/files/{file_id}/content`
Retrieve the text content of a single indexed file for display in the Monaco editor.

- **Auth Required:** Yes
- **Response 200 OK:**
```json
{
  "file_id": "f8a7b6c5-d4e3-2f1a-0b9c-8d7e6f5a4b3c",
  "path": "app/main.py",
  "language": "python",
  "content": "def run():\n    print('Hello World')\n"
}
```
- **Errors:**
  - `404 Not Found` (`FILE_NOT_FOUND`): File record or content not found.


---

## 5. Static Analysis & Functions

### POST `/api/v1/repositories/{repository_id}/analysis-runs`
Initiates a new asynchronous static analysis run for the repository.

- **Auth Required:** Yes
- **Request Body (`application/json`, optional):**
```json
{
  "config": {}
}
```
- **Response 201 Created:**
```json
{
  "id": "7b8c9d0e-1f2a-3b4c-5d6e-7f8a9b0c1d2e",
  "repository_id": "e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
  "requested_by": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "queued",
  "stage": "queued",
  "progress": 0,
  "config": {},
  "workload_spec": null,
  "workload_hash": null,
  "environment": null,
  "error": null,
  "started_at": null,
  "finished_at": null,
  "created_at": "2026-11-15T12:00:00Z",
  "updated_at": "2026-11-15T12:00:00Z"
}
```

---

### GET `/api/v1/repositories/{repository_id}/analysis-runs`
Lists all analysis runs executed for this repository.

- **Auth Required:** Yes
- **Response 200 OK:** Array of AnalysisRun objects, ordered newest first.

---

### GET `/api/v1/analysis-runs/{run_id}`
Retrieves the execution status, current stage, and progress of an analysis run.

- **Auth Required:** Yes
- **Response 200 OK:** AnalysisRun object.
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Run does not exist or user is not the owner.

---

### GET `/api/v1/repositories/{repository_id}/functions`
Retrieves all functions extracted via static AST analysis for the repository, ordered by `complexity_rank` descending.

- **Auth Required:** Yes
- **Query Parameters (optional):**
  - `file_id` (string): Filter functions belonging to a specific file.
  - `severity` (string): Filter by severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - `min_rank` (integer): Filter by minimum complexity rank (0..6).
  - `pattern` (string): Filter by detected pattern ID (`LINEAR_MEMBERSHIP_IN_LOOP`, `NESTED_LOOP_LOOKUP`, `REPEATED_SORT_FOR_EXTREME`, `STRING_CONCAT_IN_LOOP`, `NAIVE_RECURSION`, `LIST_POP_FRONT`).
- **Response 200 OK:**
```json
[
  {
    "id": "1c2d3e4f-5a6b-7c8d-9e0f-1a2b3c4d5e6f",
    "file_id": "f8a7b6c5-d4e3-2f1a-0b9c-8d7e6f5a4b3c",
    "repository_id": "e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
    "qualified_name": "demo.operations.slow_membership",
    "name": "slow_membership",
    "lineno": 7,
    "end_lineno": 13,
    "params": [
      {
        "name": "users",
        "kind": "POSITIONAL_OR_KEYWORD",
        "annotation": "List[Dict[str, Any]]",
        "default": null
      },
      {
        "name": "ids",
        "kind": "POSITIONAL_OR_KEYWORD",
        "annotation": "List[int]",
        "default": null
      }
    ],
    "complexity_class": "O(n^2)",
    "complexity_rank": 4,
    "loop_depth": 1,
    "has_recursion": false,
    "patterns": [
      {
        "pattern_id": "LINEAR_MEMBERSHIP_IN_LOOP",
        "line_number": 11,
        "matched_snippet": "u['id'] in ids"
      }
    ],
    "severity": "HIGH",
    "metrics": {
      "loc": 7,
      "cyclomatic_complexity": 3,
      "loop_depth": 1,
      "comprehension_loops": 0,
      "has_recursion": false,
      "recursive_calls_count": 0,
      "calls": ["matched.append"],
      "decorators": [],
      "is_method": false,
      "is_nested": false,
      "class_name": null,
      "complexity_reason": "Loop nesting depth 1; linear list membership check inside loop adds factor of n -> O(n^2)"
    },
    "created_at": "2026-11-15T12:00:00Z",
    "updated_at": "2026-11-15T12:00:00Z"
  }
]
```

---

### GET `/api/v1/repositories/{repository_id}/call-graph`
Retrieves the function call hierarchy graph generated by NetworkX cross-file analysis.

- **Auth Required:** Yes
- **Response 200 OK:**
```json
{
  "repository_id": "e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
  "node_count": 7,
  "edge_count": 1,
  "nodes": [
    {
      "id": "1c2d3e4f-...",
      "name": "fib",
      "qualified_name": "demo.operations.fib",
      "file_id": "f8a7b6c5-...",
      "file_path": "demo/operations.py",
      "lineno": 44,
      "end_lineno": 48,
      "severity": "CRITICAL",
      "complexity_class": "O(2^n)",
      "complexity_rank": 6,
      "fan_in": 1,
      "fan_out": 1,
      "callers": ["1c2d3e4f-..."],
      "callees": ["1c2d3e4f-..."]
    }
  ],
  "edges": [
    {
      "source": "1c2d3e4f-...",
      "target": "1c2d3e4f-...",
      "call_count": 2
    }
  ]
}
```
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Call graph has not been generated yet. Trigger an analysis run first.

---

## 6. Runtime Profiler & WebSocket Progress (Phase 3)

### POST `/api/v1/repositories/{repository_id}/analysis-runs`
Triggers an analysis pipeline execution on the specified repository with optional custom workload specification conforming to Contract G7.

- **Auth Required:** Yes
- **Request Body (`application/json`):**
```json
{
  "config": {},
  "workload_spec": {
    "sizes": [10, 50, 100],
    "entrypoints": [
      {
        "function": "demo.operations:slow_membership",
        "args": [
          { "kind": "records", "size_factor": 1.0, "fixed": null, "options": {} },
          { "kind": "int_list", "size_factor": 0.5, "fixed": null, "options": {} }
        ]
      }
    ],
    "operation_mix": { "lookup": 0.9, "insert": 0.05, "delete": 0.05 },
    "memory_constraint": "low",
    "latency_target_ms": null,
    "seed": 42
  }
}
```
- **Response 201 Created:**
```json
{
  "id": "7189f196-fd6f-4f53-a941-5ec417f90e1f",
  "repository_id": "e9b1d2c3-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
  "requested_by": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "queued",
  "stage": "queued",
  "progress": 0,
  "config": {},
  "workload_spec": { ... },
  "workload_hash": "a1b2c3d4...",
  "environment": null,
  "error": null,
  "started_at": null,
  "finished_at": null,
  "created_at": "2026-11-15T12:00:00Z",
  "updated_at": "2026-11-15T12:00:00Z"
}
```

---

### GET `/api/v1/analysis-runs/{run_id}/profile`
Retrieves runtime profiling measurements and empirical growth exponents stored in `runs/{run_id}/profile.json`.

- **Auth Required:** Yes (Owner-scoped)
- **Response 200 OK:**
```json
{
  "status": "completed",
  "entrypoints": {
    "demo.operations:slow_membership": {
      "function": "demo.operations:slow_membership",
      "status": "success",
      "growth_exponent": 1.277,
      "sizes": [10, 50, 100],
      "measurements": [
        {
          "n": 10,
          "runtime_s": 0.00012,
          "cpu_time_s": 0.00011,
          "peak_memory_kb": 14.5,
          "top_functions": [
            {
              "file": "demo/operations.py",
              "function": "slow_membership",
              "lineno": 6,
              "calls": 1,
              "total_time": 0.00008,
              "cumulative_time": 0.00012
            }
          ]
        }
      ]
    }
  },
  "summary": {
    "total_entrypoints": 1,
    "successful_entrypoints": 1,
    "failed_entrypoints": 0
  }
}
```
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Run not found or profile has not been generated (e.g. static-only mode).

---

### WebSocket `/api/v1/ws/jobs/{job_id}?token=<jwt>`
Real-time authenticated WebSocket streaming live pipeline progress from Redis pubsub channel `progress:{job_id}`.

- **Authentication:** `token` query parameter containing a valid JWT access token.
- **Authorization:** Only the job owner (or admin) can connect; unauthorized requests are closed immediately with `1008 Policy Violation`.
- **Late Subscriber Guarantee:** The initial message sent on accept is the latest saved pipeline state `{stage, progress, message, status}`, ensuring late subscribers are never blank.
- **Heartbeat:** Sends `{"type": "heartbeat", "timestamp": ...}` every 15 seconds to maintain keepalive over load balancers and proxies.
- **Message Format:**
```json
{
  "stage": "profile",
  "progress": 60,
  "message": "Running profiling inside sandbox container...",
  "status": "running"
}
```

---

## 7. Bottlenecks & Explainability (Phase 4)

### GET `/api/v1/analysis-runs/{run_id}/bottlenecks`
Retrieves ranked candidate bottlenecks for an owned analysis run, ordered by `impact_score` descending.

- **Auth Required:** Yes (Owner-scoped)
- **Query Parameters (optional):**
  - `severity` (string): Filter by severity tier (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
  - `min_impact` (float): Filter functions with `impact_score >= min_impact` (default threshold in pipeline is 0.10).
  - `pattern` (string): Filter functions by detected algorithmic pattern ID (`LINEAR_MEMBERSHIP_IN_LOOP`, `NESTED_LOOP_LOOKUP`, etc.).
- **Response 200 OK:**
```json
[
  {
    "id": "b3e712a4-5678-4321-9abc-def012345678",
    "analysis_run_id": "7189f196-fd6f-4f53-a941-5ec417f90e1f",
    "function_id": "1c2d3e4f-5a6b-7c8d-9e0f-1a2b3c4d5e6f",
    "static_score": 0.6667,
    "runtime_score": 0.952,
    "call_count": 100,
    "runtime_pct": 0.945,
    "memory_peak_kb": 240.5,
    "impact_score": 0.8125,
    "severity": "CRITICAL",
    "evidence": {
      "source": "runtime",
      "static_norm": 0.6667,
      "runtime_pct": 0.945,
      "call_freq_norm": 1.0,
      "mem_norm": 0.85,
      "workload": {
        "input_size": 100,
        "lookup_frequency": "VERY_HIGH",
        "insert_ratio": 0.05,
        "delete_ratio": 0.05,
        "read_write_ratio": 9.0,
        "data_distribution": "uniform",
        "memory_constraint": "LOW",
        "latency_requirement": "MEDIUM"
      },
      "features": {
        "input_size_log10": 2.0,
        "current_algorithm_code": 0,
        "current_complexity_rank": 4,
        "lookup_freq_level": 3,
        "insert_ratio": 0.05,
        "delete_ratio": 0.05,
        "read_write_ratio": 9.0,
        "data_distribution_code": 0,
        "memory_constraint_level": 0,
        "latency_requirement_level": 1,
        "call_count_log10": 2.0043,
        "runtime_pct": 0.945
      },
      "features_array": [2.0, 0.0, 4.0, 3.0, 0.05, 0.05, 9.0, 0.0, 0.0, 1.0, 2.0043, 0.945],
      "affected_functions": [],
      "why_flagged": {
        "reason": "Function flagged as CRITICAL bottleneck (impact score 0.8125)",
        "metric": "severity",
        "value": "CRITICAL",
        "weight": 1.0,
        "children": [
          {
            "reason": "Asymptotic complexity estimated as O(n^2) (rank 4/6)",
            "metric": "complexity_class",
            "value": "O(n^2)",
            "weight": 0.25,
            "children": [
              {
                "reason": "Inefficient algorithmic pattern detected: LINEAR_MEMBERSHIP_IN_LOOP",
                "metric": "pattern",
                "value": "LINEAR_MEMBERSHIP_IN_LOOP",
                "weight": null
              }
            ]
          },
          {
            "reason": "Dominant execution time: 94.5% of total entrypoint time",
            "metric": "runtime_pct",
            "value": "94.5%",
            "weight": 0.40
          },
          {
            "reason": "High execution frequency with 100 calls",
            "metric": "call_count",
            "value": 100,
            "weight": 0.20
          },
          {
            "reason": "Peak heap memory allocation of 240.5 KB",
            "metric": "memory_peak_kb",
            "value": "240.5 KB",
            "weight": 0.15
          },
          {
            "reason": "Evaluated under workload input size of 100 records",
            "metric": "input_size",
            "value": 100,
            "weight": null
          },
          {
            "reason": "Impact score 0.8125 maps to severity tier CRITICAL",
            "metric": "impact_score",
            "value": 0.8125,
            "weight": 1.0
          }
        ]
      }
    },
    "function": {
      "id": "1c2d3e4f-5a6b-7c8d-9e0f-1a2b3c4d5e6f",
      "name": "slow_membership",
      "qualified_name": "demo.operations.slow_membership",
      "complexity_class": "O(n^2)",
      "complexity_rank": 4
    }
  }
]
```
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Analysis run not found or user is not the owner.

---

### GET `/api/v1/bottlenecks/{bottleneck_id}`
Retrieves detailed information and complete evidence for a specific bottleneck.

- **Auth Required:** Yes (Owner-scoped)
- **Response 200 OK:** Single Bottleneck JSON object matching schema above.
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Bottleneck not found or not owned by user.

---

### GET `/api/v1/bottlenecks/{bottleneck_id}/recommendation`
Retrieves algorithmic and data structure recommendations, per-feature importances, expected complexity transitions, and plain-English factor explanations for a bottleneck.

- **Auth Required:** Yes (Owner-scoped)
- **Response 200 OK:**
```json
{
  "id": "180373e0-f0c3-42bf-9c70-ea5f2cbbd377",
  "bottleneck_id": "b-6e9381ea-3908-4171-aa31-e1cbfa1b8f04",
  "current_algorithm": "linear_scan_membership",
  "recommended_algorithm": "hash_set",
  "expected_complexity": "O(n * m) -> O(n + m)",
  "confidence": 0.8315,
  "alternatives": [
    "keep_current"
  ],
  "reason": "Recommendation of hash_set is driven primarily by: Detected Pattern (LINEAR_MEMBERSHIP_IN_LOOP, 43.3%), Input Size (100 items, 14.9%), and Asymptotic Complexity (O(n^2), 10.0%). Recommended structure: set (Workload performs repeated membership queries across 100 items. Replacing list with a hash set provides O(1) average lookup time.)",
  "source": "ml",
  "feature_importance": [
    {
      "feature": "current_algorithm_code",
      "display_name": "Detected Pattern",
      "importance": 0.4331,
      "value": 0.0,
      "formatted_value": "LINEAR_MEMBERSHIP_IN_LOOP"
    },
    {
      "feature": "input_size_log10",
      "display_name": "Input Size (N)",
      "importance": 0.1489,
      "value": 2.0,
      "formatted_value": "100 items"
    },
    {
      "feature": "current_complexity_rank",
      "display_name": "Asymptotic Complexity",
      "importance": 0.0999,
      "value": 4.0,
      "formatted_value": "O(n^2)"
    }
  ],
  "created_at": "2026-11-15T15:00:00Z",
  "updated_at": "2026-11-15T15:00:00Z"
}
```
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Bottleneck not found or user is not the owner.
  - `404 Not Found` (`NOT_READY`): Recommendation not yet ready (analysis run currently in progress).

---

## 9. Candidate Optimization Generation

### POST `/api/v1/bottlenecks/{bottleneck_id}/optimizations`
Initiates generation of an optimization candidate for a bottleneck using either deterministic LibCST templates (Mode A) or an OpenAI-compatible LLM provider (Mode B). Applies strict shared guards before persisting candidate artifacts.

- **Auth Required:** Yes (Owner-scoped)
- **Query Parameters:**
  - `sync` (optional boolean, default `false`): If `true`, forces synchronous generation inline within the HTTP request cycle; otherwise dispatches to background worker.
- **Request Body:**
```json
{
  "mode": "template",
  "template_id": "T1_SET_MEMBERSHIP"
}
```
*Note: If `template_id` is omitted, the template is automatically mapped from the bottleneck's recommendation.*
- **Response 201 Created:**
```json
{
  "id": "e4a7dc92-3bc1-4475-b66b-80fb785a2283",
  "recommendation_id": "180373e0-f0c3-42bf-9c70-ea5f2cbbd377",
  "mode": "template",
  "template_id": "T1_SET_MEMBERSHIP",
  "candidate_code": "def slow_membership(items, ids):\n    ids_set = set(ids)\n    res = []\n    for item in items:\n        if item in ids_set:\n            res.append(item)\n    return res\n",
  "patch": "--- original.py\n+++ candidate.py\n@@ -6,6 +6,7 @@\n def slow_membership(items, ids):\n+    ids_set = set(ids)\n     res = []\n",
  "status": "generated",
  "error": null,
  "decision_reason": {
    "rationale": "Convert linear scan list lookup to O(1) average hash set membership.",
    "safety_notes": [
      "Target elements in 'ids' must implement __hash__ and __eq__.",
      "The set is instantiated once prior to loop execution."
    ],
    "changed_lines": [7]
  },
  "created_at": "2026-11-16T02:00:00Z",
  "updated_at": "2026-11-16T02:00:01Z"
}
```
- **Errors:**
  - `400 Bad Request` (`INVALID_MODE`): Unsupported mode specified (must be `template` or `llm`).
  - `404 Not Found` (`NOT_FOUND`): Bottleneck not found or not owned by user.
  - `404 Not Found` (`NOT_READY`): Recommendation not yet ready for this bottleneck.

---

### GET `/api/v1/bottlenecks/{bottleneck_id}/optimizations`
Lists all candidate optimization records generated for the specified bottleneck.

- **Auth Required:** Yes (Owner-scoped)
- **Response 200 OK:** Array of `OptimizationResponse` objects.
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Bottleneck not found or not owned by user.

---

### GET `/api/v1/optimizations/{optimization_id}`
Retrieves a single optimization record, including candidate source, unified diff patch, rationale, safety notes, and execution status.

- **Auth Required:** Yes (Owner-scoped)
- **Response 200 OK:** `OptimizationResponse` object.
- **Errors:**
  - `404 Not Found` (`NOT_FOUND`): Optimization not found or not owned by user.

---

### GET `/api/v1/optimizations/config`
Retrieves generator capabilities, active LLM provider availability, and list of supported deterministic templates.

- **Auth Required:** Yes
- **Response 200 OK:**
```json
{
  "llm_provider": "none",
  "llm_enabled": false,
  "templates": [
    "T1_SET_MEMBERSHIP",
    "T2_DICT_INDEX_JOIN",
    "T3_MIN_MAX_HEAP",
    "T4_JOIN_STRINGS",
    "T5_LRU_CACHE",
    "T6_DEQUE_POPLEFT"
  ]
}
```
