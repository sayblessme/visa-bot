"""
Celery Beat schedule: periodically dispatch monitoring tasks for active watches.
"""

from celery.schedules import crontab

from app.tasks.celery_app import celery_app

celery_app.conf.beat_schedule = {
    "dispatch-monitors-every-60s": {
        "task": "app.tasks.monitor.dispatch_monitors",
        "schedule": 60.0,
    },
}
