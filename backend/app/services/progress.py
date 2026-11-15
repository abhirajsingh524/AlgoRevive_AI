import json
from typing import Any, Dict
import redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("progress")


def publish(job_id: str, payload: Dict[str, Any]) -> None:
    """Publishes a progress payload to Redis channel progress:{job_id}.
    
    Wrapped in try/except so Redis outages or connection errors never break a request.
    """
    channel = f"progress:{job_id}"
    try:
        r = redis.from_url(settings.REDIS_URL, socket_timeout=1.0)
        message = json.dumps(payload)
        r.publish(channel, message)
    except Exception as e:
        logger.warning(f"Failed to publish progress to Redis channel {channel}: {e}")


def publish_progress(
    job_id: str,
    stage: str,
    progress: int,
    status: str = "running",
    error: str | None = None,
) -> None:
    """Convenience helper to publish structured progress updates."""
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "stage": stage,
        "progress": progress,
        "status": status,
    }
    if error is not None:
        payload["error"] = error
    publish(job_id, payload)

