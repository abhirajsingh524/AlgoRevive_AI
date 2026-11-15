from fastapi import APIRouter, Response, status
import redis
from app.core.config import settings
from app.db.session import check_db_health
from app.services.storage import get_storage_service

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(response: Response) -> dict[str, str]:
    # 1. Check DB
    db_ok = check_db_health()

    # 2. Check Redis
    redis_ok = False
    try:
        r = redis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        redis_ok = bool(r.ping())
    except Exception:
        redis_ok = False

    # 3. Check Storage
    storage_ok = False
    try:
        storage = get_storage_service()
        storage_ok = storage.check_health()
    except Exception:
        storage_ok = False

    all_ready = db_ok and redis_ok and storage_ok
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "not_ready",
        "database": "healthy" if db_ok else "unhealthy",
        "redis": "healthy" if redis_ok else "unhealthy",
        "storage": "healthy" if storage_ok else "unhealthy",
    }
