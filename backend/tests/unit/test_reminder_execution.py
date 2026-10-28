from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.email.email_sender import EmailDeliveryError
from app.modules.auth.models import User
from app.modules.reminders.execution_service import ReminderExecutionService
from app.modules.reminders.models import Reminder, ReminderExecution

NOW = datetime(2026, 10, 28, 1, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("retryable", "expected_status", "expected_retry_count", "jitter_ratio"),
    [
        (True, "retry_wait", 1, -0.1),
        (True, "retry_wait", 1, 0.1),
        (False, "failed", 0, 0.0),
    ],
)
def test_execution_failure_records_retry_state_without_counting_permanent_failure_as_retry(
    retryable: bool,
    expected_status: str,
    expected_retry_count: int,
    jitter_ratio: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重试间隔应用边界抖动；仅安排重试时增加 retry_count。"""

    monkeypatch.setattr(
        "app.modules.reminders.retry_policy.random.uniform",
        lambda _lower, _upper: jitter_ratio,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Reminder.__table__, ReminderExecution.__table__],
    )
    session_factory = sessionmaker(engine, expire_on_commit=False)
    try:
        with Session(engine) as session:
            owner = User(account="owner@example.com", password_hash="hash")
            session.add(owner)
            session.flush()
            reminder = Reminder(
                user_id=owner.id,
                title="提交周报",
                content="整理本周进展。",
                repeat_type="once",
                repeat_config={},
                timezone="Asia/Shanghai",
                next_run_at=NOW - timedelta(minutes=1),
                status="active",
                version=1,
            )
            session.add(reminder)
            session.flush()
            execution = ReminderExecution(
                reminder_id=reminder.id,
                scheduled_at=NOW - timedelta(minutes=1),
                status="pending",
                retry_count=0,
            )
            session.add(execution)
            session.commit()
            execution_id = execution.id
            reminder_id = reminder.id

        def fail_delivery(*_args: object, **_kwargs: object) -> None:
            raise EmailDeliveryError("SMTP 邮件发送失败。", retryable=retryable)

        service = ReminderExecutionService(
            session_factory,
            Settings(),
            email_sender=fail_delivery,
            clock=lambda: NOW,
        )

        result = service.execute(execution_id)

        with Session(engine) as session:
            stored_execution = session.get(ReminderExecution, execution_id)
            stored_reminder = session.scalar(select(Reminder).where(Reminder.id == reminder_id))

        assert stored_execution is not None
        assert stored_reminder is not None
        assert result == ("retry_wait" if retryable else "failed")
        assert stored_execution.status == expected_status
        assert stored_execution.retry_count == expected_retry_count
        if retryable:
            assert stored_execution.next_retry_at is not None
            assert stored_execution.next_retry_at.replace(tzinfo=UTC) == NOW + timedelta(
                seconds=30 * (1 + jitter_ratio)
            )
            assert stored_reminder.status == "active"
        else:
            assert stored_execution.next_retry_at is None
            assert stored_execution.finished_at is not None
            assert stored_reminder.status == "completed"
    finally:
        engine.dispose()
