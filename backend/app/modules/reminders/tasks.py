"""定义只负责装配提醒服务的 Celery Beat 扫描任务和邮件执行任务。"""

import logging

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.infrastructure.database.session import SessionLocal
from app.modules.reminders.execution_service import ReminderExecutionService
from app.modules.reminders.scheduler import ReminderScheduler

logger = logging.getLogger(__name__)
settings = get_settings()
SCAN_TASK_NAME = "app.modules.reminders.tasks.scan_due_reminders"
SEND_TASK_NAME = "app.modules.reminders.tasks.send_reminder_execution"


@celery_app.task(name=SCAN_TASK_NAME)
def scan_due_reminders() -> dict[str, int]:
    """调用扫描 Service；任务本身不实现提醒规则或 SQL 操作。"""

    scheduler = ReminderScheduler(
        SessionLocal,
        settings,
        dispatch_execution=lambda execution_id: celery_app.send_task(
            SEND_TASK_NAME,
            args=[execution_id],
            queue=settings.reminder_task_queue,
        ),
    )
    try:
        return scheduler.run()
    except Exception:
        logger.exception("reminder_scheduled_scan_failed")
        raise


@celery_app.task(name=SEND_TASK_NAME)
def send_reminder_execution(execution_id: int) -> str:
    """按执行记录 ID 构造 Service 并处理一封提醒邮件。"""

    service = ReminderExecutionService(SessionLocal, settings)
    return service.execute(execution_id)
