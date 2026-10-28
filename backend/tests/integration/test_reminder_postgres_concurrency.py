from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.reminders import repository
from app.modules.reminders.execution_service import ReminderExecutionService
from app.modules.reminders.models import Reminder, ReminderExecution

TEST_POSTGRES_DATABASE = "orionai_reminder_test"
TEST_NOW = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
REMINDER_TABLES = [User.__table__, Reminder.__table__, ReminderExecution.__table__]


@pytest.fixture(scope="module")
def postgres_session_factory() -> sessionmaker[Session]:
    """只在显式提供专用测试库时运行 PostgreSQL 锁语义测试。"""

    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("设置 TEST_POSTGRES_URL 指向专用 orionai_reminder_test 库以运行。")
    if make_url(database_url).database != TEST_POSTGRES_DATABASE:
        pytest.fail(f"TEST_POSTGRES_URL 数据库必须命名为 {TEST_POSTGRES_DATABASE}。")

    engine = create_engine(database_url, pool_size=6)
    Base.metadata.drop_all(engine, tables=REMINDER_TABLES)
    Base.metadata.create_all(engine, tables=REMINDER_TABLES)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine, tables=REMINDER_TABLES)
        engine.dispose()


def test_skip_locked_claims_distinct_due_reminders(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    """两个事务扫描同一批提醒时，第二个事务跳过已锁行并取得另一行。"""

    first_id, second_id = _create_due_reminders(postgres_session_factory, count=2)
    first_session = postgres_session_factory()
    second_session = postgres_session_factory()
    try:
        first_batch = repository.select_due_reminders(
            first_session,
            now=TEST_NOW,
            limit=1,
        )
        second_batch = repository.select_due_reminders(
            second_session,
            now=TEST_NOW,
            limit=1,
        )

        assert len(first_batch) == 1
        assert len(second_batch) == 1
        assert first_batch[0].id != second_batch[0].id
        assert {first_batch[0].id, second_batch[0].id} == {first_id, second_id}
    finally:
        first_session.rollback()
        second_session.rollback()
        first_session.close()
        second_session.close()


def test_duplicate_worker_delivery_calls_smtp_once(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    """相同执行 ID 并发投递时只有一次 Worker 认领会进入 SMTP。"""

    execution_id = _create_pending_single_execution(postgres_session_factory)
    send_started = threading.Event()
    allow_send_finish = threading.Event()
    call_lock = threading.Lock()
    send_call_count = 0

    def blocking_sender(*_args: object, **_kwargs: object) -> None:
        nonlocal send_call_count
        with call_lock:
            send_call_count += 1
        send_started.set()
        if not allow_send_finish.wait(timeout=10):
            raise TimeoutError("test did not release the SMTP stub")

    settings = Settings()

    def execute_once() -> str:
        return ReminderExecutionService(
            postgres_session_factory,
            settings,
            email_sender=blocking_sender,
            clock=lambda: TEST_NOW,
        ).execute(execution_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(execute_once)
        assert send_started.wait(timeout=5)
        second = executor.submit(execute_once)
        assert second.result(timeout=5) == "ignored"
        allow_send_finish.set()
        assert first.result(timeout=5) == "accepted"

    assert send_call_count == 1
    with postgres_session_factory() as session:
        execution = session.get(ReminderExecution, execution_id)
        assert execution is not None
        assert execution.status == "accepted"
        assert session.scalar(select(func.count()).select_from(ReminderExecution)) == 1


def _create_due_reminders(
    session_factory: sessionmaker[Session],
    *,
    count: int,
) -> tuple[int, ...]:
    """为行锁测试插入独立的周期提醒。"""

    reminder_ids = []
    with session_factory() as session:
        for index in range(count):
            owner = User(account=f"skip-lock-{index}@example.com", password_hash="hash")
            session.add(owner)
            session.flush()
            reminder = Reminder(
                user_id=owner.id,
                title=f"每日检查 {index}",
                content="查看当天任务。",
                repeat_type="daily",
                repeat_config={"start_date": "2026-10-28", "local_time": "09:30"},
                timezone="Asia/Shanghai",
                next_run_at=TEST_NOW,
                status="active",
                version=1,
            )
            session.add(reminder)
            session.flush()
            reminder_ids.append(reminder.id)
        session.commit()
    return tuple(reminder_ids)


def _create_pending_single_execution(session_factory: sessionmaker[Session]) -> int:
    """创建一条可由任意一个 Worker 唯一认领的单次提醒执行。"""

    with session_factory() as session:
        owner = User(account="worker-race@example.com", password_hash="hash")
        session.add(owner)
        session.flush()
        reminder = Reminder(
            user_id=owner.id,
            title="发送日报",
            content="请检查今日情况。",
            repeat_type="once",
            repeat_config={},
            timezone="Asia/Shanghai",
            next_run_at=TEST_NOW,
            status="active",
            version=1,
        )
        session.add(reminder)
        session.flush()
        execution = ReminderExecution(
            reminder_id=reminder.id,
            scheduled_at=TEST_NOW,
            status="pending",
            retry_count=0,
        )
        session.add(execution)
        session.commit()
        return execution.id
