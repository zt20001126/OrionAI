from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.reminders.errors import ReminderNotFoundError
from app.modules.reminders.models import Reminder, ReminderExecution
from app.modules.reminders.schemas import (
    ReminderCreateRequest,
    ReminderExecutionListQuery,
    ReminderListQuery,
    ReminderUpdateRequest,
)
from app.modules.reminders.service import ReminderService

NOW = datetime(2026, 10, 28, 0, 0, tzinfo=UTC)


@pytest.fixture
def reminder_session() -> Session:
    """创建只含用户与提醒表的 SQLite 会话，测试不依赖 PostgreSQL 服务。"""

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Reminder.__table__, ReminderExecution.__table__],
    )
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_and_read_are_scoped_to_current_user(reminder_session: Session) -> None:
    """创建提醒后，只允许提醒所属用户读取其规则和列表。"""

    owner = User(account="owner@example.com", password_hash="hash")
    other_user = User(account="other@example.com", password_hash="hash")
    reminder_session.add_all((owner, other_user))
    reminder_session.commit()
    service = ReminderService(reminder_session, clock=lambda: NOW)
    payload = ReminderCreateRequest(
        title="提交周报",
        content="整理进展。",
        repeat_type="once",
        timezone="Asia/Shanghai",
        date=date(2026, 10, 29),
        local_time="09:30",
    )

    created = service.create(owner, payload)

    assert created.status == "active"
    assert isinstance(created.id, str)
    assert created.next_run_at == datetime(2026, 10, 29, 1, 30, tzinfo=UTC)
    assert service.list(owner, ReminderListQuery()).total == 1
    assert service.list(other_user, ReminderListQuery()).total == 0
    with pytest.raises(ReminderNotFoundError):
        service.get(other_user, int(created.id))


def test_update_existing_recurring_rule_keeps_original_past_anchor(
    reminder_session: Session,
) -> None:
    """编辑旧周期规则时保留原开始日期，并把 next_run 推进到未来。"""

    owner = User(account="owner@example.com", password_hash="hash")
    reminder_session.add(owner)
    reminder_session.flush()
    reminder = Reminder(
        user_id=owner.id,
        title="旧标题",
        content="旧内容",
        repeat_type="daily",
        repeat_config={"start_date": "2026-10-01", "local_time": "09:30"},
        timezone="Asia/Shanghai",
        next_run_at=datetime(2026, 10, 28, 1, 30, tzinfo=UTC),
        status="active",
        version=3,
    )
    reminder_session.add(reminder)
    reminder_session.commit()
    service = ReminderService(reminder_session, clock=lambda: NOW)
    payload = ReminderUpdateRequest(
        title="新标题",
        content="更新内容",
        repeat_type="daily",
        timezone="Asia/Shanghai",
        start_date=date(2026, 10, 1),
        local_time=time(10, 0),
        expected_version=3,
    )

    updated = service.update(owner, reminder.id, payload)

    assert updated.version == 4
    assert updated.repeat_config["start_date"] == "2026-10-01"
    assert updated.next_run_at == datetime(2026, 10, 28, 2, 0, tzinfo=UTC)


def test_execution_history_masks_recipient_email(reminder_session: Session) -> None:
    """历史响应返回脱敏邮箱，不暴露执行表中的完整收件地址。"""

    owner = User(account="owner@example.com", password_hash="hash")
    reminder_session.add(owner)
    reminder_session.flush()
    reminder = Reminder(
        user_id=owner.id,
        title="检查日报",
        content="按时检查日报。",
        repeat_type="once",
        repeat_config={},
        timezone="Asia/Shanghai",
        next_run_at=datetime(2026, 10, 29, 1, 30, tzinfo=UTC),
        status="completed",
        version=1,
    )
    reminder_session.add(reminder)
    reminder_session.flush()
    reminder_session.add(
        ReminderExecution(
            reminder_id=reminder.id,
            scheduled_at=datetime(2026, 10, 29, 1, 30, tzinfo=UTC),
            status="accepted",
            recipient_email="owner@example.com",
        )
    )
    reminder_session.commit()

    result = ReminderService(reminder_session, clock=lambda: NOW).list_executions(
        owner,
        reminder.id,
        ReminderExecutionListQuery(),
    )

    assert result.items[0].recipient_email_masked == "o***@example.com"
    assert "owner@example.com" not in result.model_dump_json()


def test_resume_catches_up_only_latest_occurrence_missed_while_paused(
    reminder_session: Session,
) -> None:
    """恢复过期周期规则时只安排暂停期间最近一次遗漏计划。"""

    owner = User(account="owner@example.com", password_hash="hash")
    reminder_session.add(owner)
    reminder_session.flush()
    reminder = Reminder(
        user_id=owner.id,
        title="每日检查",
        content="查看当天任务。",
        repeat_type="daily",
        repeat_config={"start_date": "2026-10-28", "local_time": "09:30"},
        timezone="Asia/Shanghai",
        next_run_at=datetime(2026, 10, 29, 1, 30, tzinfo=UTC),
        status="paused",
        version=2,
    )
    reminder_session.add(reminder)
    reminder_session.commit()

    resumed = ReminderService(
        reminder_session, clock=lambda: datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
    ).resume(
        owner,
        reminder.id,
    )

    assert resumed.status == "active"
    assert resumed.next_run_at == datetime(2026, 10, 30, 1, 30, tzinfo=UTC)
