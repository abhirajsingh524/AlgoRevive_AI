from app.models.audit_log import AuditLog


def test_auth_full_flow(client, db_session):
    # 1. Register short password rejected
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "short"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PASSWORD"

    # 2. Register valid user
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "securepassword123", "full_name": "Alice Smith"},
    )
    assert resp.status_code == 201
    user_data = resp.json()
    assert user_data["email"] == "alice@example.com"
    assert user_data["full_name"] == "Alice Smith"

    # 3. Duplicate email rejected
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "anotherpassword123"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "EMAIL_ALREADY_REGISTERED"

    # 4. Login wrong password rejected
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"

    # 5. Login success
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "securepassword123"},
    )
    assert resp.status_code == 200
    token_data = resp.json()
    assert "access_token" in token_data
    token = token_data["access_token"]

    # 6. /auth/me with valid token
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"

    # 7. /auth/me with bad token
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad-token-123"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"

    # 8. Check audit logs
    audit_logs = db_session.query(AuditLog).filter(AuditLog.user_id == user_data["id"]).all()
    actions = [a.action for a in audit_logs]
    assert "REGISTER" in actions
    assert "LOGIN" in actions
