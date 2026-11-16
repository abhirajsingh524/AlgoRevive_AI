"""Seed script to bootstrap a ready-to-explore demo environment in local SQLite."""

import os
import sys
import uuid
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.models.project import Project
from app.models.recommendation import Recommendation
from app.models.repository import Repository
from app.models.user import User
from app.services.analysis_service import execute_analysis
from app.services.optimization_service import execute_optimization
from app.services.storage import get_storage_service


def seed_demo():
    print("1. Creating database tables if not exist...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    storage = get_storage_service()

    try:
        # 1. Create or find demo user
        demo_email = "demo@example.com"
        user = db.query(User).filter(User.email == demo_email).first()
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email=demo_email,
                hashed_password=hash_password("Password123!"),
                full_name="Demo Developer",
                role="developer",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"   Created demo user: {demo_email} / Password123!")
        else:
            print(f"   Demo user {demo_email} already exists.")

        # 2. Check if demo project exists
        project = db.query(Project).filter(Project.owner_id == user.id, Project.name == "Demo Performance Project").first()
        if not project:
            project = Project(
                id=str(uuid.uuid4()),
                owner_id=user.id,
                name="Demo Performance Project",
                description="Reference repository demonstrating classic algorithmic bottlenecks and Phase 6 candidate optimizations.",
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            print("   Created project: Demo Performance Project")

        # 3. Check if demo repo exists
        repo = db.query(Repository).filter(Repository.project_id == project.id, Repository.version_label == "v1.0-demo").first()
        if not repo:
            repo = Repository(
                id=str(uuid.uuid4()),
                project_id=project.id,
                version_label="v1.0-demo",
                source_type="zip",
                storage_key=f"repos/{uuid.uuid4()}/original.zip",
                status="ready",
                file_count=2,
                total_loc=150,
            )
            db.add(repo)
            db.commit()
            db.refresh(repo)
            print("   Created repository record: demo_repo (v1.0-demo)")

            # 4. Ingest files from examples/demo_repo
            demo_repo_dir = backend_dir.parent / "examples" / "demo_repo"
            if not demo_repo_dir.exists():
                demo_repo_dir = Path("examples/demo_repo").resolve()

            print(f"   Reading demo repo files from {demo_repo_dir}...")
            files_to_ingest = [
                "demo/operations.py",
                "demo/__init__.py",
                "algorevive.workload.json",
            ]

            for rel_path in files_to_ingest:
                local_file = demo_repo_dir / rel_path
                if local_file.exists():
                    content = local_file.read_bytes()
                    storage_key = f"repos/{repo.id}/files/{rel_path}"
                    storage.put_file(storage_key, content)

                    if rel_path.endswith(".py"):
                        f_rec = File(
                            id=str(uuid.uuid4()),
                            repository_id=repo.id,
                            path=rel_path,
                            language="python",
                            loc=len(content.splitlines()),
                            sha256="demo_hash",
                            storage_key=storage_key,
                        )
                        db.add(f_rec)
            db.commit()

            # 5. Run analysis pipeline
            print("   Executing analysis pipeline for demo repository...")
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

            execute_analysis(db=db, storage=storage, run_id=run.id)
            print(f"   Analysis run complete: status={run.status}, stage={run.stage}")

            # 6. Generate candidate optimizations for all detected bottlenecks
            bottlenecks = db.query(Bottleneck).filter(Bottleneck.analysis_run_id == run.id).all()
            print(f"   Found {len(bottlenecks)} bottlenecks. Generating candidate optimizations...")
            from app.models.optimization import Optimization
            for bn in bottlenecks:
                rec = db.query(Recommendation).filter(Recommendation.bottleneck_id == bn.id).first()
                if rec and rec.recommended_algorithm != "keep_current":
                    opt = Optimization(
                        id=str(uuid.uuid4()),
                        recommendation_id=rec.id,
                        mode="template",
                        status="generated",
                    )
                    db.add(opt)
                    db.commit()
                    try:
                        execute_optimization(db=db, storage=storage, optimization_id=opt.id)
                        print(f"     Optimization generated for {bn.function.name}: status={opt.status}")
                    except Exception as opt_err:
                        print(f"     Optimization for {bn.function.name} error: {opt_err}")

        print("\nDemo seeding successfully completed!")
        print("--------------------------------------------------")
        print("Login credentials:")
        print("  Email:    demo@example.com")
        print("  Password: Password123!")
        print("--------------------------------------------------")

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
