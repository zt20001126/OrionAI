"""认领提醒执行、调用 SMTP 并持久化结果与有界重试状态。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.infrastructure.email.email_sender import EmailDeliveryError, send_email
from app.modules.reminders import repository
from app.modules.reminders.constants import (
    ERROR_MESSAGE_MAX_LENGTH,
    EXECUTION_ACCEPTED,
    EXECUTION_CANCELLED,
    EXECUTION_FAILED,
    EXECUTION_PENDING,
    EXECUTION_RETRY_WAIT,
    EXECUTION_SENDING,
    MAX_RETRY_COUNT,
    REMINDER_ACTIVE,
)
from app.modules.reminders.errors import ReminderUnavailableError
from app.modules.reminders.lifecycle import complete_if_no_future
from app.modules.reminders.models import Reminder, ReminderExecution
from app.modules.reminders.retry_policy import retry_delay

logger = logging.getLogger(__name__)
EmailSender = Callable[..., None]


@dataclass(frozen=True)
class ClaimedExecution:
    """Worker 已提交认领后可在事务外安全用于渲染邮件的不可变快照。"""

    execution_id: int
    recipient_email: str
    title: str
    content: str
    scheduled_at: datetime
    timezone: str


class ReminderExecutionService:
    """提醒执行应用服务，保持数据库锁与阻塞 SMTP 调用互不重叠。"""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        email_sender: EmailSender = send_email,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._email_sender = email_sender
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, execution_id: int) -> str:
        """执行一条待发送记录，发送结果以数据库状态为准。

        Step 1: 先锁 Reminder、再锁 Execution，原子认领唯一发送者。
        Step 2: 在事务外构造并发送邮件，避免 SMTP 阻塞时占用数据库行锁。
        Step 3: 通过新事务保存 SMTP 接受、失败重试或终态失败。
        """

        claimed = self._claim(execution_id)
        if claimed is None:
            return "ignored"
        try:
            self._send(claimed)
        except EmailDeliveryError as error:
            self._record_failure(
                execution_id,
                message=str(error),
                retryable=error.retryable,
            )
            return "retry_wait" if error.retryable else "failed"
        except Exception:
            logger.exception("reminder_email_unexpected_error execution_id=%s", execution_id)
            self._record_failure(
                execution_id,
                message="提醒邮件处理失败。",
                retryable=False,
            )
            return "failed"

        self._record_accepted(execution_id)
        return "accepted"

    def _claim(self, execution_id: int) -> ClaimedExecution | None:
        """校验提醒状态、读取最新账号邮箱并持久化 sending 认领。"""

        now = _as_utc(self._clock())
        try:
            with self._session_factory() as session:
                execution_snapshot = repository.get_execution(session, execution_id)
                if execution_snapshot is None:
                    session.commit()
                    return None
                reminder = repository.get_reminder_for_worker(
                    session, execution_snapshot.reminder_id, for_update=True
                )
                execution = repository.get_execution(session, execution_id, for_update=True)
                if reminder is None or execution is None:
                    session.commit()
                    return None
                if not _is_dispatchable(execution, now):
                    session.commit()
                    return None
                if reminder.status != REMINDER_ACTIVE:
                    _cancel_execution(execution, now, "提醒已暂停或取消，未继续发送。")
                    session.commit()
                    return None

                recipient_email = repository.get_user_email(session, reminder.user_id)
                if not recipient_email or "@" not in recipient_email:
                    execution.status = EXECUTION_FAILED
                    execution.error_message = "账号邮箱不可用，无法发送提醒。"
                    execution.finished_at = now
                    execution.next_retry_at = None
                    complete_if_no_future(reminder)
                    session.commit()
                    return None

                execution.status = EXECUTION_SENDING
                execution.started_at = now
                execution.recipient_email = recipient_email
                execution.error_message = None
                execution.next_retry_at = None
                execution.finished_at = None
                snapshot = ClaimedExecution(
                    execution_id=execution.id,
                    recipient_email=recipient_email,
                    title=reminder.title,
                    content=reminder.content,
                    scheduled_at=_as_utc(execution.scheduled_at),
                    timezone=reminder.timezone,
                )
                session.commit()
                return snapshot
        except SQLAlchemyError as error:
            logger.exception(
                "reminder_execution_claim_database_error execution_id=%s", execution_id
            )
            raise ReminderUnavailableError from error

    def _send(self, claimed: ClaimedExecution) -> None:
        """使用快照渲染计划时间，转义 HTML 并调用通用 SMTP 基础设施。"""

        scheduled_local = claimed.scheduled_at.astimezone(ZoneInfo(claimed.timezone))
        display_time = scheduled_local.strftime("%Y-%m-%d %H:%M")
        escaped_title = escape(claimed.title)
        escaped_content = escape(claimed.content).replace("\n", "<br>")
        safe_subject_title = claimed.title.replace("\r", " ").replace("\n", " ")
        plain_body = (
            "OrionAI 提醒\n\n"
            f"{claimed.title}\n\n"
            f"{claimed.content}\n\n"
            f"原计划提醒时间：{display_time} ({claimed.timezone})\n"
            "此邮件由 OrionAI 自动发送。"
        )
        html_body = (
            "<html><body>"
            "<p><strong>OrionAI 提醒</strong></p>"
            f"<h2>{escaped_title}</h2>"
            f"<p>{escaped_content}</p>"
            f"<p>原计划提醒时间：{escape(display_time)} ({escape(claimed.timezone)})</p>"
            "<p>此邮件由 OrionAI 自动发送。</p>"
            "</body></html>"
        )
        self._email_sender(
            self._settings,
            recipient=claimed.recipient_email,
            subject=f"OrionAI 提醒：{safe_subject_title}",
            text_body=plain_body,
            html_body=html_body,
        )

    def _record_accepted(self, execution_id: int) -> None:
        """把 SMTP 接受请求记录为 accepted，不声称邮件已投递。"""

        now = _as_utc(self._clock())
        with self._session_factory() as session:
            reminder, execution = _lock_execution_pair(session, execution_id)
            if reminder is None or execution is None or execution.status != EXECUTION_SENDING:
                session.commit()
                return
            execution.status = EXECUTION_ACCEPTED
            execution.error_message = None
            execution.next_retry_at = None
            execution.finished_at = now
            complete_if_no_future(reminder)
            session.commit()

    def _record_failure(
        self,
        execution_id: int,
        *,
        message: str,
        retryable: bool,
    ) -> None:
        """按可重试类型和次数上限写入 retry_wait 或 failed 终态。"""

        now = _as_utc(self._clock())
        with self._session_factory() as session:
            reminder, execution = _lock_execution_pair(session, execution_id)
            if reminder is None or execution is None or execution.status != EXECUTION_SENDING:
                session.commit()
                return

            safe_message = message.strip()[:ERROR_MESSAGE_MAX_LENGTH]
            can_retry = retryable and execution.retry_count < MAX_RETRY_COUNT
            if can_retry:
                execution.retry_count += 1
                execution.status = EXECUTION_RETRY_WAIT
                execution.next_retry_at = now + retry_delay(execution.retry_count)
                execution.finished_at = None
            else:
                execution.status = EXECUTION_FAILED
                execution.next_retry_at = None
                execution.finished_at = now
                complete_if_no_future(reminder)
            execution.error_message = safe_message or "邮件发送失败。"
            session.commit()


def _lock_execution_pair(
    session: Session,
    execution_id: int,
) -> tuple[Reminder | None, ReminderExecution | None]:
    """按全模块统一的提醒、执行顺序锁定两行。"""

    execution_snapshot = repository.get_execution(session, execution_id)
    if execution_snapshot is None:
        return None, None
    reminder = repository.get_reminder_for_worker(
        session, execution_snapshot.reminder_id, for_update=True
    )
    execution = repository.get_execution(session, execution_id, for_update=True)
    return reminder, execution


def _is_dispatchable(execution: ReminderExecution, now: datetime) -> bool:
    """检查 pending 或已到重试时刻记录是否可以被 Worker 原子认领。"""

    if execution.status == EXECUTION_PENDING:
        return True
    return (
        execution.status == EXECUTION_RETRY_WAIT
        and execution.next_retry_at is not None
        and _as_utc(execution.next_retry_at) <= now
    )


def _cancel_execution(
    execution: ReminderExecution,
    now: datetime,
    message: str,
) -> None:
    """将尚未开始发送的执行记录转为取消终态。"""

    execution.status = EXECUTION_CANCELLED
    execution.next_retry_at = None
    execution.error_message = message
    execution.finished_at = now


def _as_utc(value: datetime) -> datetime:
    """确保时钟和数据库时间均按带时区 UTC instant 比较。"""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
