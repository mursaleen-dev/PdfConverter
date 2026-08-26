"""Celery app configuration."""
import os
from celery import Celery
from kombu import Exchange, Queue

# Celery broker (Redis) URL
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

# When no Redis/worker is available (e.g. local dev without Docker), tasks run
# synchronously in-process instead of being queued. Same task code path either
# way; only the execution model changes. Set CELERY_TASK_ALWAYS_EAGER=false
# once Redis + a real worker are running.
TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "true").lower() == "true"

celery_app = Celery("pdf_tools", broker=CELERY_BROKER_URL)

# Configure Celery
celery_app.conf.update(
    # Broker settings
    broker_url=CELERY_BROKER_URL,
    result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),

    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (memory management)
    task_track_started=True,
    task_acks_late=True,

    # Retry settings
    task_autoretry_for=(Exception,),
    task_max_retries=2,
    task_default_retry_delay=60,

    # Queue configuration (single default queue for now)
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
    ),

    # Hard time limits (prevent hung tasks)
    task_time_limit=600,  # Global hard limit: 10 minutes

    # Eager mode: run tasks synchronously in the calling process, no broker
    # or separate worker needed. Used for local dev when Redis/Docker isn't
    # available. task_eager_propagates surfaces exceptions immediately
    # instead of swallowing them, matching real worker behavior for testing.
    task_always_eager=TASK_ALWAYS_EAGER,
    task_eager_propagates=TASK_ALWAYS_EAGER,
)


# Auto-discover tasks from all modules
celery_app.autodiscover_tasks(["app.tasks"])

# Backwards-compat alias (some tooling/docs reference `app`)
app = celery_app
