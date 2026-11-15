def test_projects_crud_and_isolation(client):
    # 1. Register User A and User B
    resp_a = client.post(
        "/api/v1/auth/register",
        json={"email": "usera@example.com", "password": "password123", "full_name": "User A"},
    )
    assert resp_a.status_code == 201
    resp_login_a = client.post(
        "/api/v1/auth/login",
        json={"email": "usera@example.com", "password": "password123"},
    )
    token_a = resp_login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_b = client.post(
        "/api/v1/auth/register",
        json={"email": "userb@example.com", "password": "password123", "full_name": "User B"},
    )
    assert resp_b.status_code == 201
    resp_login_b = client.post(
        "/api/v1/auth/login",
        json={"email": "userb@example.com", "password": "password123"},
    )
    token_b = resp_login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. User A creates project
    resp = client.post(
        "/api/v1/projects",
        json={"name": "Project Alpha", "description": "High performance python code"},
        headers=headers_a,
    )
    assert resp.status_code == 201
    proj_a = resp.json()
    proj_id = proj_a["id"]
    assert proj_a["name"] == "Project Alpha"

    # 3. User A lists projects
    resp = client.get("/api/v1/projects", headers=headers_a)
    assert resp.status_code == 200
    assert any(p["id"] == proj_id for p in resp.json())

    # 4. User B lists projects (should NOT see User A's project)
    resp = client.get("/api/v1/projects", headers=headers_b)
    assert resp.status_code == 200
    assert not any(p["id"] == proj_id for p in resp.json())

    # 5. User B tries to get User A's project -> 404 (Contract H4)
    resp = client.get(f"/api/v1/projects/{proj_id}", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"

    # 6. User B tries to patch User A's project -> 404
    resp = client.patch(
        f"/api/v1/projects/{proj_id}",
        json={"name": "Hacked Name"},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 7. User B tries to delete User A's project -> 404
    resp = client.delete(f"/api/v1/projects/{proj_id}", headers=headers_b)
    assert resp.status_code == 404

    # 8. User A updates project
    resp = client.patch(
        f"/api/v1/projects/{proj_id}",
        json={"name": "Project Alpha Updated"},
        headers=headers_a,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Project Alpha Updated"

    # 9. User A deletes project -> 204
    resp = client.delete(f"/api/v1/projects/{proj_id}", headers=headers_a)
    assert resp.status_code == 204

    # 10. User A gets deleted project -> 404
    resp = client.get(f"/api/v1/projects/{proj_id}", headers=headers_a)
    assert resp.status_code == 404
