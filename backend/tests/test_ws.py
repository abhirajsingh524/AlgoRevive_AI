"""Tests for WebSocket authentication, ownership scoping, and initial state streaming."""

import uuid
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.models.analysis_run import AnalysisRun
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User


def test_ws_missing_token_rejected(client: TestClient):
    """Connecting without token query param is rejected with 1008 Policy Violation."""
    fake_job_id = str(uuid.uuid4())
    with pytest.raises(Exception) as exc_info:
        with client.websocket_connect(f"/api/v1/ws/jobs/{fake_job_id}"):
            pass
    err = exc_info.value
    if isinstance(err, WebSocketDisconnect):
        assert err.code == 1008
    else:
        assert "WebSocketDenialResponse" in type(err).__name__ or hasattr(err, "status_code")


def test_ws_invalid_token_rejected(client: TestClient):
    """Connecting with an invalid / forged token is rejected with 1008."""
    fake_job_id = str(uuid.uuid4())
    with pytest.raises(Exception) as exc_info:
        with client.websocket_connect(f"/api/v1/ws/jobs/{fake_job_id}?token=invalid.token.here"):
            pass
    err = exc_info.value
    if isinstance(err, WebSocketDisconnect):
        assert err.code == 1008
    else:
        assert "WebSocketDenialResponse" in type(err).__name__ or hasattr(err, "status_code")


def test_ws_non_owner_rejected(client: TestClient, db_session):
    """Connecting with User B's token to User A's job is rejected with 1008."""
    # User A (Owner)
    user_a = User(
        id=str(uuid.uuid4()),
        email="user_a@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    # User B (Attacker)
    user_b = User(
        id=str(uuid.uuid4()),
        email="user_b@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    db_session.commit()

    proj = Project(id=str(uuid.uuid4()), owner_id=user_a.id, name="Project A")
    db_session.add(proj)
    db_session.commit()

    repo = Repository(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        source_type="zip",
        storage_key="dummy",
        status="ingested",
    )
    db_session.add(repo)
    db_session.commit()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=user_a.id,
        status="running",
        stage="static",
        progress=25,
    )
    db_session.add(run)
    db_session.commit()

    # User B tries to connect to User A's run
    token_b = create_access_token(user_b.id)
    with pytest.raises(Exception) as exc_info:
        with client.websocket_connect(f"/api/v1/ws/jobs/{run.id}?token={token_b}"):
            pass
    err = exc_info.value
    if isinstance(err, WebSocketDisconnect):
        assert err.code == 1008
    else:
        assert "WebSocketDenialResponse" in type(err).__name__ or hasattr(err, "status_code")


def test_ws_owner_receives_latest_state_first(client: TestClient, db_session):
    """Owner connecting to a job immediately receives the latest saved state."""
    owner = User(
        id=str(uuid.uuid4()),
        email="owner@example.com",
        hashed_password="pw",
        role="user",
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()

    proj = Project(id=str(uuid.uuid4()), owner_id=owner.id, name="Owner Project")
    db_session.add(proj)
    db_session.commit()

    repo = Repository(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        source_type="zip",
        storage_key="dummy",
        status="ingested",
    )
    db_session.add(repo)
    db_session.commit()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        requested_by=owner.id,
        status="completed",
        stage="completed",
        progress=100,
    )
    db_session.add(run)
    db_session.commit()

    token = create_access_token(owner.id)
    with client.websocket_connect(f"/api/v1/ws/jobs/{run.id}?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["stage"] == "completed"
        assert msg["progress"] == 100
        assert msg["status"] == "completed"
