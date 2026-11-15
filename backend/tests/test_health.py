from fastapi.testclient import TestClient
from app.main import app
from app.services.storage import LocalStorage

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_local_storage(tmp_path):
    storage = LocalStorage(base_dir=str(tmp_path))
    test_key = "test/sample.txt"
    test_data = b"hello algorevive"
    
    assert storage.check_health() is True
    assert storage.exists(test_key) is False
    
    storage.put_file(test_key, test_data)
    assert storage.exists(test_key) is True
    assert storage.get_file(test_key) == test_data
    
    storage.delete_file(test_key)
    assert storage.exists(test_key) is False
