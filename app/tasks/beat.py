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
    "keepalive-vfs-token-every-5min": {
        "task": "app.tasks.vfs_token_refresh.keepalive_vfs_token",
        "schedule": 300.0,  # 5 minutes
    },
}
