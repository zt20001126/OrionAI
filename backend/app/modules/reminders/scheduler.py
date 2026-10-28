"""扫描到期提醒、恢复租约过期任务并在事务提交后投递 Celery 消息。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.modules.reminders import repository
from app.modules.reminders.constants import (
    EXECUTION_CANCELLED,
    EXECUTION_FAILED,
    EXECUTION_PENDING,
    EXECUTION_RETRY_WAIT,
    EXECUTION_SENDING,
    MAX_RETRY_COUNT,
    REMINDER_CANCELLED,
    REMINDER_COMPLETED,
    REMINDER_PAUSED,
    REPEAT_ONCE,
)
from app.modules.reminders.errors import ReminderScheduleError, ReminderUnavailableError
from app.modules.reminders.lifecycle import complete_if_no_future
from app.modules.reminders.models import Reminder, ReminderExecution
from app.modules.reminders.recurrence import latest_due_occurrence, next_occurrence_after
from app.modules.reminders.retry_policy import retry_delay

logger = logging.getLogger(__name__)
ExecutionDispatcher = Callable[[int], None]


class ReminderScheduler:
    """提醒扫描服务；PostgreSQL 中的提醒和执行行是任务状态的唯一事实来源。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        dispatch_execution: ExecutionDispatcher,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._dispatch_execution = dispatch_execution

    def run(self, *, now: datetime | None = None) -> dict[str, int]:
        """完成一轮到期扫描与投递恢复。

        Step 1: 在 PostgreSQL 事务中认领到期提醒并创建唯一执行记录。
        Step 2: 恢复租约过期的 sending 执行，提交所有状态变更。
        Step 3: 事务外重新投递 pending 和到期 retry_wait 执行 ID。
        """

        scan_time = _as_utc(now or datetime.now(UTC))
        created_count = 0
        recovered_count = 0
        try:
            with self._session_factory() as session:
                due_reminders = repository.select_due_reminders(
                    session,
                    now=scan_time,
                    limit=self._settings.reminder_scan_batch_size,
                )
                for reminder in due_reminders:
                    created_count += self._schedule_due_reminder(session, reminder, now=scan_time)
                recovered_count = self._recover_expired_executions(session, now=scan_time)
                session.commit()
        except ReminderScheduleError:
            logger.exception("reminder_schedule_rule_invalid")
            raise
        except SQLAlchemyError as error:
            logger.exception("reminder_scan_database_error")
            raise ReminderUnavailableError from error

        dispatch_count = self._dispatch_ready_executions(now=scan_time)
        return {
            "created": created_count,
            "recovered": recovered_count,
            "dispatched": dispatch_count,
        }

    def _schedule_due_reminder(
        self,
        session: Session,
        reminder: Reminder,
        *,
        now: datetime,
    ) -> int:
        """为锁定提醒生成一个执行记录并原子推进下次计划。"""

        scheduled_at = reminder.next_run_at
        if scheduled_at is None:
            return 0
        if reminder.repeat_type == REPEAT_ONCE:
            latest_due = _as_utc(scheduled_at)
            # 执行尚未终结时保留原计划，支持展示和修改排队中的单次提醒。
            next_run_at = scheduled_at
        else:
            latest_due = latest_due_occurrence(
                reminder.repeat_type,
                reminder.repeat_config,
                reminder.timezone,
                now=now,
                end_date=reminder.end_date,
            )
            next_run_at = next_occurrence_after(
                reminder.repeat_type,
                reminder.repeat_config,
                reminder.timezone,
                reference=now,
                end_date=reminder.end_date,
            )

        if latest_due is None:
            reminder.next_run_at = next_run_at
            if next_run_at is None:
                reminder.status = REMINDER_COMPLETED
            return 0

        existing = repository.get_execution_for_schedule(session, reminder.id, latest_due)
        created_count = 0
        if existing is None:
            session.add(
                ReminderExecution(
                    reminder_id=reminder.id,
                    scheduled_at=latest_due,
                    status=EXECUTION_PENDING,
                    retry_count=0,
                )
            )
            session.flush()
            created_count = 1

        reminder.next_run_at = next_run_at
        # 最后一次周期执行完成前保持 active，Worker 在终态时再标记 completed。
        return created_count

    def _recover_expired_executions(self, session: Session, *, now: datetime) -> int:
        """以 Reminder→Execution 的统一锁顺序恢复僵死发送租约。"""

        cutoff = now - timedelta(seconds=self._settings.reminder_sending_lease_seconds)
        execution_ids = repository.select_expired_sending_execution_ids(
            session,
            lease_expired_at=cutoff,
            limit=self._settings.reminder_scan_batch_size,
        )
        recovered_count = 0
        for execution_id in execution_ids:
            execution_snapshot = repository.get_execution(session, execution_id)
            if execution_snapshot is None:
                continue
            reminder = repository.get_reminder_for_worker(
                session, execution_snapshot.reminder_id, for_update=True
            )
            execution = repository.get_execution(session, execution_id, for_update=True)
            if (
                reminder is None
                or execution is None
                or execution.status != EXECUTION_SENDING
                or execution.started_at is None
                or _as_utc(execution.started_at) > cutoff
            ):
                continue

            if reminder.status in (REMINDER_PAUSED, REMINDER_CANCELLED):
                execution.status = EXECUTION_CANCELLED
                execution.next_retry_at = None
                execution.finished_at = now
                execution.error_message = "提醒已暂停或取消，未继续发送。"
                recovered_count += 1
                continue

            if execution.retry_count >= MAX_RETRY_COUNT:
                execution.status = EXECUTION_FAILED
                execution.next_retry_at = None
                execution.finished_at = now
                execution.error_message = "Worker 执行中断，已达到最大尝试次数。"
                complete_if_no_future(reminder)
            else:
                execution.retry_count += 1
                execution.status = EXECUTION_RETRY_WAIT
                execution.next_retry_at = now + retry_delay(execution.retry_count)
                execution.error_message = "Worker 执行中断，发送结果未知，将在稍后重试。"
            recovered_count += 1
        return recovered_count

    def _dispatch_ready_executions(self, *, now: datetime) -> int:
        """提交事务后投递数据库中仍可执行的任务，发布故障不改变业务状态。"""

        with self._session_factory() as session:
            execution_ids = repository.list_dispatchable_execution_ids(
                session,
                now=now,
                limit=self._settings.reminder_scan_batch_size,
            )
        dispatch_count = 0
        for execution_id in execution_ids:
            try:
                self._dispatch_execution(execution_id)
                dispatch_count += 1
            except Exception:
                logger.exception("reminder_execution_dispatch_failed execution_id=%s", execution_id)
        return dispatch_count


def _as_utc(value: datetime) -> datetime:
    """将 SQLAlchemy 时间值规范为带时区 UTC。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
