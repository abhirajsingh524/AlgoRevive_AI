from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "algorevive",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=False,
    broker_transport_options={
        "socket_timeout": 1.0,
        "socket_connect_timeout": 1.0,
        "max_retries": 0,
    },
)


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"
