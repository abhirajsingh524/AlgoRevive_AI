import asyncio
from collections import defaultdict
import json
import threading
import time
from typing import Any, Dict, Set
import redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("progress")

_last_redis_failure: float = 0.0

# In-memory subscriber registry for standalone / local execution without Redis
_local_subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
_subscribers_lock = threading.Lock()


def register_local_listener(job_id: str, queue: asyncio.Queue) -> None:
    """Register an asyncio queue to receive live progress updates for job_id."""
    with _subscribers_lock:
        _local_subscribers[job_id].add(queue)


def unregister_local_listener(job_id: str, queue: asyncio.Queue) -> None:
    """Unregister an asyncio queue from job_id progress updates."""
    with _subscribers_lock:
        if job_id in _local_subscribers:
            _local_subscribers[job_id].discard(queue)
            if not _local_subscribers[job_id]:
                del _local_subscribers[job_id]


def broadcast_local(job_id: str, payload: Dict[str, Any]) -> None:
    """Deliver progress payload to any registered in-memory asyncio queues."""
    with _subscribers_lock:
        queues = list(_local_subscribers.get(job_id, []))

    for q in queues:
        try:
            q.put_nowait(payload)
        except Exception:
            pass


def publish(job_id: str, payload: Dict[str, Any]) -> None:
    """Publishes a progress payload to local memory bus and Redis channel progress:{job_id}.
    
    Wrapped in try/except with a brief failure cooldown so Redis outages
    or connection timeouts never slow down requests or test execution.
    """
    global _last_redis_failure

    # 1. Deliver immediately to any local in-memory listeners
    broadcast_local(job_id, payload)

    # 2. Also publish to Redis if available
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

