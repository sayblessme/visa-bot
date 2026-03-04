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
    "refresh-vfs-token-every-10min": {
        "task": "app.tasks.vfs_token_refresh.refresh_vfs_token",
        "schedule": 600.0,  # 10 minutes
    },
}
