from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.reminders.constants import RETRY_DELAYS
from app.modules.reminders.models import Reminder, ReminderExecution
from app.modules.reminders.scheduler import ReminderScheduler

NOW = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)


def test_scheduler_creates_only_latest_missed_occurrence_and_republishes_pending() -> None:
    """调度器折叠停机积压，并从数据库重新投递未认领的执行。"""

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Reminder.__table__, ReminderExecution.__table__],
    )
    session_factory = sessionmaker(engine, expire_on_commit=False)
    dispatched_ids: list[int] = []
    try:
        with Session(engine) as session:
            owner = User(account="owner@example.com", password_hash="hash")
            session.add(owner)
            session.flush()
            reminder = Reminder(
                user_id=owner.id,
                title="每日检查",
                content="查看当天任务。",
                repeat_type="daily",
                repeat_config={"start_date": "2026-10-28", "local_time": "09:30"},
                timezone="Asia/Shanghai",
                next_run_at=datetime(2026, 10, 29, 1, 30, tzinfo=UTC),
                status="active",
                version=1,
            )
            session.add(reminder)
            session.commit()

        scheduler = ReminderScheduler(
            session_factory,
            Settings(),
            dispatched_ids.append,
        )
        first_scan = scheduler.run(now=NOW)
        second_scan = scheduler.run(now=NOW)

        with Session(engine) as session:
            executions = list(session.scalars(select(ReminderExecution)))
            updated_reminder = session.scalar(select(Reminder))
            count = session.scalar(select(func.count()).select_from(ReminderExecution))

        assert first_scan == {"created": 1, "recovered": 0, "dispatched": 1}
        assert second_scan == {"created": 0, "recovered": 0, "dispatched": 1}
        assert count == 1
        assert executions[0].scheduled_at.replace(tzinfo=UTC) == datetime(
            2026, 10, 30, 1, 30, tzinfo=UTC
        )
        assert updated_reminder is not None
        assert updated_reminder.next_run_at is not None
        assert updated_reminder.next_run_at.replace(tzinfo=UTC) == datetime(
            2026, 10, 31, 1, 30, tzinfo=UTC
        )
        assert dispatched_ids == [executions[0].id, executions[0].id]
    finally:
        engine.dispose()


def test_scheduler_retries_expired_worker_lease_with_shared_jitter(
    monkeypatch,
) -> None:
    """Worker 租约恢复复用 SMTP 重试策略的抖动间隔。"""

    monkeypatch.setattr(
        "app.modules.reminders.retry_policy.random.uniform",
        lambda _lower, upper: upper,
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
                title="单次提醒",
                content="检查运行结果。",
                repeat_type="once",
                repeat_config={},
                timezone="UTC",
                next_run_at=NOW + timedelta(days=1),
                status="active",
                version=1,
            )
            session.add(reminder)
            session.flush()
            execution = ReminderExecution(
                reminder_id=reminder.id,
                scheduled_at=NOW - timedelta(minutes=10),
                status="sending",
                retry_count=0,
                started_at=NOW - timedelta(minutes=10),
            )
            session.add(execution)
            session.commit()
            execution_id = execution.id

        scheduler = ReminderScheduler(session_factory, Settings(), lambda _id: None)
        result = scheduler.run(now=NOW)

        with Session(engine) as session:
            recovered = session.get(ReminderExecution, execution_id)

        assert result["recovered"] == 1
        assert recovered is not None
        assert recovered.status == "retry_wait"
        assert recovered.retry_count == 1
        assert recovered.next_retry_at is not None
        assert recovered.next_retry_at.replace(tzinfo=UTC) == NOW + RETRY_DELAYS[0] * 1.1
    finally:
        engine.dispose()
