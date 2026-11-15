import io
import zipfile
from app.models.audit_log import AuditLog


def create_zip_in_memory(file_dict: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in file_dict.items():
            zf.writestr(filename, data)
    return buf.getvalue()


def get_auth_headers_and_project(client):
    # Register & Login
    client.post(
        "/api/v1/auth/register",
        json={"email": "developer@example.com", "password": "password123", "full_name": "Dev"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "developer@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create project
    proj_resp = client.post(
        "/api/v1/projects",
        json={"name": "Repo Project", "description": "Testing repos"},
        headers=headers,
    )
    return headers, proj_resp.json()["id"]


def test_upload_success_and_browsing(client, db_session):
    headers, project_id = get_auth_headers_and_project(client)

    # 1. Create a clean zip with some python files and ignored dirs
    zip_bytes = create_zip_in_memory({
        "main.py": b"def hello():\n    print('world')\n",
        "utils/helper.py": b"def add(a, b):\n    return a + b\n",
        ".git/config": b"ignored git data",
        "__pycache__/cache.pyc": b"ignored pycache",
    })

    # Upload zip
    files = {"files": ("repo.zip", zip_bytes, "application/zip")}
    data = {"version_label": "v1.0"}
    resp = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        headers=headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 201
    repo_data = resp.json()
    repo_id = repo_data["id"]
    assert repo_data["version_label"] == "v1.0"
    assert repo_data["status"] == "ingested"
    assert repo_data["file_count"] == 2  # .git and __pycache__ ignored!
    assert repo_data["total_loc"] == 4

    # 2. List repositories in project
    resp = client.get(f"/api/v1/projects/{project_id}/repositories", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert any(r["id"] == repo_id for r in resp.json())

    # 3. Get repository
    resp = client.get(f"/api/v1/repositories/{repo_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == repo_id

    # 4. List files
    resp = client.get(f"/api/v1/repositories/{repo_id}/files", headers=headers)
    assert resp.status_code == 200
    file_list = resp.json()
    assert len(file_list) == 2
    paths = [f["path"] for f in file_list]
    assert "main.py" in paths
    assert "utils/helper.py" in paths

    # 5. Get file content
    main_file = next(f for f in file_list if f["path"] == "main.py")
    resp = client.get(f"/api/v1/repositories/{repo_id}/files/{main_file['id']}/content", headers=headers)
    assert resp.status_code == 200
    content_data = resp.json()
    assert "def hello():" in content_data["content"]
    assert content_data["language"] == "python"

    # 6. Verify audit log entry
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "UPLOAD",
        AuditLog.entity_id == repo_id,
    ).first()
    assert audit is not None
    assert audit.meta["file_count"] == 2


def test_zip_slip_rejected(client):
    headers, project_id = get_auth_headers_and_project(client)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", b"root:x:0:0::/root:/bin/bash")

    files = {"files": ("slip.zip", buf.getvalue(), "application/zip")}
    resp = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        headers=headers,
        files=files,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "ZIP_SLIP_DETECTED"


def test_absolute_path_rejected(client):
    headers, project_id = get_auth_headers_and_project(client)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/root/evil.py", b"evil code")

    files = {"files": ("abs.zip", buf.getvalue(), "application/zip")}
    resp = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        headers=headers,
        files=files,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "ABSOLUTE_PATH_DETECTED"


def test_symlink_rejected(client):
    headers, project_id = get_auth_headers_and_project(client)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zinfo = zipfile.ZipInfo("link.py")
        # 0o120000 indicates symlink in POSIX permissions
        zinfo.external_attr = 0o120777 << 16
        zf.writestr(zinfo, "/etc/passwd")

    files = {"files": ("symlink.zip", buf.getvalue(), "application/zip")}
    resp = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        headers=headers,
        files=files,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "SYMLINK_DETECTED"


def test_oversize_file_rejected(client):
    headers, project_id = get_auth_headers_and_project(client)

    # File exceeding 2 MB decompressed
    large_content = b"A" * (2 * 1024 * 1024 + 10)
    zip_bytes = create_zip_in_memory({"huge.py": large_content})

    files = {"files": ("huge.zip", zip_bytes, "application/zip")}
    resp = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        headers=headers,
        files=files,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "FILE_TOO_LARGE"
