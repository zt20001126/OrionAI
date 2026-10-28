"""编排提醒 CRUD、用户权限、状态迁移和事务边界。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.reminders import repository
from app.modules.reminders.constants import (
    EXECUTION_SENDING,
    REMINDER_ACTIVE,
    REMINDER_CANCELLED,
    REMINDER_COMPLETED,
    REMINDER_PAUSED,
    REPEAT_ONCE,
)
from app.modules.reminders.errors import (
    ReminderConflictError,
    ReminderNotFoundError,
    ReminderScheduleError,
    ReminderUnavailableError,
)
from app.modules.reminders.models import Reminder, ReminderExecution
from app.modules.reminders.recurrence import (
    build_repeat_config,
    first_scheduled_at,
    latest_due_occurrence,
    next_occurrence_after,
)
from app.modules.reminders.schemas import (
    ReminderCreateRequest,
    ReminderExecutionListQuery,
    ReminderExecutionListResponse,
    ReminderExecutionResponse,
    ReminderListQuery,
    ReminderListResponse,
    ReminderResponse,
    ReminderUpdateRequest,
)

logger = logging.getLogger(__name__)


class ReminderService:
    """提醒应用服务，负责用户提醒的校验、状态流转和数据库事务。"""

    def __init__(
        self,
        session: Session,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(self, current_user: User, payload: ReminderCreateRequest) -> ReminderResponse:
        """创建当前用户的提醒。

        Step 1: 依据本地日期、时间及时区计算严格晚于当前时刻的首次计划。
        Step 2: 在单个事务中保存规则及其下次 UTC 执行时间。
        Step 3: 提交后构造不暴露用户邮箱的响应 DTO。
        """

        now = self._now()
        try:
            next_run_at = first_scheduled_at(
                payload.repeat_type,
                scheduled_date=payload.date,
                start_date=payload.start_date,
                local_time=payload.local_time,
                timezone_name=payload.timezone,
                now=now,
            )
            repeat_config = build_repeat_config(
                payload.repeat_type,
                scheduled_date=payload.date,
                start_date=payload.start_date,
                local_time=payload.local_time,
            )
            reminder = Reminder(
                user_id=current_user.id,
                title=payload.title,
                content=payload.content,
                repeat_type=payload.repeat_type,
                repeat_config=repeat_config,
                timezone=payload.timezone,
                next_run_at=next_run_at,
                end_date=payload.end_date,
                status=REMINDER_ACTIVE,
                version=1,
            )
            self._session.add(reminder)
            self._session.flush()
            self._session.commit()
            self._session.refresh(reminder)
            return _reminder_response(reminder)
        except ReminderScheduleError:
            self._session.rollback()
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            logger.exception("reminder_create_database_error user_id=%s", current_user.id)
            raise ReminderUnavailableError from error

    def list(self, current_user: User, query: ReminderListQuery) -> ReminderListResponse:
        """分页读取当前用户提醒，不读取其他用户的计划规则。"""

        try:
            reminders, total = repository.list_reminders(
                self._session,
                current_user.id,
                status=query.status,
                limit=query.limit,
                offset=query.offset,
            )
            return ReminderListResponse(
                items=[_reminder_response(item) for item in reminders],
                total=total,
                limit=query.limit,
                offset=query.offset,
            )
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ReminderUnavailableError from error

    def get(self, current_user: User, reminder_id: int) -> ReminderResponse:
        """读取当前用户的一条提醒，隐藏其他用户资源是否存在。"""

        try:
            reminder = repository.get_reminder_for_user(self._session, current_user.id, reminder_id)
            if reminder is None:
                raise ReminderNotFoundError
            return _reminder_response(reminder)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ReminderUnavailableError from error

    def update(
        self,
        current_user: User,
        reminder_id: int,
        payload: ReminderUpdateRequest,
    ) -> ReminderResponse:
        """原子替换提醒规则并拒绝与并发发送或编辑冲突。

        Step 1: 锁定当前用户的提醒并校验状态和乐观版本。
        Step 2: 锁定未终结执行；如果 Worker 已进入 SMTP 阶段则返回冲突。
        Step 3: 取消旧规则尚未开始的执行，替换规则、时间、版本并提交。
        """

        try:
            reminder = repository.get_reminder_for_user(
                self._session, current_user.id, reminder_id, for_update=True
            )
            if reminder is None:
                raise ReminderNotFoundError
            _ensure_editable(reminder, payload.expected_version)
            active_executions = repository.lock_active_executions(self._session, reminder.id)
            if any(item.status == EXECUTION_SENDING for item in active_executions):
                raise ReminderConflictError("提醒正在发送，当前无法修改。")

            now = self._now()
            repeat_config = build_repeat_config(
                payload.repeat_type,
                scheduled_date=payload.date,
                start_date=payload.start_date,
                local_time=payload.local_time,
            )
            if (
                payload.repeat_type != REPEAT_ONCE
                and payload.repeat_type == reminder.repeat_type
                and repeat_config.get("start_date") == reminder.repeat_config.get("start_date")
            ):
                # 原周期开始日期可能已过去；未改变规则锚点时，从现在计算下一次执行。
                next_run_at = next_occurrence_after(
                    payload.repeat_type,
                    repeat_config,
                    payload.timezone,
                    reference=now,
                    end_date=payload.end_date,
                )
                if next_run_at is None:
                    raise ReminderScheduleError("该周期规则已无未来执行时间。")
            else:
                next_run_at = first_scheduled_at(
                    payload.repeat_type,
                    scheduled_date=payload.date,
                    start_date=payload.start_date,
                    local_time=payload.local_time,
                    timezone_name=payload.timezone,
                    now=now,
                )
            repository.cancel_unstarted_executions(self._session, reminder.id, finished_at=now)
            reminder.title = payload.title
            reminder.content = payload.content
            reminder.repeat_type = payload.repeat_type
            reminder.repeat_config = repeat_config
            reminder.timezone = payload.timezone
            reminder.next_run_at = next_run_at
            reminder.end_date = payload.end_date
            reminder.version += 1
            self._session.flush()
            self._session.commit()
            self._session.refresh(reminder)
            return _reminder_response(reminder)
        except (ReminderConflictError, ReminderNotFoundError, ReminderScheduleError):
            self._session.rollback()
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            logger.exception("reminder_update_database_error reminder_id=%s", reminder_id)
            raise ReminderUnavailableError from error

    def pause(self, current_user: User, reminder_id: int) -> ReminderResponse:
        """暂停周期提醒并取消尚未开始处理的当前执行。"""

        try:
            reminder = self._lock_user_reminder(current_user.id, reminder_id)
            if reminder.status == REMINDER_PAUSED:
                self._session.commit()
                return _reminder_response(reminder)
            if reminder.status != REMINDER_ACTIVE or reminder.repeat_type == REPEAT_ONCE:
                raise ReminderConflictError("仅可暂停仍有效的周期提醒。")
            now = self._now()
            repository.lock_active_executions(self._session, reminder.id)
            repository.cancel_unstarted_executions(self._session, reminder.id, finished_at=now)
            reminder.status = REMINDER_PAUSED
            reminder.version += 1
            self._session.flush()
            self._session.commit()
            self._session.refresh(reminder)
            return _reminder_response(reminder)
        except (ReminderConflictError, ReminderNotFoundError):
            self._session.rollback()
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ReminderUnavailableError from error

    def resume(self, current_user: User, reminder_id: int) -> ReminderResponse:
        """恢复周期提醒，从恢复时刻之后的第一个规则时间继续。"""

        try:
            reminder = self._lock_user_reminder(current_user.id, reminder_id)
            if reminder.status == REMINDER_ACTIVE:
                self._session.commit()
                return _reminder_response(reminder)
            if reminder.status != REMINDER_PAUSED or reminder.repeat_type == REPEAT_ONCE:
                raise ReminderConflictError("仅可恢复已暂停的周期提醒。")
            now = self._now()
            latest_missed = latest_due_occurrence(
                reminder.repeat_type,
                reminder.repeat_config,
                reminder.timezone,
                now=now,
                end_date=reminder.end_date,
            )
            paused_plan = _ensure_aware(reminder.next_run_at)
            if (
                latest_missed is not None
                and paused_plan is not None
                and latest_missed >= paused_plan
            ):
                next_run_at = latest_missed
            else:
                next_run_at = next_occurrence_after(
                    reminder.repeat_type,
                    reminder.repeat_config,
                    reminder.timezone,
                    reference=now,
                    end_date=reminder.end_date,
                )
            reminder.next_run_at = next_run_at
            reminder.status = REMINDER_ACTIVE if next_run_at is not None else REMINDER_COMPLETED
            reminder.version += 1
            self._session.flush()
            self._session.commit()
            self._session.refresh(reminder)
            return _reminder_response(reminder)
        except (ReminderConflictError, ReminderNotFoundError, ReminderScheduleError):
            self._session.rollback()
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ReminderUnavailableError from error

    def cancel(self, current_user: User, reminder_id: int) -> ReminderResponse:
        """软取消提醒、保留历史并阻止所有未开始的执行继续发送。"""

        try:
            reminder = self._lock_user_reminder(current_user.id, reminder_id)
            if reminder.status == REMINDER_CANCELLED:
                self._session.commit()
                return _reminder_response(reminder)
            if reminder.status == REMINDER_COMPLETED:
                raise ReminderConflictError("已完成的提醒不能取消。")
            now = self._now()
            repository.lock_active_executions(self._session, reminder.id)
            repository.cancel_unstarted_executions(self._session, reminder.id, finished_at=now)
            reminder.status = REMINDER_CANCELLED
            reminder.next_run_at = None
            reminder.version += 1
            self._session.flush()
            self._session.commit()
            self._session.refresh(reminder)
            return _reminder_response(reminder)
        except (ReminderConflictError, ReminderNotFoundError):
            self._session.rollback()
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ReminderUnavailableError from error

    def list_executions(
        self,
        current_user: User,
        reminder_id: int,
        query: ReminderExecutionListQuery,
    ) -> ReminderExecutionListResponse:
        """校验提醒归属后读取执行历史，并对收件邮箱做掩码处理。"""

        try:
            reminder = repository.get_reminder_for_user(self._session, current_user.id, reminder_id)
            if reminder is None:
                raise ReminderNotFoundError
            executions, total = repository.list_executions(
                self._session,
                reminder_id,
                limit=query.limit,
                offset=query.offset,
            )
            return ReminderExecutionListResponse(
                items=[_execution_response(item) for item in executions],
                total=total,
                limit=query.limit,
                offset=query.offset,
            )
        except ReminderNotFoundError:
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            raise ReminderUnavailableError from error

    def _lock_user_reminder(self, user_id: int, reminder_id: int) -> Reminder:
        """按用户范围取得提醒并锁定，供状态操作串行化。"""

        reminder = repository.get_reminder_for_user(
            self._session, user_id, reminder_id, for_update=True
        )
        if reminder is None:
            raise ReminderNotFoundError
        return reminder

    def _now(self) -> datetime:
        """使用注入时钟获取带时区当前时间，便于边界规则确定性测试。"""

        value = self._clock()
        if value.tzinfo is None:
            raise ReminderScheduleError("服务端时钟必须返回带时区时间。")
        return value.astimezone(UTC)


def _ensure_editable(reminder: Reminder, expected_version: int) -> None:
    """校验提醒状态与乐观版本，避免旧表单覆盖较新的规则。"""

    if reminder.status not in (REMINDER_ACTIVE, REMINDER_PAUSED):
        raise ReminderConflictError("已取消或已完成的提醒不能编辑。")
    if reminder.version != expected_version:
        raise ReminderConflictError("提醒已在其他位置更新，请刷新后再编辑。")


def _reminder_response(reminder: Reminder) -> ReminderResponse:
    """把 ORM 字段转换为稳定的提醒响应 DTO。"""

    return ReminderResponse(
        id=str(reminder.id),
        title=reminder.title,
        content=reminder.content,
        repeat_type=reminder.repeat_type,
        repeat_config=reminder.repeat_config,
        timezone=reminder.timezone,
        next_run_at=_ensure_aware(reminder.next_run_at),
        end_date=reminder.end_date,
        status=reminder.status,
        version=reminder.version,
        created_at=_ensure_aware(reminder.created_at),
        updated_at=_ensure_aware(reminder.updated_at),
    )


def _execution_response(execution: ReminderExecution) -> ReminderExecutionResponse:
    """构造执行历史响应，并仅返回掩码后的邮箱。"""

    return ReminderExecutionResponse(
        id=str(execution.id),
        scheduled_at=_ensure_aware(execution.scheduled_at),
        status=execution.status,
        retry_count=execution.retry_count,
        next_retry_at=_ensure_aware(execution.next_retry_at),
        recipient_email_masked=_mask_email(execution.recipient_email),
        error_message=execution.error_message,
        started_at=_ensure_aware(execution.started_at),
        finished_at=_ensure_aware(execution.finished_at),
        created_at=_ensure_aware(execution.created_at),
    )


def _ensure_aware(value: datetime | None) -> datetime | None:
    """修正 SQLite 测试驱动返回的 naive UTC 时间为可序列化 aware 时间。"""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mask_email(email: str | None) -> str | None:
    """只暴露邮箱本地部分首字符和域名，避免历史接口泄露完整地址。"""

    if email is None or "@" not in email:
        return None
    local_part, domain = email.rsplit("@", maxsplit=1)
    if not local_part or not domain:
        return None
    return f"{local_part[0]}***@{domain}"
