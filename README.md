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

### Architecture & Progress
- Contract: [docs/ARCHITECTURE_CONTRACT.md](docs/ARCHITECTURE_CONTRACT.md)
- Progress & Status: [docs/PROGRESS.md](docs/PROGRESS.md)
- API Documentation: [docs/API.md](docs/API.md)
