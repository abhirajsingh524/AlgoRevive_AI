from app.services.progress import publish
from app.workers.celery_app import ping


def test_celery_ping_task():
    # Direct task execution test
    result = ping()
    assert result == "pong"


def test_progress_publish_handles_redis_outage():
    # Calling publish with invalid or disconnected redis should not raise any exception
    publish("fake-job-id-123", {"stage": "test", "progress": 50})
