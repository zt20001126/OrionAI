from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.config import BASIC_CONVERSATION_AGENT
from app.agent.schemas import AgentResponse, Question, QuestionOption, QuestionPayload
from app.core.application import create_app
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User


class ScriptedAgent:
    """以固定 Agent 响应验证 Service 和 HTTP 持久化边界。"""

    def __init__(self, responses: list[AgentResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(
        self,
        request: object,
        *,
        runnable_config: dict[str, Any],
        message_id: str | None,
    ) -> AgentResponse:
        self.calls.append(
            {
                "request": request,
                "runnable_config": runnable_config,
                "message_id": message_id,
            }
        )
        return self.responses.pop(0)


@asynccontextmanager
async def _test_lifespan(_application: FastAPI):
    """对话 API 测试不连接真实 Checkpointer 或模型。"""

    yield


@pytest.fixture
def conversation_client() -> Iterator[tuple[TestClient, dict[str, User], ScriptedAgent]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        owner = User(account="owner@example.com", password_hash="hash")
        other_user = User(account="other@example.com", password_hash="hash")
        session.add_all([owner, other_user])
        session.commit()
        session.refresh(owner)
        session.refresh(other_user)

    users = {"current": owner, "other": other_user}
    agent = ScriptedAgent(
        [
            AgentResponse(
                agent=BASIC_CONVERSATION_AGENT,
                status="completed",
                answer="你好，我可以帮助你。",
            ),
            AgentResponse(
                agent=BASIC_CONVERSATION_AGENT,
                status="waiting",
                questions=QuestionPayload(
                    questions=[
                        Question(
                            id="style",
                            title="希望采用哪种表达风格？",
                            type="SingleChoice",
                            options=[
                                QuestionOption(label=label, description=f"选择{label}")
                                for label in ["简洁", "详细", "正式", "轻松"]
                            ],
                            allow_custom_input=False,
                        )
                    ]
                ),
            ),
            AgentResponse(
                agent=BASIC_CONVERSATION_AGENT,
                status="completed",
                answer="我会采用简洁风格。",
            ),
        ]
    )
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        return users["current"]

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.state.conversation_agent = agent
    try:
        with TestClient(test_app) as client:
            yield client, users, agent
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_conversation_endpoints_require_login() -> None:
    with TestClient(create_app(lifespan=_test_lifespan)) as client:
        response = client.get("/api/conversations")

    assert response.status_code == 401


def test_chat_persists_messages_and_resumes_waiting_questions(
    conversation_client: tuple[TestClient, dict[str, User], ScriptedAgent],
) -> None:
    client, users, agent = conversation_client
    created = client.post("/api/conversations")
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    first_turn = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "你好"},
    )
    assert first_turn.status_code == 200
    assert first_turn.json()["status"] == "completed"
    assert first_turn.json()["message"]["content"] == {
        "parts": [{"type": "text", "text": "你好，我可以帮助你。"}]
    }

    waiting_turn = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "帮我写一份说明"},
    )
    assert waiting_turn.status_code == 200
    assert waiting_turn.json()["status"] == "waiting"
    assert waiting_turn.json()["message"]["content"]["parts"][0]["type"] == "question"
    blocked_message = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "先继续说"},
    )
    assert blocked_message.status_code == 409

    invalid_answer = client.post(
        f"/api/conversations/{conversation_id}/answers",
        json={"answers": {"style": "不存在的选项"}},
    )
    assert invalid_answer.status_code == 422

    resumed_turn = client.post(
        f"/api/conversations/{conversation_id}/answers",
        json={"answers": {"style": "简洁"}},
    )
    assert resumed_turn.status_code == 200
    assert resumed_turn.json()["status"] == "completed"
    assert agent.calls[1]["runnable_config"] == agent.calls[2]["runnable_config"]

    messages = client.get(f"/api/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert [item["role"] for item in items] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert items[2]["content"] == {"parts": [{"type": "text", "text": "帮我写一份说明"}]}
    assert items[4]["content"]["parts"][0]["text"].endswith("简洁")
    assert client.get("/api/conversations").json()["items"][0]["id"] == conversation_id
    assert users["other"].id != users["current"].id


def test_conversation_is_hidden_from_other_users(
    conversation_client: tuple[TestClient, dict[str, User], ScriptedAgent],
) -> None:
    client, users, _agent = conversation_client
    conversation = client.post("/api/conversations").json()
    users["current"] = users["other"]

    response = client.get(f"/api/conversations/{conversation['id']}/messages")

    assert response.status_code == 404
