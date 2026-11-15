import io
import os
import zipfile
from app.services.analysis_service import execute_analysis
from app.services.storage import get_storage_service


def _create_user_and_token(client, email="analyst@example.com"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Analyst"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project_and_repo(client, headers):
    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Analysis Project", "description": "Test static analysis"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    # Read demo operations file
    demo_file = os.path.abspath("examples/demo_repo/demo/operations.py")
    if not os.path.exists(demo_file):
        demo_file = os.path.abspath("../examples/demo_repo/demo/operations.py")
    with open(demo_file, "rb") as f:
        demo_code = f.read()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("demo/__init__.py", "from demo.operations import *")
        zf.writestr("demo/operations.py", demo_code)

    zip_bytes = zip_buf.getvalue()

    upload_resp = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        files={"files": ("demo_repo.zip", zip_bytes, "application/zip")},
        data={"version_label": "v1.0"},
        headers=headers,
    )
    assert upload_resp.status_code == 201
    return project_id, upload_resp.json()["id"]


def test_analysis_pipeline_and_endpoints(client, db_session):
    headers = _create_user_and_token(client, "user_a@example.com")
    project_id, repo_id = _create_project_and_repo(client, headers)
    storage = get_storage_service()

    # 1. Trigger analysis run via API
    create_run_resp = client.post(
        f"/api/v1/repositories/{repo_id}/analysis-runs",
        json={"config": {"test": True}},
        headers=headers,
    )
    assert create_run_resp.status_code == 201
    run_data = create_run_resp.json()
    run_id = run_data["id"]
    assert run_data["repository_id"] == repo_id
    assert run_data["status"] == "queued"

    # 2. Execute pipeline orchestrator
    run_obj = execute_analysis(db=db_session, storage=storage, run_id=run_id)
    assert run_obj.status == "completed"
    assert run_obj.stage == "completed"
    assert run_obj.progress == 100

    # 3. Verify idempotent re-run: execute again for same repo
    create_run_2 = client.post(
        f"/api/v1/repositories/{repo_id}/analysis-runs",
        headers=headers,
    )
    assert create_run_2.status_code == 201
    run_2_id = create_run_2.json()["id"]

    run_obj_2 = execute_analysis(db=db_session, storage=storage, run_id=run_2_id)
    assert run_obj_2.status == "completed"

    # 4. List analysis runs
    list_runs_resp = client.get(
        f"/api/v1/repositories/{repo_id}/analysis-runs",
        headers=headers,
    )
    assert list_runs_resp.status_code == 200
    runs = list_runs_resp.json()
    assert len(runs) >= 2

    # 5. Get single analysis run
    get_run_resp = client.get(
        f"/api/v1/analysis-runs/{run_id}",
        headers=headers,
    )
    assert get_run_resp.status_code == 200
    assert get_run_resp.json()["id"] == run_id

    # 6. List functions (assert sorted by rank desc)
    funcs_resp = client.get(
        f"/api/v1/repositories/{repo_id}/functions",
        headers=headers,
    )
    assert funcs_resp.status_code == 200
    funcs = funcs_resp.json()
    assert len(funcs) == 7

    # Verify descending rank sort
    ranks = [f["complexity_rank"] for f in funcs]
    assert ranks == sorted(ranks, reverse=True)

    # Top function should be fib (rank 6)
    assert funcs[0]["name"] == "fib"
    assert funcs[0]["severity"] == "CRITICAL"

    # 7. Test filters on /functions:
    # Severity filter
    crit_resp = client.get(
        f"/api/v1/repositories/{repo_id}/functions?severity=CRITICAL",
        headers=headers,
    )
    assert crit_resp.status_code == 200
    assert len(crit_resp.json()) == 1
    assert crit_resp.json()[0]["name"] == "fib"

    # Min rank filter
    high_resp = client.get(
        f"/api/v1/repositories/{repo_id}/functions?min_rank=4",
        headers=headers,
    )
    assert high_resp.status_code == 200
    # fib (6), slow_membership (4), nested_match (4), repeated_sort (4) -> 4 functions
    assert len(high_resp.json()) == 4

    # Pattern filter
    pat_resp = client.get(
        f"/api/v1/repositories/{repo_id}/functions?pattern=LINEAR_MEMBERSHIP_IN_LOOP",
        headers=headers,
    )
    assert pat_resp.status_code == 200
    assert len(pat_resp.json()) == 1
    assert pat_resp.json()[0]["name"] == "slow_membership"

    # 8. Call graph endpoint
    cg_resp = client.get(
        f"/api/v1/repositories/{repo_id}/call-graph",
        headers=headers,
    )
    assert cg_resp.status_code == 200
    cg_data = cg_resp.json()
    assert cg_data["repository_id"] == repo_id
    assert cg_data["node_count"] == 7
    # fib has a self-call recursive edge
    assert any(e["source"] == e["target"] for e in cg_data["edges"])


def test_analysis_ownership_isolation(client, db_session):
    headers_a = _create_user_and_token(client, "user_owner@example.com")
    headers_b = _create_user_and_token(client, "user_intruder@example.com")

    project_id, repo_id = _create_project_and_repo(client, headers_a)
    storage = get_storage_service()

    # User A creates analysis run
    create_run = client.post(
        f"/api/v1/repositories/{repo_id}/analysis-runs",
        headers=headers_a,
    )
    run_id = create_run.json()["id"]
    execute_analysis(db=db_session, storage=storage, run_id=run_id)

    # User B attempts to access User A's repository resources -> MUST be 404
    resp = client.post(
        f"/api/v1/repositories/{repo_id}/analysis-runs",
        headers=headers_b,
    )
    assert resp.status_code == 404

    resp = client.get(
        f"/api/v1/repositories/{repo_id}/analysis-runs",
        headers=headers_b,
    )
    assert resp.status_code == 404

    resp = client.get(
        f"/api/v1/analysis-runs/{run_id}",
        headers=headers_b,
    )
    assert resp.status_code == 404

    resp = client.get(
        f"/api/v1/repositories/{repo_id}/functions",
        headers=headers_b,
    )
    assert resp.status_code == 404

    resp = client.get(
        f"/api/v1/repositories/{repo_id}/call-graph",
        headers=headers_b,
    )
    assert resp.status_code == 404
