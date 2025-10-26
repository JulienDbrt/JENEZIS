"""
Celery application for async task execution.

Handles background tasks like LLM enrichment, batch processing, etc.
"""

import os

from celery import Celery

# Redis broker URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
app = Celery(
    "erwin_harmonizer",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.tasks.enrichment", "src.tasks.suggestions"],
)

# Configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # Soft limit at 9 minutes
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    broker_connection_retry_on_startup=True,
)

# Task routes (optional - for multiple queues)
app.conf.task_routes = {
    "src.tasks.enrichment.*": {"queue": "enrichment"},
    "src.tasks.suggestions.*": {"queue": "suggestions"},
}


if __name__ == "__main__":
    app.start()
