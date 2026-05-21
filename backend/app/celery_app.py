"""Celery app + beat schedule."""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "jobhunter",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.scrape_tasks",
        "app.workers.score_tasks",
        "app.workers.generate_tasks",
        "app.workers.apply_tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    task_default_queue="default",
    task_routes={
        "app.workers.scrape_tasks.*": {"queue": "scrape"},
        "app.workers.score_tasks.*": {"queue": "scoring"},
        "app.workers.generate_tasks.*": {"queue": "generation"},
        "app.workers.apply_tasks.*": {"queue": "apply"},
    },
    beat_schedule={
        "scrape-active-criteria-every-6h": {
            "task": "app.workers.scrape_tasks.scrape_all_active_criteria",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
