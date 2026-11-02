"""验证会员准入接口及各技能 Router 的执行权限边界。"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application import create_app
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.client import get_redis_client
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.membership.dependencies import get_membership_access_service
from app.modules.membership.errors import MembershipRequiredError
from app.modules.reminders.models import Reminder


class StubMembershipAccessService:
    """按测试状态返回会员资格，并记录后端保护依赖调用。"""

    def __init__(self) -> None:
        self.is_member_value = False
        self.require_calls = 0

    def is_member(self, _user_id: int, *, is_guest: bool = False) -> bool:
        return self.is_member_value and not is_guest

    def require_member(self, _user_id: int, *, is_guest: bool = False) -> None:
        self.require_calls += 1
        if is_guest or not self.is_member_value:
            raise MembershipRequiredError


class StubRedis:
    """阻止 API 测试意外连接真实 Redis。"""

    def get(self, _key: str) -> None:
        return None

    def set(self, *_args: object, **_kwargs: object) -> bool:
        return True

    def delete(self, _key: str) -> int:
        return 0


@asynccontextmanager
async def _test_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """技能会员准入 API 测试不启动 Agent 或外部服务。"""

    yield


@pytest.fixture
def membership_access_client() -> Iterator[tuple[TestClient, dict[str, Any]]]:
    """创建隔离数据库、固定身份和会员准入替身。"""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        user = User(account="access-owner@example.test", password_hash="hash", is_guest=False)
        session.add(user)
        session.commit()
        session.refresh(user)

    access_service = StubMembershipAccessService()
    state: dict[str, Any] = {
        "user": user,
        "access_service": access_service,
        "session_factory": session_factory,
    }
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        return state["user"]

    def override_access_service() -> StubMembershipAccessService:
        return state["access_service"]

    def override_redis_client() -> Iterator[StubRedis]:
        yield StubRedis()

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.dependency_overrides[get_membership_access_service] = override_access_service
    test_app.dependency_overrides[get_redis_client] = override_redis_client
    try:
        with TestClient(test_app) as client:
            yield client, state
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_access_endpoint_reports_current_service_result(
    membership_access_client: tuple[TestClient, dict[str, Any]],
) -> None:
    """准入接口只返回当前资格布尔值，会员状态变化后响应随之变化。"""

    client, state = membership_access_client
    response = client.get("/api/v1/users/me/membership/access")

    assert response.status_code == 200
    assert response.json() == {"is_member": False}

    state["access_service"].is_member_value = True
    member_response = client.get("/api/v1/users/me/membership/access")
    assert member_response.status_code == 200
    assert member_response.json() == {"is_member": True}


def test_nonmember_cannot_start_skills_but_can_read_or_stop_existing_data(
    membership_access_client: tuple[TestClient, dict[str, Any]],
) -> None:
    """非会员的技能执行入口返回 403，历史读取和提醒停止操作保持开放。"""

    client, state = membership_access_client
    with state["session_factory"]() as session:
        reminder = Reminder(
            user_id=state["user"].id,
            title="已存在的提醒",
            content="到期后仍可停止",
            repeat_type="daily",
            repeat_config={"local_time": "12:00"},
            timezone="Asia/Shanghai",
            next_run_at=datetime.now(UTC) + timedelta(days=1),
            status="active",
            version=1,
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)
        reminder_id = reminder.id

    conversation_response = client.post(
        "/api/conversations",
        json={"skill_code": "general_chat"},
    )
    training_response = client.post("/api/v1/memory-training/sessions")
    reminder_response = client.post(
        "/api/v1/reminders",
        json={
            "title": "测试提醒",
            "content": "测试内容",
            "repeat_type": "once",
            "timezone": "Asia/Shanghai",
            "date": "2026-11-03",
            "local_time": "12:00",
        },
    )

    assert conversation_response.status_code == 403
    assert training_response.status_code == 403
    assert reminder_response.status_code == 403
    assert state["access_service"].require_calls == 3
    assert client.get("/api/conversations").status_code == 200
    assert client.get("/api/v1/reminders").status_code == 200
    assert client.post(f"/api/v1/reminders/{reminder_id}/resume").status_code == 403
    assert state["access_service"].require_calls == 4
    paused = client.post(f"/api/v1/reminders/{reminder_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    cancelled = client.post(f"/api/v1/reminders/{reminder_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert state["access_service"].require_calls == 4


def test_member_passes_backend_gate(
    membership_access_client: tuple[TestClient, dict[str, Any]],
) -> None:
    """有效会员通过准入依赖，后续由原技能 Service 处理请求。"""

    client, state = membership_access_client
    state["access_service"].is_member_value = True

    response = client.post(
        "/api/conversations",
        json={"skill_code": "general_chat"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "请先将此助手添加到我的技能后再使用。"
    assert state["access_service"].require_calls == 1
