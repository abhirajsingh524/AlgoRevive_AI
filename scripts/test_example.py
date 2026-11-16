"""End-to-end verification script for testing AlgoRevive AI on a sample project."""

import os
import sys
import uuid
from pathlib import Path

# Setup paths
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.models.optimization import Optimization
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.repository import Repository
from app.models.user import User
from app.services.analysis_service import execute_analysis
from app.services.optimization_service import execute_optimization
from app.services.storage import get_storage_service


def run_test():
    print("=" * 70)
    print("      ALGORITHMIC REVIVE AI - FULL WORKFLOW TEST ON SAMPLE PROJECT      ")
    print("=" * 70)

    db = SessionLocal()
    storage = get_storage_service()

    # 1. Get or create demo user
    user = db.query(User).filter(User.email == "demo@example.com").first()
    if not user:
        print("[!] Demo user not found. Please start the server once or run seed_demo_data.py.")
        return

    # 2. Create sample test project
    project_name = "Quick Sample Test"
    project = db.query(Project).filter(Project.owner_id == user.id, Project.name == project_name).first()
    if not project:
        project = Project(
            id=str(uuid.uuid4()),
            owner_id=user.id,
            name=project_name,
            description="Testing Phase 1-6 end-to-end workflows on 6 algorithmic patterns.",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

    print(f"\n[1] Project: {project.name} (ID: {project.id})")

    # 3. Create repository record
    version = f"v{uuid.uuid4().hex[:4]}"
    repo = Repository(
        id=str(uuid.uuid4()),
        project_id=project.id,
        version_label=version,
        source_type="files",
        storage_key=f"repos/{uuid.uuid4()}/original.zip",
        status="ready",
        file_count=1,
        total_loc=65,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # 4. Upload examples/sample_project.py to storage
    sample_file_path = Path(__file__).resolve().parent.parent / "examples" / "sample_project.py"
    sample_bytes = sample_file_path.read_bytes()
    storage_key = f"repos/{repo.id}/files/sample_project.py"
    storage.put_file(storage_key, sample_bytes)

    file_rec = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="sample_project.py",
        language="python",
        loc=len(sample_bytes.splitlines()),
        sha256="sample_hash",
        storage_key=storage_key,
    )
    db.add(file_rec)
    db.commit()
    print(f"[2] Ingested File: sample_project.py (Repo ID: {repo.id})")

    # 5. Run analysis pipeline through all 8 stages
    print("[3] Running 8-Stage Analysis Pipeline...")
    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=user.id,
        status="queued",
        stage="queued",
        progress=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    completed_run = execute_analysis(db=db, storage=storage, run_id=run.id)
    print(f"    Status: {completed_run.status.upper()} | Stage: {completed_run.stage.upper()} | Progress: {completed_run.progress}%")

    # 6. Retrieve detected bottlenecks & recommendations
    bottlenecks = db.query(Bottleneck).filter(Bottleneck.analysis_run_id == run.id).all()
    print(f"\n[4] Detected Bottlenecks ({len(bottlenecks)} found):")
    print("-" * 70)

    TEMPLATE_MAP = {
        "find_active_users": "T1_SET_MEMBERSHIP",
        "match_orders_to_customers": "T2_DICT_INDEX_JOIN",
        "get_top_priority_item": "T3_MIN_MAX_HEAP",
        "generate_log_report": "T4_JOIN_STRINGS",
        "calculate_fibonacci": "T5_LRU_CACHE",
        "process_task_queue": "T6_DEQUE_POPLEFT",
    }

    for idx, b in enumerate(bottlenecks, 1):
        fn = db.query(Function).filter(Function.id == b.function_id).first()
        rec = db.query(Recommendation).filter(Recommendation.bottleneck_id == b.id).first()
        rec_algo = rec.recommended_algorithm if rec else "N/A"
        conf = f"{rec.confidence * 100:.1f}%" if rec and rec.confidence else "N/A"
        source = rec.source if rec else "N/A"

        print(f" {idx}. Function: {fn.name}()")
        print(f"    - Complexity Rank: {fn.complexity_class} (Severity: {b.severity}, Impact: {b.impact_score:.2f})")
        print(f"    - ML Recommendation: {rec_algo} (Confidence: {conf}, Source: {source})")

        # Generate Phase 6 candidate optimization
        template_id = TEMPLATE_MAP.get(fn.name)
        if template_id and rec:
            opt = Optimization(
                id=str(uuid.uuid4()),
                recommendation_id=rec.id,
                mode="template",
                template_id=template_id,
                status="generated",
            )
            db.add(opt)
            db.commit()
            opt_res = execute_optimization(db=db, storage=storage, optimization_id=opt.id)
            print(f"    - Phase 6 Candidate Diff: [{opt_res.status.upper()}] with template {template_id}")

    print("=" * 70)
    print("                    TEST EXECUTION SUMMARY                              ")
    print("=" * 70)
    print(f"Open in Browser to view side-by-side Monaco Diff & Interactive UI:")
    print(f"  URL: http://localhost:5173/repositories/{repo.id}/analysis/{run.id}")
    print("=" * 70)


if __name__ == "__main__":
    run_test()
