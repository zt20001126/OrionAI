"""封装提醒模块的 SQLAlchemy 查询、行锁和持久化操作。"""

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.reminders.constants import (
    EXECUTION_CANCELLED,
    EXECUTION_PENDING,
    EXECUTION_RETRY_WAIT,
    EXECUTION_SENDING,
    REMINDER_ACTIVE,
)
from app.modules.reminders.models import Reminder, ReminderExecution


def get_reminder_for_user(
    session: Session,
    user_id: int,
    reminder_id: int,
    *,
    for_update: bool = False,
) -> Reminder | None:
    """只按提醒 ID 和当前用户 ID 读取资源，可选锁定提醒行。"""

    statement = select(Reminder).where(
        Reminder.id == reminder_id,
        Reminder.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_reminder_for_worker(
    session: Session,
    reminder_id: int,
    *,
    for_update: bool = False,
) -> Reminder | None:
    """按 Worker 已持久化的提醒 ID 读取提醒，支持串行化状态转换。"""

    statement = select(Reminder).where(Reminder.id == reminder_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def list_reminders(
    session: Session,
    user_id: int,
    *,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Reminder], int]:
    """分页读取当前用户提醒及匹配总数。"""

    filters = [Reminder.user_id == user_id]
    if status is not None:
        filters.append(Reminder.status == status)
    total = session.scalar(select(func.count()).select_from(Reminder).where(*filters)) or 0
    statement = (
        select(Reminder)
        .where(*filters)
        .order_by(Reminder.created_at.desc(), Reminder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement)), total


def select_due_reminders(
    session: Session,
    *,
    now: datetime,
    limit: int,
) -> list[Reminder]:
    """用 PostgreSQL 行锁认领一批到期提醒，允许多个扫描器跳过彼此持锁行。"""

    statement = (
        select(Reminder)
        .where(
            Reminder.status == REMINDER_ACTIVE,
            Reminder.next_run_at.is_not(None),
            Reminder.next_run_at <= now,
        )
        .order_by(Reminder.next_run_at.asc(), Reminder.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(session.scalars(statement))


def get_execution(
    session: Session,
    execution_id: int,
    *,
    for_update: bool = False,
) -> ReminderExecution | None:
    """读取执行记录；Worker 先读取关联 ID，再按提醒、执行顺序加锁。"""

    statement = select(ReminderExecution).where(ReminderExecution.id == execution_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_execution_for_schedule(
    session: Session,
    reminder_id: int,
    scheduled_at: datetime,
) -> ReminderExecution | None:
    """按数据库唯一键读取已经创建的计划执行记录。"""

    statement = select(ReminderExecution).where(
        ReminderExecution.reminder_id == reminder_id,
        ReminderExecution.scheduled_at == scheduled_at,
    )
    return session.scalar(statement)


def list_executions(
    session: Session,
    reminder_id: int,
    *,
    limit: int,
    offset: int,
) -> tuple[list[ReminderExecution], int]:
    """按计划时间倒序分页读取单个提醒的执行历史。"""

    total = (
        session.scalar(
            select(func.count())
            .select_from(ReminderExecution)
            .where(ReminderExecution.reminder_id == reminder_id)
        )
        or 0
    )
    statement = (
        select(ReminderExecution)
        .where(ReminderExecution.reminder_id == reminder_id)
        .order_by(ReminderExecution.scheduled_at.desc(), ReminderExecution.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement)), total


def lock_active_executions(
    session: Session,
    reminder_id: int,
) -> list[ReminderExecution]:
    """锁定提醒尚未终结的执行，供编辑、暂停和取消复核。"""

    statement = (
        select(ReminderExecution)
        .where(
            ReminderExecution.reminder_id == reminder_id,
            ReminderExecution.status.in_(
                (EXECUTION_PENDING, EXECUTION_RETRY_WAIT, EXECUTION_SENDING)
            ),
        )
        .order_by(ReminderExecution.scheduled_at.asc(), ReminderExecution.id.asc())
        .with_for_update()
    )
    return list(session.scalars(statement))


def cancel_unstarted_executions(
    session: Session,
    reminder_id: int,
    *,
    finished_at: datetime,
) -> int:
    """终止尚未进入邮件发送的执行，保留历史记录而不删除。"""

    result = session.execute(
        update(ReminderExecution)
        .where(
            ReminderExecution.reminder_id == reminder_id,
            ReminderExecution.status.in_((EXECUTION_PENDING, EXECUTION_RETRY_WAIT)),
        )
        .values(
            status=EXECUTION_CANCELLED,
            next_retry_at=None,
            finished_at=finished_at,
        )
    )
    return result.rowcount or 0


def list_dispatchable_execution_ids(
    session: Session,
    *,
    now: datetime,
    limit: int,
) -> list[int]:
    """读取待投递或已到重试时刻的执行 ID；不依赖 Redis 保存业务状态。"""

    statement = (
        select(ReminderExecution.id)
        .where(
            or_(
                ReminderExecution.status == EXECUTION_PENDING,
                (
                    (ReminderExecution.status == EXECUTION_RETRY_WAIT)
                    & (ReminderExecution.next_retry_at <= now)
                ),
            )
        )
        .order_by(ReminderExecution.created_at.asc(), ReminderExecution.id.asc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def select_expired_sending_execution_ids(
    session: Session,
    *,
    lease_expired_at: datetime,
    limit: int,
) -> list[int]:
    """读取超过租约时间的执行 ID，后续按 Reminder→Execution 顺序加锁。"""

    statement = (
        select(ReminderExecution.id)
        .where(
            ReminderExecution.status == EXECUTION_SENDING,
            ReminderExecution.started_at.is_not(None),
            ReminderExecution.started_at <= lease_expired_at,
        )
        .order_by(ReminderExecution.started_at.asc(), ReminderExecution.id.asc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def get_user_email(session: Session, user_id: int) -> str | None:
    """读取提醒所属用户当前账号邮箱，供执行首次认领时创建快照。"""

    return session.scalar(select(User.account).where(User.id == user_id))
