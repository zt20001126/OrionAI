"""配置后台 Celery Worker 与 Beat，复用 Redis 且不启动 FastAPI 应用生命周期。"""

from celery import Celery
from celery.schedules import schedule

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "orionai",
    broker=settings.redis_url,
    include=["app.modules.reminders.tasks"],
)
celery_app.conf.update(
    broker_url=settings.redis_url,
    result_backend=None,
    task_default_queue=settings.reminder_task_queue,
    task_routes={
        "app.modules.reminders.tasks.scan_due_reminders": {"queue": settings.reminder_task_queue},
        "app.modules.reminders.tasks.send_reminder_execution": {
            "queue": settings.reminder_task_queue
        },
    },
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "scan-reminders-every-configured-interval": {
            "task": "app.modules.reminders.tasks.scan_due_reminders",
            "schedule": schedule(settings.reminder_scan_interval_seconds),
            "options": {"queue": settings.reminder_task_queue},
        }
    },
)
