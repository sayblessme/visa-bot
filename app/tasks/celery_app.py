from celery import Celery

from app.config import settings

celery_app = Celery(
    "visa_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

# Explicit imports — autodiscover doesn't work with our package layout
import app.tasks.monitor  # noqa: E402, F401
import app.tasks.book  # noqa: E402, F401
import app.tasks.beat  # noqa: E402, F401
