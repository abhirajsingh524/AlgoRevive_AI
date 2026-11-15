"""Integration tests for the profiler pipeline stage, static-only fallback, and demo repository."""

import json
from pathlib import Path
import uuid
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.models.analysis_run import AnalysisRun
from app.models.file import File
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.services.analysis_service import execute_analysis
from app.services.storage import get_storage_service


def test_profile_stage_static_only_fallback_when_no_workload_spec(db_session):
    """When a repository has no workload spec, profile stage is skipped with a warning and run completes."""
    user = User(
        id=str(uuid.uuid4()),
        email="dev_static@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    proj = Project(id=str(uuid.uuid4()), owner_id=user.id, name="Static Only Project")
    db_session.add(proj)
    db_session.commit()

    storage = get_storage_service()
    repo_id = str(uuid.uuid4())
    repo = Repository(
        id=repo_id,
        project_id=proj.id,
        source_type="zip",
        storage_key=f"repos/{repo_id}/original.zip",
        status="ingested",
        file_count=1,
        total_loc=10,
    )
    db_session.add(repo)
    db_session.commit()

    file_storage_key = f"repos/{repo_id}/files/simple.py"
    storage.put_file(file_storage_key, b"def add(a, b):\n    return a + b\n")

    f_record = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="simple.py",
        language="python",
        loc=2,
        sha256="abc",
        storage_key=file_storage_key,
    )
    db_session.add(f_record)
    db_session.commit()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=user.id,
        status="queued",
        stage="queued",
        progress=0,
    )
    db_session.add(run)
    db_session.commit()

    completed_run = execute_analysis(db_session, storage, run.id)

    assert completed_run.status == "completed"
    assert completed_run.stage == "completed"
    assert completed_run.progress == 100
    assert completed_run.error is None
    # Profile result should not exist in storage for static-only run
    assert not storage.exists(f"runs/{run.id}/profile.json")


def test_profile_stage_on_demo_repo_growth_exponents(client: TestClient, db_session):
    """Ingest demo repo files, run analysis pipeline, and verify empirical growth exponents."""
    user = User(
        id=str(uuid.uuid4()),
        email="demo_analyst@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    proj = Project(id=str(uuid.uuid4()), owner_id=user.id, name="Demo Repo Project")
    db_session.add(proj)
    db_session.commit()

    storage = get_storage_service()
    repo_id = str(uuid.uuid4())
    repo = Repository(
        id=repo_id,
        project_id=proj.id,
        source_type="zip",
        storage_key=f"repos/{repo_id}/original.zip",
        status="ingested",
        file_count=2,
        total_loc=120,
    )
    db_session.add(repo)
    db_session.commit()

    # Load actual demo repo files from disk
    demo_dir = Path("examples/demo_repo")
    operations_py = (demo_dir / "demo" / "operations.py").read_bytes()
    workload_json = (demo_dir / "algorevive.workload.json").read_bytes()

    f1_key = f"repos/{repo_id}/files/demo/operations.py"
    f2_key = f"repos/{repo_id}/files/algorevive.workload.json"
    storage.put_file(f1_key, operations_py)
    storage.put_file(f2_key, workload_json)

    file_op = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="demo/operations.py",
        language="python",
        loc=65,
        sha256="hash1",
        storage_key=f1_key,
    )
    file_wl = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="algorevive.workload.json",
        language="json",
        loc=50,
        sha256="hash2",
        storage_key=f2_key,
    )
    db_session.add_all([file_op, file_wl])
    db_session.commit()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=user.id,
        status="queued",
        stage="queued",
        progress=0,
    )
    db_session.add(run)
    db_session.commit()

    completed_run = execute_analysis(db_session, storage, run.id)

    assert completed_run.status == "completed"
    assert completed_run.stage == "completed"
    assert completed_run.environment is not None
    assert "python_version" in completed_run.environment
    assert "os" in completed_run.environment
    assert "cpu_count" in completed_run.environment

    # Verify profile file exists in storage
    profile_key = f"runs/{run.id}/profile.json"
    assert storage.exists(profile_key)
    profile_data = json.loads(storage.get_file(profile_key).decode("utf-8"))

    eps = profile_data["entrypoints"]
    assert "demo.operations:slow_membership" in eps
    assert "demo.operations:nested_match" in eps
    assert "demo.operations:fib" in eps
    assert "demo.operations:efficient_total" in eps

    slow_mem_exp = eps["demo.operations:slow_membership"]["growth_exponent"]
    nested_exp = eps["demo.operations:nested_match"]["growth_exponent"]
    fib_exp = eps["demo.operations:fib"]["growth_exponent"]
    efficient_exp = eps["demo.operations:efficient_total"]["growth_exponent"]

    # Verify contract: slow_membership, nested_match, and fib grow faster than efficient_total
    assert slow_mem_exp > efficient_exp
    assert nested_exp > efficient_exp
    assert fib_exp > efficient_exp

    # Test GET /analysis-runs/{run_id}/profile endpoint
    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/analysis-runs/{run.id}/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "completed"
    assert "entrypoints" in res_json


def test_profiler_failure_path_broken_code_keeps_run_completed(client: TestClient, db_session):
    """Broken user code records warnings/errors gracefully without crashing orchestrator or worker."""
    user = User(
        id=str(uuid.uuid4()),
        email="broken_code_user@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    proj = Project(id=str(uuid.uuid4()), owner_id=user.id, name="Broken Code Project")
    db_session.add(proj)
    db_session.commit()

    storage = get_storage_service()
    repo_id = str(uuid.uuid4())
    repo = Repository(
        id=repo_id,
        project_id=proj.id,
        source_type="zip",
        storage_key=f"repos/{repo_id}/original.zip",
        status="ingested",
        file_count=2,
        total_loc=20,
    )
    db_session.add(repo)
    db_session.commit()

    broken_py = b"def divide_zero(x):\n    return x / 0\n"
    spec_bytes = json.dumps({
        "sizes": [10, 20],
        "entrypoints": [
            {
                "function": "broken:divide_zero",
                "args": [{"kind": "int_list"}],
            }
        ],
        "seed": 42,
    }).encode("utf-8")

    f1_key = f"repos/{repo_id}/files/broken.py"
    f2_key = f"repos/{repo_id}/files/algorevive.workload.json"
    storage.put_file(f1_key, broken_py)
    storage.put_file(f2_key, spec_bytes)

    f1 = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="broken.py",
        language="python",
        loc=2,
        sha256="h1",
        storage_key=f1_key,
    )
    f2 = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="algorevive.workload.json",
        language="json",
        loc=10,
        sha256="h2",
        storage_key=f2_key,
    )
    db_session.add_all([f1, f2])
    db_session.commit()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=user.id,
        status="queued",
        stage="queued",
        progress=0,
    )
    db_session.add(run)
    db_session.commit()

    completed_run = execute_analysis(db_session, storage, run.id)

    # Pipeline completes without crashing
    assert completed_run.status == "completed"
    assert completed_run.stage == "completed"
    assert completed_run.error is None

    # Profile exists and indicates error for the broken entrypoint
    profile_key = f"runs/{run.id}/profile.json"
    assert storage.exists(profile_key)
    pdata = json.loads(storage.get_file(profile_key).decode("utf-8"))
    ep = pdata["entrypoints"]["broken:divide_zero"]
    assert ep["status"] == "error"
    assert "division by zero" in ep["error"] or "unsupported operand" in ep["error"]
