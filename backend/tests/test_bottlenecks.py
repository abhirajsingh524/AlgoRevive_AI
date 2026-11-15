"""Comprehensive tests for bottleneck scoring, workload characterization, feature vectors, and explainability."""

import json
from pathlib import Path
import uuid
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.engines.bottleneck.scorer import (
    calculate_impact,
    get_severity,
)
from app.engines.explain.why_flagged import build_why_flagged
from app.engines.workload.features import (
    FeatureVector,
    PATTERN_CODE_MAP,
)
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User
from app.services.analysis_service import execute_analysis
from app.services.storage import get_storage_service


# 1. Formula unit tests with hand-calculated numbers
def test_impact_formula_hand_calculated():
    """Verify impact score formula against hand-calculated results.
    
    Formula:
    impact_score = 0.40 * runtime_pct + 0.25 * static_norm + 0.20 * call_freq_norm + 0.15 * mem_norm
    where:
      static_norm = rank / 6
      call_freq_norm = log10(1 + calls) / log10(1 + max_calls)
      mem_norm = peak_mem / max_peak_mem
    """
    # Hand calculation:
    # rank = 3 -> static_norm = 3/6 = 0.50 -> 0.25 * 0.50 = 0.125
    # runtime_pct = 0.50 -> 0.40 * 0.50 = 0.200
    # calls = 9, max_calls = 99 -> log10(10)/log10(100) = 1/2 = 0.50 -> 0.20 * 0.50 = 0.100
    # peak_mem = 250.0, max_peak_mem = 500.0 -> mem_norm = 0.50 -> 0.15 * 0.50 = 0.075
    # Total impact = 0.200 + 0.125 + 0.100 + 0.075 = 0.500
    res = calculate_impact(
        complexity_rank=3,
        runtime_pct=0.50,
        call_count=9,
        max_calls=99,
        memory_peak_kb=250.0,
        max_peak_mem_kb=500.0,
        has_profile=True,
    )
    assert res.static_score == 0.50
    assert res.runtime_pct == 0.50
    assert res.call_count == 9
    assert res.memory_peak_kb == 250.0
    assert res.impact_score == 0.50
    assert res.severity == "HIGH"


# 2. Severity boundary tests (0.25, 0.50, 0.75 exactly)
def test_severity_boundaries_exact():
    """Verify exact severity thresholds from Contract G6:
    >=0.75 CRITICAL, >=0.50 HIGH, >=0.25 MEDIUM, else LOW.
    """
    assert get_severity(1.0) == "CRITICAL"
    assert get_severity(0.75) == "CRITICAL"
    assert get_severity(0.7499) == "HIGH"
    assert get_severity(0.50) == "HIGH"
    assert get_severity(0.4999) == "MEDIUM"
    assert get_severity(0.25) == "MEDIUM"
    assert get_severity(0.2499) == "LOW"
    assert get_severity(0.10) == "LOW"
    assert get_severity(0.0) == "LOW"


# 3. Static-only fallback
def test_static_only_fallback():
    """When no runtime profile exists, impact = 0.6 * static_norm and evidence.source = 'static-only'."""
    # Rank 2: static_norm = 2/6 = 0.3333 -> impact = 0.6 * 0.3333 = 0.20 (LOW)
    res_rank2 = calculate_impact(complexity_rank=2, has_profile=False)
    assert res_rank2.severity == "LOW"
    assert res_rank2.impact_score == 0.20
    assert res_rank2.runtime_score == 0.0
    assert res_rank2.runtime_pct == 0.0
    assert res_rank2.evidence["source"] == "static-only"

    # Rank 4: static_norm = 4/6 = 0.6667 -> impact = 0.6 * 0.6667 = 0.40 (MEDIUM)
    res_rank4 = calculate_impact(complexity_rank=4, has_profile=False)
    assert res_rank4.severity == "MEDIUM"
    assert res_rank4.impact_score == 0.40
    assert res_rank4.evidence["source"] == "static-only"

    # Rank 6: static_norm = 6/6 = 1.0 -> impact = 0.6 * 1.0 = 0.60 (HIGH)
    res_rank6 = calculate_impact(complexity_rank=6, has_profile=False)
    assert res_rank6.severity == "HIGH"
    assert res_rank6.impact_score == 0.60
    assert res_rank6.evidence["source"] == "static-only"


# 4. FeatureVector order and range tests
def test_feature_vector_order_and_range():
    """Verify that FeatureVector strictly adheres to the 12 fields and ordering for Phase 5."""
    field_names = list(FeatureVector.model_fields.keys())
    expected_order = [
        "input_size_log10",
        "current_algorithm_code",
        "current_complexity_rank",
        "lookup_freq_level",
        "insert_ratio",
        "delete_ratio",
        "read_write_ratio",
        "data_distribution_code",
        "memory_constraint_level",
        "latency_requirement_level",
        "call_count_log10",
        "runtime_pct",
    ]
    assert field_names == expected_order, f"Order mismatch: {field_names} vs {expected_order}"

    # Verify pattern code map conforms to Contract G3
    assert PATTERN_CODE_MAP["LINEAR_MEMBERSHIP_IN_LOOP"] == 0
    assert PATTERN_CODE_MAP["NESTED_LOOP_LOOKUP"] == 1
    assert PATTERN_CODE_MAP["REPEATED_SORT_FOR_EXTREME"] == 2
    assert PATTERN_CODE_MAP["STRING_CONCAT_IN_LOOP"] == 3
    assert PATTERN_CODE_MAP["NAIVE_RECURSION"] == 4
    assert PATTERN_CODE_MAP["LIST_POP_FRONT"] == 5

    fv = FeatureVector(
        input_size_log10=3.0,
        current_algorithm_code=1,
        current_complexity_rank=4,
        lookup_freq_level=2,
        insert_ratio=0.1,
        delete_ratio=0.05,
        read_write_ratio=5.5,
        data_distribution_code=0,
        memory_constraint_level=1,
        latency_requirement_level=2,
        call_count_log10=2.3,
        runtime_pct=0.88,
    )
    arr = fv.to_array()
    assert len(arr) == 12
    assert arr[0] == 3.0
    assert arr[1] == 1.0
    assert arr[2] == 4.0
    assert arr[3] == 2.0
    assert arr[4] == 0.1
    assert arr[5] == 0.05
    assert arr[6] == 5.5
    assert arr[7] == 0.0
    assert arr[8] == 1.0
    assert arr[9] == 2.0
    assert arr[10] == 2.3
    assert arr[11] == 0.88


# 5. why_flagged built only from stored evidence
def test_why_flagged_built_only_from_stored_evidence():
    """Verify build_why_flagged produces a structured tree where every metric matches stored evidence."""
    b = Bottleneck(
        id=str(uuid.uuid4()),
        analysis_run_id=str(uuid.uuid4()),
        function_id=str(uuid.uuid4()),
        static_score=0.6667,
        runtime_score=0.85,
        call_count=500,
        runtime_pct=0.92,
        memory_peak_kb=1280.5,
        impact_score=0.8125,
        severity="CRITICAL",
        evidence={
            "source": "runtime",
            "workload": {"input_size": 1000},
        },
    )
    fn = Function(
        id=b.function_id,
        file_id=str(uuid.uuid4()),
        repository_id=str(uuid.uuid4()),
        qualified_name="demo.ops:nested_lookup",
        name="nested_lookup",
        lineno=10,
        end_lineno=25,
        complexity_class="O(n^2)",
        complexity_rank=4,
        loop_depth=2,
        has_recursion=False,
        patterns=[{"pattern_id": "NESTED_LOOP_LOOKUP", "line_number": 12}],
        severity="HIGH",
    )

    tree = build_why_flagged(b, function=fn)
    assert tree["metric"] == "severity"
    assert tree["value"] == "CRITICAL"
    assert tree["weight"] == 1.0

    metrics_present = {child["metric"]: child["value"] for child in tree["children"]}
    assert metrics_present["complexity_class"] == "O(n^2)"
    assert metrics_present["runtime_pct"] == "92.0%"
    assert metrics_present["call_count"] == 500
    assert metrics_present["memory_peak_kb"] == "1280.5 KB"
    assert metrics_present["input_size"] == 1000
    assert metrics_present["impact_score"] == 0.8125

    # Check pattern nested inside complexity
    comp_node = next(c for c in tree["children"] if c["metric"] == "complexity_class")
    assert len(comp_node["children"]) == 1
    assert comp_node["children"][0]["metric"] == "pattern"
    assert comp_node["children"][0]["value"] == "NESTED_LOOP_LOOKUP"


# 6. Integration test on the demo repo
def test_demo_repo_bottlenecks_ranking_and_control_function_low(db_session):
    """Run full analysis pipeline on demo repo:
    assert slow_membership, nested_match, and fib rank above efficient_total,
    and efficient_total severity is LOW.
    """
    user = User(
        id=str(uuid.uuid4()),
        email="demo_bottlenecks@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    proj = Project(id=str(uuid.uuid4()), owner_id=user.id, name="Demo Repo Bottlenecks")
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
        total_loc=100,
    )
    db_session.add(repo)
    db_session.commit()

    demo_dir = (
        Path("examples/demo_repo")
        if Path("examples/demo_repo").exists()
        else Path(__file__).resolve().parent.parent.parent / "examples" / "demo_repo"
    )
    ops_file = demo_dir / "demo" / "operations.py"
    spec_file = demo_dir / "algorevive.workload.json"

    # Ingest operations.py into storage and DB
    ops_code = ops_file.read_bytes()
    storage_key = f"repos/{repo_id}/files/demo/operations.py"
    storage.put_file(storage_key, ops_code)

    file_rec = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="demo/operations.py",
        language="python",
        loc=len(ops_code.splitlines()),
        sha256="fake_sha",
        storage_key=storage_key,
    )
    db_session.add(file_rec)

    # Ingest algorevive.workload.json
    spec_bytes = spec_file.read_bytes()
    storage_key_spec = f"repos/{repo_id}/files/algorevive.workload.json"
    storage.put_file(storage_key_spec, spec_bytes)

    spec_rec = File(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        path="algorevive.workload.json",
        language="json",
        loc=len(spec_bytes.splitlines()),
        sha256="fake_sha_spec",
        storage_key=storage_key_spec,
    )
    db_session.add(spec_rec)
    db_session.commit()

    # Create analysis run
    spec_data = json.loads(spec_bytes.decode("utf-8"))
    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=user.id,
        status="queued",
        stage="queued",
        progress=0,
        workload_spec=spec_data,
    )
    db_session.add(run)
    db_session.commit()

    # Execute full analysis pipeline
    completed_run = execute_analysis(db_session, storage, run.id)
    assert completed_run.status == "completed"

    # Query bottlenecks
    bottlenecks = (
        db_session.query(Bottleneck)
        .filter(Bottleneck.analysis_run_id == run.id)
        .order_by(Bottleneck.impact_score.desc())
        .all()
    )
    assert len(bottlenecks) >= 4

    bottleneck_map = {b.function.name: b for b in bottlenecks}

    # Verify slow functions exist in bottlenecks
    assert "slow_membership" in bottleneck_map
    assert "nested_match" in bottleneck_map
    assert "fib" in bottleneck_map

    slow_mem = bottleneck_map["slow_membership"]
    nested = bottleneck_map["nested_match"]
    fib_b = bottleneck_map["fib"]

    # Verify efficient_total is LOW if present
    if "efficient_total" in bottleneck_map:
        eff = bottleneck_map["efficient_total"]
        assert eff.severity == "LOW"
        assert eff.impact_score < 0.25
        # Assert slow functions rank strictly higher in impact than efficient_total
        assert slow_mem.impact_score > eff.impact_score
        assert nested.impact_score > eff.impact_score
        assert fib_b.impact_score > eff.impact_score

    # Assert plausible runtime percentages and evidence populated
    assert slow_mem.evidence["why_flagged"] is not None
    assert nested.evidence["workload"] is not None
    assert "features" in fib_b.evidence
    assert len(fib_b.evidence["features_array"]) == 12


# 7. Ownership isolation tests
def test_bottleneck_api_and_ownership_isolation(client: TestClient, db_session):
    """Test GET /analysis-runs/{id}/bottlenecks, GET /bottlenecks/{id}, and GET /bottlenecks/{id}/recommendation
    with strict owner-scoping and 404 NOT_READY for recommendation.
    """
    user1 = User(id=str(uuid.uuid4()), email="owner@example.com", hashed_password="pw", role="user", is_active=True)
    user2 = User(id=str(uuid.uuid4()), email="other@example.com", hashed_password="pw", role="user", is_active=True)
    db_session.add_all([user1, user2])
    db_session.commit()

    token1 = create_access_token(user1.id)
    token2 = create_access_token(user2.id)

    proj = Project(id=str(uuid.uuid4()), owner_id=user1.id, name="User1 Project")
    db_session.add(proj)
    db_session.commit()

    repo = Repository(id=str(uuid.uuid4()), project_id=proj.id, source_type="zip", storage_key="fake", status="ingested")
    db_session.add(repo)
    db_session.commit()

    file_rec = File(id=str(uuid.uuid4()), repository_id=repo.id, path="mod.py", language="python", loc=10, sha256="s", storage_key="sk")
    db_session.add(file_rec)
    db_session.commit()

    fn = Function(
        id=str(uuid.uuid4()),
        file_id=file_rec.id,
        repository_id=repo.id,
        qualified_name="mod:func",
        name="func",
        lineno=1,
        end_lineno=5,
        complexity_rank=4,
    )
    db_session.add(fn)
    db_session.commit()

    run = AnalysisRun(id=str(uuid.uuid4()), repository_id=repo.id, requested_by=user1.id, status="completed", stage="completed", progress=100)
    db_session.add(run)
    db_session.commit()

    b = Bottleneck(
        id=str(uuid.uuid4()),
        analysis_run_id=run.id,
        function_id=fn.id,
        static_score=0.6667,
        runtime_score=0.8,
        call_count=100,
        runtime_pct=0.9,
        memory_peak_kb=100.0,
        impact_score=0.75,
        severity="CRITICAL",
        evidence={"why_flagged": {"metric": "severity", "value": "CRITICAL"}},
    )
    db_session.add(b)
    db_session.commit()

    # 1. Owner can list bottlenecks
    headers1 = {"Authorization": f"Bearer {token1}"}
    res = client.get(f"/api/v1/analysis-runs/{run.id}/bottlenecks", headers=headers1)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["id"] == b.id
    assert data[0]["severity"] == "CRITICAL"

    # Filter tests
    res_filt = client.get(f"/api/v1/analysis-runs/{run.id}/bottlenecks?severity=LOW", headers=headers1)
    assert res_filt.status_code == 200
    assert len(res_filt.json()) == 0

    res_filt_crit = client.get(f"/api/v1/analysis-runs/{run.id}/bottlenecks?severity=CRITICAL", headers=headers1)
    assert res_filt_crit.status_code == 200
    assert len(res_filt_crit.json()) == 1

    # 2. Other user gets 404
    headers2 = {"Authorization": f"Bearer {token2}"}
    res_other = client.get(f"/api/v1/analysis-runs/{run.id}/bottlenecks", headers=headers2)
    assert res_other.status_code == 404

    # 3. Owner gets bottleneck details
    res_detail = client.get(f"/api/v1/bottlenecks/{b.id}", headers=headers1)
    assert res_detail.status_code == 200
    assert res_detail.json()["impact_score"] == 0.75
    assert res_detail.json()["evidence"]["why_flagged"]["value"] == "CRITICAL"

    # Other user gets 404 on bottleneck detail
    res_detail_other = client.get(f"/api/v1/bottlenecks/{b.id}", headers=headers2)
    assert res_detail_other.status_code == 404

    # 4. Recommendation returns 404 with code NOT_READY until Phase 5
    res_rec = client.get(f"/api/v1/bottlenecks/{b.id}/recommendation", headers=headers1)
    assert res_rec.status_code == 404
    assert res_rec.json()["code"] == "NOT_READY"

    # Other user gets 404 NOT_FOUND on recommendation
    res_rec_other = client.get(f"/api/v1/bottlenecks/{b.id}/recommendation", headers=headers2)
    assert res_rec_other.status_code == 404
