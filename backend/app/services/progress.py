import json
import time
from typing import Any, Dict
import redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("progress")

_last_redis_failure: float = 0.0


def publish(job_id: str, payload: Dict[str, Any]) -> None:
    """Publishes a progress payload to Redis channel progress:{job_id}.
    
    Wrapped in try/except with a brief failure cooldown so Redis outages
    or connection timeouts never slow down requests or test execution.
    """
    global _last_redis_failure
    now = time.time()
    if now - _last_redis_failure < 5.0:
        return

    channel = f"progress:{job_id}"
    cache_key = f"progress_latest:{job_id}"
    try:
        r = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        message = json.dumps(payload)
        r.publish(channel, message)
        r.set(cache_key, message, ex=3600)
    except Exception as e:
        _last_redis_failure = time.time()
        logger.warning(f"Failed to publish progress to Redis channel {channel}: {e}")


def publish_progress(
    job_id: str,
    stage: str,
    progress: int,
    status: str = "running",
    message: str | None = None,
    error: str | None = None,
) -> None:
    """Convenience helper to publish structured progress updates."""
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "stage": stage,
        "progress": progress,
        "status": status,
        "message": message or f"Stage: {stage} ({progress}%)",
    }
    if error is not None:
        payload["error"] = error
        payload["message"] = error
    publish(job_id, payload)

